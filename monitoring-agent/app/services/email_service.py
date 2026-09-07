import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.config import get_settings

settings = get_settings()


class EmailService:
    """Service for email notifications."""

    def __init__(self):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_user
        self.smtp_password = settings.smtp_password
        self.smtp_from = settings.smtp_from
        self.enabled = settings.email_enabled

    async def send_email(
        self,
        to: List[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an email notification."""
        if not self.enabled or not self.smtp_host:
            return {"success": False, "error": "Email not configured"}

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_from
            msg["To"] = ", ".join(to)

            if text_content:
                msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_port == 587:
                    server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_from, to, msg.as_string())

            return {"success": True, "recipients": to}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_incident_alert(
        self,
        to: List[str],
        incident_id: str,
        severity: str,
        category: str,
        affected_component: str,
        error_signature: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send incident alert email."""
        severity_color = {
            "CRITICAL": "#dc3545",
            "HIGH": "#fd7e14",
            "MEDIUM": "#ffc107",
            "LOW": "#28a745",
        }.get(severity, "#6c757d")

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: {severity_color}; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .content {{ background-color: #f8f9fa; padding: 20px; border: 1px solid #ddd; }}
        .footer {{ background-color: #343a40; color: white; padding: 10px; text-align: center; border-radius: 0 0 5px 5px; font-size: 12px; }}
        .label {{ font-weight: bold; color: #495057; }}
        .value {{ color: #212529; }}
        .error-box {{ background-color: #fff; border: 1px solid #dee2e6; padding: 10px; margin-top: 10px; border-radius: 3px; font-family: monospace; font-size: 12px; word-break: break-all; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🚨 Incident Alert</h2>
        </div>
        <div class="content">
            <p><span class="label">Incident ID:</span> <span class="value">{incident_id}</span></p>
            <p><span class="label">Severity:</span> <span class="value" style="color: {severity_color}; font-weight: bold;">{severity}</span></p>
            <p><span class="label">Category:</span> <span class="value">{category}</span></p>
            <p><span class="label">Component:</span> <span class="value">{affected_component}</span></p>
            <p><span class="label">Time:</span> <span class="value">{datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}</span></p>
            {"<p><span class='label'>Error:</span></p><div class='error-box'>" + error_signature[:500] + "</div>" if error_signature else ""}
        </div>
        <div class="footer">
            <p>Project Monitor - Automated Incident Alert</p>
        </div>
    </div>
</body>
</html>
"""
        text_content = f"""
INCIDENT ALERT

Incident ID: {incident_id}
Severity: {severity}
Category: {category}
Component: {affected_component}
Time: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}
{chr(10) + "Error: " + error_signature[:200] if error_signature else ""}
"""
        return await self.send_email(to, f"[{severity}] Incident Alert - {incident_id}", html_content, text_content)

    async def send_daily_report(
        self,
        to: List[str],
        client_name: str,
        report_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send daily monitoring report."""
        summary = report_data.get("summary", {})

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .content {{ background-color: #f8f9fa; padding: 20px; border: 1px solid #ddd; }}
        .footer {{ background-color: #343a40; color: white; padding: 10px; text-align: center; border-radius: 0 0 5px 5px; font-size: 12px; }}
        .metric {{ display: inline-block; width: 45%; margin: 5px; padding: 15px; background: white; border-radius: 5px; text-align: center; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #007bff; }}
        .metric-label {{ font-size: 12px; color: #6c757d; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>📊 Daily Monitoring Report</h2>
            <p>{client_name}</p>
        </div>
        <div class="content">
            <div class="metric">
                <div class="metric-value">{summary.get('total_projects', 0)}</div>
                <div class="metric-label">Total Projects</div>
            </div>
            <div class="metric">
                <div class="metric-value">{summary.get('avg_uptime', 99.9)}%</div>
                <div class="metric-label">Avg Uptime</div>
            </div>
            <div class="metric">
                <div class="metric-value">{summary.get('total_incidents', 0)}</div>
                <div class="metric-label">Incidents</div>
            </div>
            <div class="metric">
                <div class="metric-value">{summary.get('resolved_incidents', 0)}</div>
                <div class="metric-label">Resolved</div>
            </div>
        </div>
        <div class="footer">
            <p>Project Monitor - Daily Report</p>
        </div>
    </div>
</body>
</html>
"""
        return await self.send_email(
            to,
            f"Daily Monitoring Report - {client_name} - {datetime.utcnow().strftime('%Y-%m-%d')}",
            html_content,
        )


email_service = EmailService()
