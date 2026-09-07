import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.config import get_settings

settings = get_settings()


class VerificationService:
    """Service for verifying remediation results."""

    def __init__(self):
        self.checks = {
            "health_check": self._verify_health_check,
            "log_check": self._verify_log_check,
            "service_status": self._verify_service_status,
            "connectivity": self._verify_connectivity,
            "disk_space": self._verify_disk_space,
        }

    async def verify_remediation(
        self,
        incident_id: str,
        verification_plan: List[str],
        server_connection: Optional[Dict[str, Any]] = None,
        expected_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute verification plan and return results."""
        if not verification_plan:
            return {"success": False, "error": "No verification checks specified", "results": []}
        results = []
        passed_count = 0
        failed_count = 0

        for check_name in verification_plan:
            check_func = self._get_check_function(check_name)

            if not check_func:
                failed_count += 1
                results.append({"check_name": check_name, "passed": False, "error": "Unsupported verification check"})
            if check_func:
                try:
                    result = await check_func(
                        server_connection=server_connection,
                        expected_url=expected_url,
                    )
                    result["check_name"] = check_name
                    results.append(result)

                    if result["passed"]:
                        passed_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    results.append({
                        "check_name": check_name,
                        "passed": False,
                        "error": str(e),
                    })
                    failed_count += 1
            else:
                results.append({
                    "check_name": check_name,
                    "passed": False,
                    "error": f"Unknown check: {check_name}",
                })
                failed_count += 1

        all_passed = failed_count == 0

        return {
            "success": all_passed,
            "incident_id": incident_id,
            "checks_passed": passed_count,
            "checks_failed": failed_count,
            "results": results,
            "verified_at": datetime.utcnow().isoformat(),
        }

    def _get_check_function(self, check_name: str):
        """Get the verification check function."""
        check_mapping = {
            "Check application health": "health_check",
            "Check service status": "service_status",
            "Review logs": "log_check",
            "Verify connectivity": "connectivity",
            "Check disk space": "disk_space",
            "Verify HTTP response": "health_check",
            "Check error rates": "log_check",
        }

        normalized = check_mapping.get(check_name, check_name)
        return self.checks.get(normalized)

    async def _verify_health_check(
        self,
        server_connection: Optional[Dict[str, Any]] = None,
        expected_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify application health via HTTP check."""
        import httpx

        url = expected_url or "http://localhost:8000/health"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)

                return {
                    "passed": response.status_code == 200,
                    "status_code": response.status_code,
                    "response_time_ms": response.elapsed.total_seconds() * 1000,
                }

        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }

    async def _verify_log_check(
        self,
        server_connection: Optional[Dict[str, Any]] = None,
        expected_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify no critical errors in recent logs."""
        if server_connection:
            return await self._check_remote_logs(server_connection)
        else:
            return await self._check_local_logs()

    async def _check_local_logs(self) -> Dict[str, Any]:
        """Check local application logs."""
        try:
            log_paths = [
                "/var/log/app/error.log",
                "/var/log/app/application.log",
            ]

            critical_errors = 0

            for log_path in log_paths:
                try:
                    with open(log_path, "r") as f:
                        recent_lines = f.readlines()[-100:]

                    for line in recent_lines:
                        if any(level in line.upper() for level in ["CRITICAL", "FATAL", "EXCEPTION"]):
                            critical_errors += 1

                except FileNotFoundError:
                    continue

            return {
                "passed": critical_errors == 0,
                "critical_errors_found": critical_errors,
            }

        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }

    async def _check_remote_logs(
        self,
        server_connection: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Check remote application logs via SSH."""
        try:
            import paramiko

            from app.services.ssh_service import create_ssh_client

            ssh = create_ssh_client()

            ssh.connect(
                hostname=server_connection["host"],
                port=server_connection.get("port", 22),
                username=server_connection.get("username"),
                key_filename=server_connection.get("key_path"),
                password=server_connection.get("password"),
                timeout=30,
            )

            cmd = "journalctl -n 100 --no-pager 2>/dev/null || tail -100 /var/log/syslog 2>/dev/null || echo 'No logs found'"
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)

            logs = stdout.read().decode()
            ssh.close()

            critical_count = sum(
                1 for line in logs.split("\n")
                if any(level in line.upper() for level in ["CRITICAL", "FATAL", "EXCEPTION"])
            )

            return {
                "passed": critical_count == 0,
                "critical_errors_found": critical_count,
            }

        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }

    async def _verify_service_status(
        self,
        server_connection: Optional[Dict[str, Any]] = None,
        expected_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify service is running."""
        if server_connection:
            return await self._check_remote_service(server_connection)
        else:
            return await self._check_local_service()

    async def _check_local_service(self) -> Dict[str, Any]:
        """Check local service status."""
        try:
            process = await asyncio.create_subprocess_shell(
                "systemctl is-active app.service 2>/dev/null || echo 'unknown'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            status = stdout.decode().strip()

            return {
                "passed": status == "active" or status == "unknown",
                "service_status": status,
            }

        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }

    async def _check_remote_service(
        self,
        server_connection: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Check remote service status via SSH."""
        try:
            import paramiko

            from app.services.ssh_service import create_ssh_client

            ssh = create_ssh_client()

            ssh.connect(
                hostname=server_connection["host"],
                port=server_connection.get("port", 22),
                username=server_connection.get("username"),
                key_filename=server_connection.get("key_path"),
                password=server_connection.get("password"),
                timeout=30,
            )

            cmd = "systemctl is-active app.service 2>/dev/null || ps aux | grep -v grep | grep -c 'app' || echo 'unknown'"
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)

            status = stdout.read().decode().strip()
            ssh.close()

            return {
                "passed": status == "active" or status.isdigit(),
                "service_status": status,
            }

        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }

    async def _verify_connectivity(
        self,
        server_connection: Optional[Dict[str, Any]] = None,
        expected_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify network connectivity."""
        import httpx

        url = expected_url or "http://localhost:8000"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)

                return {
                    "passed": response.status_code < 500,
                    "status_code": response.status_code,
                }

        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }

    async def _verify_disk_space(
        self,
        server_connection: Optional[Dict[str, Any]] = None,
        expected_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify sufficient disk space."""
        if server_connection:
            return await self._check_remote_disk(server_connection)
        else:
            return await self._check_local_disk()

    async def _check_local_disk(self) -> Dict[str, Any]:
        """Check local disk space."""
        try:
            import shutil

            total, used, free = shutil.disk_usage("/")

            free_percent = (free / total) * 100

            return {
                "passed": free_percent > 10,
                "free_percent": round(free_percent, 1),
                "free_gb": round(free / (1024**3), 1),
            }

        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }

    async def _check_remote_disk(
        self,
        server_connection: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Check remote disk space via SSH."""
        try:
            import paramiko

            from app.services.ssh_service import create_ssh_client

            ssh = create_ssh_client()

            ssh.connect(
                hostname=server_connection["host"],
                port=server_connection.get("port", 22),
                username=server_connection.get("username"),
                key_filename=server_connection.get("key_path"),
                password=server_connection.get("password"),
                timeout=30,
            )

            cmd = "df -h / | tail -1 | awk '{print $5}' | sed 's/%//'"
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)

            used_percent = stdout.read().decode().strip()
            ssh.close()

            free_percent = 100 - int(used_percent)

            return {
                "passed": free_percent > 10,
                "free_percent": free_percent,
            }

        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }


verification_service = VerificationService()
