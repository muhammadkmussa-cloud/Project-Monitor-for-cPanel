import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.config import get_settings

settings = get_settings()


class TelegramPollingConflict(RuntimeError):
    pass


class TelegramService:
    """Service for Telegram notifications and approval flow."""

    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.enabled = settings.telegram_enabled

    async def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Send a message via Telegram."""
        from app.services.settings_service import read_setting
        enabled = await read_setting("notifications.telegram_enabled", True)
        if enabled in (False, "false", "False") or not self.enabled or not self.bot_token:
            return {"success": False, "error": "Telegram not configured"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                if reply_markup:
                    payload["reply_markup"] = reply_markup

                response = await client.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json=payload,
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def bot_call(self, method, payload):
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(f"https://api.telegram.org/bot{self.bot_token}/{method}", json=payload)
            data = response.json()
            if method == "getUpdates" and response.status_code == 409:
                raise TelegramPollingConflict("Another Telegram consumer is active")
            if not data.get("ok"):
                raise RuntimeError("Telegram request failed: " + method)
            return data["result"]

    async def send_review(self, review_id, document):
        import json
        from app.services.settings_service import read_setting
        if not self.enabled or not self.bot_token or await read_setting("notifications.telegram_enabled", True) in (False,"false","False"):
            return {"success": False}
        project = document['project']
        # Full attachment makes every command and metadata field reviewable even
        # when the plan exceeds Telegram's message size limit.
        blob = json.dumps(document, indent=2, ensure_ascii=False, default=str).encode()
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(f"https://api.telegram.org/bot{self.bot_token}/sendDocument",
                data={"chat_id": self.chat_id, "caption": "Complete review: project metadata, exact proposed steps, evidence and rollback. Credentials are redacted."},
                files={"document": ("fix-review-"+review_id+".json", blob, "application/json")})
            if not response.json().get('ok'):
                return {"success": False}
        def short(value, size=650):
            text = str(value or 'Not available')
            return text if len(text)<=size else text[:size]+'… (full details in attachment)'
        text = (f"FIX REVIEW — {short(project.get('project_name'),150)}\n"
                f"Client: {short(document.get('client_name'),100)}\n"
                f"Project ID: {project['project_id']}\n"
                f"Domain: {short(project.get('domain'),180)}\n"
                f"Environment: {project.get('environment')} | App: {project.get('application_type')} / {project.get('framework')}\n"
                f"Server: {short(project.get('server_host'),120)} | Path: {short(project.get('project_path'),150)}\n"
                f"Incident: {document['incident']['incident_id']}\n"
                f"Error: {short(document['incident'].get('error_signature'),180)}\n"
                f"Severity: {document['incident']['severity']} | Risk: {document['risk']} | Confidence: {document['confidence']}\n\n"
                f"WHY: {short(document['root_cause'],400)}\n\n"
                f"PROPOSED FIX: {short(document['fix_explanation'],650)}\n\n"
                f"ROLLBACK: {short(document['rollback'],350)}\n"
                f"Expires: {document['expires_at']}\n\n"
                + ("Approve queues the exact attached steps for execution, subject to safety checks. Reject prevents execution."
                   if document['executable'] else "MANUAL REVIEW REQUIRED: no safe executable plan is available or project remediation is disabled. Approve records your review only; it will not run commands.")
                + "\nRead the attached full steps before deciding.")
        result = await self.send_message(text, parse_mode=None, reply_markup={"inline_keyboard":[[
            {"text":"✅ Approve", "callback_data":"pm:a:"+review_id},
            {"text":"❌ Reject", "callback_data":"pm:r:"+review_id}]]})
        if result.get('success'):
            return {"success": True, "message_id":result['data']['result']['message_id']}
        return result

    async def send_incident_alert(
        self,
        incident_id: str,
        severity: str,
        category: str,
        affected_component: str,
        error_signature: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send incident alert notification."""
        severity_emoji = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🟢",
        }.get(severity, "⚪")

        text = f"""{severity_emoji} <b>INCIDENT ALERT</b>

<b>ID:</b> <code>{incident_id}</code>
<b>Severity:</b> {severity}
<b>Category:</b> {category}
<b>Component:</b> {affected_component}
<b>Time:</b> {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}"""

        if error_signature:
            text += f"\n<b>Error:</b> <code>{error_signature[:200]}</code>"

        return await self.send_message(text)

    async def send_approval_request(
        self,
        incident_id: str,
        diagnosis: Dict[str, Any],
        fix_description: str,
    ) -> Dict[str, Any]:
        """Send approval request for proposed fix."""
        severity = diagnosis.get("severity", "MEDIUM")
        confidence = diagnosis.get("confidence", 0)
        risk_level = diagnosis.get("risk_level", "MEDIUM")

        risk_emoji = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🟢",
        }.get(risk_level, "⚪")

        text = f"""🔧 <b>FIX APPROVAL REQUEST</b>

<b>Incident:</b> <code>{incident_id}</code>
<b>Severity:</b> {severity}
<b>Confidence:</b> {confidence:.0%}
<b>Risk Level:</b> {risk_emoji} {risk_level}

<b>Proposed Fix:</b>
{fix_description}

<b>Root Cause:</b>
{diagnosis.get('root_cause', 'Unknown')}

<b>Rollback Plan:</b>
{diagnosis.get('rollback_plan', 'No rollback plan')}"""

        approve_callback = f"approve_{incident_id}"
        reject_callback = f"reject_{incident_id}"
        manual_callback = f"manual_{incident_id}"

        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Approve",
                        "callback_data": approve_callback,
                    },
                    {
                        "text": "❌ Reject",
                        "callback_data": reject_callback,
                    },
                ],
                [
                    {
                        "text": "🧑‍💻 Manual Review",
                        "callback_data": manual_callback,
                    }
                ],
            ]
        }

        return await self.send_message(text, reply_markup=reply_markup)

    async def send_fix_result(
        self,
        incident_id: str,
        success: bool,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send fix execution result notification."""
        status_emoji = "✅" if success else "❌"
        status_text = "SUCCESS" if success else "FAILED"

        text = f"""{status_emoji} <b>FIX {status_text}</b>

<b>Incident:</b> <code>{incident_id}</code>
<b>Status:</b> {status_text}
<b>Time:</b> {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}"""

        if not success:
            error = result.get("error", "Unknown error")
            text += f"\n<b>Error:</b> <code>{error[:200]}</code>"

        return await self.send_message(text)

    async def send_rollback_notification(
        self,
        incident_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Send rollback notification."""
        text = f"""🔄 <b>ROLLBACK TRIGGERED</b>

<b>Incident:</b> <code>{incident_id}</code>
<b>Reason:</b> {reason}
<b>Time:</b> {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}"""

        return await self.send_message(text)

    async def handle_callback_query(
        self,
        callback_data: str,
        incident_id: str,
    ) -> Dict[str, Any]:
        """Handle Telegram callback query (approve/reject)."""
        action = callback_data.split("_")[0]

        if action == "approve":
            return {"action": "approve", "incident_id": incident_id}
        elif action == "reject":
            return {"action": "reject", "incident_id": incident_id}
        elif action == "manual":
            return {"action": "manual", "incident_id": incident_id}
        else:
            return {"action": "unknown", "incident_id": incident_id}


telegram_service = TelegramService()
