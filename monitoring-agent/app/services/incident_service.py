from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID

from app.config import get_settings

settings = get_settings()


class IncidentService:
    """Service for detecting and managing incidents."""

    def detect_incident(
        self,
        project_id: UUID,
        client_id: UUID,
        health_check: Dict[str, Any],
        server_stats: Optional[Dict[str, Any]] = None,
        log_analysis: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Analyze check results and detect incidents."""
        incidents = []

        if health_check.get("status") in ["DOWN", "CRITICAL"]:
            incidents.append({
                "project_id": project_id,
                "client_id": client_id,
                "category": self._categorize_health_failure(health_check),
                "severity": self._determine_severity(health_check, server_stats),
                "error_signature": self._generate_signature(health_check),
                "affected_component": self._identify_component(health_check),
                "details": health_check,
            })

        if server_stats:
            resource_incidents = self._check_resource_thresholds(
                project_id, client_id, server_stats
            )
            incidents.extend(resource_incidents)

        if not incidents:
            return None

        return incidents[0] if len(incidents) == 1 else {
            "multiple": True,
            "incidents": incidents,
        }

    def _categorize_health_failure(self, health_check: Dict[str, Any]) -> str:
        """Categorize the type of health failure."""
        status_code = health_check.get("http_status_code")

        if status_code == 502:
            return "HTTP_ERROR"
        elif status_code == 503:
            return "HTTP_ERROR"
        elif status_code == 500:
            return "APPLICATION_ERROR"
        elif status_code is None:
            error = health_check.get("details", {}).get("error", "")
            if "timed out" in error.lower():
                return "NETWORK_ERROR"
            elif "refused" in error.lower():
                return "PROCESS_CRASH"
            return "NETWORK_ERROR"

        return "APPLICATION_ERROR"

    def _determine_severity(
        self,
        health_check: Dict[str, Any],
        server_stats: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Determine incident severity."""
        status = health_check.get("status", "UNKNOWN")

        if status == "DOWN":
            return "CRITICAL"
        elif status == "CRITICAL":
            return "HIGH"

        if server_stats:
            if server_stats.get("disk_percent", 0) > settings.disk_critical_threshold:
                return "CRITICAL"
            if server_stats.get("memory_percent", 0) > settings.ram_critical_threshold:
                return "HIGH"

        return "MEDIUM"

    def _generate_signature(self, health_check: Dict[str, Any]) -> str:
        """Generate error signature for deduplication."""
        status_code = health_check.get("http_status_code", "none")
        status = health_check.get("status", "unknown")
        return f"{status}:{status_code}"

    def _identify_component(self, health_check: Dict[str, Any]) -> str:
        """Identify which component is affected."""
        status_code = health_check.get("http_status_code")

        if status_code in [502, 503]:
            return "web_server"
        elif status_code == 500:
            return "application"
        elif status_code is None:
            return "network"

        return "unknown"

    def _check_resource_thresholds(
        self,
        project_id: UUID,
        client_id: UUID,
        server_stats: Dict[str, Any],
    ) -> list:
        """Check server resource thresholds and create incidents."""
        incidents = []

        disk = server_stats.get("disk_percent", 0)
        if disk > settings.disk_critical_threshold:
            incidents.append({
                "project_id": project_id,
                "client_id": client_id,
                "category": "DISK_FULL",
                "severity": "CRITICAL",
                "error_signature": f"disk_critical:{disk}",
                "affected_component": "disk",
                "details": {"disk_percent": disk},
            })
        elif disk > settings.disk_warning_threshold:
            incidents.append({
                "project_id": project_id,
                "client_id": client_id,
                "category": "DISK_FULL",
                "severity": "MEDIUM",
                "error_signature": f"disk_warning:{disk}",
                "affected_component": "disk",
                "details": {"disk_percent": disk},
            })

        memory = server_stats.get("memory_percent", 0)
        if memory > settings.ram_critical_threshold:
            incidents.append({
                "project_id": project_id,
                "client_id": client_id,
                "category": "MEMORY_EXHAUSTION",
                "severity": "HIGH",
                "error_signature": f"memory_critical:{memory}",
                "affected_component": "memory",
                "details": {"memory_percent": memory},
            })

        return incidents


incident_service = IncidentService()
