import asyncio
import subprocess
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from app.config import get_settings
from app.services.backup_service import backup_service
from app.services.telegram_service import telegram_service

settings = get_settings()


class SafetyLevel(Enum):
    SAFE = "safe"
    MODERATE = "moderate"
    RISKY = "risky"
    DANGEROUS = "dangerous"


class RemediationAction:
    """Represents a single remediation action."""

    def __init__(
        self,
        action_type: str,
        description: str,
        command: Optional[str] = None,
        file_path: Optional[str] = None,
        content: Optional[str] = None,
        requires_approval: bool = False,
        safety_level: SafetyLevel = SafetyLevel.SAFE,
        original_sha256: Optional[str] = None,
        rollback_on_failure: bool = False,
        reviewed_diff: Optional[str] = None,
    ):
        self.original_sha256=original_sha256
        self.rollback_on_failure=rollback_on_failure
        self.reviewed_diff=reviewed_diff
        self.action_type = action_type
        self.description = description
        self.command = command
        self.file_path = file_path
        self.content = content
        self.requires_approval = requires_approval
        self.safety_level = safety_level

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_sha256":self.original_sha256,
            "rollback_on_failure":self.rollback_on_failure,
            "reviewed_diff":self.reviewed_diff,
            "action_type": self.action_type,
            "description": self.description,
            "command": self.command,
            "file_path": self.file_path,
            "content": self.content,
            "requires_approval": self.requires_approval,
            "safety_level": self.safety_level.value,
        }


class RemediationEngine:
    """Engine for executing remediation actions with safety controls."""

    def __init__(self):
        self.safety_rules = self._load_safety_rules()

    def _load_safety_rules(self) -> Dict[str, List[str]]:
        """Load rules for what actions are allowed at each safety level."""
        return {
            "safe": [
                "restart_service",
                "clear_cache",
                "rotate_logs",
                "update_config",
            ],
            "moderate": [
                "restart_service",
                "clear_cache",
                "rotate_logs",
                "update_config",
                "modify_file",
                "run_script",
            ],
            "risky": [
                "restart_service",
                "clear_cache",
                "rotate_logs",
                "update_config",
                "modify_file",
                "run_script",
                "database_migration",
                "dependency_update",
            ],
            "dangerous": [
                "restart_service",
                "clear_cache",
                "rotate_logs",
                "update_config",
                "modify_file",
                "run_script",
                "database_migration",
                "dependency_update",
                "rollback_deployment",
                "restore_backup",
            ],
        }

    def parse_actions_from_diagnosis(
        self,
        diagnosis: Dict[str, Any],
    ) -> List[RemediationAction]:
        """Parse diagnosis into executable remediation actions."""
        actions = []

        commands = diagnosis.get("commands_required", [])
        for cmd in commands:
            safety = self._assess_command_safety(cmd)
            actions.append(
                RemediationAction(
                    action_type="run_command",
                    description=f"Execute: {cmd}",
                    command=cmd,
                    requires_approval=safety in ["risky", "dangerous"],
                    safety_level=SafetyLevel(safety),
                )
            )

        files = diagnosis.get("files_affected", [])
        for file_path in files:
            actions.append(
                RemediationAction(
                    action_type="modify_file",
                    description=f"Review and modify: {file_path}",
                    file_path=file_path,
                    requires_approval=True,
                    safety_level=SafetyLevel.MODERATE,
                )
            )

        if diagnosis.get("requires_human_approval", True):
            for action in actions:
                action.requires_approval = True

        return actions

    def _assess_command_safety(self, command: str) -> str:
        """Assess the safety level of a command."""
        import shlex
        if not isinstance(command, str) or any(c in command for c in (";", "|", "&", "`", "$", "\n", ">", "<")):
            return "dangerous"
        try:
            args = shlex.split(command)
        except ValueError:
            return "dangerous"
        if not args:
            return "dangerous"
        if args[0] == "sudo":
            args = args[1:]
        if not args:
            return "dangerous"
        if args[0] in {"uname", "uptime", "df", "free"}:
            return "safe"
        if args[:2] in [["systemctl", "status"], ["systemctl", "is-active"], ["nginx", "-t"]]:
            return "safe"
        if args[:2] == ["systemctl", "restart"] and len(args) == 3 and not args[2].startswith("-"):
            return "risky"
        if len(args) == 3 and args[:2] == ["php", "artisan"] and args[2] in {"cache:clear", "config:clear", "route:clear", "view:clear", "optimize:clear"}:
            return "risky"
        return "dangerous"

    async def execute_plan(
        self,
        incident_id: str,
        actions: List[RemediationAction],
        approval_status: str = "pending",
        server_connection: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a remediation plan."""
        if approval_status != "approved":
            return {
                "success": False,
                "error": "Plan not approved",
                "status": "pending_approval",
            }

        if not server_connection:
            return {"success": False, "error": "A stored remote project connection is required"}
        if not actions:
            return {"success": False, "error": "No executable actions in proposal"}
        if any(a.safety_level == SafetyLevel.DANGEROUS or (a.command and self._assess_command_safety(a.command) == "dangerous") for a in actions):
            return {"success": False, "error": "Blocked command in proposal"}
        backup_result = None
        if server_connection:
            file_paths = [
                a.file_path for a in actions
                if a.file_path and a.action_type == "modify_file"
            ]
            if file_paths:
                backup_result = await backup_service.create_backup(
                    incident_id=incident_id,
                    file_paths=file_paths,
                    server_connection=server_connection,
                )

        if backup_result and not backup_result["success"]:
            return {"success": False, "error": "Backup failed; remediation was not started"}
        results = []
        executed_count = 0
        failed_count = 0

        for action in actions:
            if failed_count:
                results.append({'action':action.to_dict(),'status':'not_run','reason':'An earlier action failed'})
                continue
            if action.requires_approval and approval_status != "approved":
                results.append({
                    "action": action.to_dict(),
                    "status": "skipped",
                    "reason": "requires_approval",
                })
                continue

            try:
                if action.action_type == "run_command":
                    result = await self._execute_command(
                        action.command, server_connection
                    )
                elif action.action_type == "json_patch":
                    from app.services.repair_service import apply_patch
                    result=await apply_patch(action,server_connection,run_id=run_id)
                elif action.action_type == "modify_file":
                    result = await self._execute_file_modification(
                        action, server_connection
                    )
                elif action.action_type == "restart_service":
                    result = await self._execute_restart(
                        action.command, server_connection
                    )
                else:
                    result = {
                        "success": False,
                        "error": f"Unknown action type: {action.action_type}",
                    }

                results.append({
                    "action": action.to_dict(),
                    "status": "completed" if result["success"] else "failed",
                    "result": result,
                })

                if result["success"]:
                    executed_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                results.append({
                    "action": action.to_dict(),
                    "status": "error",
                    "error": str(e),
                })
                failed_count += 1

        all_success = failed_count == 0


        return {
            "success": all_success,
            "incident_id": incident_id,
            "executed_actions": executed_count,
            "failed_actions": failed_count,
            "results": results,
            "backup_id": backup_result["data"]["backup_id"] if backup_result else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _execute_command(
        self,
        command: str,
        server_connection: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a command locally or remotely."""
        if server_connection:
            return await self._execute_remote_command(command, server_connection)
        return {"success": False, "error": "Local remediation is disabled"}

    async def _execute_local_command(self, command: str) -> Dict[str, Any]:
        """Execute a command locally."""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=60
            )

            return {
                "success": process.returncode == 0,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "return_code": process.returncode,
            }

        except asyncio.TimeoutError:
            return {"success": False, "error": "Command timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_remote_command(
        self,
        command: str,
        server_connection: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a command remotely via SSH."""
        from app.services.ssh_service import ssh_service
        connection = dict(server_connection)
        project_path = connection.pop('project_path', None)
        if project_path:
            import shlex
            path = ('"$HOME"' if project_path == '~' else '"$HOME"/' + shlex.quote(project_path[2:]) if project_path.startswith('~/') else shlex.quote(project_path))
            command = 'cd -- ' + path + ' && ' + command
        result = await ssh_service.execute_command(command=command, **connection)
        return {"success": result["success"], "stdout": result["output"], "stderr": result["error"], "return_code": result["exit_code"]}


    async def _execute_file_modification(
        self,
        action: RemediationAction,
        server_connection: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a file modification action."""
        if action.content:
            if server_connection:
                return await self._write_remote_file(
                    action.file_path, action.content, server_connection
                )
            else:
                return await self._write_local_file(
                    action.file_path, action.content
                )

        return {"success": False, "error": "No file content supplied; no modification performed"}

    async def _write_local_file(
        self,
        file_path: str,
        content: str,
    ) -> Dict[str, Any]:
        """Write content to a local file."""
        try:
            from pathlib import Path

            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _write_remote_file(
        self,
        file_path: str,
        content: str,
        server_connection: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Write content to a remote file via SSH."""
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
            with sftp.open(file_path, "w") as remote_file:
                remote_file.write(content)

            sftp.close()
            ssh.close()

            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_restart(
        self,
        command: str,
        server_connection: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a service restart."""
        return await self._execute_command(command, server_connection)


remediation_engine = RemediationEngine()
