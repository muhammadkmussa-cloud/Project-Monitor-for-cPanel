import asyncio
from typing import Optional, Dict, Any

import paramiko

from app.services.ssh_service import _connect_kwargs


class SFTPService:
    """Service for SFTP file-system monitoring (used when SSH shell is limited)."""

    async def _sftp(self, host, port, username, key_path=None, password=None, private_key=None):
        from app.services.ssh_service import create_ssh_client
        client = create_ssh_client()
        kwargs = _connect_kwargs(host, port, username, key_path, password, private_key)
        client.connect(**kwargs)
        return client, client.open_sftp()

    async def list_directory(
        self,
        host: str,
        port: int,
        username: str,
        path: str = ".",
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            client, sftp = await self._sftp(host, port, username, key_path, password, private_key)
            entries = sftp.listdir_attr(path)
            result = [
                {
                    "name": e.filename,
                    "type": "dir" if _is_dir(e) else "file",
                    "size": e.st_size,
                    "mtime": e.st_mtime,
                }
                for e in entries
            ]
            sftp.close()
            client.close()
            return {"success": True, "path": path, "entries": result, "count": len(result)}
        except paramiko.AuthenticationException:
            return {"success": False, "error": "Authentication failed"}
        except paramiko.SSHException as e:
            return {"success": False, "error": f"SFTP error: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def stat_path(
        self,
        host: str,
        port: int,
        username: str,
        path: str,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            client, sftp = await self._sftp(host, port, username, key_path, password, private_key)
            try:
                st = sftp.stat(path)
                exists = True
            except FileNotFoundError:
                st = None
                exists = False
            sftp.close()
            client.close()
            if not exists:
                return {"success": False, "path": path, "error": "Not found"}
            return {
                "success": True,
                "path": path,
                "is_dir": _is_dir(st),
                "size": st.st_size,
                "mtime": st.st_mtime,
            }
        except paramiko.AuthenticationException:
            return {"success": False, "error": "Authentication failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}


def _is_dir(attr) -> bool:
    try:
        import stat as stat_mod
        return stat_mod.S_ISDIR(attr.st_mode)
    except Exception:
        return False


sftp_service = SFTPService()
