import hashlib
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.ssh_service import ssh_service
from app.utils.redactor import Redactor


class LogService:
    """Service for collecting and processing logs from monitored servers."""

    def __init__(self):
        self.redactor = Redactor()

    async def get_recent_logs(
        self,
        host: str,
        port: int,
        username: str,
        log_path: str,
        lines: int = 100,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent log entries from a file."""
        command = f"tail -n {lines} {log_path}"
        result = await ssh_service.execute_command(
            host, port, username, command, key_path, password
        )

        if not result["success"]:
            return []

        logs = []
        for line in result["output"].split("\n"):
            if line.strip():
                cleaned = self.redactor.redact(line)
                parsed = self._parse_log_line(cleaned)
                logs.append(parsed)

        return logs

    async def get_error_logs(
        self,
        host: str,
        port: int,
        username: str,
        log_path: str,
        lines: int = 100,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get error log entries from a file."""
        command = f"grep -i 'error\\|fatal\\|critical\\|exception\\|warning' {log_path} | tail -n {lines}"
        result = await ssh_service.execute_command(
            host, port, username, command, key_path, password
        )

        if not result["success"]:
            return []

        logs = []
        for line in result["output"].split("\n"):
            if line.strip():
                cleaned = self.redactor.redact(line)
                parsed = self._parse_log_line(cleaned)
                if parsed["level"] in ["error", "fatal", "critical", "warning"]:
                    logs.append(parsed)

        return logs

    async def read_project_error_log(
        self,
        host: str,
        port: int,
        username: str,
        domain: Optional[str],
        project_path: Optional[str],
        lines: int = 100,
        errors_only: bool = True,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Locate and read the most relevant application/PHP error log for a project.

        cPanel accounts are non-root, so Apache/access logs are unreadable. PHP
        error logs, when enabled, are written under the account. This tries a set
        of well-known per-account candidates and returns the newest matching file.
        """
        domain = (domain or "").strip()
        cwd = project_path or "~"
        candidates = (
            "$HOME/logs/{d}.error.log", "$HOME/logs/{d}.php.error.log",
            "$HOME/logs/{d}/error.log", "$HOME/logs/error.log",
            "{p}/error_log", "{p}/logs/error.log", "$HOME/.logs/{d}.error.log",
            "$HOME/php.error.log",
        )
        import shlex
        def quote_path(path):
            if path.startswith('$HOME/'):
                return '"$HOME"/' + shlex.quote(path[6:])
            if path.startswith('~/'):
                return '"$HOME"/' + shlex.quote(path[2:])
            return shlex.quote(path)
        if cwd == '~': cwd = '$HOME'
        cand_list = " ".join(quote_path(c.format(d=domain, p=cwd)) for c in candidates)
        lines = max(1, min(int(lines), 1000))
        if errors_only:
            tail_cmd = "grep -iE 'error|fatal|exception|critical|warning' \"$f\" | tail -n {lines}"
        else:
            tail_cmd = "tail -n {lines} \"$f\""
        command = (
            f'for f in {cand_list}; do '
            f'if [ -f "$f" ]; then '
            f'echo "__FILE__:$f"; {tail_cmd.format(lines=lines)}; '
            f'fi; done'
        )
        result = await ssh_service.execute_command(
            host, port, username, command, key_path, password, private_key
        )
        if not result["success"]:
            return {"success": False, "found": False, "entries": [], "files": [], "error": result.get("error") or "SSH command failed"}

        entries: List[Dict[str, Any]] = []
        files: List[str] = []
        current_file: Optional[str] = None
        for raw in result["output"].splitlines():
            if raw.startswith("__FILE__:"):
                current_file = raw.split(":", 1)[1]
                if current_file not in files:
                    files.append(current_file)
                continue
            if not raw.strip():
                continue
            parsed = self._parse_log_line(raw.strip())
            parsed["source"] = current_file
            entries.append(parsed)

        entries = entries[: int(lines)]
        return {
            "success": True,
            "found": bool(files),
            "entries": entries,
            "files": files,
            "total": len(entries),
        }

    async def collect_logs_from_multiple_sources(
        self,
        host: str,
        port: int,
        username: str,
        log_locations: List[str],
        lines_per_source: int = 50,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Collect logs from multiple locations and deduplicate."""
        all_logs = []

        for log_path in log_locations:
            logs = await self.get_recent_logs(
                host, port, username, log_path, lines_per_source,
                key_path, password
            )
            all_logs.extend(logs)

        seen_signatures = set()
        unique_logs = []
        for log in all_logs:
            signature = self._generate_error_signature(log["message"])
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                log["error_signature"] = signature
                unique_logs.append(log)

        unique_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return {
            "total_entries": len(all_logs),
            "unique_entries": len(unique_logs),
            "logs": unique_logs[:200],
        }

    def _parse_log_line(self, line: str) -> Dict[str, Any]:
        """Parse a log line into structured format."""
        level = "info"
        if any(keyword in line.lower() for keyword in ["error", "fatal", "critical", "exception"]):
            level = "error"
        elif "warning" in line.lower() or "warn" in line.lower():
            level = "warning"
        elif "debug" in line.lower():
            level = "debug"

        timestamp = None
        timestamp_match = re.search(
            r'\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}',
            line
        )
        if timestamp_match:
            timestamp = timestamp_match.group()

        return {
            "timestamp": timestamp,
            "level": level,
            "message": line,
            "source": None,
            "metadata": {},
        }

    def _generate_error_signature(self, message: str) -> str:
        """Generate a unique signature for error deduplication."""
        normalized = re.sub(r'\d+', 'N', message)
        normalized = re.sub(r'0x[0-9a-fA-F]+', 'HEX', normalized)
        normalized = re.sub(r'/[\w/]+', 'PATH', normalized)
        return hashlib.md5(normalized.encode()).hexdigest()


log_service = LogService()
