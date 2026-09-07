import asyncio
import io
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any

import paramiko

from app.config import get_settings

settings = get_settings()


def _load_pkey(private_key: Optional[str] = None, password: Optional[str] = None):
    if not private_key:
        return None
    key_classes = [
        paramiko.Ed25519Key,
        paramiko.RSAKey,
        paramiko.ECDSAKey,
    ]
    for cls in key_classes:
        try:
            return cls.from_private_key(io.StringIO(private_key), password=password)
        except Exception:
            continue
    raise ValueError("Invalid or unsupported private key")


def _connect_kwargs(
    host: str,
    port: int,
    username: str,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    private_key: Optional[str] = None,
) -> Dict[str, Any]:
    kwargs = {
        "hostname": host,
        "port": port,
        "username": username,
        "timeout": settings.ssh_timeout,
    }
    pkey = _load_pkey(private_key, password) if private_key else None
    if pkey is not None:
        kwargs["pkey"] = pkey
        if password:
            kwargs["password"] = password
    elif key_path:
        kwargs["key_filename"] = key_path
    elif password:
        kwargs["password"] = password
    else:
        raise ValueError("No authentication method provided (password, key_path or private_key)")
    return kwargs


def create_ssh_client():
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    known_hosts = Path(settings.ssh_known_hosts)
    if known_hosts.is_file():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    return client


class SSHService:
    """Service for managing SSH connections to monitored servers."""

    def __init__(self):
        self.timeout = settings.ssh_timeout
        self.retry_attempts = settings.ssh_retry_attempts

    async def test_connection(self, host, port, username, key_path=None, password=None, private_key=None):
        result = await self.execute_command(host, port, username, "uname -a", key_path, password, private_key)
        return {"success": result["success"], "message": "Connection successful" if result["success"] else result["error"],
                "host": host, "username": username, "os_info": result.get("output", "")}

    async def execute_command(self, host, port, username, command, key_path=None, password=None, private_key=None, timeout=None):
        return await asyncio.to_thread(self._execute_sync, host, port, username, command,
                                       key_path, password, private_key, timeout or self.timeout)

    def _execute_sync(self, host, port, username, command, key_path, password, private_key, timeout):
        client = create_ssh_client()
        deadline = time.monotonic() + timeout
        try:
            kwargs = _connect_kwargs(host, port, username, key_path, password, private_key)
            phase_timeout = min(timeout / 4, 10)
            kwargs.update(timeout=phase_timeout, auth_timeout=phase_timeout, banner_timeout=phase_timeout, channel_timeout=phase_timeout)
            client.connect(**kwargs)
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError("SSH connection deadline exceeded")
            _, stdout, _ = client.exec_command(command, timeout=remaining)
            channel = stdout.channel
            output, error = bytearray(), bytearray()
            # Drain both streams before waiting for exit to avoid a full-window deadlock.
            while True:
                if channel.recv_ready():
                    output.extend(channel.recv(65536))
                if channel.recv_stderr_ready():
                    error.extend(channel.recv_stderr(65536))
                if len(output) + len(error) > 4 * 1024 * 1024:
                    raise ValueError("SSH output exceeds 4 MiB limit")
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("SSH command timed out")
                time.sleep(0.01)
            code = channel.recv_exit_status()
            return {"success": code == 0, "exit_code": code, "output": output.decode(errors="replace").strip(),
                    "error": error.decode(errors="replace").strip()}
        except Exception as exc:
            return {"success": False, "exit_code": -1, "output": "", "error": str(exc)}
        finally:
            client.close()

    async def _run(self, host, port, username, cmd, key_path, password, private_key):
        result = await self.execute_command(host, port, username, cmd, key_path, password, private_key)
        if result["success"]:
            return result["output"]
        raise RuntimeError(result.get("error") or "SSH command failed")

    async def get_server_stats(
        self,
        host: str,
        port: int,
        username: str,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get server resource statistics."""
        commands = {
            "cpu": "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'",
            "memory": "free -m | awk 'NR==2{printf \"%.2f\", $3*100/$2}'",
            "disk": "df -P ~ | awk 'NR==2{print $5}' | sed 's/%//'",
            "load": "cat /proc/loadavg | awk '{print $1, $2, $3}'",
            "uptime": "cat /proc/uptime | awk '{print int($1)}'",
        }
        mem = await self._run(host, port, username, commands["memory"], key_path, password, private_key)
        cpu = await self._run(host, port, username, commands["cpu"], key_path, password, private_key)
        return {
            "cpu_percent": float(cpu or 0),
            "memory_percent": float(mem or 0),
            "disk_percent": float(await self._run(host, port, username, commands["disk"], key_path, password, private_key) or 0),
            "load_average": [float(x) for x in (await self._run(host, port, username, commands["load"], key_path, password, private_key) or "0 0 0").split()],
            "uptime": int(await self._run(host, port, username, commands["uptime"], key_path, password, private_key) or 0),
        }


ssh_service = SSHService()
