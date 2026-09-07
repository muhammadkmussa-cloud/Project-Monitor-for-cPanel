from pathlib import Path
from app.config import get_settings
from app.db import fetch_one


class RetentionService:
    async def cleanup_old_data(self):
        raise NotImplementedError("Data deletion is not enabled")

    async def get_retention_stats(self):
        tables = {}
        for table, timestamp in (("monitoring_checks", "checked_at"), ("incidents", "created_at"),
                                 ("notifications", "created_at"), ("audit_logs", "created_at")):
            row = await fetch_one(f"SELECT COUNT(*) AS count, MIN({timestamp}) AS oldest FROM {table}")
            tables[table] = {"row_count": row["count"], "oldest_record": row["oldest"]}
        return {"retention_days": get_settings().data_retention_days, "cleanup_enabled": False,
                "archive_enabled": False, "table_stats": tables, "last_cleanup": None, "next_cleanup": None}

    async def get_storage_usage(self):
        row = await fetch_one("SELECT pg_database_size(current_database()) AS bytes")
        root = Path(get_settings().local_backup_path)
        files = [p for p in root.rglob("*") if p.is_file()] if root.exists() else []
        return {"database": {"total_size_mb": round(row["bytes"] / 1048576, 2)},
                "backups": {"total_size_mb": round(sum(p.stat().st_size for p in files) / 1048576, 2),
                            "count": len(list(root.glob("*/manifest.json")))}}


retention_service = RetentionService()
