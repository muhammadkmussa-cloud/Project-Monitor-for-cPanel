"""Default-deny API policy. Tenant accounts can read their own monitoring data."""
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from app.auth import get_current_user
from app.db import fetch_one


async def enforce_access(request: Request):
    if request.url.path == "/api/v1/auth/login":
        return
    user = await get_current_user(request)
    route = request.scope["route"].path.removeprefix("/api/v1")
    method = request.method
    resource = route.strip("/").split("/")[0]
    action = "read" if method == "GET" else "write"
    scopes = user.get("permissions", [])
    # Empty scopes on legacy keys mean inherit the user's role. Explicit scopes
    # can only restrict it. Newly issued keys default to read-only scopes.
    if user.get("api_key") and scopes and not any(
        scope in scopes for scope in ("*:*", f"{resource}:*", f"{resource}:{action}")
    ):
        raise HTTPException(403, "API key scope does not permit this operation")
    for key, value in request.path_params.items():
        if key.endswith("_id") and key not in {"backup_id", "plan_id"}:
            try:
                UUID(str(value))
            except ValueError:
                raise HTTPException(422, f"Invalid {key}")
    if user["role"] in {"admin", "owner"}:
        return
    readable = (
        route == "/auth/me"
        or route in {"/projects", "/incidents", "/billing/plans", "/billing/plans/{plan_id}"}
        or route.startswith("/analytics/")
        or route in {"/projects/{project_id}", "/projects/{project_id}/health",
                     "/incidents/{incident_id}", "/incidents/{incident_id}/diagnosis"}
    )
    if method != "GET" or not readable:
        raise HTTPException(403, "Admin access required")
    tenant = user["client_id"]
    ids = dict(request.query_params)
    ids.update(request.path_params)
    if ids.get("client_id") and str(ids["client_id"]) != tenant:
        raise HTTPException(404, "Resource not found")
    for key, table in (("project_id", "projects"), ("incident_id", "incidents")):
        if ids.get(key):
            try:
                value = str(UUID(str(ids[key])))
            except ValueError:
                raise HTTPException(422, f"Invalid {key}")
            row = await fetch_one(f"SELECT client_id FROM {table} WHERE {key} = $1", value)
            if not row or str(row["client_id"]) != tenant:
                raise HTTPException(404, "Resource not found")
