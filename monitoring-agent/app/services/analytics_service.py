from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta


class AnalyticsService:
    """Service for historical analytics and trend analysis."""

    async def get_dashboard_summary(
        self,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get dashboard summary data from PostgreSQL."""
        from app.db import fetch_one, fetch_all

        client_filter = ""
        params = []
        if client_id:
            client_filter = "WHERE client_id = $1"
            params.append(client_id)

        total_projects = await fetch_one(f"SELECT COUNT(*) as cnt FROM projects {client_filter}", *params)
        open_incidents = await fetch_one(
            f"SELECT COUNT(*) as cnt FROM incidents WHERE status IN ('OPEN', 'INVESTIGATING', 'AWAITING_APPROVAL') {('AND client_id = $1' if client_id else '')}",
            *(params if client_id else []),
        )
        today_incidents = await fetch_one(
            f"SELECT COUNT(*) as cnt FROM incidents WHERE created_at >= CURRENT_DATE {'AND client_id=$1' if client_id else ''}", *params,
        )
        resolved_today = await fetch_one(
            f"SELECT COUNT(*) as cnt FROM incidents WHERE status='RESOLVED' AND resolved_at>=CURRENT_DATE {'AND client_id=$1' if client_id else ''}", *params)
        today_checks = await fetch_one(
            f"SELECT COUNT(*) as cnt FROM monitoring_checks WHERE checked_at >= CURRENT_DATE {'AND client_id=$1' if client_id else ''}", *params,
        )
        successful_today = await fetch_one(
            f"SELECT COUNT(*) as cnt FROM monitoring_checks WHERE checked_at >= CURRENT_DATE AND status = 'HEALTHY' {'AND client_id=$1' if client_id else ''}", *params,
        )

        total_p = total_projects["cnt"] if total_projects else 0
        open_i = open_incidents["cnt"] if open_incidents else 0
        today_i = today_incidents["cnt"] if today_incidents else 0
        today_c = today_checks["cnt"] if today_checks else 0
        succ_c = successful_today["cnt"] if successful_today else 0

        uptime = round((succ_c / today_c * 100), 1) if today_c > 0 else None

        system_health = {}
        for component in ["monitoring-agent", "postgres", "redis", "n8n"]:
            row = await fetch_one(
                "SELECT status FROM system_health WHERE component = $1 ORDER BY checked_at DESC LIMIT 1",
                component,
            )
            system_health[component] = row["status"] if row else "unknown"

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "overview": {
                "total_projects": total_p,
                "active_projects": total_p,
                "total_incidents_today": today_i,
                "resolved_incidents_today": resolved_today["cnt"] if resolved_today else 0,
                "open_incidents": open_i,
                "avg_uptime_percent": uptime,
                "total_health_checks_today": today_c,
            },
            "recent_incidents": [],
            "upcoming_maintenance": [],
            "system_health": system_health,
            "alerts": [],
        }

    async def get_incident_trends(
        self,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get incident trends over time."""
        from app.db import fetch_all, fetch_one

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        conditions = ["created_at >= $1"]
        params: list = [start_date]
        idx = 2
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

        by_severity = {}
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            row = await fetch_one(
                f"SELECT COUNT(*) as cnt FROM incidents {where} AND severity = ${idx}",
                *params, sev,
            )
            by_severity[sev] = row["cnt"] if row else 0

        by_category = {}
        cat_rows = await fetch_all(
            f"SELECT category, COUNT(*) as cnt FROM incidents {where} GROUP BY category ORDER BY cnt DESC",
            *params,
        )
        for r in cat_rows:
            by_category[r["category"]] = r["cnt"]

        daily_rows = await fetch_all(
            f"SELECT DATE(created_at) as day, COUNT(*) as cnt FROM incidents {where} GROUP BY DATE(created_at) ORDER BY day",
            *params,
        )
        daily_trend = [{"date": str(r["day"]), "count": r["cnt"]} for r in daily_rows]

        top_components = await fetch_all(
            f"SELECT affected_component, COUNT(*) as cnt FROM incidents {where} AND affected_component IS NOT NULL GROUP BY affected_component ORDER BY cnt DESC LIMIT 5",
            *params,
        )

        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat(), "days": days},
            "summary": {
                "total_incidents": total["cnt"] if total else 0,
                "avg_daily": round((total["cnt"] if total else 0) / max(days, 1), 1),
                "peak_day": daily_trend[-1]["date"] if daily_trend else None,
                "peak_count": max((d["count"] for d in daily_trend), default=0),
            },
            "by_severity": by_severity,
            "by_category": by_category,
            "daily_trend": daily_trend,
            "hourly_distribution": [0] * 24,
            "mttr_minutes": 0,
            "top_affected_components": [{"component": r["affected_component"], "count": r["cnt"]} for r in top_components],
        }

    async def get_health_trends(
        self,
        project_id: str,
        days: int = 7,
    ) -> Dict[str, Any]:
        """Get health check trends for a project."""
        from app.db import fetch_all, fetch_one

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        total = await fetch_one(
            "SELECT COUNT(*) as cnt FROM monitoring_checks WHERE project_id = $1 AND checked_at >= $2",
            project_id, start_date,
        )
        successful = await fetch_one(
            "SELECT COUNT(*) as cnt FROM monitoring_checks WHERE project_id = $1 AND checked_at >= $2 AND status = 'HEALTHY'",
            project_id, start_date,
        )
        avg_resp = await fetch_one(
            "SELECT AVG(response_time_ms) as avg_rt FROM monitoring_checks WHERE project_id = $1 AND checked_at >= $2 AND response_time_ms IS NOT NULL",
            project_id, start_date,
        )

        total_c = total["cnt"] if total else 0
        succ_c = successful["cnt"] if successful else 0
        uptime = round((succ_c / total_c * 100), 1) if total_c > 0 else None

        daily = await fetch_all(
            """SELECT DATE(checked_at) AS day, AVG(response_time_ms) AS response_time_ms,
               100.0 * COUNT(*) FILTER (WHERE status='HEALTHY') / COUNT(*) AS healthy_percent
               FROM monitoring_checks WHERE project_id=$1 AND checked_at >= $2
               GROUP BY DATE(checked_at) ORDER BY day""", project_id, start_date)
        percentiles = await fetch_one(
            """SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY response_time_ms) AS p95,
                      percentile_cont(0.99) WITHIN GROUP (ORDER BY response_time_ms) AS p99
               FROM monitoring_checks WHERE project_id=$1 AND checked_at >= $2""", project_id, start_date)
        return {
            "project_id": project_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat(), "days": days},
            "uptime_percent": uptime,
            "avg_response_time_ms": round(float(avg_resp["avg_rt"] or 0), 0),
            "p95_response_time_ms": percentiles["p95"],
            "p99_response_time_ms": percentiles["p99"],
            "total_checks": total_c,
            "successful_checks": succ_c,
            "failed_checks": total_c - succ_c,
            "response_time_trend": [{"date": str(row["day"]), "response_time_ms": float(row["response_time_ms"]) if row["response_time_ms"] is not None else None, "healthy_percent": float(row["healthy_percent"])} for row in daily],
            "availability_by_hour": [],
        }

    async def get_server_performance(
        self,
        project_id: str,
        days: int = 7,
    ) -> Dict[str, Any]:
        """Get server performance trends."""
        from app.db import fetch_one

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        cpu = await fetch_one(
            "SELECT AVG(cpu_usage_percent) as avg, MAX(cpu_usage_percent) as max, MIN(cpu_usage_percent) as min FROM monitoring_checks WHERE project_id = $1 AND checked_at >= $2",
            project_id, start_date,
        )
        mem = await fetch_one(
            "SELECT AVG(memory_usage_percent) as avg, MAX(memory_usage_percent) as max, MIN(memory_usage_percent) as min FROM monitoring_checks WHERE project_id = $1 AND checked_at >= $2",
            project_id, start_date,
        )
        disk = await fetch_one(
            "SELECT AVG(disk_usage_percent) as avg, MAX(disk_usage_percent) as max, MIN(disk_usage_percent) as min FROM monitoring_checks WHERE project_id = $1 AND checked_at >= $2",
            project_id, start_date,
        )

        def _safe(row, key):
            return round(float(row[key] or 0), 1) if row else 0

        return {
            "project_id": project_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat(), "days": days},
            "cpu": {"avg_percent": _safe(cpu, "avg"), "max_percent": _safe(cpu, "max"), "min_percent": _safe(cpu, "min"), "trend": []},
            "memory": {"avg_percent": _safe(mem, "avg"), "max_percent": _safe(mem, "max"), "min_percent": _safe(mem, "min"), "trend": []},
            "disk": {"avg_percent": _safe(disk, "avg"), "max_percent": _safe(disk, "max"), "min_percent": _safe(disk, "min"), "trend": []},
            "network": {"bytes_sent": 0, "bytes_received": 0, "connections": 0},
        }

    async def get_remediation_stats(
        self,
        project_id: Optional[str] = None,
        days: int = 30,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get remediation statistics."""
        from app.db import fetch_one

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        conditions = ["created_at >= $1"]
        params: list = [start_date]
        idx = 2
        if project_id:
            conditions.append(f"project_id = ${idx}")
            params.append(project_id)
            idx += 1

        if client_id:
            conditions.append(f"project_id IN (SELECT project_id FROM projects WHERE client_id=${idx})")
            params.append(client_id)
            idx += 1
        where = "WHERE " + " AND ".join(conditions)

        total = await fetch_one(f"SELECT COUNT(*) as cnt FROM remediation_runs {where}", *params)
        successful = await fetch_one(f"SELECT COUNT(*) as cnt FROM remediation_runs {where} AND status = 'COMPLETED'", *params)
        failed = await fetch_one(f"SELECT COUNT(*) as cnt FROM remediation_runs {where} AND status = 'FAILED'", *params)
        rolled_back = await fetch_one(f"SELECT COUNT(*) as cnt FROM remediation_runs {where} AND status = 'ROLLED_BACK'", *params)

        t = total["cnt"] if total else 0
        s = successful["cnt"] if successful else 0

        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat(), "days": days},
            "total_attempts": t,
            "successful": s,
            "failed": failed["cnt"] if failed else 0,
            "rolled_back": rolled_back["cnt"] if rolled_back else 0,
            "success_rate_percent": round((s / t * 100), 1) if t > 0 else 0,
            "avg_execution_time_seconds": 0,
            "by_safety_level": {"safe": {"total": 0, "success": 0}, "moderate": {"total": 0, "success": 0}, "risky": {"total": 0, "success": 0}, "dangerous": {"total": 0, "success": 0}},
            "top_failure_reasons": [],
        }

    async def get_client_summary(
        self,
        client_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get summary for a client."""
        from app.db import fetch_one

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        total_p = await fetch_one("SELECT COUNT(*) as cnt FROM projects WHERE client_id = $1", client_id)
        total_i = await fetch_one("SELECT COUNT(*) as cnt FROM incidents WHERE client_id = $1 AND created_at >= $2", client_id, start_date)
        open_i = await fetch_one("SELECT COUNT(*) as cnt FROM incidents WHERE client_id = $1 AND status IN ('OPEN', 'INVESTIGATING')", client_id)
        resolved_i = await fetch_one("SELECT COUNT(*) as cnt FROM incidents WHERE client_id = $1 AND status = 'RESOLVED' AND created_at >= $2", client_id, start_date)

        return {
            "client_id": client_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat(), "days": days},
            "total_projects": total_p["cnt"] if total_p else 0,
            "active_projects": total_p["cnt"] if total_p else 0,
            "total_incidents": total_i["cnt"] if total_i else 0,
            "open_incidents": open_i["cnt"] if open_i else 0,
            "resolved_incidents": resolved_i["cnt"] if resolved_i else 0,
            "avg_uptime_percent": None,
            "total_health_checks": 0,
            "successful_checks": 0,
            "cost_savings": {"automated_fixes": 0, "reduced_downtime_hours": 0, "estimated_savings_usd": 0},
        }

    async def get_performance_report(
        self,
        project_id: str,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """Generate performance report for a date range."""
        return {
            "project_id": project_id,
            "period": {"start": start_date, "end": end_date},
            "summary": {"uptime_percent": None, "total_incidents": 0, "avg_response_time_ms": None, "total_health_checks": 0, "successful_checks": 0},
            "daily_breakdown": [],
            "top_incidents": [],
            "recommendations": [],
        }

    async def get_cost_analysis(
        self,
        client_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Analyze cost savings from automation."""
        from app.db import fetch_one

        remediations = await fetch_one(
            "SELECT COUNT(*) as cnt FROM remediation_runs r JOIN incidents i ON r.incident_id = i.incident_id WHERE i.client_id = $1 AND r.status = 'COMPLETED'",
            client_id,
        )
        count = remediations["cnt"] if remediations else 0
        hours_saved = count * 0.5
        savings = hours_saved * 75

        return {
            "client_id": client_id,
            "period_days": days,
            "savings": {
                "automated_remediations": {"count": count, "estimated_hours_saved": hours_saved, "cost_per_hour": 75, "total_saved": savings},
                "reduced_downtime": {"hours_avoided": count * 0.25, "cost_per_hour": 500, "total_saved": count * 0.25 * 500},
                "proactive_monitoring": {"issues_prevented": 0, "estimated_cost_per_issue": 200, "total_saved": 0},
            },
            "total_savings": savings + (count * 0.25 * 500),
            "roi_percent": round(((savings + count * 125) / max(savings, 1)) * 100, 0),
        }


analytics_service = AnalyticsService()
