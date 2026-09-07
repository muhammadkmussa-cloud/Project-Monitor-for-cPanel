import time
import hashlib
from typing import Dict, Any, Optional
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

settings = get_settings()


class RateLimitStore:
    """In-memory rate limit store."""

    def __init__(self):
        self.requests = defaultdict(list)
        self.limits = {}

    def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> Dict[str, Any]:
        """Check if rate limit is exceeded."""
        now = time.time()
        if len(self.requests) > 10000:
            self.cleanup()
        window_start = now - window_seconds

        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if req_time > window_start
        ]

        current_count = len(self.requests[key])

        if current_count >= limit:
            reset_time = self.requests[key][0] + window_seconds
            return {
                "allowed": False,
                "limit": limit,
                "remaining": 0,
                "reset_at": reset_time,
                "retry_after": int(reset_time - now),
            }

        self.requests[key].append(now)

        return {
            "allowed": True,
            "limit": limit,
            "remaining": limit - current_count - 1,
            "reset_at": now + window_seconds,
        }

    def get_usage(self, key: str) -> Dict[str, Any]:
        """Get current usage for a key."""
        now = time.time()
        window_60s = now - 60
        window_3600s = now - 3600

        recent_requests = [
            req_time for req_time in self.requests[key]
            if req_time > window_60s
        ]

        hourly_requests = [
            req_time for req_time in self.requests[key]
            if req_time > window_3600s
        ]

        return {
            "requests_last_minute": len(recent_requests),
            "requests_last_hour": len(hourly_requests),
        }

    def cleanup(self, max_age_seconds: int = 3600):
        """Clean up old entries."""
        now = time.time()
        cutoff = now - max_age_seconds

        keys_to_remove = []
        for key in self.requests:
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if req_time > cutoff
            ]
            if not self.requests[key]:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.requests[key]


rate_limit_store = RateLimitStore()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for API rate limiting."""

    def __init__(self, app, default_limit: int = 100, default_window: int = 60):
        super().__init__(app)
        self.default_limit = default_limit
        self.default_window = default_window
        self.endpoint_limits = {
            "/api/v1/auth/login": {"limit": 10, "window": 60},
            "/api/v1/diagnose": {"limit": 10, "window": 60},
            "/api/v1/remediation/execute": {"limit": 5, "window": 60},
            "/api/v1/backups": {"limit": 20, "window": 60},
            "/api/v1/notifications/send": {"limit": 30, "window": 60},
        }

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        client_key = self._get_client_key(request)
        endpoint_config = self.endpoint_limits.get(
            request.url.path,
            {"limit": self.default_limit, "window": self.default_window},
        )

        result = rate_limit_store.check_rate_limit(
            key=f"{client_key}:{request.url.path}",
            limit=endpoint_config["limit"],
            window_seconds=endpoint_config["window"],
        )

        if not result["allowed"]:
            return Response(
                content='{"error": "Rate limit exceeded", "retry_after": ' + str(result["retry_after"]) + '}',
                status_code=429,
                headers={
                    "X-RateLimit-Limit": str(result["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(result["reset_at"])),
                    "Retry-After": str(result["retry_after"]),
                    "Content-Type": "application/json",
                },
            )

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(result["limit"])
        response.headers["X-RateLimit-Remaining"] = str(result["remaining"])
        response.headers["X-RateLimit-Reset"] = str(int(result["reset_at"]))

        return response

    def _get_client_key(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Login is always tied to the actual socket peer, never caller-supplied headers.
        if request.url.path != "/api/v1/auth/login":
            credential = request.headers.get("X-API-Key") or request.headers.get("Authorization")
            if credential:
                return "credential:" + hashlib.sha256(credential.encode()).hexdigest()
        return "ip:" + (request.client.host if request.client else "unknown")


def get_rate_limit_status(client_key: str) -> Dict[str, Any]:
    """Get rate limit status for a client."""
    usage = rate_limit_store.get_usage(client_key)
    return {
        "client_key": client_key,
        "usage": usage,
    }


def reset_rate_limits(client_key: Optional[str] = None):
    """Reset rate limits for a client or all clients."""
    if client_key:
        rate_limit_store.requests.pop(client_key, None)
    else:
        rate_limit_store.requests.clear()
