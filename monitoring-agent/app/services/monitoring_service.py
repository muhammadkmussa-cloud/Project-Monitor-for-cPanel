import asyncio
import json
import socket
import time
import ssl
from urllib.parse import urlsplit
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.db import fetch_one, execute

settings = get_settings()


def _build_url(project: dict) -> str:
    target = (
        project.get("health_check_url")
        or project.get("domain")
        or project.get("server_host")
    )
    if not target:
        return None
    target = target.strip()
    if "://" not in target:
        target = f"https://{target}"
    return target


async def _ssl_days_remaining(host: str, port: int = 443) -> int:
    try:
        loop = asyncio.get_running_loop()
        context = ssl.create_default_context()

        def _check():
            with socket.create_connection((host, port), timeout=8) as sock:
                with context.wrap_socket(sock, server_hostname=host) as tls:
                    der = tls.getpeercert()
                    if not der:
                        return None
                    not_after = datetime.strptime(der["notAfter"], "%b %d %H:%M:%S %Y %Z")
                    return (not_after - datetime.utcnow()).days

        return await loop.run_in_executor(None, _check)
    except Exception:
        return None


async def run_http_health_check(project_id: str, *, project_snapshot=None) -> dict:
    project = project_snapshot if project_snapshot is not None else await fetch_one("SELECT * FROM projects WHERE project_id = $1", project_id)
    if not project:
        return {"error": "Project not found", "status": "UNKNOWN"}

    url = _build_url(dict(project))
    if not url:
        return {
            "error": "Project has no domain/server_host/health_check_url configured",
            "status": "UNKNOWN",
        }

    status = "UNKNOWN"
    http_status_code = None
    response_time_ms = None
    ssl_days = None
    details = {"url": url}

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            follow_redirects=True,
            verify=True,
        ) as client:
            started = time.monotonic()
            async with client.stream('GET',url) as response:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                http_status_code = response.status_code
                final_url = str(response.url)
            # Availability latency measures time to response headers; body
            # correctness belongs to the bounded application-contract check.
            response_time_ms = elapsed_ms
            details.update(
                {
                    "http_status_code": http_status_code,
                    "response_time_ms": elapsed_ms,
                    "final_url": final_url,
                    "response_time_scope": "response_headers",
                }
            )
            if final_url.lower().startswith("https://"):
                parsed = urlsplit(final_url)
                ssl_days = await _ssl_days_remaining(parsed.hostname, parsed.port or 443)
                details["ssl_days_remaining"] = ssl_days
                if ssl_days is None: details["ssl_check_error"] = True

            from app.services.scheduler_service import config_for
            thresholds=config_for(project).get('http',{})
            warning_ms=thresholds.get('warning_ms',settings.response_time_warning_ms)
            critical_ms=thresholds.get('critical_ms',settings.response_time_critical_ms)
            ssl_warning=thresholds.get('ssl_warning_days',settings.ssl_warning_days)
            ssl_critical=thresholds.get('ssl_critical_days',settings.ssl_critical_days)
            if http_status_code >= 500:
                status = "DOWN"
            elif http_status_code >= 400:
                status = "DEGRADED"
            elif response_time_ms and response_time_ms > critical_ms:
                status = "DEGRADED"
            elif ssl_days is not None and ssl_days<=ssl_critical:
                status = "CRITICAL"
            elif details.get("ssl_check_error"):
                status = "WARNING"
            elif (ssl_days is not None and ssl_days <= ssl_warning) or elapsed_ms > warning_ms:
                status = "WARNING"
            else:
                status = "HEALTHY"

    except httpx.HTTPStatusError as e:
        http_status_code = e.response.status_code
        status = "DEGRADED" if 400 <= http_status_code < 500 else "DOWN"
        details["error"] = f"HTTP {http_status_code}"
    except httpx.ConnectError as e:
        status = "DOWN"
        details["error"] = f"Connection failed: {str(e)[:200]}"
    except httpx.TimeoutException:
        status = "DOWN"
        details["error"] = "Request timed out"
    except Exception as e:
        status = "DOWN"
        details["error"] = f"Check failed: {str(e)[:200]}"

    client_id = project["client_id"]
    await execute(
        """INSERT INTO monitoring_checks
           (project_id, client_id, check_type, status, response_time_ms, http_status_code, ssl_days_remaining, details, checked_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
        str(project["project_id"]),
        str(client_id),
        "http",
        status,
        response_time_ms,
        http_status_code,
        ssl_days,
        json.dumps(details),
        datetime.now(timezone.utc),
    )

    await execute(
        """UPDATE projects
           SET current_status = $2, last_check_at = NOW(), updated_at = NOW()
           WHERE project_id = $1""",
        str(project["project_id"]),
        status,
    )

    return {
        "status": status,
        "http_status_code": http_status_code,
        "response_time_ms": response_time_ms,
        "ssl_days_remaining": ssl_days,
        "details": details,
    }


monitoring_service = None
