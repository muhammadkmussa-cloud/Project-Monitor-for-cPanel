import httpx
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.config import get_settings

settings = get_settings()


class AIService:
    """Service for AI-powered incident diagnosis using DeepSeek."""

    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model
        self.base_url = settings.deepseek_base_url

    async def diagnose_incident(
        self,
        incident_data: Dict[str, Any],
        log_entries: List[Dict[str, Any]],
        server_stats: Optional[Dict[str, Any]] = None,
        git_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Analyze an incident and provide diagnosis."""
        if not self.api_key:
            return self._fallback_diagnosis(incident_data)

        from app.utils.redactor import redactor
        incident_data = redactor.redact_dict(incident_data)
        log_entries = [redactor.redact_dict(entry) for entry in log_entries]
        server_stats = redactor.redact_dict(server_stats) if server_stats else None
        git_info = redactor.redact_dict(git_info) if git_info else None
        prompt = self._build_diagnosis_prompt(
            incident_data, log_entries, server_stats, git_info
        )

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": self._get_system_prompt(),
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "temperature": 0.3,
                        "max_tokens": 2000,
                        "response_format": {"type": "json_object"},
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    diagnosis = json.loads(content)
                    return self._validate_diagnosis(diagnosis)
                else:
                    return self._fallback_diagnosis(incident_data)

        except Exception as e:
            return self._fallback_diagnosis(incident_data, str(e))

    def _get_system_prompt(self) -> str:
        return """You are a senior DevOps/SRE engineer analyzing system incidents.

For every incident, determine:
- what happened
- when it started
- what changed before the incident
- affected component
- likely root cause
- evidence supporting the diagnosis
- alternative possible causes
- severity (LOW, MEDIUM, HIGH, CRITICAL)
- confidence (0.0 to 1.0)
- proposed fix
- files affected
- commands required
- risks
- rollback plan
- verification plan

You MUST respond in valid JSON with this exact structure:
{
    "severity": "HIGH",
    "category": "APPLICATION_ERROR",
    "root_cause": "...",
    "evidence": ["...", "..."],
    "affected_component": "...",
    "confidence": 0.91,
    "proposed_fix": "...",
    "files_affected": [],
    "commands_required": [],
    "risk_level": "MEDIUM",
    "rollback_plan": "...",
    "verification_plan": [],
    "requires_human_approval": true
}

Rules:
- Never invent server state
- Never assume a command succeeded without evidence
- State explicitly when evidence is insufficient
- Always err on the side of caution
- Never propose destructive actions without human approval"""

    def _build_diagnosis_prompt(
        self,
        incident_data: Dict[str, Any],
        log_entries: List[Dict[str, Any]],
        server_stats: Optional[Dict[str, Any]],
        git_info: Optional[Dict[str, Any]],
    ) -> str:
        prompt = f"""Analyze this incident:

INCIDENT DETAILS:
- Category: {incident_data.get('category', 'unknown')}
- Severity: {incident_data.get('severity', 'unknown')}
- Status: {incident_data.get('status', 'unknown')}
- Error Signature: {incident_data.get('error_signature', 'none')}
- Affected Component: {incident_data.get('affected_component', 'unknown')}
- First Seen: {incident_data.get('first_seen', 'unknown')}
- Occurrence Count: {incident_data.get('occurrence_count', 1)}

"""

        if log_entries:
            recent_logs = log_entries[:20]
            log_text = "\n".join([
                f"[{log.get('level', 'info')}] {log.get('message', '')}"
                for log in recent_logs
            ])
            prompt += f"""RECENT LOGS:
{log_text}

"""

        if server_stats:
            prompt += f"""SERVER STATS:
- CPU: {server_stats.get('cpu_percent', 'unknown')}%
- Memory: {server_stats.get('memory_percent', 'unknown')}%
- Disk: {server_stats.get('disk_percent', 'unknown')}%
- Load: {server_stats.get('load_average', 'unknown')}

"""

        if git_info:
            prompt += f"""GIT INFO:
- Branch: {git_info.get('branch', 'unknown')}
- Latest Commit: {git_info.get('latest_commit', 'unknown')}
- Has Uncommitted Changes: {git_info.get('has_uncommitted_changes', False)}

"""

        prompt += """Provide your diagnosis in the required JSON format."""

        return prompt

    def _validate_diagnosis(self, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize AI diagnosis response."""
        required_fields = [
            "severity", "category", "root_cause", "evidence",
            "affected_component", "confidence", "proposed_fix",
            "risk_level", "requires_human_approval"
        ]

        for field in required_fields:
            if field not in diagnosis:
                diagnosis[field] = self._get_default_value(field)

        valid_severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        if diagnosis["severity"] not in valid_severities:
            diagnosis["severity"] = "MEDIUM"

        if not isinstance(diagnosis["confidence"], (int, float)):
            diagnosis["confidence"] = 0.5
        else:
            diagnosis["confidence"] = max(0.0, min(1.0, diagnosis["confidence"]))

        if not isinstance(diagnosis["evidence"], list):
            diagnosis["evidence"] = [str(diagnosis["evidence"])]

        if not isinstance(diagnosis["files_affected"], list):
            diagnosis["files_affected"] = []

        if not isinstance(diagnosis["commands_required"], list):
            diagnosis["commands_required"] = []

        if not isinstance(diagnosis["verification_plan"], list):
            diagnosis["verification_plan"] = []

        return diagnosis

    def _get_default_value(self, field: str) -> Any:
        defaults = {
            "severity": "MEDIUM",
            "category": "UNKNOWN",
            "root_cause": "Unable to determine root cause",
            "evidence": [],
            "affected_component": "unknown",
            "confidence": 0.3,
            "proposed_fix": "Manual investigation required",
            "files_affected": [],
            "commands_required": [],
            "risk_level": "MEDIUM",
            "rollback_plan": "No automated rollback available",
            "verification_plan": [],
            "requires_human_approval": True,
        }
        return defaults.get(field, None)

    def _fallback_diagnosis(
        self,
        incident_data: Dict[str, Any],
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Provide fallback diagnosis when AI is unavailable."""
        return {
            "severity": incident_data.get("severity", "MEDIUM"),
            "category": incident_data.get("category", "UNKNOWN"),
            "root_cause": f"AI diagnosis unavailable. Manual investigation required. {error or ''}",
            "evidence": ["AI service unavailable or returned error"],
            "affected_component": incident_data.get("affected_component", "unknown"),
            "confidence": 0.1,
            "proposed_fix": "Manual investigation required. Check logs and server status.",
            "files_affected": [],
            "commands_required": [],
            "risk_level": "MEDIUM",
            "rollback_plan": "No automated rollback available",
            "verification_plan": ["Check application health", "Review logs"],
            "requires_human_approval": True,
            "ai_unavailable": True,
        }


ai_service = AIService()
