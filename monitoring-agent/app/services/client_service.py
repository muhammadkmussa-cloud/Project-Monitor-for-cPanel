from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import uuid4
import json

from app.db import fetch_one, fetch_all, execute, execute_returning


class ClientService:
    @staticmethod
    def public_client(row):
        result = dict(row)
        if isinstance(result.get("settings"), str):
            result["settings"] = json.loads(result["settings"])
        return result

    async def create_client(
        self, client_name: str, contact_email: str, company_name: Optional[str] = None,
        phone: Optional[str] = None, address: Optional[str] = None,
        timezone: str = "UTC", plan: str = "starter",
    ) -> Dict[str, Any]:
        settings_data = self._get_default_settings(plan)
        settings_data.update({"plan": plan, "address": address, "timezone": timezone})
        row = await execute_returning(
            """INSERT INTO clients (client_id, client_name, email, company, phone, status, settings)
               VALUES ($1, $2, $3, $4, $5, 'active', $6)
               RETURNING *""",
            uuid4(), client_name, contact_email, company_name, phone, json.dumps(settings_data),
        )
        return self.public_client(row) if row else {}

    async def get_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        try:
            row = await fetch_one("SELECT * FROM clients WHERE client_id = $1", client_id)
            return self.public_client(row) if row else None
        except Exception:
            return None

    async def list_clients(self, status: Optional[str] = None, plan: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        conditions = []
        params = []
        idx = 1
        if status:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        if plan:
            conditions.append(f"COALESCE(settings->>'plan', 'starter') = ${idx}")
            params.append(plan)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await fetch_all(f"SELECT * FROM clients {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}", *params, limit, skip)
        return [self.public_client(r) for r in rows]

    async def update_client(self, client_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        mapping = {"client_name": "client_name", "company_name": "company", "contact_email": "email", "phone": "phone", "status": "status"}
        sets, params = [], []
        extras = {k: v for k, v in kwargs.items() if k in {"address", "timezone", "plan"}}
        for field, value in kwargs.items():
            if field in mapping:
                params.append(value)
                sets.append(f"{mapping[field]} = ${len(params)}")
        if extras:
            params.append(json.dumps(extras))
            sets.append(f"settings = COALESCE(settings, '{{}}'::jsonb) || ${len(params)}::jsonb")
        if not sets:
            return await self.get_client(client_id)
        params.append(client_id)
        row = await execute_returning(f"UPDATE clients SET {', '.join(sets)} WHERE client_id = ${len(params)} RETURNING *", *params)
        return self.public_client(row) if row else None


    async def delete_client(self, client_id: str) -> bool:
        result = await execute("UPDATE clients SET status = 'inactive' WHERE client_id = $1", client_id)
        return result == "UPDATE 1"

    async def get_client_usage(self, client_id: str) -> Optional[Dict[str, Any]]:
        client = await self.get_client(client_id)
        if not client:
            return None
        project_count = await fetch_one("SELECT COUNT(*) as cnt FROM projects WHERE client_id = $1", client_id)
        return {
            "client_id": client_id,
            "projects": project_count["cnt"] if project_count else 0,
        }

    def _get_default_settings(self, plan: str) -> Dict[str, Any]:
        base = {
            "notifications": {"email_enabled": True, "slack_enabled": False, "telegram_enabled": True},
            "monitoring": {"check_interval_seconds": 300, "health_check_enabled": True},
            "remediation": {"auto_remediation_enabled": False, "require_approval_above": "safe"},
        }
        if plan == "professional":
            base["remediation"]["auto_remediation_enabled"] = True
            base["notifications"]["slack_enabled"] = True
        elif plan == "enterprise":
            base["remediation"]["auto_remediation_enabled"] = True
            base["notifications"]["slack_enabled"] = True
            base["monitoring"]["check_interval_seconds"] = 60
        return base


client_service = ClientService()
