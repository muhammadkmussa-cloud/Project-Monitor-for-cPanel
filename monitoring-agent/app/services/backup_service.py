import json
import subprocess
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import re

from app.config import get_settings

settings = get_settings()


class BackupService:
    """Service for creating and managing file backups before remediation."""

    def __init__(self):
        self.backup_dir = Path(settings.local_backup_path)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    async def create_backup(
        self,
        incident_id: str,
        file_paths: List[str],
        server_connection: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create backup of files before modification."""
        backup_id = f"backup_{uuid4().hex}"
        backup_path = self.backup_dir / backup_id
        backup_path.mkdir(parents=True, exist_ok=True)

        backed_up_files = []
        errors = []

        for file_path in file_paths:
            try:
                if server_connection:
                    result = await self._backup_remote_file(
                        file_path, backup_path, server_connection
                    )
                else:
                    result = await self._backup_local_file(file_path, backup_path)

                if result["success"]:
                    backed_up_files.append(result["data"])
                else:
                    errors.append({"file": file_path, "error": result["error"]})

            except Exception as e:
                errors.append({"file": file_path, "error": str(e)})

        backup_record = {
            "backup_id": backup_id,
            "incident_id": incident_id,
            "created_at": datetime.utcnow().isoformat(),
            "files_backed_up": len(backed_up_files),
            "files_failed": len(errors),
            "files": backed_up_files,
            "errors": errors,
            "status": "completed" if not errors else "partial",
        }

        manifest_path = backup_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(backup_record, f, indent=2)

        return {
            "success": len(errors) == 0,
            "data": backup_record,
        }

    async def _backup_local_file(
        self,
        file_path: str,
        backup_path: Path,
    ) -> Dict[str, Any]:
        """Backup a local file."""
        try:
            source = Path(file_path)
            if not source.exists():
                return {"success": False, "error": "File not found"}

            with open(source, "rb") as f:
                content = f.read()
                file_hash = hashlib.sha256(content).hexdigest()

            relative_path = hashlib.sha256(str(source).encode()).hexdigest() + "_" + source.name
            backup_file = backup_path / relative_path
            backup_file.write_bytes(content)

            return {
                "success": True,
                "data": {
                    "original_path": file_path,
                    "backup_path": str(backup_file),
                    "hash": file_hash,
                    "size": len(content),
                },
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _backup_remote_file(
        self,
        file_path: str,
        backup_path: Path,
        server_connection: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Backup a remote file via SSH."""
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

            sftp = ssh.open_sftp()

            remote_stat = sftp.stat(file_path)
            with sftp.open(file_path, "rb") as remote_file:
                content = remote_file.read()
                file_hash = hashlib.sha256(content).hexdigest()

            file_name = Path(file_path).name
            backup_file = backup_path / (hashlib.sha256(file_path.encode()).hexdigest() + "_" + file_name)
            backup_file.write_bytes(content)

            sftp.close()
            ssh.close()

            return {
                "success": True,
                "data": {
                    "original_path": file_path,
                    "backup_path": str(backup_file),
                    "hash": file_hash,
                    "size": remote_stat.st_size,
                    "remote": True,
                },
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def restore_backup(
        self,
        backup_id: str,
        server_connection: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Restore files from a backup."""
        backup_path = self._safe_backup_path(backup_id)
        manifest_path = backup_path / "manifest.json"

        if not manifest_path.exists():
            return {"success": False, "error": "Backup manifest not found"}

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        restored_files = []
        errors = []

        for file_info in manifest.get("files", []):
            try:
                backup_file = Path(file_info["backup_path"])
                original_path = file_info["original_path"]

                if not backup_file.exists():
                    errors.append({
                        "file": original_path,
                        "error": "Backup file not found",
                    })
                    continue

                if not backup_file.resolve().is_relative_to(backup_path.resolve()):
                    raise ValueError("Backup file is outside its backup directory")
                if hashlib.sha256(backup_file.read_bytes()).hexdigest() != file_info["hash"]:
                    raise ValueError("Backup checksum mismatch")
                if file_info.get("remote") and not server_connection:
                    raise ValueError("Remote backups require the original remote connection")
                if server_connection:
                    result = await self._restore_remote_file(
                        backup_file, original_path, server_connection
                    )
                else:
                    result = await self._restore_local_file(
                        backup_file, original_path
                    )

                if result["success"]:
                    restored_files.append(original_path)
                else:
                    errors.append({
                        "file": original_path,
                        "error": result["error"],
                    })

            except Exception as e:
                errors.append({
                    "file": file_info.get("original_path", "unknown"),
                    "error": str(e),
                })

        return {
            "success": len(errors) == 0,
            "restored_files": len(restored_files),
            "failed_files": len(errors),
            "errors": errors,
        }

    async def _restore_local_file(
        self,
        backup_file: Path,
        original_path: str,
    ) -> Dict[str, Any]:
        """Restore a local file from backup."""
        try:
            import shutil

            dest = Path(original_path)
            dest.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(backup_file, dest)

            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _restore_remote_file(
        self,
        backup_file: Path,
        original_path: str,
        server_connection: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Restore a remote file via SSH."""
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

            sftp = ssh.open_sftp()

            with open(backup_file, "rb") as f:
                content = f.read()

            with sftp.open(original_path, "wb") as remote_file:
                remote_file.write(content)

            sftp.close()
            ssh.close()

            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _safe_backup_path(self, backup_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", backup_id):
            raise ValueError("Invalid backup ID")
        path = (self.backup_dir / backup_id).resolve()
        if not path.is_relative_to(self.backup_dir.resolve()):
            raise ValueError("Backup is outside storage")
        return path

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups."""
        backups = []

        for backup_path in self.backup_dir.iterdir():
            if backup_path.is_dir():
                manifest_path = backup_path / "manifest.json"
                if manifest_path.exists():
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)
                    backups.append(manifest)

        return sorted(backups, key=lambda x: x.get("created_at", ""), reverse=True)

    def get_backup(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific backup."""
        manifest_path = self._safe_backup_path(backup_id) / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r") as f:
                return json.load(f)
        return None


backup_service = BackupService()
