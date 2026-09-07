import httpx
import ssl
import socket
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from app.config import get_settings

settings = get_settings()


class HealthService:
    """Service for performing health checks on monitored projects."""

    async def check_http(
        self,
        url: str,
        timeout: int = 30,
        expected_status: int = 200,
    ) -> Dict[str, Any]:
        """Perform HTTP health check."""
        try:
            start_time = datetime.now()
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url)
                end_time = datetime.now()
                response_time_ms = int((end_time - start_time).total_seconds() * 1000)

                is_healthy = response.status_code == expected_status

                if response_time_ms > settings.response_time_critical_ms:
                    status = "CRITICAL"
                elif response_time_ms > settings.response_time_warning_ms:
                    status = "WARNING"
                elif is_healthy:
                    status = "HEALTHY"
                else:
                    status = "DOWN"

                return {
                    "status": status,
                    "http_status_code": response.status_code,
                    "response_time_ms": response_time_ms,
                    "redirect_url": str(response.url) if str(response.url) != url else None,
                    "details": {
                        "url": url,
                        "expected_status": expected_status,
                        "content_length": len(response.content),
                    },
                }

        except httpx.TimeoutException:
            return {
                "status": "DOWN",
                "http_status_code": None,
                "response_time_ms": None,
                "details": {"error": "Connection timed out", "url": url},
            }
        except httpx.ConnectError:
            return {
                "status": "DOWN",
                "http_status_code": None,
                "response_time_ms": None,
                "details": {"error": "Connection refused", "url": url},
            }
        except Exception as e:
            return {
                "status": "UNKNOWN",
                "http_status_code": None,
                "response_time_ms": None,
                "details": {"error": str(e), "url": url},
            }

    async def check_ssl(
        self,
        domain: str,
        port: int = 443,
    ) -> Dict[str, Any]:
        """Check SSL certificate status."""
        try:
            context = ssl.create_default_context()
            with socket.create_connection((domain, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()

                    not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
                    days_remaining = (not_after - datetime.now()).days

                    if days_remaining <= settings.ssl_critical_days:
                        status = "CRITICAL"
                    elif days_remaining <= settings.ssl_warning_days:
                        status = "WARNING"
                    else:
                        status = "HEALTHY"

                    return {
                        "status": status,
                        "ssl_days_remaining": days_remaining,
                        "issuer": dict(x[0] for x in cert.get("issuer", [])).get("organizationName"),
                        "subject": dict(x[0] for x in cert.get("subject", [])).get("commonName"),
                        "not_after": not_after.isoformat(),
                        "details": {
                            "domain": domain,
                            "port": port,
                            "serial_number": cert.get("serialNumber"),
                        },
                    }

        except ssl.SSLCertVerificationError as e:
            return {
                "status": "CRITICAL",
                "ssl_days_remaining": 0,
                "details": {"error": f"SSL verification failed: {str(e)}", "domain": domain},
            }
        except Exception as e:
            return {
                "status": "UNKNOWN",
                "ssl_days_remaining": None,
                "details": {"error": str(e), "domain": domain},
            }

    async def check_health_endpoint(
        self,
        url: str,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """Check application health endpoint (e.g., /health)."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    try:
                        data = response.json()
                        app_status = data.get("status", "unknown")

                        if app_status == "ok":
                            status = "HEALTHY"
                        elif app_status == "warning":
                            status = "WARNING"
                        else:
                            status = "CRITICAL"

                        return {
                            "status": status,
                            "http_status_code": 200,
                            "app_status": app_status,
                            "details": data,
                        }
                    except Exception:
                        return {
                            "status": "HEALTHY",
                            "http_status_code": 200,
                            "app_status": "ok",
                            "details": {"raw_response": response.text[:500]},
                        }
                else:
                    return {
                        "status": "CRITICAL",
                        "http_status_code": response.status_code,
                        "app_status": "error",
                        "details": {"error": f"HTTP {response.status_code}"},
                    }

        except Exception as e:
            return {
                "status": "DOWN",
                "http_status_code": None,
                "app_status": "unreachable",
                "details": {"error": str(e)},
            }


health_service = HealthService()
