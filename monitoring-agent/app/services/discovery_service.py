from typing import Dict, Any, List, Optional

from app.services.ssh_service import ssh_service


class DiscoveryService:
    """Service for performing read-only discovery on monitored servers."""

    async def discover_project(
        self,
        host: str,
        port: int,
        username: str,
        project_path: Optional[str] = None,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform comprehensive read-only discovery of a project."""
        discovery = {}

        discovery["os_info"] = await self._get_os_info(host, port, username, key_path, password)
        discovery["cpu_info"] = await self._get_cpu_info(host, port, username, key_path, password)
        discovery["memory_info"] = await self._get_memory_info(host, port, username, key_path, password)
        discovery["disk_info"] = await self._get_disk_info(host, port, username, key_path, password)

        discovery["php_version"] = await self._get_php_version(host, port, username, key_path, password)
        discovery["node_version"] = await self._get_node_version(host, port, username, key_path, password)
        discovery["python_version"] = await self._get_python_version(host, port, username, key_path, password)

        discovery["web_server"] = await self._get_web_server(host, port, username, key_path, password)

        if project_path:
            discovery["git_info"] = await self._get_git_info(
                host, port, username, project_path, key_path, password
            )
            discovery["project_structure"] = await self._get_project_structure(
                host, port, username, project_path, key_path, password
            )
            discovery["framework"] = await self._detect_framework(
                host, port, username, project_path, key_path, password
            )

        discovery["active_processes"] = await self._get_active_processes(
            host, port, username, key_path, password
        )

        return discovery

    async def _exec(self, host, port, username, command, key_path=None, password=None):
        """Execute command and return output."""
        result = await ssh_service.execute_command(
            host, port, username, command, key_path, password
        )
        return result["output"] if result["success"] else None

    async def _get_os_info(self, host, port, username, key_path=None, password=None):
        return await self._exec(
            host, port, username,
            "cat /etc/os-release 2>/dev/null | head -5 && uname -a",
            key_path, password
        )

    async def _get_cpu_info(self, host, port, username, key_path=None, password=None):
        return await self._exec(
            host, port, username,
            "lscpu 2>/dev/null | head -10 || cat /proc/cpuinfo | head -10",
            key_path, password
        )

    async def _get_memory_info(self, host, port, username, key_path=None, password=None):
        return await self._exec(
            host, port, username,
            "free -h",
            key_path, password
        )

    async def _get_disk_info(self, host, port, username, key_path=None, password=None):
        return await self._exec(
            host, port, username,
            "df -h",
            key_path, password
        )

    async def _get_php_version(self, host, port, username, key_path=None, password=None):
        return await self._exec(
            host, port, username,
            "php -v 2>/dev/null | head -1",
            key_path, password
        )

    async def _get_node_version(self, host, port, username, key_path=None, password=None):
        return await self._exec(
            host, port, username,
            "node -v 2>/dev/null",
            key_path, password
        )

    async def _get_python_version(self, host, port, username, key_path=None, password=None):
        return await self._exec(
            host, port, username,
            "python3 --version 2>/dev/null || python --version 2>/dev/null",
            key_path, password
        )

    async def _get_web_server(self, host, port, username, key_path=None, password=None):
        nginx = await self._exec(
            host, port, username,
            "nginx -v 2>&1 | head -1",
            key_path, password
        )
        if nginx and "nginx" in nginx.lower():
            return f"Nginx: {nginx}"

        apache = await self._exec(
            host, port, username,
            "apache2 -v 2>/dev/null | head -1 || httpd -v 2>/dev/null | head -1",
            key_path, password
        )
        if apache and ("apache" in apache.lower() or "httpd" in apache.lower()):
            return f"Apache: {apache}"

        return None

    async def _get_git_info(self, host, port, username, project_path, key_path=None, password=None):
        branch = await self._exec(
            host, port, username,
            f"cd {project_path} && git branch --show-current 2>/dev/null",
            key_path, password
        )
        commit = await self._exec(
            host, port, username,
            f"cd {project_path} && git log -1 --format='%H %s' 2>/dev/null",
            key_path, password
        )
        status = await self._exec(
            host, port, username,
            f"cd {project_path} && git status --short 2>/dev/null",
            key_path, password
        )

        if branch or commit:
            return {
                "branch": branch,
                "latest_commit": commit,
                "has_uncommitted_changes": bool(status),
            }
        return None

    async def _get_project_structure(self, host, port, username, project_path, key_path=None, password=None):
        output = await self._exec(
            host, port, username,
            f"ls -la {project_path} 2>/dev/null",
            key_path, password
        )
        if output:
            return [line for line in output.split("\n") if line.strip()]
        return []

    async def _detect_framework(self, host, port, username, project_path, key_path=None, password=None):
        composer = await self._exec(
            host, port, username,
            f"cat {project_path}/composer.json 2>/dev/null | head -5",
            key_path, password
        )
        if composer and "laravel" in composer.lower():
            return "Laravel"

        wp = await self._exec(
            host, port, username,
            f"ls {project_path}/wp-config.php 2>/dev/null",
            key_path, password
        )
        if wp:
            return "WordPress"

        package = await self._exec(
            host, port, username,
            f"cat {project_path}/package.json 2>/dev/null | head -5",
            key_path, password
        )
        if package:
            return "Node.js"

        requirements = await self._exec(
            host, port, username,
            f"ls {project_path}/requirements.txt 2>/dev/null || ls {project_path}/Pipfile 2>/dev/null",
            key_path, password
        )
        if requirements:
            return "Python"

        return None

    async def _get_active_processes(self, host, port, username, key_path=None, password=None):
        output = await self._exec(
            host, port, username,
            "ps aux --sort=-%mem | head -20",
            key_path, password
        )
        if output:
            return output.split("\n")
        return []


discovery_service = DiscoveryService()
