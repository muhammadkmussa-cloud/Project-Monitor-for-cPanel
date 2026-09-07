from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import base64
import io
import json


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else datetime.utcnow()


class ReportService:
    """Service for generating monitoring reports."""

    async def generate_incident_report(
        self,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate incident report."""
        from app.db import fetch_all, fetch_one

        sd = start_date or (datetime.utcnow() - timedelta(days=30)).isoformat()
        ed = end_date or datetime.utcnow().isoformat()

        conditions = ["created_at >= $1::timestamptz", "created_at <= $2::timestamptz"]
        params: list = [_parse_dt(sd), _parse_dt(ed)]
        idx = 3
        if project_id:
            conditions.append(f"project_id = ${idx}")
            params.append(project_id)
            idx += 1
        if client_id:
            conditions.append(f"client_id = ${idx}")
            params.append(client_id)
            idx += 1

        where = "WHERE " + " AND ".join(conditions)

        total = await fetch_one(f"SELECT COUNT(*) as cnt FROM incidents {where}", *params)
        by_sev = {}
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            row = await fetch_one(f"SELECT COUNT(*) as cnt FROM incidents {where} AND severity = ${idx}", *params, sev)
            by_sev[sev] = row["cnt"] if row else 0

        by_cat = {}
        cat_rows = await fetch_all(f"SELECT category, COUNT(*) as cnt FROM incidents {where} GROUP BY category", *params)
        for r in cat_rows:
            by_cat[r["category"]] = r["cnt"]

        resolved = await fetch_one(f"SELECT COUNT(*) as cnt FROM incidents {where} AND status = 'RESOLVED'", *params)
        open_c = await fetch_one(f"SELECT COUNT(*) as cnt FROM incidents {where} AND status IN ('OPEN', 'INVESTIGATING')", *params)

        return {
            "report_type": "incident",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {"start": sd, "end": ed},
            "summary": {
                "total_incidents": total["cnt"] if total else 0,
                "by_severity": by_sev,
                "by_category": by_cat,
                "avg_resolution_time_minutes": 0,
                "resolved_count": resolved["cnt"] if resolved else 0,
                "open_count": open_c["cnt"] if open_c else 0,
            },
            "incidents": [],
            "trends": {"daily": [], "weekly": []},
        }

    async def generate_uptime_report(
        self,
        project_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate uptime report for a project."""
        from app.db import fetch_one

        sd = start_date or (datetime.utcnow() - timedelta(days=30)).isoformat()
        ed = end_date or datetime.utcnow().isoformat()

        total = await fetch_one(
            "SELECT COUNT(*) as cnt FROM monitoring_checks WHERE project_id = $1 AND checked_at >= $2::timestamptz AND checked_at <= $3::timestamptz",
            project_id, _parse_dt(sd), _parse_dt(ed),
        )
        successful = await fetch_one(
            "SELECT COUNT(*) as cnt FROM monitoring_checks WHERE project_id = $1 AND checked_at >= $2::timestamptz AND checked_at <= $3::timestamptz AND status = 'HEALTHY'",
            project_id, _parse_dt(sd), _parse_dt(ed),
        )

        t = total["cnt"] if total else 0
        s = successful["cnt"] if successful else 0
        uptime = round((s / t * 100), 1) if t > 0 else None

        return {
            "report_type": "uptime",
            "project_id": project_id,
            "generated_at": datetime.utcnow().isoformat(),
            "period": {"start": sd, "end": ed},
            "summary": {
                "uptime_percent": uptime,
                "total_downtime_minutes": round((t - s) * 5, 0),
                "longest_outage_minutes": 0,
                "total_checks": t,
                "successful_checks": s,
                "failed_checks": t - s,
            },
            "daily_uptime": [],
            "incidents_causing_downtime": [],
        }

    async def generate_performance_report(
        self,
        project_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate performance report for a project."""
        from app.db import fetch_one

        sd = start_date or (datetime.utcnow() - timedelta(days=7)).isoformat()
        ed = end_date or datetime.utcnow().isoformat()

        cpu = await fetch_one(
            "SELECT AVG(cpu_usage_percent) as avg, AVG(memory_usage_percent) as mem_avg, AVG(disk_usage_percent) as disk_avg, AVG(response_time_ms) as rt_avg FROM monitoring_checks WHERE project_id = $1 AND checked_at >= $2::timestamptz",
            project_id, _parse_dt(sd),
        )

        def _v(key):
            return round(float(cpu[key] or 0), 1) if cpu else 0

        return {
            "report_type": "performance",
            "project_id": project_id,
            "generated_at": datetime.utcnow().isoformat(),
            "period": {"start": sd, "end": ed},
            "summary": {
                "avg_response_time_ms": _v("rt_avg"),
                "p95_response_time_ms": 0,
                "p99_response_time_ms": 0,
                "avg_cpu_percent": _v("avg"),
                "avg_memory_percent": _v("mem_avg"),
                "avg_disk_percent": _v("disk_avg"),
            },
            "response_time": {"daily_avg": [], "hourly_avg": [0] * 24},
            "resources": {"cpu_trend": [], "memory_trend": [], "disk_trend": []},
        }

    async def generate_remediation_report(
        self,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate remediation activity report."""
        from app.db import fetch_all, fetch_one

        sd = start_date or (datetime.utcnow() - timedelta(days=30)).isoformat()
        ed = end_date or datetime.utcnow().isoformat()

        conditions = ["r.created_at >= $1::timestamptz"]
        params: list = [_parse_dt(sd)]
        idx = 2
        if project_id:
            conditions.append(f"r.project_id = ${idx}")
            params.append(project_id)
            idx += 1
        if client_id:
            conditions.append(f"i.client_id = ${idx}")
            params.append(client_id)
            idx += 1

        where = "WHERE " + " AND ".join(conditions)
        join = "FROM remediation_runs r JOIN incidents i ON r.incident_id = i.incident_id"

        total = await fetch_one(f"SELECT COUNT(*) as cnt {join} {where}", *params)
        successful = await fetch_one(f"SELECT COUNT(*) as cnt {join} {where} AND r.status = 'COMPLETED'", *params)
        failed = await fetch_one(f"SELECT COUNT(*) as cnt {join} {where} AND r.status = 'FAILED'", *params)
        rolled = await fetch_one(f"SELECT COUNT(*) as cnt {join} {where} AND r.status = 'ROLLED_BACK'", *params)

        t = total["cnt"] if total else 0
        s = successful["cnt"] if successful else 0

        return {
            "report_type": "remediation",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {"start": sd, "end": ed},
            "summary": {
                "total_attempts": t,
                "successful": s,
                "failed": failed["cnt"] if failed else 0,
                "rolled_back": rolled["cnt"] if rolled else 0,
                "success_rate_percent": round((s / t * 100), 1) if t > 0 else 0,
            },
            "by_safety_level": {"safe": {"total": 0, "success": 0}, "moderate": {"total": 0, "success": 0}, "risky": {"total": 0, "success": 0}, "dangerous": {"total": 0, "success": 0}},
            "top_fixes": [],
            "timeline": [],
        }

    async def generate_executive_summary(
        self,
        client_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Generate executive summary report."""
        from app.db import fetch_one

        sd = (datetime.utcnow() - timedelta(days=days)).isoformat()

        total_p = await fetch_one("SELECT COUNT(*) as cnt FROM projects WHERE client_id = $1", client_id)
        total_i = await fetch_one("SELECT COUNT(*) as cnt FROM incidents WHERE client_id = $1 AND created_at >= $2::timestamptz", client_id, _parse_dt(sd))
        open_i = await fetch_one("SELECT COUNT(*) as cnt FROM incidents WHERE client_id = $1 AND status IN ('OPEN', 'INVESTIGATING')", client_id)
        resolved = await fetch_one("SELECT COUNT(*) as cnt FROM incidents WHERE client_id = $1 AND status = 'RESOLVED' AND created_at >= $2::timestamptz", client_id, _parse_dt(sd))
        automated = await fetch_one(
            "SELECT COUNT(*) as cnt FROM remediation_runs r JOIN incidents i ON r.incident_id = i.incident_id WHERE i.client_id = $1 AND r.status = 'COMPLETED'",
            client_id,
        )

        t_i = total_i["cnt"] if total_i else 0
        a_f = automated["cnt"] if automated else 0
        savings = a_f * 75 + a_f * 125

        return {
            "report_type": "executive_summary",
            "client_id": client_id,
            "generated_at": datetime.utcnow().isoformat(),
            "period_days": days,
            "highlights": {
                "uptime_percent": None,
                "total_incidents": t_i,
                "automated_fixes": a_f,
                "estimated_savings_usd": savings,
            },
            "key_metrics": {
                "mttr_minutes": 0,
                "incidents_per_project": round(t_i / max(total_p["cnt"] if total_p else 1, 1), 1),
                "automation_rate_percent": round((a_f / max(t_i, 1)) * 100, 0),
            },
            "project_status": [],
            "recommendations": [],
        }

    async def export_report(
        self,
        report_data: Dict[str, Any],
        format: str = "json",
    ) -> Dict[str, Any]:
        """Export report in specified format."""
        if format == "json":
            return {
                "success": True,
                "format": "json",
                "data": report_data,
                "filename": f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
            }
        elif format == "csv":
            return {
                "success": True,
                "format": "csv",
                "data": self._convert_to_csv(report_data),
                "filename": f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
            }
        elif format == "pdf":
            return {
                "success": True,
                "format": "pdf",
                "data": self._convert_to_pdf_base64(report_data),
                "filename": f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf",
            }
        else:
            return {"success": False, "error": f"Unsupported format: {format}"}

    def _convert_to_csv(self, data: Dict[str, Any]) -> str:
        lines = []
        lines.append(f"Report Type: {data.get('report_type', 'unknown')}")
        lines.append(f"Generated At: {data.get('generated_at', '')}")
        lines.append("")
        summary = data.get("summary", {})
        if summary:
            lines.append("Summary")
            for key, value in summary.items():
                lines.append(f"{key},{value}")
        return "\n".join(lines)

    def _convert_to_pdf_base64(self, data: Dict[str, Any]) -> str:
        """Render a simple PDF from report data and return it base64-encoded."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib import colors
        except Exception as exc:  # pragma: no cover
            return f"PDF generation failed: {exc}"

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
        styles = getSampleStyleSheet()
        h1 = styles["Title"]
        h2 = styles["Heading2"]
        normal = ParagraphStyle("normal", parent=styles["BodyText"], fontSize=9, leading=12)

        story = [Paragraph(f"{data.get('report_type', 'report').replace('_', ' ').title()} Report", h1)]
        story.append(Paragraph(f"Generated: {data.get('generated_at', '')}", styles["Normal"]))
        story.append(Spacer(1, 6 * mm))

        summary = data.get("summary", {})
        if isinstance(summary, dict):
            story.append(Paragraph("Summary", h2))
            rows = [["Metric", "Value"]]
            for key, value in summary.items():
                rows.append([key.replace("_", " ").title(), str(value)])
            table = Table(rows, colWidths=[80 * mm, 100 * mm])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            story.append(table)
            story.append(Spacer(1, 4 * mm))

        for key in ("highlights", "key_metrics", "project_status"):
            section = data.get(key)
            if isinstance(section, dict) and section:
                story.append(Paragraph(key.replace("_", " ").title(), h2))
                for k, v in section.items():
                    story.append(Paragraph(f"<b>{k.replace('_', ' ').title()}:</b> {v}", normal))
                story.append(Spacer(1, 3 * mm))

        doc.build(story)
        encoded = base64.b64encode(buf.getvalue()).decode()
        return encoded


report_service = ReportService()
