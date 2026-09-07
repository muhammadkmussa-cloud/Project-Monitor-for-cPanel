import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.config import get_settings

settings = get_settings()


class SlackService:
    """Service for Slack notifications."""

    def __init__(self):
        self.webhook_url = settings.slack_webhook_url
        self.bot_token = settings.slack_bot_token
        self.enabled = settings.slack_enabled

    async def send_message(
        self,
        text: str,
        channel: Optional[str] = None,
        blocks: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Send a message via Slack webhook."""
        if not self.enabled or not self.webhook_url:
            return {"success": False, "error": "Slack not configured"}

        try:
            payload = {"text": text}
            if blocks:
                payload["blocks"] = blocks

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                )

                if response.status_code == 200:
                    return {"success": True}
                else:
                    return {"success": False, "error": response.text}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_incident_alert(
        self,
        incident_id: str,
        severity: str,
        category: str,
        affected_component: str,
        error_signature: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send incident alert to Slack."""
        severity_emoji = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🟢",
        }.get(severity, "⚪")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_emoji} Incident Alert",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Incident ID:*\n`{incident_id}`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Category:*\n{category}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Component:*\n{affected_component}",
                    },
                ],
            },
        ]

        if error_signature:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Error:*\n```{error_signature[:300]}```",
                    },
                }
            )

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    }
                ],
            }
        )

        return await self.send_message(
            text=f"{severity_emoji} {severity} Incident: {incident_id}",
            blocks=blocks,
        )

    async def send_approval_request(
        self,
        incident_id: str,
        diagnosis: Dict[str, Any],
        fix_description: str,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send approval request to Slack."""
        severity = diagnosis.get("severity", "MEDIUM")
        confidence = diagnosis.get("confidence", 0)
        risk_level = diagnosis.get("risk_level", "MEDIUM")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔧 Fix Approval Request",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Incident:*\n`{incident_id}`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Confidence:*\n{confidence:.0%}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Risk Level:*\n{risk_level}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Proposed Fix:*\n{fix_description}",
                },
            },
        ]

        return await self.send_message(
            text=f"Approval Request for Incident: {incident_id}",
            blocks=blocks,
        )

    async def send_fix_result(
        self,
        incident_id: str,
        success: bool,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send fix execution result to Slack."""
        status_emoji = "✅" if success else "❌"
        status_text = "SUCCESS" if success else "FAILED"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} Fix {status_text}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Incident:*\n`{incident_id}`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{status_text}",
                    },
                ],
            },
        ]

        if not success:
            error = result.get("error", "Unknown error")
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Error:*\n```{error[:300]}```",
                    },
                }
            )

        return await self.send_message(
            text=f"{status_emoji} Fix {status_text} for Incident: {incident_id}",
            blocks=blocks,
        )

    async def send_daily_report(
        self,
        client_name: str,
        report_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send daily monitoring report to Slack."""
        summary = report_data.get("summary", {})

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 Daily Monitoring Report",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Client:* {client_name}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Projects:*\n{summary.get('total_projects', 0)}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Uptime:*\n{summary.get('avg_uptime', 99.9)}%",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Incidents:*\n{summary.get('total_incidents', 0)}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Resolved:*\n{summary.get('resolved_incidents', 0)}",
                    },
                ],
            },
        ]

        return await self.send_message(
            text=f"Daily Report for {client_name}",
            blocks=blocks,
        )


slack_service = SlackService()
