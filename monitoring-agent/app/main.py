from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio

from app.config import get_settings
from app.api.routes import router
from app.services.rate_limit_service import RateLimitMiddleware
from app.auth import decode_token
from app.access import enforce_access
import json
import asyncpg
from uuid import UUID
from app.db import get_pool, close_pool


settings = get_settings()

PUBLIC_PATHS = {
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}

PUBLIC_PATHS.add("/api/v1/auth/login")


def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS


async def periodic_health_check():
    """Background task to check all service health every 60 seconds."""
    while True:
        try:
            from app.services.self_monitor_service import check_all_services
            await check_all_services()
            from app.services.scheduler_service import check_scheduler_health
            await check_scheduler_health()
        except Exception:
            pass
        await asyncio.sleep(60)


async def periodic_error_scan():
    """Periodically scan enabled projects for new application/error-log entries."""
    while True:
        await asyncio.sleep(600)
        try:
            from app.services.error_scanner import scan_all_enabled
            result = await scan_all_enabled()
            import logging
            for project in result['results']:
                if not project.get('success'):
                    logging.getLogger(__name__).warning('Application log scan failed for %s', project['project_id'])
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Application log scan failed')


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    task = asyncio.create_task(periodic_health_check())
    from app.services.scheduler_service import scheduler_loop
    scan_task = asyncio.create_task(scheduler_loop())
    from app.services.incident_review_service import review_worker, telegram_poll
    review_task = asyncio.create_task(review_worker())
    telegram_task = asyncio.create_task(telegram_poll())
    yield
    task.cancel()
    scan_task.cancel()
    review_task.cancel()
    telegram_task.cancel()
    await asyncio.gather(task, scan_task, review_task, telegram_task, return_exceptions=True)
    await close_pool()


app = FastAPI(
    title="Project Monitor - Monitoring Agent",
    description="AI-powered multi-project website and application monitoring platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if is_public_path(path):
        return await call_next(request)

    if request.method == "OPTIONS":
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_token(token)
        if payload:
            from app.db import fetch_one
            try:
                user_id = str(UUID(payload["sub"]))
            except (ValueError, KeyError, TypeError):
                return JSONResponse(status_code=401, content={"detail": "Invalid token subject"})
            row = await fetch_one(
                "SELECT u.user_id, u.email, u.role, u.client_id FROM users u "
                "JOIN clients c ON c.client_id=u.client_id "
                "WHERE u.user_id=$1 AND u.status='active' AND (c.status='active' OR u.role IN ('admin','owner'))", user_id)
            if row:
                request.state.user = {"sub": str(row["user_id"]), "email": row["email"],
                                      "role": row["role"], "client_id": str(row["client_id"])}
                return await call_next(request)
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

    if api_key:
        import hashlib
        from app.db import fetch_one
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        row = await fetch_one(
            "SELECT ak.*, u.role, u.email FROM api_keys ak JOIN users u ON ak.user_id = u.user_id JOIN clients c ON c.client_id=u.client_id WHERE ak.key_hash = $1 AND ak.status = 'active' AND u.status='active' AND (c.status='active' OR u.role IN ('admin','owner')) AND (ak.expires_at IS NULL OR ak.expires_at > NOW())",
            key_hash,
        )
        if row:
            request.state.user = {
                "sub": str(row["user_id"]),
                "email": row["email"],
                "client_id": str(row["client_id"]),
                "api_key": True,
                "permissions": json.loads(row["permissions"]) if isinstance(row["permissions"], str) else (row["permissions"] or []),
                "role": row["role"],
            }
            return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "Not authenticated"})


if settings.rate_limit_enabled:
    app.add_middleware(
        RateLimitMiddleware,
        default_limit=settings.rate_limit_default,
        default_window=settings.rate_limit_window,
    )

app.include_router(router, prefix="/api/v1", dependencies=[Depends(enforce_access)])


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "monitoring-agent"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.monitoring_agent_host,
        port=settings.monitoring_agent_port,
        reload=True,
    )


@app.exception_handler(asyncpg.UniqueViolationError)
async def duplicate_record(request, exc):
    return JSONResponse(status_code=409, content={"detail": "This record already exists"})


@app.exception_handler(asyncpg.ForeignKeyViolationError)
async def invalid_reference(request, exc):
    return JSONResponse(status_code=422, content={"detail": "Referenced record does not exist or is still in use"})


@app.exception_handler(asyncpg.InvalidTextRepresentationError)
async def invalid_database_value(request, exc):
    return JSONResponse(status_code=422, content={"detail": "Invalid value for this field"})
