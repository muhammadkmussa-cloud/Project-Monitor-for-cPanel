from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from uuid import uuid4
import json

from app.db import fetch_one, fetch_all, execute, execute_returning


PLANS = {
    "starter": {
        "name": "Starter",
        "monthly_price": 49,
        "annual_price": 470,
        "features": [
            "5 projects",
            "1,000 API calls/day",
            "500MB storage",
            "Email support",
            "30-day data retention",
        ],
        "limits": {
            "max_projects": 5,
            "daily_api_calls": 1000,
            "max_storage_mb": 500,
        },
    },
    "professional": {
        "name": "Professional",
        "monthly_price": 199,
        "annual_price": 1910,
        "features": [
            "25 projects",
            "10,000 API calls/day",
            "5GB storage",
            "Priority support",
            "90-day data retention",
            "Auto-remediation",
            "Slack integration",
        ],
        "limits": {
            "max_projects": 25,
            "daily_api_calls": 10000,
            "max_storage_mb": 5000,
        },
    },
    "enterprise": {
        "name": "Enterprise",
        "monthly_price": 799,
        "annual_price": 7670,
        "features": [
            "100 projects",
            "100,000 API calls/day",
            "50GB storage",
            "Dedicated support",
            "365-day data retention",
            "Advanced auto-remediation",
            "All integrations",
            "Custom branding",
            "SLA guarantee",
        ],
        "limits": {
            "max_projects": 100,
            "daily_api_calls": 100000,
            "max_storage_mb": 50000,
        },
    },
}


async def create_invoice(
    client_id: str,
    plan: str,
    billing_cycle: str = "monthly",
    amount: Optional[float] = None,
) -> Dict[str, Any]:
    plan_data = PLANS.get(plan, PLANS["starter"])

    if amount is None:
        amount = plan_data["monthly_price"] if billing_cycle == "monthly" else plan_data["annual_price"]

    invoice_id = str(uuid4())
    due_date = datetime.utcnow() + timedelta(days=30)
    items = [{"description": f"{plan_data['name']} Plan - {billing_cycle}", "amount": amount, "quantity": 1}]

    await execute(
        """INSERT INTO billing_invoices (invoice_id, client_id, plan, billing_cycle, amount, currency, status, due_date, items)
           VALUES ($1::uuid, $2::uuid, $3, $4, $5, 'USD', 'pending', $6, $7::jsonb)""",
        invoice_id, client_id, plan, billing_cycle, amount, due_date, json.dumps(items),
    )

    return {
        "invoice_id": invoice_id,
        "client_id": client_id,
        "plan": plan,
        "billing_cycle": billing_cycle,
        "amount": amount,
        "currency": "USD",
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "due_date": due_date.isoformat(),
        "paid_at": None,
        "payment_method": None,
        "items": items,
    }


async def get_invoice(invoice_id: str) -> Optional[Dict[str, Any]]:
    row = await fetch_one(
        "SELECT * FROM billing_invoices WHERE invoice_id = $1::uuid", invoice_id
    )
    if not row:
        return None
    return dict(row)


async def list_invoices(
    client_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    query = "SELECT * FROM billing_invoices WHERE 1=1"
    params: list = []
    idx = 1
    if client_id:
        query += f" AND client_id = ${idx}::uuid"
        params.append(client_id)
        idx += 1
    if status:
        query += f" AND status = ${idx}"
        params.append(status)
        idx += 1
    query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)
    rows = await fetch_all(query, *params)
    return [dict(r) for r in rows]


async def mark_invoice_paid(invoice_id: str, payment_method: str = "card") -> Optional[Dict[str, Any]]:
    row = await execute_returning(
        """UPDATE billing_invoices
           SET status = 'paid', paid_at = NOW(), payment_method = $1, updated_at = NOW()
           WHERE invoice_id = $2::uuid RETURNING *""",
        payment_method, invoice_id,
    )
    return dict(row) if row else None


async def record_usage(
    client_id: str,
    metric: str,
    quantity: int,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    record_id = str(uuid4())
    await execute(
        """INSERT INTO billing_usage (record_id, client_id, metric, quantity, metadata)
           VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb)""",
        record_id, client_id, metric, quantity, json.dumps(metadata or {}),
    )
    return {
        "record_id": record_id,
        "client_id": client_id,
        "metric": metric,
        "quantity": quantity,
        "metadata": metadata or {},
        "recorded_at": datetime.utcnow().isoformat(),
    }


async def get_usage_summary(
    client_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    query = "SELECT metric, SUM(quantity) as total_quantity, COUNT(*) as record_count FROM billing_usage WHERE client_id = $1::uuid"
    params: list = [client_id]
    idx = 2
    if start_date:
        query += f" AND recorded_at >= ${idx}"
        params.append(start_date)
        idx += 1
    if end_date:
        query += f" AND recorded_at <= ${idx}"
        params.append(end_date)
        idx += 1
    query += " GROUP BY metric"
    rows = await fetch_all(query, *params)

    usage_by_metric = {}
    total_records = 0
    for r in rows:
        usage_by_metric[r["metric"]] = {
            "quantity": r["total_quantity"],
            "count": r["record_count"],
        }
        total_records += r["record_count"]

    return {
        "client_id": client_id,
        "period": {
            "start": start_date or (datetime.utcnow() - timedelta(days=30)).isoformat(),
            "end": end_date or datetime.utcnow().isoformat(),
        },
        "total_records": total_records,
        "usage_by_metric": usage_by_metric,
    }


async def calculate_overage(client_id: str, plan: str) -> Dict[str, Any]:
    plan_data = PLANS.get(plan, PLANS["starter"])
    limits = plan_data["limits"]

    usage_summary = await get_usage_summary(client_id)
    usage_by_metric = usage_summary.get("usage_by_metric", {})

    overages = {}
    total_overage = 0

    api_usage = usage_by_metric.get("api_calls", {}).get("quantity", 0)
    daily_limit = limits["daily_api_calls"]
    if api_usage > daily_limit:
        overage = api_usage - daily_limit
        overages["api_calls"] = {"overage": overage, "rate": 0.001, "charge": overage * 0.001}
        total_overage += overage * 0.001

    storage_usage = usage_by_metric.get("storage", {}).get("quantity", 0)
    storage_limit = limits["max_storage_mb"]
    if storage_usage > storage_limit:
        overage = storage_usage - storage_limit
        overages["storage"] = {"overage_mb": overage, "rate": 0.10, "charge": overage * 0.10}
        total_overage += overage * 0.10

    return {
        "client_id": client_id,
        "plan": plan,
        "overages": overages,
        "total_overage_charge": round(total_overage, 2),
    }


async def get_plan_details(plan: str) -> Optional[Dict[str, Any]]:
    return PLANS.get(plan)


async def list_plans() -> List[Dict[str, Any]]:
    return [{"id": pid, **pdata} for pid, pdata in PLANS.items()]


async def get_client_billing_summary(client_id: str) -> Dict[str, Any]:
    invoices = await list_invoices(client_id=client_id)
    pending_invoices = [i for i in invoices if i["status"] == "pending"]
    paid_invoices = [i for i in invoices if i["status"] == "paid"]

    total_pending = sum(float(i["amount"]) for i in pending_invoices)
    total_paid = sum(float(i["amount"]) for i in paid_invoices)

    return {
        "client_id": client_id,
        "total_invoices": len(invoices),
        "pending_invoices": len(pending_invoices),
        "paid_invoices": len(paid_invoices),
        "total_pending_amount": total_pending,
        "total_paid_amount": total_paid,
        "recent_invoices": invoices[:5],
    }
