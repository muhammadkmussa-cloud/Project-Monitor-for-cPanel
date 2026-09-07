from typing import Dict, Any, Optional, List
from datetime import datetime

from app.services.backup_service import backup_service
from app.services.verification_service import verification_service
from app.services.telegram_service import telegram_service
from app.services.remediation_engine import remediation_engine


class RollbackService:
    """Service for automatic rollback when remediation fails."""

    def __init__(self):
        self.max_verification_attempts = 3
        self.verification_delay_seconds = 30

    async def execute_with_rollback(
        self,
        incident_id: str,
        actions: List[Dict[str, Any]],
        verification_plan: List[str],
        server_connection: Optional[Dict[str, Any]] = None,
        expected_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute remediation with automatic rollback on failure."""
        backup_result = await backup_service.create_backup(
            incident_id=incident_id,
            file_paths=[a.get("file_path") for a in actions if a.get("file_path")],
            server_connection=server_connection,
        )

        if not backup_result["success"]:
            return {
                "success": False,
                "error": "Failed to create backup before remediation",
                "status": "backup_failed",
            }

        backup_id = backup_result["data"]["backup_id"]

        from app.services.remediation_engine import RemediationAction, SafetyLevel

        remediation_actions = []
        for action_data in actions:
            remediation_actions.append(
                RemediationAction(
                    action_type=action_data.get("action_type", "run_command"),
                    description=action_data.get("description", ""),
                    command=action_data.get("command"),
                    file_path=action_data.get("file_path"),
                    content=action_data.get("content"),
                    requires_approval=action_data.get("requires_approval", False),
                    safety_level=SafetyLevel(
                        action_data.get("safety_level", "safe")
                    ),
                )
            )

        execution_result = await remediation_engine.execute_plan(
            incident_id=incident_id,
            actions=remediation_actions,
            approval_status="approved",
            server_connection=server_connection,
        )

        if not execution_result["success"]:
            rollback_result = await self._perform_rollback(
                incident_id=incident_id,
                backup_id=backup_id,
                server_connection=server_connection,
            )

            return {
                "success": False,
                "status": "rolled_back",
                "reason": "Remediation failed, automatic rollback triggered",
                "execution_result": execution_result,
                "rollback_result": rollback_result,
            }

        verification_passed = False
        last_verification = None

        for attempt in range(self.max_verification_attempts):
            if attempt > 0:
                import asyncio
                await asyncio.sleep(self.verification_delay_seconds)

            verification_result = await verification_service.verify_remediation(
                incident_id=incident_id,
                verification_plan=verification_plan,
                server_connection=server_connection,
                expected_url=expected_url,
            )

            last_verification = verification_result

            if verification_result["success"]:
                verification_passed = True
                break

        if not verification_passed:
            rollback_result = await self._perform_rollback(
                incident_id=incident_id,
                backup_id=backup_id,
                server_connection=server_connection,
            )

            await telegram_service.send_rollback_notification(
                incident_id=incident_id,
                reason="Post-fix verification failed after multiple attempts",
            )

            return {
                "success": False,
                "status": "rolled_back",
                "reason": "Verification failed, automatic rollback triggered",
                "verification_result": last_verification,
                "rollback_result": rollback_result,
            }

        return {
            "success": True,
            "status": "completed",
            "execution_result": execution_result,
            "verification_result": last_verification,
            "backup_id": backup_id,
        }

    async def _perform_rollback(
        self,
        incident_id: str,
        backup_id: str,
        server_connection: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Perform rollback from backup."""
        try:
            restore_result = await backup_service.restore_backup(
                backup_id=backup_id,
                server_connection=server_connection,
            )

            if restore_result["success"]:
                return {
                    "success": True,
                    "restored_files": restore_result["restored_files"],
                    "backup_id": backup_id,
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to restore from backup",
                    "details": restore_result,
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def manual_rollback(
        self,
        incident_id: str,
        backup_id: str,
        server_connection: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Manually trigger rollback for an incident."""
        return await self._perform_rollback(
            incident_id=incident_id,
            backup_id=backup_id,
            server_connection=server_connection,
        )


rollback_service = RollbackService()
