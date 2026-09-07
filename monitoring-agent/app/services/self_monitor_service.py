import httpx
import time
import asyncio
import json
from datetime import datetime

from app.db import fetch_one, fetch_all, execute


async def check_service(name: str, url: str, timeout: int = 5) -> dict:
    """Check a single service health."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            latency_ms = int((time.monotonic() - start) * 1000)
            status = "healthy" if 200 <= resp.status_code < 400 else "degraded"
            return {
                "component": name,
                "status": status,
                "response_time_ms": latency_ms,
                "details": {"status_code": resp.status_code, "url": url},
            }
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "component": name,
            "status": "unhealthy",
            "response_time_ms": latency_ms,
            "details": {"error": "timeout", "url": url},
        }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "component": name,
            "status": "unhealthy",
            "response_time_ms": latency_ms,
            "details": {"error": str(e), "url": url},
        }


async def check_all_services() -> list:
    """Check all platform services and store results."""
    from app.config import get_settings
    from redis.asyncio import Redis
    config = get_settings()
    checks = [("monitoring-agent", "http://monitoring-agent:8000/health"),
              ("frontend", "http://frontend:3000/"), ("n8n", config.n8n_base_url.rstrip("/") + "/healthz")]
    results = list(await asyncio.gather(*(check_service(name, url) for name, url in checks)))
    for component in ("postgres", "redis"):
        started = time.monotonic()
        try:
            if component == "postgres":
                await asyncio.wait_for(fetch_one("SELECT 1 AS ok"), timeout=5)
            else:
                async with Redis.from_url(config.redis_url, socket_timeout=5, socket_connect_timeout=5) as cache:
                    await cache.ping()
            result = {"component": component, "status": "healthy", "details": {}}
        except Exception:
            result = {"component": component, "status": "unhealthy", "details": {"error": "Service check failed"}}
        result["response_time_ms"] = int((time.monotonic()-started)*1000)
        results.append(result)
    for result in results:
        # Upsert into system_health
        await execute(
            """INSERT INTO system_health (component, status, response_time_ms, details, checked_at)
               VALUES ($1, $2, $3, $4::jsonb, NOW())
               ON CONFLICT (component) DO UPDATE
               SET status = EXCLUDED.status,
                   response_time_ms = EXCLUDED.response_time_ms,
                   details = EXCLUDED.details,
                   checked_at = NOW()""",
            result["component"],
            result["status"],
            result["response_time_ms"],
            json.dumps(result["details"]),
        )

    return results


async def get_system_health() -> dict:
    """Get latest health status of all services."""
    rows = await fetch_all(
        "SELECT component, status, response_time_ms, details, checked_at FROM system_health ORDER BY checked_at DESC"
    )

    services = {}
    for row in rows:
        component = row["component"]
        if component not in services:
            services[component] = dict(row)

    overall = "healthy" if services else "unknown"
    for svc in services.values():
        if svc["status"] == "unhealthy":
            overall = "degraded"
            break
        elif svc["status"] == "degraded":
            overall = "degraded"

    return {
        "overall": overall,
        "services": services,
        "checked_at": datetime.utcnow().isoformat(),
    }
