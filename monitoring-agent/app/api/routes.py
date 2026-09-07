from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from typing import List, Optional, Dict, Any, Literal
from uuid import UUID, uuid4
from datetime import datetime

from app.api.schemas import (
    ProjectCreate, ProjectResponse,
    IncidentCreate, IncidentResponse,
    HealthCheckResult, ServerStats, DiscoveryResult,
    LogEntry, SSHTestResult,
    DiagnosisRequest, DiagnosisResponse,
    ApprovalRequest, ApprovalResponse,
    RemediationPlanRequest, RemediationPlanResponse, RemediationActionItem,
    RemediationExecuteRequest, RemediationResultResponse,
    BackupResponse, RollbackRequest,
    VerificationResult, NotificationRequest,
    CredentialCreate, LoginRequest, UserCreate, APIKeyCreate,
)
from app.auth import require_admin, get_current_user, tenant_scope
import json
import shlex

router = APIRouter()


def shell_path(path: str) -> str:
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        return '"$HOME"/' + shlex.quote(path[2:])
    return shlex.quote(path)



def dict_to_project_response(r: dict) -> ProjectResponse:
    """Map a projects table row (asyncpg Record->dict) to ProjectResponse."""
    return ProjectResponse(
        project_id=str(r["project_id"]), client_id=str(r["client_id"]),
        project_name=r["project_name"], domain=r.get("domain"),
        server_host=r.get("server_host"),
        ssh_port=int(r.get("ssh_port") or 22),
        ssh_username=r.get("ssh_username"),
        connection_type=r.get("connection_type", "ssh"),
        project_path=r.get("project_path"),
        health_check_url=r.get("health_check_url"),
        application_type=r.get("application_type", "other"),
        framework=r.get("framework"),
        environment=r.get("environment", "production"),
        monitoring_enabled=r.get("monitoring_enabled", True),
        check_interval=int(r.get("check_interval") or 300),
        current_status=r.get("current_status", "UNKNOWN"),
        remediation_enabled=r.get("remediation_enabled", False),
        created_at=r["created_at"].isoformat() if r.get("created_at") else None,
        updated_at=r["updated_at"].isoformat() if r.get("updated_at") else None,
        last_check_at=r["last_check_at"].isoformat() if r.get("last_check_at") else None,
    )


async def _resolve_ssh_target(project_id: UUID) -> tuple:
    """Return (project_dict, connection_kwargs, error)."""
    from app.db import fetch_one
    from app.services import credential_service

    project = await fetch_one("SELECT * FROM projects WHERE project_id = $1", str(project_id))
    if not project:
        return None, None, "Project not found"
    cred = await credential_service.get_decrypted_credential(str(project_id), "ssh")
    host = cred.get("host") if cred and cred.get("host") else project["server_host"]
    port = int(cred.get("port") if cred and cred.get("port") else (project["ssh_port"] or 22))
    username = cred.get("username") if cred and cred.get("username") else project["ssh_username"]
    if not host or not username:
        return dict(project), None, "No server_host/username configured and no SSH credential stored"
    kwargs = {}
    if cred:
        if cred.get("password"):
            kwargs["password"] = cred["password"]
        if cred.get("private_key"):
            kwargs["private_key"] = cred["private_key"]
        elif cred.get("key_path"):
            kwargs["key_path"] = cred["key_path"]
    return dict(project), {"host": host, "port": port, "username": username, **kwargs}, None


# ==================================================
# Project Credential Endpoints (admin)
# ==================================================

@router.post("/projects/{project_id}/credentials", response_model=dict)
async def create_project_credential(project_id: UUID, body: CredentialCreate, user: dict = Depends(require_admin)):
    """Store an encrypted SSH/SFTP credential for a project."""
    from app.services import credential_service

    payload = {
        "host": body.host,
        "port": body.port,
        "username": body.username,
        "password": body.password,
        "private_key": body.private_key,
        "key_path": body.key_path,
    }
    cred = await credential_service.store_credential(
        str(project_id), body.credential_type, payload, name=body.name
    )
    return cred


@router.get("/projects/{project_id}/credentials", response_model=List[dict])
async def list_project_credentials(project_id: UUID):
    from app.services import credential_service
    return await credential_service.list_credentials(str(project_id))


@router.delete("/projects/{project_id}/credentials/{credential_id}", response_model=dict)
async def delete_project_credential(project_id: UUID, credential_id: UUID, user: dict = Depends(require_admin)):
    from app.services import credential_service
    ok = await credential_service.delete_credential(str(project_id), str(credential_id))
    if not ok:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"message": "Credential deleted"}


# ==================================================
# Project Endpoints
# ==================================================

@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(
    monitoring_enabled: Optional[bool] = Query(None),
    client_id: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    tenant_id: Optional[str] = Depends(tenant_scope),
):
    """List all projects with optional filtering."""
    client_id = tenant_id or client_id
    from app.db import fetch_all
    conditions = []
    params = []
    idx = 1
    if client_id:
        conditions.append(f"client_id = ${idx}")
        params.append(str(client_id))
        idx += 1
    if monitoring_enabled is not None:
        conditions.append(f"monitoring_enabled = ${idx}")
        params.append(monitoring_enabled)
        idx += 1
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await fetch_all(f"SELECT * FROM projects {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}", *params, limit, skip)
    return [dict_to_project_response(r) for r in rows]


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(project: ProjectCreate, user: dict = Depends(require_admin)):
    from app.db import execute_returning
    values = project.model_dump()
    values["project_id"] = uuid4()
    for field in ("log_locations", "thresholds"):
        values[field] = json.dumps(values[field])
    fields = list(values)
    row = await execute_returning(
        f"INSERT INTO projects ({', '.join(fields)}) VALUES ({', '.join('$'+str(i+1) for i in range(len(fields)))}) RETURNING *",
        *values.values())
    return dict_to_project_response(dict(row))


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: UUID, project: ProjectCreate, user: dict = Depends(require_admin)):
    from app.db import execute_returning, fetch_one
    existing = await fetch_one("SELECT client_id FROM projects WHERE project_id=$1", str(project_id))
    if existing and str(existing["client_id"]) != str(project.client_id):
        raise HTTPException(409, "Project transfers between clients require a separate migration")
    values = project.model_dump()
    for field in ("log_locations", "thresholds"):
        values[field] = json.dumps(values[field])
    fields = list(values)
    row = await execute_returning(
        f"UPDATE projects SET {', '.join(field+'=$'+str(i+2) for i,field in enumerate(fields))}, updated_at=NOW() WHERE project_id=$1 RETURNING *",
        str(project_id), *values.values())
    if not row:
        raise HTTPException(404, "Project not found")
    return dict_to_project_response(dict(row))


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID):
    """Get project details by ID."""
    from app.db import fetch_one
    row = await fetch_one("SELECT * FROM projects WHERE project_id = $1", str(project_id))
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    r = dict(row)
    return dict_to_project_response(r)


@router.delete("/projects/{project_id}", response_model=dict)
async def delete_project(project_id: UUID, user: dict = Depends(require_admin)):
    """Delete a project (and its cascaded data). Admin only."""
    from app.db import execute
    result = await execute("DELETE FROM projects WHERE project_id = $1", str(project_id))
    if "DELETE 0" in result:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project deleted"}


@router.post("/projects/{project_id}/test-connection", response_model=SSHTestResult)
async def test_connection(project_id: UUID):
    """Test SSH connection to a project's server."""
    from app.services.ssh_service import ssh_service

    project, kwargs, error = await _resolve_ssh_target(project_id)
    if error:
        return SSHTestResult(success=False, message=error)
    result = await ssh_service.test_connection(**kwargs)
    return SSHTestResult(
        success=result.get("success", False),
        message=result.get("message", ""),
        host=result.get("host") or kwargs.get("host"),
        username=result.get("username") or kwargs.get("username"),
        os_info=result.get("os_info"),
    )


@router.post("/projects/{project_id}/discover", response_model=DiscoveryResult)
async def discover_project(project_id: UUID):
    """Run read-only discovery on a project's server."""
    from app.services.ssh_service import ssh_service

    project, kwargs, error = await _resolve_ssh_target(project_id)
    if error:
        return DiscoveryResult(os_info=error, cpu_info="", memory_total="", disk_info="")
    cwd = shell_path(project.get("project_path") or "~")
    cmds = {
        "os": "uname -a",
        "cpu": "lscpu | grep 'Model name' | sed 's/.*: *//'",
        "memory": "free -h | awk 'NR==2{print $2}'",
        "disk": "df -h ~ | awk 'NR==2{print $2, $3, $4}'",
        "php": "php -v | head -1",
        "node": "node -v 2>/dev/null",
        "python": "python3 --version 2>/dev/null",
        "web_server": "head -1 /etc/apache2/conf/* 2>/dev/null; hostname",
        "git": f"git -C {cwd} rev-parse --is-inside-work-tree 2>/dev/null; git -C {cwd} log -1 --oneline 2>/dev/null",
    }
    out = {}
    for k, cmd in cmds.items():
        r = await ssh_service.execute_command(**kwargs, command=cmd)
        out[k] = r.get("output") if r.get("success") else ""
    structure = []
    r = await ssh_service.execute_command(**kwargs, command=f"ls {cwd}")
    if r.get("success"):
        structure = [x for x in r["output"].splitlines() if x][:40]
    return DiscoveryResult(
        os_info=out.get("os", ""),
        cpu_info=out.get("cpu", ""),
        memory_total=out.get("memory", ""),
        disk_info=out.get("disk", ""),
        php_version=out.get("php") or None,
        node_version=out.get("node") or None,
        python_version=out.get("python") or None,
        web_server=out.get("web_server") or None,
        git_info={"branch": out.get("git", "")} if out.get("git") else None,
        project_structure=structure,
        log_locations=[],
    )


# ==================================================
# Health Check Endpoints
# ==================================================

@router.get("/projects/{project_id}/health", response_model=HealthCheckResult)
async def check_project_health(project_id: UUID):
    """Perform health check on a project."""
    from app.services.monitoring_service import run_http_health_check

    result = await run_http_health_check(str(project_id))
    return HealthCheckResult(
        status=result.get("status", "UNKNOWN"),
        http_status_code=result.get("http_status_code"),
        response_time_ms=result.get("response_time_ms"),
        ssl_days_remaining=result.get("ssl_days_remaining"),
        details=result.get("details", {}),
    )


@router.post("/projects/{project_id}/scan-errors")
async def scan_project_errors(project_id: UUID):
    """Scan a project's error log for new errors and raise incidents."""
    from app.services.error_scanner import scan_project
    return await scan_project(str(project_id))


@router.post("/scan-errors/all")
async def scan_all_project_errors(user: dict = Depends(require_admin)):
    """Scan all enabled projects for new log errors."""
    from app.services.error_scanner import scan_all_enabled
    return await scan_all_enabled()


@router.get("/projects/{project_id}/server-stats", response_model=ServerStats)
async def get_server_stats(project_id: UUID):
    """Get server resource statistics for a project."""
    from app.services.ssh_service import ssh_service

    project, kwargs, error = await _resolve_ssh_target(project_id)
    if error:
        return ServerStats(cpu_percent=0.0, memory_percent=0.0, disk_percent=0.0, load_average=[0,0,0], uptime=0, details={"error": error})
    try:
        stats = await ssh_service.get_server_stats(**kwargs)
    except (RuntimeError, ValueError):
        raise HTTPException(502, "Server statistics could not be collected")
    return ServerStats(
        cpu_percent=stats.get("cpu_percent", 0.0),
        memory_percent=stats.get("memory_percent", 0.0),
        disk_percent=stats.get("disk_percent", 0.0),
        load_average=stats.get("load_average", [0, 0, 0]),
        uptime=stats.get("uptime", 0),
    )


@router.get("/projects/{project_id}/processes")
async def get_processes(project_id: UUID):
    """Get running processes on a project's server."""
    from app.services.ssh_service import ssh_service

    project, kwargs, error = await _resolve_ssh_target(project_id)
    if error:
        return {"processes": [], "error": error}
    r = await ssh_service.execute_command(
        **kwargs,
        command="ps aux --sort=-%cpu | head -20",
    )
    processes = []
    if r.get("success"):
        for line in r["output"].splitlines()[1:]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append({
                    "user": parts[0], "pid": parts[1], "cpu": parts[2],
                    "mem": parts[3], "command": parts[10],
                })
    return {"processes": processes}


# ==================================================
# Log Endpoints
# ==================================================

@router.get("/projects/{project_id}/logs", response_model=List[LogEntry])
async def get_logs(
    project_id: UUID,
    lines: int = Query(100, ge=1, le=10000),
    level: Optional[str] = Query(None),
):
    """Get recent log entries from a project."""
    from app.services.log_service import log_service

    project, kwargs, error = await _resolve_ssh_target(project_id)
    if error:
        return []
    result = await log_service.read_project_error_log(
        **kwargs,
        domain=project.get("domain"),
        project_path=project.get("project_path"),
        lines=lines,
        errors_only=False,
    )
    entries = []
    for item in result.get("entries", []):
        lvl = "ERROR" if item["level"] in ("error", "fatal", "critical") else "WARNING" if item["level"] == "warning" else "INFO"
        if level and lvl.upper() != level.upper():
            continue
        entries.append(LogEntry(level=lvl, message=(item.get("message") or "")[:2000], source=item.get("source")))
    return entries


@router.get("/projects/{project_id}/errors", response_model=List[LogEntry])
async def get_errors(
    project_id: UUID,
    lines: int = Query(100, ge=1, le=10000),
):
    """Get recent error log entries from a project."""
    from app.services.log_service import log_service

    project, kwargs, error = await _resolve_ssh_target(project_id)
    if error:
        return []
    result = await log_service.read_project_error_log(
        **kwargs,
        domain=project.get("domain"),
        project_path=project.get("project_path"),
        lines=lines,
        errors_only=True,
    )
    return [LogEntry(level="ERROR", message=(item.get("message") or "")[:2000], source=item.get("source")) for item in result.get("entries", [])]


# ==================================================
# Git Endpoints
# ==================================================

@router.get("/projects/{project_id}/git/status")
async def get_git_status(project_id: UUID):
    """Get Git status for a project."""
    from app.services.ssh_service import ssh_service

    project, kwargs, error = await _resolve_ssh_target(project_id)
    if error:
        return {"error": error}
    cwd = shell_path(project.get("project_path") or ".")
    r = await ssh_service.execute_command(
        **kwargs,
        command=f"cd {cwd} && git status --short 2>/dev/null || echo '__NO_GIT__'",
    )
    if not r.get("success") or "__NO_GIT__" in r.get("output", ""):
        return {"is_repo": False, "changes": [], "message": "Not a git repository"}
    return {"is_repo": True, "changes": [x for x in r["output"].splitlines() if x]}


@router.get("/projects/{project_id}/git/commits")
async def get_git_commits(
    project_id: UUID,
    count: int = Query(10, ge=1, le=100),
):
    """Get recent Git commits for a project."""
    from app.services.ssh_service import ssh_service

    project, kwargs, error = await _resolve_ssh_target(project_id)
    if error:
        return {"commits": [], "error": error}
    cwd = shell_path(project.get("project_path") or ".")
    r = await ssh_service.execute_command(
        **kwargs,
        command=f"cd {cwd} && git log -{count} --format='%h|%an|%ad|%s' --date=short 2>/dev/null || echo '__NO_GIT__'",
    )
    if not r.get("success") or "__NO_GIT__" in r.get("output", ""):
        return {"commits": [], "message": "Not a git repository"}
    commits = []
    for line in r["output"].splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({"hash": parts[0], "author": parts[1], "date": parts[2], "message": parts[3]})
    return {"commits": commits}


# ==================================================
# Incident Endpoints
# ==================================================

@router.get("/incidents", response_model=List[IncidentResponse])
async def list_incidents(
    project_id: Optional[UUID] = Query(None),
    client_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    tenant_id: Optional[str] = Depends(tenant_scope),
):
    """List incidents with optional filtering."""
    client_id = tenant_id or client_id
    from app.db import fetch_all
    conditions = []
    params = []
    idx = 1
    if project_id:
        conditions.append(f"project_id = ${idx}")
        params.append(str(project_id))
        idx += 1
    if client_id:
        conditions.append(f"client_id = ${idx}")
        params.append(str(client_id))
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await fetch_all(f"SELECT * FROM incidents {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}", *params, limit, skip)
    return [IncidentResponse(
        incident_id=str(r["incident_id"]), project_id=str(r["project_id"]),
        client_id=str(r["client_id"]), category=r["category"],
        severity=r["severity"], status=r["status"],
        error_signature=r.get("error_signature"),
        affected_component=r.get("affected_component"),
        first_seen=r["first_seen"].isoformat() if r.get("first_seen") else None,
        last_seen=r["last_seen"].isoformat() if r.get("last_seen") else None,
        occurrence_count=r.get("occurrence_count", 1),
        created_at=r["created_at"].isoformat() if r.get("created_at") else None,
    ) for r in rows]


@router.post("/incidents", response_model=IncidentResponse, status_code=201)
async def create_incident(incident: IncidentCreate):
    """Create a new incident record."""
    from app.db import execute_returning, fetch_one
    project = await fetch_one("SELECT client_id FROM projects WHERE project_id=$1", str(incident.project_id))
    if not project or str(project["client_id"]) != str(incident.client_id):
        raise HTTPException(422, "Incident client must match the project")
    valid_categories = ('HTTP_ERROR','APPLICATION_ERROR','DATABASE_FAILURE','REDIS_FAILURE','PROCESS_CRASH','SSL_ERROR','DNS_ERROR','DISK_FULL','MEMORY_EXHAUSTION','CPU_OVERLOAD','DEPLOYMENT_FAILURE','CONFIGURATION_ERROR','PERMISSION_ERROR','DEPENDENCY_ERROR','NETWORK_ERROR','UNKNOWN')
    valid_severities = ('LOW','MEDIUM','HIGH','CRITICAL')
    cat = incident.category if incident.category in valid_categories else 'UNKNOWN'
    sev = incident.severity if incident.severity in valid_severities else 'MEDIUM'
    row = await execute_returning(
        """INSERT INTO incidents (incident_id, project_id, client_id, category, severity, status, error_signature, affected_component)
           VALUES ($1, $2, $3, $4, $5, 'OPEN', $6, $7)
           RETURNING *""",
        uuid4(), str(incident.project_id), str(incident.client_id),
        cat, sev, incident.error_signature, incident.affected_component,
    )
    r = dict(row)
    return IncidentResponse(
        incident_id=str(r["incident_id"]), project_id=str(r["project_id"]),
        client_id=str(r["client_id"]), category=r["category"],
        severity=r["severity"], status=r["status"],
        error_signature=r.get("error_signature"),
        affected_component=r.get("affected_component"),
        first_seen=r["first_seen"].isoformat() if r.get("first_seen") else None,
        last_seen=r["last_seen"].isoformat() if r.get("last_seen") else None,
        occurrence_count=r.get("occurrence_count", 1),
        created_at=r["created_at"].isoformat() if r.get("created_at") else None,
    )


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: UUID):
    """Get incident details by ID."""
    from app.db import fetch_one
    row = await fetch_one("SELECT * FROM incidents WHERE incident_id = $1", str(incident_id))
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    r = dict(row)
    return IncidentResponse(
        incident_id=str(r["incident_id"]), project_id=str(r["project_id"]),
        client_id=str(r["client_id"]), category=r["category"],
        severity=r["severity"], status=r["status"],
        error_signature=r.get("error_signature"),
        affected_component=r.get("affected_component"),
        first_seen=r["first_seen"].isoformat() if r.get("first_seen") else None,
        last_seen=r["last_seen"].isoformat() if r.get("last_seen") else None,
        occurrence_count=r.get("occurrence_count", 1),
        created_at=r["created_at"].isoformat() if r.get("created_at") else None,
    )


# ==================================================
# AI Diagnosis Endpoints
# ==================================================

@router.post("/diagnose", response_model=DiagnosisResponse)
async def diagnose_incident(request: DiagnosisRequest):
    """Trigger AI diagnosis for an incident."""
    from app.services.ai_service import ai_service
    from app.db import fetch_one, execute_returning
    import json

    incident = await fetch_one("SELECT * FROM incidents WHERE incident_id = $1", str(request.incident_id))
    if not incident:
        raise HTTPException(404, "Incident not found")
    incident_data = {
        "incident_id": str(request.incident_id),
        "category": incident["category"] if incident else "UNKNOWN",
        "severity": incident["severity"] if incident else "MEDIUM",
        "status": incident["status"] if incident else "OPEN",
        "affected_component": incident["affected_component"] or "unknown",
        "error_signature": incident["error_signature"],
        "recorded_error": incident["raw_error_reference"],
    }

    measurement = await fetch_one("SELECT status,http_status_code,response_time_ms,ssl_days_remaining,details FROM monitoring_checks WHERE project_id=$1 ORDER BY checked_at DESC LIMIT 1",str(incident['project_id']))
    if measurement:
        incident_data['latest_health_check'] = dict(measurement)
    context = await fetch_one("SELECT project_name,domain,application_type,framework,environment,project_path FROM projects WHERE project_id=$1",str(incident['project_id']))
    if context:
        incident_data['project'] = dict(context)

    log_entries: List[Dict[str, Any]] = []
    server_stats: Optional[Dict[str, Any]] = None
    try:
        project, kwargs, _ = await _resolve_ssh_target(incident["project_id"])
        if kwargs:
            from app.services.log_service import log_service
            from app.services.ssh_service import ssh_service
            if request.include_logs:
                lres = await log_service.read_project_error_log(
                    **kwargs,
                    domain=project.get("domain") if project else None,
                    project_path=project.get("project_path") if project else None,
                    lines=60,
                    errors_only=True,
                )
                log_entries = lres.get("entries", [])[:40]
            if request.include_server_stats:
                server_stats = await ssh_service.get_server_stats(**kwargs)
    except Exception:
        pass

    diagnosis_result = await ai_service.diagnose_incident(
        incident_data=incident_data,
        log_entries=log_entries,
        server_stats=server_stats,
        git_info=None,
    )

    project_id = incident["project_id"] if incident else str(uuid4())
    row = await execute_returning(
        """INSERT INTO ai_diagnoses
            (diagnosis_id, incident_id, project_id, model_used, diagnosis, confidence,
             severity_assessment, root_cause, evidence, proposed_fix, affected_files,
             commands_required, risk_level, rollback_plan, verification_plan, requires_human_approval)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
           RETURNING *""",
        uuid4(), str(request.incident_id), project_id,
        diagnosis_result.get("model_used", "deepseek-chat"),
        json.dumps(diagnosis_result),
        diagnosis_result.get("confidence", 0.5),
        diagnosis_result.get("severity", "MEDIUM"),
        diagnosis_result.get("root_cause", "Unknown"),
        json.dumps(diagnosis_result.get("evidence", [])),
        diagnosis_result.get("proposed_fix", "Manual investigation required"),
        json.dumps(diagnosis_result.get("files_affected", [])),
        json.dumps(diagnosis_result.get("commands_required", [])),
        diagnosis_result.get("risk_level", "MEDIUM"),
        diagnosis_result.get("rollback_plan", "No rollback plan"),
        json.dumps(diagnosis_result.get("verification_plan", [])),
        diagnosis_result.get("requires_human_approval", True),
    )

    return DiagnosisResponse(
        diagnosis_id=str(row["diagnosis_id"]),
        incident_id=str(row["incident_id"]),
        severity=str(row["severity_assessment"]),
        category=incident_data["category"],
        root_cause=str(row["root_cause"]),
        evidence=json.loads(row["evidence"]) if isinstance(row["evidence"], str) else (row["evidence"] or []),
        affected_component=incident_data["affected_component"],
        confidence=float(row["confidence"]),
        proposed_fix=str(row["proposed_fix"]),
        files_affected=json.loads(row["affected_files"]) if isinstance(row["affected_files"], str) else (row["affected_files"] or []),
        commands_required=json.loads(row["commands_required"]) if isinstance(row["commands_required"], str) else (row["commands_required"] or []),
        risk_level=str(row["risk_level"]),
        rollback_plan=str(row["rollback_plan"]),
        verification_plan=json.loads(row["verification_plan"]) if isinstance(row["verification_plan"], str) else (row["verification_plan"] or []),
        requires_human_approval=bool(row["requires_human_approval"]),
        created_at=row["created_at"],
    )


# ==================================================
# Approval Endpoints
# ==================================================

@router.post("/approvals", response_model=ApprovalResponse)
async def create_approval(request: ApprovalRequest, user: dict = Depends(require_admin)):
    """Create an approval record for a diagnosis."""
    from app.db import fetch_one, execute_returning

    diagnosis = await fetch_one("SELECT * FROM ai_diagnoses WHERE diagnosis_id = $1", str(request.diagnosis_id))
    if not diagnosis:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    incident = await fetch_one("SELECT * FROM incidents WHERE incident_id = $1", str(request.incident_id))
    project_id = str(incident["project_id"]) if incident else str(diagnosis["project_id"])
    client_id = str(incident["client_id"]) if incident else "00000000-0000-0000-0000-000000000001"

    if not incident or str(diagnosis["incident_id"]) != str(request.incident_id):
        raise HTTPException(409, "Diagnosis and incident do not match")
    proposal_row = await fetch_one("SELECT * FROM fix_proposals WHERE incident_id=$1 AND diagnosis_id=$2 ORDER BY created_at DESC LIMIT 1",
                                   str(request.incident_id), str(request.diagnosis_id))
    if not proposal_row:
        raise HTTPException(409, "Create and review a remediation plan first")
    if proposal_row["safety_level"] == "BLOCKED":
        raise HTTPException(403, "Plan is blocked")
    status_val = {"approve": "APPROVED", "reject": "REJECTED", "manual": "PENDING"}.get(request.action)
    if not status_val:
        raise HTTPException(422, "Invalid approval action")
    approved_by = user["sub"] if request.action in {"approve", "reject"} else None
    from app.services.incident_review_service import snapshot
    project=await fetch_one('SELECT * FROM projects WHERE project_id=$1',project_id)
    review_hash=await snapshot(proposal_row,dict(project))
    row = await execute_returning(
        """INSERT INTO approvals (approval_id, proposal_id, incident_id, project_id, client_id, status, approved_by, notes, approval_method, responded_at,review_hash)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CASE WHEN $7::varchar IS NOT NULL THEN NOW() ELSE NULL END,$10)
           RETURNING *""",
        uuid4(), str(proposal_row["proposal_id"]), str(request.incident_id),
        project_id, client_id, status_val, approved_by, request.notes, request.action,review_hash,
    )

    return ApprovalResponse(
        approval_id=row["approval_id"],
        incident_id=row["incident_id"],
        diagnosis_id=request.diagnosis_id,
        action=request.action,
        status=row["status"],
        approved_by=row["approved_by"],
        approved_at=row["responded_at"],
        notes=row["notes"],
    )


@router.get("/approvals/{approval_id}", response_model=ApprovalResponse)
async def get_approval(approval_id: UUID):
    """Get approval details by ID."""
    from app.db import fetch_one
    row = await fetch_one("SELECT * FROM approvals WHERE approval_id = $1", str(approval_id))
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")

    proposal = await fetch_one("SELECT * FROM fix_proposals WHERE proposal_id = $1", str(row["proposal_id"]))
    diagnosis_id = str(proposal["diagnosis_id"]) if proposal else str(row["incident_id"])

    return ApprovalResponse(
        approval_id=row["approval_id"],
        incident_id=row["incident_id"],
        diagnosis_id=UUID(diagnosis_id),
        action=row.get("approval_method", "approve"),
        status=row["status"],
        approved_by=row["approved_by"],
        approved_at=row["responded_at"],
        notes=row["notes"],
    )


@router.post("/approvals/{approval_id}/approve")
async def approve_diagnosis(approval_id: UUID, user: dict = Depends(require_admin)):
    """Approve a diagnosis for remediation."""
    from app.db import fetch_one, execute
    row = await fetch_one("SELECT * FROM approvals WHERE approval_id = $1", str(approval_id))
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")

    from app.services.incident_review_service import snapshot
    proposal=await fetch_one('SELECT * FROM fix_proposals WHERE proposal_id=$1',str(row['proposal_id']))
    project=await fetch_one('SELECT * FROM projects WHERE project_id=$1',str(row['project_id']))
    review_hash=await snapshot(proposal,dict(project))
    await execute("UPDATE approvals SET status = 'APPROVED', approved_by = $2, responded_at = NOW(),review_hash=$3 WHERE approval_id = $1", str(approval_id), user['sub'],review_hash)
    return {"message": "Diagnosis approved", "approval_id": str(approval_id)}


@router.post("/approvals/{approval_id}/reject")
async def reject_diagnosis(approval_id: UUID, user: dict = Depends(require_admin)):
    """Reject a diagnosis."""
    from app.db import fetch_one, execute
    row = await fetch_one("SELECT * FROM approvals WHERE approval_id = $1", str(approval_id))
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")

    await execute("UPDATE approvals SET status = 'REJECTED', approved_by = $2, responded_at = NOW() WHERE approval_id = $1", str(approval_id), user['sub'])
    return {"message": "Diagnosis rejected", "approval_id": str(approval_id)}


# ==================================================
# Remediation Endpoints
# ==================================================

@router.post("/remediation/plan", response_model=RemediationPlanResponse)
async def create_remediation_plan(request: RemediationPlanRequest, user: dict = Depends(require_admin)):
    """Create a remediation plan from a diagnosis."""
    from app.services.remediation_engine import remediation_engine
    from app.db import fetch_one, execute_returning
    import json

    diagnosis = await fetch_one("SELECT * FROM ai_diagnoses WHERE diagnosis_id = $1", str(request.diagnosis_id))
    if not diagnosis:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    if str(diagnosis["incident_id"]) != str(request.incident_id):
        raise HTTPException(409, "Diagnosis does not belong to this incident")
    def as_list(value):
        value = json.loads(value) if isinstance(value, str) else value
        if not isinstance(value, list):
            raise HTTPException(422, "Diagnosis actions must be a list")
        return value
    diagnosis_data = {
        "commands_required": as_list(diagnosis.get("commands_required") or []),
        "files_affected": as_list(diagnosis.get("affected_files") or []),
        "requires_human_approval": True,
    }

    actions = remediation_engine.parse_actions_from_diagnosis(diagnosis_data)

    project_id = str(diagnosis["project_id"])
    row = await execute_returning(
        """INSERT INTO fix_proposals (proposal_id, incident_id, diagnosis_id, project_id, proposal_summary, detailed_steps, safety_level)
           VALUES ($1, $2, $3, $4, $5, $6, 'APPROVAL_REQUIRED')
           RETURNING *""",
        uuid4(), str(request.incident_id), str(request.diagnosis_id), project_id,
        diagnosis.get("proposed_fix", "No fix proposed"),
        json.dumps([a.to_dict() for a in actions]),
    )

    return RemediationPlanResponse(
        plan_id=row["proposal_id"],
        incident_id=request.incident_id,
        actions=[
            RemediationActionItem(
                action_type=action.action_type,
                description=action.description,
                command=action.command,
                file_path=action.file_path,
                requires_approval=action.requires_approval,
                safety_level=action.safety_level.value,
            )
            for action in actions
        ],
        total_actions=len(actions),
        requires_approval=any(a.requires_approval for a in actions),
        status="created",
        created_at=row["created_at"],
    )


@router.post("/remediation/execute", response_model=RemediationResultResponse)
async def execute_remediation(request: RemediationExecuteRequest, user: dict = Depends(require_admin)):
    """Execute a remediation plan."""
    from app.services.remediation_engine import remediation_engine, RemediationAction, SafetyLevel
    from app.db import fetch_one, execute_returning

    from app.db import execute
    proposal = await fetch_one("SELECT * FROM fix_proposals WHERE proposal_id = $1 AND (expires_at IS NULL OR expires_at > NOW())", str(request.plan_id))
    if not proposal:
        raise HTTPException(404, "Remediation plan not found or expired")
    if str(proposal["incident_id"]) != str(request.incident_id):
        raise HTTPException(409, "Plan does not belong to this incident")
    if proposal["safety_level"] == "BLOCKED":
        raise HTTPException(403, "This plan is blocked")
    incident_state = await fetch_one("SELECT * FROM incidents WHERE incident_id=$1", str(request.incident_id))
    if not incident_state or incident_state["status"] in {"IGNORED", "RESOLVED", "ROLLED_BACK"}:
        raise HTTPException(409, "This incident no longer permits remediation")
    if request.server_connection:
        raise HTTPException(422, "Execution targets must come from stored project credentials")
    approval = await fetch_one(
        """SELECT * FROM approvals WHERE proposal_id=$1 AND incident_id=$2 AND status='APPROVED'
           AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY responded_at DESC LIMIT 1""",
        str(request.plan_id), str(request.incident_id))
    if not approval or (request.approval_id and str(approval["approval_id"]) != str(request.approval_id)):
        raise HTTPException(409, "A matching, unexpired approval is required")
    from app.services.incident_review_service import snapshot
    stored_project=await fetch_one('SELECT * FROM projects WHERE project_id=$1',str(proposal['project_id']))
    if not approval.get('review_hash') or await snapshot(proposal,dict(stored_project))!=approval['review_hash']:
        raise HTTPException(409,'Approved proposal or target changed; a new review is required')
    project, connection, error = await _resolve_ssh_target(proposal["project_id"])
    if error or not project.get("remediation_enabled"):
        raise HTTPException(409, error or "Remediation is disabled for this project")
    steps = proposal.get("detailed_steps", [])
    if isinstance(steps, str):
        steps = json.loads(steps)
    if not isinstance(steps, list) or not steps or len(steps)>10:
        raise HTTPException(409, "Plan has no executable actions")
    try:
        actions = [RemediationAction(**{k: v for k, v in step.items() if k != "safety_level"}, safety_level=SafetyLevel(step.get("safety_level", "risky"))) for step in steps]
    except (TypeError, ValueError):
        raise HTTPException(422, "Invalid plan actions")
    from app.services.repair_service import approved_action
    if not all(approved_action(a,dict(stored_project)) for a in actions):
        raise HTTPException(403,'Plan contains an unsupported repair; use a configured template or exact reviewed JSON patch')
    if any(a.action_type=='json_patch' for a in actions) and len(actions)!=1:
        raise HTTPException(422,'File changes require a single-file proposal')
    if any(a.command and remediation_engine._assess_command_safety(a.command) == "dangerous" for a in actions):
        raise HTTPException(403, "Plan contains a blocked command")
    run = await execute_returning(
        """INSERT INTO remediation_runs (run_id, incident_id, project_id, proposal_id, approval_id, status, started_at)
           VALUES ($1,$2,$3,$4,$5,'IN_PROGRESS',NOW()) ON CONFLICT DO NOTHING RETURNING *""",
        uuid4(), str(request.incident_id), str(proposal["project_id"]), str(request.plan_id), str(approval["approval_id"]))
    if not run:
        raise HTTPException(409, "This proposal has already been executed or claimed")
    connection = {**connection, "project_path": project.get("project_path")}
    claimed=await execute_returning("UPDATE incidents SET status='REMEDIATING',verification_status='PENDING',updated_at=NOW() WHERE incident_id=$1 AND status NOT IN ('RESOLVED','IGNORED','ROLLED_BACK','REMEDIATING') RETURNING *",str(request.incident_id))
    if not claimed:
        await execute("UPDATE remediation_runs SET status='FAILED',completed_at=NOW(),error_log='Incident changed before execution' WHERE run_id=$1",str(run['run_id']))
        raise HTTPException(409,'Incident changed before execution')
    from app.services.incident_verification import verify, finish
    from app.services.credential_service import encrypt_value
    project={**dict(project),'_verification_connection':encrypt_value(json.dumps(connection))}
    await execute('UPDATE remediation_runs SET verification_context=$2::jsonb WHERE run_id=$1',str(run['run_id']),json.dumps({'incident':dict(incident_state),'project':dict(project)},default=str))
    baseline=await verify(dict(incident_state),dict(project))
    await execute('UPDATE remediation_runs SET baseline=$2::jsonb WHERE run_id=$1',str(run['run_id']),json.dumps(baseline,default=str))
    try:
        if baseline['outcome']=='VERIFIED':
            result={'success':True,'executed_actions':0,'results':[{'status':'not_run','reason':'Original condition already stably healthy before execution'}]}
        else:
            result = await remediation_engine.execute_plan(incident_id=str(request.incident_id), actions=actions,
                                                           approval_status="approved", server_connection=connection,run_id=str(run["run_id"]))
    except Exception:
        await execute("UPDATE remediation_runs SET status='FAILED', completed_at=NOW(), error_log='Execution failed; inspect service logs' WHERE run_id=$1", str(run["run_id"]))
        await execute("UPDATE incidents SET status='FAILED',verification_status='SKIPPED',updated_at=NOW() WHERE incident_id=$1 AND status='REMEDIATING'",str(request.incident_id))
        raise HTTPException(502, "Remediation failed; inspect service logs")
    await execute('UPDATE remediation_runs SET execution_finished_at=NOW(),commands_succeeded=$2,steps_executed=$3::jsonb,error_log=$4 WHERE run_id=$1',str(run['run_id']),result['success'],json.dumps(result.get('results',[])),result.get('error'))
    verification=baseline if baseline['outcome']=='VERIFIED' else await verify(dict(incident_state),dict(project))
    verification=await finish(run,dict(incident_state),dict(project),verification,result['success'])
    status = "COMPLETED" if result["success"] else "FAILED"
    await execute("UPDATE remediation_runs SET status=$2, completed_at=NOW(), steps_executed=$3::jsonb, error_log=$4 WHERE run_id=$1",
                  str(run["run_id"]), status, json.dumps(result.get("results", [])), result.get("error"))
    return RemediationResultResponse(result_id=run["run_id"], incident_id=request.incident_id, plan_id=request.plan_id,
        success=result["success"], status=status, executed_actions=result.get("executed_actions", 0),
        failed_actions=result.get("failed_actions", 0), backup_id=result.get("backup_id"), verification_passed={'VERIFIED':True,'STILL_FAILING':False,'UNAVAILABLE':None}[verification['outcome']],
        verification_outcome=verification['outcome'],verification_details=verification,
        rolled_back=bool(verification.get("rollback",{}).get("success")), results=result.get("results", []), created_at=run["created_at"])


# ==================================================
# Backup Endpoints
# ==================================================

@router.post("/backups", response_model=BackupResponse)
async def create_backup(
    incident_id: UUID,
    file_paths: List[str],
):
    """Create a backup of files before remediation."""
    from app.services.backup_service import backup_service

    result = await backup_service.create_backup(
        incident_id=str(incident_id),
        file_paths=file_paths,
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail="Backup creation failed")

    return BackupResponse(**result["data"])


@router.get("/backups")
async def list_backups():
    """List all available backups."""
    from app.services.backup_service import backup_service

    return backup_service.list_backups()


@router.get("/backups/{backup_id}")
async def get_backup(backup_id: str):
    """Get details of a specific backup."""
    from app.services.backup_service import backup_service

    backup = backup_service.get_backup(backup_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    return backup


@router.post("/backups/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    server_connection: Optional[Dict[str, Any]] = None,
):
    """Restore files from a backup."""
    from app.services.backup_service import backup_service

    result = await backup_service.restore_backup(
        backup_id=backup_id,
        server_connection=server_connection,
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail="Backup restoration failed")

    return result


# ==================================================
# Rollback Endpoints
# ==================================================

@router.post("/rollback")
async def perform_rollback(request: RollbackRequest, user: dict = Depends(require_admin)):
    """Perform rollback for an incident."""
    from app.services.rollback_service import rollback_service

    result = await rollback_service.manual_rollback(
        incident_id=str(request.incident_id),
        backup_id=request.backup_id,
        server_connection=request.server_connection,
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail="Rollback failed")

    return result


# ==================================================
# Verification Endpoints
# ==================================================

@router.post("/verify")
async def verify_remediation(
    incident_id: UUID,
    verification_plan: List[str],
    server_connection: Optional[Dict[str, Any]] = None,
    expected_url: Optional[str] = None,
):
    """Verify remediation results."""
    from app.services.verification_service import verification_service

    result = await verification_service.verify_remediation(
        incident_id=str(incident_id),
        verification_plan=verification_plan,
        server_connection=server_connection,
        expected_url=expected_url,
    )

    return result


# ==================================================
# Notification Endpoints
# ==================================================

@router.post("/notifications/send")
async def send_notification(request: NotificationRequest):
    """Send a notification via Telegram."""
    from app.services.telegram_service import telegram_service

    result = await telegram_service.send_message(
        text=f"[{request.severity.upper()}] {request.message}",
    )

    return result


@router.post("/notifications/test")
async def test_notification(message: str = "Test notification from Project Monitor"):
    """Send a test notification to verify Telegram integration."""
    from app.services.telegram_service import telegram_service

    result = await telegram_service.send_message(
        text=f"[TEST] {message}\n\n<i>Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>",
    )

    return result


@router.post("/notifications/incident-alert")
async def send_incident_alert(
    incident_id: UUID,
    severity: str,
    category: str,
    affected_component: str,
    error_signature: Optional[str] = None,
):
    """Send incident alert notification."""
    from app.services.telegram_service import telegram_service

    result = await telegram_service.send_incident_alert(
        incident_id=str(incident_id),
        severity=severity,
        category=category,
        affected_component=affected_component,
        error_signature=error_signature,
    )

    return result


@router.post("/notifications/approval-request")
async def send_approval_request(
    incident_id: UUID,
    diagnosis_id: UUID,
):
    """Send approval request for a diagnosis."""
    from app.services.telegram_service import telegram_service
    from app.db import fetch_one

    diagnosis = await fetch_one("SELECT * FROM ai_diagnoses WHERE diagnosis_id = $1", str(diagnosis_id))
    if not diagnosis:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    result = await telegram_service.send_approval_request(
        incident_id=str(incident_id),
        diagnosis=dict(diagnosis),
        fix_description=str(diagnosis.get("proposed_fix", "No fix proposed")),
    )

    return result


# ==================================================
# Telegram Webhook Endpoints
# ==================================================

@router.post("/telegram/webhook")
async def telegram_webhook(callback_data: Dict[str, Any]):
    """Handle Telegram callback queries."""
    from app.services.telegram_service import telegram_service

    query = callback_data.get("callback_query", {})
    data = query.get("data", "")

    if "_" in data:
        parts = data.split("_", 1)
        action = parts[0]
        incident_id = parts[1]

        result = await telegram_service.handle_callback_query(
            callback_data=data,
            incident_id=incident_id,
        )

        return result

    return {"action": "unknown"}


# ==================================================
# Analytics Endpoints (Phase 3)
# ==================================================

@router.get("/analytics/dashboard")
async def get_dashboard_summary(client_id: Optional[str] = None, tenant_id: Optional[str] = Depends(tenant_scope)):
    """Get dashboard summary data."""
    from app.services.analytics_service import analytics_service

    return await analytics_service.get_dashboard_summary(client_id=tenant_id or client_id)


@router.get("/analytics/incident-trends")
async def get_incident_trends(
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    tenant_id: Optional[str] = Depends(tenant_scope),
):
    """Get incident trends over time."""
    client_id = tenant_id or client_id
    from app.services.analytics_service import analytics_service

    return await analytics_service.get_incident_trends(
        project_id=project_id,
        client_id=client_id,
        days=days,
    )


@router.get("/analytics/health-trends/{project_id}")
async def get_health_trends(
    project_id: str,
    days: int = Query(7, ge=1, le=90),
):
    """Get health check trends for a project."""
    from app.services.analytics_service import analytics_service

    return await analytics_service.get_health_trends(
        project_id=project_id,
        days=days,
    )


@router.get("/analytics/server-performance/{project_id}")
async def get_server_performance(
    project_id: str,
    days: int = Query(7, ge=1, le=90),
):
    """Get server performance trends."""
    from app.services.analytics_service import analytics_service

    return await analytics_service.get_server_performance(
        project_id=project_id,
        days=days,
    )


@router.get("/analytics/remediation-stats")
async def get_remediation_stats(
    project_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    tenant_id: Optional[str] = Depends(tenant_scope),
):
    """Get remediation statistics."""
    from app.services.analytics_service import analytics_service

    return await analytics_service.get_remediation_stats(
        project_id=project_id,
        client_id=tenant_id,
        days=days,
    )


@router.get("/analytics/client-summary/{client_id}")
async def get_client_summary(
    client_id: str,
    days: int = Query(30, ge=1, le=365),
):
    """Get summary for a client."""
    from app.services.analytics_service import analytics_service

    return await analytics_service.get_client_summary(
        client_id=client_id,
        days=days,
    )


@router.get("/analytics/cost-analysis/{client_id}")
async def get_cost_analysis(
    client_id: str,
    days: int = Query(30, ge=1, le=365),
):
    """Analyze cost savings from automation."""
    from app.services.analytics_service import analytics_service

    return await analytics_service.get_cost_analysis(
        client_id=client_id,
        days=days,
    )


# ==================================================
# Report Endpoints (Phase 3)
# ==================================================

@router.get("/reports/incident")
async def generate_incident_report(
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Generate incident report."""
    from app.services.report_service import report_service

    return await report_service.generate_incident_report(
        project_id=project_id,
        client_id=client_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/reports/uptime/{project_id}")
async def generate_uptime_report(
    project_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Generate uptime report for a project."""
    from app.services.report_service import report_service

    return await report_service.generate_uptime_report(
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/reports/performance/{project_id}")
async def generate_performance_report(
    project_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Generate performance report for a project."""
    from app.services.report_service import report_service

    return await report_service.generate_performance_report(
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/reports/remediation")
async def generate_remediation_report(
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Generate remediation activity report."""
    from app.services.report_service import report_service

    return await report_service.generate_remediation_report(
        project_id=project_id,
        client_id=client_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/reports/executive-summary/{client_id}")
async def generate_executive_summary(
    client_id: str,
    days: int = Query(30, ge=1, le=365),
):
    """Generate executive summary report."""
    from app.services.report_service import report_service

    return await report_service.generate_executive_summary(
        client_id=client_id,
        days=days,
    )


@router.post("/reports/export")
async def export_report(
    report_data: Dict[str, Any],
    format: str = Query("json", pattern="^(json|csv|pdf)$"),
):
    """Export report in specified format."""
    from app.services.report_service import report_service

    return await report_service.export_report(
        report_data=report_data,
        format=format,
    )


# ==================================================
# Email Notification Endpoints (Phase 3)
# ==================================================

@router.post("/notifications/email/send")
async def send_email_notification(
    to: List[str],
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
):
    """Send email notification."""
    from app.services.email_service import email_service

    return await email_service.send_email(
        to=to,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )


@router.post("/notifications/email/incident-alert")
async def send_email_incident_alert(
    to: List[str],
    incident_id: str,
    severity: str,
    category: str,
    affected_component: str,
    error_signature: Optional[str] = None,
):
    """Send incident alert email."""
    from app.services.email_service import email_service

    return await email_service.send_incident_alert(
        to=to,
        incident_id=incident_id,
        severity=severity,
        category=category,
        affected_component=affected_component,
        error_signature=error_signature,
    )


@router.post("/notifications/email/daily-report")
async def send_daily_report_email(
    to: List[str],
    client_name: str,
    report_data: Dict[str, Any],
):
    """Send daily monitoring report email."""
    from app.services.email_service import email_service

    return await email_service.send_daily_report(
        to=to,
        client_name=client_name,
        report_data=report_data,
    )


# ==================================================
# Slack Notification Endpoints (Phase 3)
# ==================================================

@router.post("/notifications/slack/send")
async def send_slack_notification(
    text: str,
    channel: Optional[str] = None,
):
    """Send Slack notification."""
    from app.services.slack_service import slack_service

    return await slack_service.send_message(
        text=text,
        channel=channel,
    )


@router.post("/notifications/slack/incident-alert")
async def send_slack_incident_alert(
    incident_id: str,
    severity: str,
    category: str,
    affected_component: str,
    error_signature: Optional[str] = None,
):
    """Send incident alert to Slack."""
    from app.services.slack_service import slack_service

    return await slack_service.send_incident_alert(
        incident_id=incident_id,
        severity=severity,
        category=category,
        affected_component=affected_component,
        error_signature=error_signature,
    )


@router.post("/notifications/slack/approval-request")
async def send_slack_approval_request(
    incident_id: str,
    diagnosis_id: str,
):
    """Send approval request to Slack."""
    from app.services.slack_service import slack_service
    from app.db import fetch_one

    diagnosis = await fetch_one("SELECT * FROM ai_diagnoses WHERE diagnosis_id = $1", diagnosis_id)
    if not diagnosis:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    return await slack_service.send_approval_request(
        incident_id=incident_id,
        diagnosis=dict(diagnosis),
        fix_description=str(diagnosis.get("proposed_fix", "No fix proposed")),
    )


# ==================================================
# Data Retention Endpoints (Phase 3)
# ==================================================

@router.post("/retention/cleanup")
async def run_cleanup(user: dict = Depends(require_admin)):
    """Run data cleanup job."""
    from app.services.retention_service import retention_service

    raise HTTPException(501, "Automatic data cleanup is not implemented; no data was deleted")


@router.get("/retention/stats")
async def get_retention_stats():
    """Get retention statistics."""
    from app.services.retention_service import retention_service

    return await retention_service.get_retention_stats()


@router.get("/retention/storage")
async def get_storage_usage():
    """Get storage usage statistics."""
    from app.services.retention_service import retention_service

    return await retention_service.get_storage_usage()


# ==================================================
# Client Management Endpoints (Phase 4)
# ==================================================

@router.post("/clients", status_code=201)
async def create_client(
    client_name: str,
    contact_email: str,
    company_name: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    timezone: str = "UTC",
    plan: str = "starter",
):
    """Create a new client."""
    from app.services.client_service import client_service

    return await client_service.create_client(
        client_name=client_name,
        contact_email=contact_email,
        company_name=company_name,
        phone=phone,
        address=address,
        timezone=timezone,
        plan=plan,
    )


@router.get("/clients")
async def list_clients(
    status: Optional[str] = None,
    plan: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """List clients with filtering."""
    from app.services.client_service import client_service

    return await client_service.list_clients(
        status=status,
        plan=plan,
        skip=skip,
        limit=limit,
    )


@router.get("/clients/{client_id}")
async def get_client(client_id: str):
    """Get client by ID."""
    from app.services.client_service import client_service

    client = await client_service.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.put("/clients/{client_id}")
async def update_client(
    client_id: str,
    client_name: Optional[str] = None,
    company_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    timezone: Optional[str] = None,
    status: Optional[str] = None,
    plan: Optional[str] = None,
):
    """Update client information."""
    from app.services.client_service import client_service

    kwargs = {}
    if client_name is not None:
        kwargs["client_name"] = client_name
    if company_name is not None:
        kwargs["company_name"] = company_name
    if contact_email is not None:
        kwargs["contact_email"] = contact_email
    if phone is not None:
        kwargs["phone"] = phone
    if address is not None:
        kwargs["address"] = address
    if timezone is not None:
        kwargs["timezone"] = timezone
    if status is not None:
        kwargs["status"] = status
    if plan is not None:
        kwargs["plan"] = plan

    client = await client_service.update_client(client_id, **kwargs)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(require_admin)):
    """Soft delete a client."""
    from app.services.client_service import client_service

    success = await client_service.delete_client(client_id)
    if not success:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"message": "Client deleted"}


@router.get("/clients/{client_id}/usage")
async def get_client_usage(client_id: str):
    """Get client usage statistics."""
    from app.services.client_service import client_service

    usage = await client_service.get_client_usage(client_id)
    if not usage:
        raise HTTPException(status_code=404, detail="Client not found")
    return usage


@router.get("/clients/{client_id}/billing")
async def get_client_billing(client_id: str):
    """Get client billing summary."""
    from app.services import billing_service

    return await billing_service.get_client_billing_summary(client_id)


# ==================================================
# User Management Endpoints (Phase 4)
# ==================================================

@router.post("/users", status_code=201)
async def create_user(body: UserCreate, user: dict = Depends(require_admin)):
    from app.services.rbac_service import rbac_service
    return await rbac_service.create_user(client_id=str(body.client_id), email=body.email, name=body.name,
                                           password=body.password, role=body.role)


@router.get("/users")
async def list_users(
    client_id: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
):
    """List users with filtering."""
    from app.services.rbac_service import rbac_service

    return await rbac_service.list_users(
        client_id=client_id,
        role=role,
        status=status,
    )


@router.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get user by ID."""
    from app.services.rbac_service import rbac_service

    user = await rbac_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    name: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
):
    """Update user information."""
    from app.services.rbac_service import rbac_service

    kwargs = {}
    if name is not None:
        kwargs["name"] = name
    if role is not None:
        kwargs["role"] = role
    if status is not None:
        kwargs["status"] = status

    user = await rbac_service.update_user(user_id, **kwargs)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_admin)):
    """Soft delete a user."""
    from app.services.rbac_service import rbac_service

    success = await rbac_service.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}


@router.post("/auth/login")
async def login(
    body: Optional[LoginRequest] = None,
    email: Optional[str] = Query(None),
    password: Optional[str] = Query(None),
):
    """Authenticate user and return JWT token. Accepts JSON body or query params."""
    from app.services.rbac_service import rbac_service
    from app.auth import create_token

    if body is not None:
        email = body.email
        password = body.password
    if not email or not password:
        raise HTTPException(status_code=422, detail="email and password are required")

    user = await rbac_service.authenticate_user(email, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    from app.services.settings_service import read_setting
    try:
        minutes = max(5, min(1440, int(await read_setting("security.session_timeout", 1440))))
    except (TypeError, ValueError):
        minutes = 1440
    token = create_token(
        expires_hours=minutes / 60,
        user_id=user["user_id"],
        email=user["email"],
        role=user["role"],
    )

    return {
        "token": token,
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
        },
    }


@router.post("/auth/api-keys")
async def create_api_key(body: APIKeyCreate, user: dict = Depends(require_admin)):
    from app.services.rbac_service import rbac_service
    return await rbac_service.create_api_key(user_id=str(body.user_id), name=body.name,
        permissions=body.permissions, expires_in_days=body.expires_in_days)


@router.post("/auth/api-keys/{key_id}/revoke")
async def revoke_api_key(key_id: str):
    """Revoke an API key."""
    from app.services.rbac_service import rbac_service

    success = await rbac_service.revoke_api_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"message": "API key revoked"}


@router.get("/auth/permissions/{user_id}")
async def get_user_permissions(user_id: str):
    """Get all permissions for a user."""
    from app.services.rbac_service import rbac_service

    return await rbac_service.get_user_permissions(user_id)


@router.get("/roles")
async def list_roles():
    """List all roles."""
    from app.services.rbac_service import rbac_service

    return await rbac_service.list_roles()


# ==================================================
# Billing Endpoints (Phase 4)
# ==================================================

@router.post("/billing/invoices", status_code=201)
async def create_invoice(
    client_id: str,
    plan: str,
    billing_cycle: str = "monthly",
    amount: Optional[float] = None,
    user: dict = Depends(require_admin),
):
    """Create an invoice for a client."""
    from app.services import billing_service

    return await billing_service.create_invoice(
        client_id=client_id,
        plan=plan,
        billing_cycle=billing_cycle,
        amount=amount,
    )


@router.get("/billing/invoices")
async def list_invoices(
    client_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
):
    """List invoices with filtering."""
    from app.services import billing_service

    return await billing_service.list_invoices(
        client_id=client_id,
        status=status,
        limit=limit,
    )


@router.get("/billing/invoices/{invoice_id}")
async def get_invoice(invoice_id: str):
    """Get invoice by ID."""
    from app.services import billing_service

    invoice = await billing_service.get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.post("/billing/invoices/{invoice_id}/pay")
async def mark_invoice_paid(
    invoice_id: str,
    payment_method: str = "card",
    user: dict = Depends(require_admin),
):
    """Mark an invoice as paid."""
    from app.services import billing_service

    invoice = await billing_service.mark_invoice_paid(invoice_id, payment_method)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.get("/billing/plans")
async def list_plans():
    """List all available plans."""
    from app.services import billing_service

    return await billing_service.list_plans()


@router.get("/billing/plans/{plan_id}")
async def get_plan(plan_id: str):
    """Get plan details."""
    from app.services import billing_service

    plan = await billing_service.get_plan_details(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.get("/billing/usage/{client_id}")
async def get_usage_summary(
    client_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Get usage summary for a client."""
    from app.services import billing_service

    return await billing_service.get_usage_summary(
        client_id=client_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/billing/overage/{client_id}")
async def calculate_overage(
    client_id: str,
    plan: str,
):
    """Calculate overage charges for a client."""
    from app.services import billing_service

    return await billing_service.calculate_overage(
        client_id=client_id,
        plan=plan,
    )


# ==================================================
# Scan Trigger Endpoint
# ==================================================

@router.post("/trigger-scan", status_code=202)
async def trigger_scan(background_tasks: BackgroundTasks, user: dict = Depends(require_admin)):
    """Queue an in-process manual scan; scheduled scans retry unfinished work."""
    from app.services.scan_service import run_cycle
    background_tasks.add_task(run_cycle, force=True)
    return {"status": "queued", "message": "Health scan queued. Results will appear as checks finish."}


# ==================================================
# Incident Approval/Rejection Endpoints
# ==================================================

@router.post("/incidents/{incident_id}/approve")
async def approve_incident(incident_id: str, user: dict = Depends(require_admin)):
    from app.db import fetch_one, execute, execute_returning
    incident = await fetch_one("SELECT * FROM incidents WHERE incident_id=$1", incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    proposal = await fetch_one("SELECT * FROM fix_proposals WHERE incident_id=$1 AND (expires_at IS NULL OR expires_at>NOW()) ORDER BY created_at DESC LIMIT 1", incident_id)
    if not proposal:
        raise HTTPException(409, "Create and review a remediation plan before approval")
    if proposal["safety_level"] == "BLOCKED":
        raise HTTPException(403, "Plan is blocked")
    approval = await execute_returning(
        """INSERT INTO approvals (approval_id,proposal_id,incident_id,project_id,client_id,status,approved_by,responded_at,approval_method)
           VALUES ($1,$2,$3,$4,$5,'APPROVED',$6,NOW(),'dashboard') RETURNING *""",
        uuid4(), str(proposal["proposal_id"]), incident_id, str(incident["project_id"]), str(incident["client_id"]), user["sub"])
    await execute("UPDATE incidents SET status='APPROVED', updated_at=NOW() WHERE incident_id=$1", incident_id)
    return {"status": "approved", "incident_id": incident_id, "plan_id": str(proposal["proposal_id"]),
            "approval_id": str(approval["approval_id"]), "message": "Plan approved. Execution must be requested separately."}


@router.post("/incidents/{incident_id}/reject")
async def reject_incident(incident_id: str, reason: Optional[str] = None):
    """Reject the proposed fix for an incident."""
    from app.db import fetch_one, execute

    incident = await fetch_one("SELECT * FROM incidents WHERE incident_id = $1", incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await execute("UPDATE approvals SET status='REJECTED', responded_at=NOW() WHERE incident_id=$1 AND status IN ('PENDING','APPROVED')", incident_id)
    await execute("UPDATE incidents SET status = 'IGNORED', updated_at = NOW() WHERE incident_id = $1", incident_id)

    return {"status": "rejected", "incident_id": incident_id, "message": "Fix proposal rejected"}


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str):
    """Mark an incident as resolved."""
    from app.db import fetch_one, execute

    incident = await fetch_one("SELECT * FROM incidents WHERE incident_id = $1", incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    await execute("UPDATE incidents SET status = 'RESOLVED', resolved_at = NOW(), updated_at = NOW() WHERE incident_id = $1", incident_id)
    return {"status": "resolved", "incident_id": incident_id, "message": "Incident marked resolved"}


@router.get("/incidents/{incident_id}/diagnosis")
async def get_incident_diagnosis(incident_id: str):
    """Get the latest AI diagnosis for an incident."""
    from app.db import fetch_all
    import json

    rows = await fetch_all(
        """SELECT diagnosis_id, model_used, diagnosis, confidence, severity_assessment,
                  root_cause, proposed_fix, risk_level, requires_human_approval, created_at
           FROM ai_diagnoses WHERE incident_id = $1 ORDER BY created_at DESC LIMIT 1""",
        incident_id,
    )
    if not rows:
        return {"diagnosis": None}
    r = rows[0]
    try:
        diag = json.loads(r["diagnosis"]) if isinstance(r["diagnosis"], str) else (r["diagnosis"] or {})
    except Exception:
        diag = {}
    return {
        "diagnosis_id": str(r["diagnosis_id"]),
        "model_used": r["model_used"],
        "confidence": r["confidence"],
        "severity_assessment": r["severity_assessment"],
        "root_cause": r["root_cause"],
        "proposed_fix": r["proposed_fix"],
        "risk_level": r["risk_level"],
        "evidence": diag.get("evidence", []),
        "requires_human_approval": r["requires_human_approval"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


# ==================================================
# Rate Limit Endpoints (Phase 4)
# ==================================================

@router.get("/rate-limit/status")
async def get_rate_limit_status(client_key: str):
    """Get rate limit status for a client."""
    from app.services.rate_limit_service import get_rate_limit_status

    return get_rate_limit_status(client_key)


@router.post("/rate-limit/reset")
async def reset_rate_limits(client_key: Optional[str] = None):
    """Reset rate limits for a client or all clients."""
    from app.services.rate_limit_service import reset_rate_limits

    reset_rate_limits(client_key)
    return {"message": "Rate limits reset"}


# ==================================================
# Settings Endpoints
# ==================================================

@router.get("/settings")
async def get_settings():
    """Get all platform settings."""
    from app.db import fetch_all
    rows = await fetch_all("SELECT setting_key, setting_value FROM platform_settings ORDER BY setting_key")
    return {r["setting_key"]: json.loads(r["setting_value"]) if isinstance(r["setting_value"], str) else r["setting_value"] for r in rows}


@router.put("/settings/{key}")
async def update_setting(key: str, body: Dict[str, Any], user: dict = Depends(require_admin)):
    """Update a setting."""
    from app.db import execute_returning
    import json
    value = body.get("value", body)
    if key not in {"profile.name", "profile.company", "notifications.telegram_enabled", "security.session_timeout"}:
        raise HTTPException(422, "Unsupported setting")
    if key == "security.session_timeout":
        if isinstance(value, bool) or not isinstance(value, int) or not 5 <= value <= 1440:
            raise HTTPException(422, "Session timeout must be between 5 and 1440 minutes")
    elif key == "notifications.telegram_enabled" and not isinstance(value, bool):
        raise HTTPException(422, "Notification setting must be a boolean")
    elif key.startswith("profile.") and (not isinstance(value, str) or len(value) > 255):
        raise HTTPException(422, "Profile setting must be text of at most 255 characters")
    await execute_returning(
        """INSERT INTO platform_settings (setting_key, setting_value) VALUES ($1, $2::jsonb)
           ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at=NOW()
           RETURNING *""", key, json.dumps(value))
    return {"key": key, "value": value}


# ==================================================
# Self-Monitoring Endpoints
# ==================================================

@router.get("/system/health/detailed")
async def get_system_health():
    """Get detailed health of all platform services."""
    from app.services.self_monitor_service import get_system_health as get_health
    return await get_health()


@router.post("/system/health/check")
async def trigger_health_check(user: dict = Depends(require_admin)):
    """Trigger a health check of all services."""
    from app.services.self_monitor_service import check_all_services
    results = await check_all_services()
    return {"status": "checked", "results": results}


@router.get("/auth/me")
async def current_identity(user: dict = Depends(get_current_user)):
    from app.services.rbac_service import rbac_service
    return await rbac_service.get_user(user["sub"])


@router.post("/monitoring/run")
async def run_scheduled_monitoring(user: dict = Depends(require_admin)):
    from app.services.scan_service import run_cycle
    result = await run_cycle()
    if any(p["status"] == "error" for p in result["projects"]):
        raise HTTPException(502, "Some project checks failed; inspect agent logs")
    return result


from app.db import fetch_one, fetch_all, execute
from pydantic import BaseModel, Field, ConfigDict, model_validator

class CheckSchedule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = True
    interval: int = Field(default=300, ge=30, le=86400)

class ResourceLimit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    warning: float = Field(ge=0,le=100)
    critical: float = Field(ge=0,le=100)
    @model_validator(mode='after')
    def ascending(self):
        if self.warning>=self.critical: raise ValueError('Warning must be below critical')
        return self

class ResourceLimits(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cpu: ResourceLimit = ResourceLimit(warning=80,critical=95)
    memory: ResourceLimit = ResourceLimit(warning=80,critical=95)
    disk: ResourceLimit = ResourceLimit(warning=75,critical=90)
    inodes: ResourceLimit = ResourceLimit(warning=80,critical=95)

class ResourceSchedule(CheckSchedule):
    thresholds: ResourceLimits = ResourceLimits()

class ApplicationContract(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=80)
    path: str = Field(min_length=1,max_length=1024)
    method: str = 'GET'
    expected_status: int = Field(default=200,ge=100,le=599)
    contains: Optional[str] = Field(default=None,max_length=256)
    json_equals: Dict[str,Any] = {}
    body: Optional[Dict[str,Any]] = None
    use_credentials: bool = False
    username_field: str = 'email'
    password_field: str = 'password'
    capture_token_path: Optional[str] = None
    use_bearer_from_previous: bool = False
    @model_validator(mode='after')
    def safe_contract(self):
        if not self.path.startswith('/') or self.path.startswith('//') or '\\' in self.path or any(ord(c)<32 for c in self.path): raise ValueError('Use a same-origin absolute path')
        if self.method not in ('GET','POST'): raise ValueError('Only GET and opted-in POST checks are supported')
        if self.use_credentials and self.method!='POST': raise ValueError('Login credentials require a POST step')
        if not self.contains and not self.json_equals and self.expected_status==200 and not self.capture_token_path: raise ValueError('Add a content or JSON assertion beyond HTTP 200')
        if len(json.dumps(self.body or {}))>4096 or len(json.dumps(self.json_equals))>4096: raise ValueError('Contract data is too large')
        from app.services.incident_review_service import clean
        if clean(self.body or {}) != (self.body or {}): raise ValueError('Store secrets in an encrypted HTTP credential, not the request body')
        return self

class ApplicationSchedule(CheckSchedule):
    enabled: bool = False
    allow_mutations: bool = False
    checks: List[ApplicationContract] = Field(default=[],max_length=10)
    @model_validator(mode='after')
    def configured(self):
        if self.enabled and not self.checks: raise ValueError('Configure application contracts before enabling')
        if any(c.method=='POST' for c in self.checks) and not self.allow_mutations: raise ValueError('POST journeys require explicit mutation opt-in')
        return self

class HTTPCheckSchedule(CheckSchedule):
    warning_ms: int = Field(default=2000,ge=1,le=60000)
    critical_ms: int = Field(default=5000,ge=1,le=120000)
    ssl_warning_days: int = Field(default=30,ge=1,le=365)
    ssl_critical_days: int = Field(default=7,ge=0,le=365)
    @model_validator(mode='after')
    def thresholds_order(self):
        if self.warning_ms>=self.critical_ms or self.ssl_critical_days>=self.ssl_warning_days: raise ValueError('Warning and critical thresholds must be ordered')
        return self

class IncidentPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    failure_checks: int = Field(default=2,ge=1,le=10)
    recovery_checks: int = Field(default=2,ge=1,le=10)
    escalate_after: int = Field(default=5,ge=2,le=100)

class MonitoringConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    http: HTTPCheckSchedule = HTTPCheckSchedule()
    logs: CheckSchedule = CheckSchedule(interval=600)
    resources: ResourceSchedule = ResourceSchedule()
    application: ApplicationSchedule = ApplicationSchedule()
    policy: IncidentPolicy = IncidentPolicy()

@router.put('/projects/{project_id}/monitoring-config')
async def set_monitoring_config(project_id: UUID, config: MonitoringConfig, user: dict = Depends(require_admin)):
    existing=await fetch_one('SELECT environment FROM projects WHERE project_id=$1',str(project_id))
    if existing and any(c.method=='POST' for c in config.application.checks) and existing['environment'] not in ('staging','test','development'): raise HTTPException(422,'Synthetic mutations are restricted to staging/test/development projects')
    row=await fetch_one('UPDATE projects SET monitoring_config=$2::jsonb,updated_at=NOW() WHERE project_id=$1 RETURNING project_id',str(project_id),config.model_dump_json())
    if not row: raise HTTPException(404,'Project not found')
    await execute('UPDATE project_check_state SET next_due_at=NOW() WHERE project_id=$1',str(project_id))
    return config.model_dump()

@router.get('/projects/{project_id}/monitoring-status')
async def monitoring_status(project_id: UUID):
    from app.services.scheduler_service import config_for, interval_for, enabled, KINDS
    row=await fetch_one('SELECT * FROM projects WHERE project_id=$1',str(project_id))
    if not row: raise HTTPException(404,'Project not found')
    checks=await fetch_all("SELECT *,next_due_at<NOW()-INTERVAL '90 seconds' AND (lease_until IS NULL OR lease_until<NOW()) AS stale FROM project_check_state WHERE project_id=$1 ORDER BY check_kind",str(project_id))
    worker=await fetch_one("SELECT last_heartbeat,NOW()-last_heartbeat>INTERVAL '90 seconds' AS stale FROM monitoring_worker_state WHERE worker_name='scheduler'")
    return {'config':{**{kind:{**config_for(row).get(kind,{}),'enabled':enabled(row,kind),'interval':interval_for(row,kind)} for kind in KINDS},'policy':config_for(row).get('policy',{'failure_checks':2,'recovery_checks':2,'escalate_after':5})},'checks':[{**dict(c),'enabled':enabled(row,c['check_kind']),'stale':c['stale'] and enabled(row,c['check_kind'])} for c in checks],'scheduler':dict(worker) if worker else {'stale':True}}

class RepairProposalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    template: Literal['restart_service','laravel_cache_clear','json_patch']
    explanation: str = Field(min_length=10,max_length=2000)
    service: Optional[str] = Field(default=None,max_length=128)
    cache: str = 'optimize:clear'
    file_path: Optional[str] = Field(default=None,max_length=256)
    content: Optional[str] = Field(default=None,max_length=65536)
    rollback_on_failure: bool = False


@router.post('/incidents/{incident_id}/repair-proposal')
async def create_repair_proposal(incident_id: UUID,request: RepairProposalRequest,user: dict=Depends(require_admin)):
    from app.db import execute_returning,get_pool
    from app.services.repair_service import template_actions,propose_patch
    incident=await fetch_one('SELECT * FROM incidents WHERE incident_id=$1',str(incident_id))
    if not incident or incident['status'] in ('RESOLVED','IGNORED','REMEDIATING','ROLLED_BACK'): raise HTTPException(409,'Incident unavailable for a new proposal')
    project,connection,error=await _resolve_ssh_target(str(incident['project_id']))
    if error: raise HTTPException(409,error)
    try:
        if request.template=='json_patch':
            if not request.file_path or request.content is None: raise ValueError('File path and complete replacement JSON required')
            steps=[await propose_patch({**connection,'project_path':project.get('project_path')},request.file_path,request.content,request.rollback_on_failure)]
        else: steps=[a.to_dict() for a in template_actions(dict(project),request.template,request.service,request.cache)]
    except ValueError as exc: raise HTTPException(422,str(exc))
    pool=await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            current=await conn.fetchrow('SELECT status FROM incidents WHERE incident_id=$1 FOR UPDATE',str(incident_id))
            if current['status'] in ('RESOLVED','IGNORED','REMEDIATING','ROLLED_BACK'): raise HTTPException(409,'Incident changed during proposal preparation')
            diagnosis=await conn.fetchrow("INSERT INTO ai_diagnoses(incident_id,project_id,diagnosis,root_cause,proposed_fix,risk_level,confidence,verification_plan,rollback_plan) VALUES($1,$2,'{}',$3,$3,'MEDIUM',100,'[]',$4) RETURNING *",str(incident_id),str(incident['project_id']),request.explanation,'Restore the reviewed original only if its replacement hash still matches' if request.rollback_on_failure else 'No automatic rollback')
            proposal=await conn.fetchrow("INSERT INTO fix_proposals(incident_id,project_id,diagnosis_id,proposal_summary,detailed_steps,safety_level) VALUES($1,$2,$3,$4,$5::jsonb,'APPROVAL_REQUIRED') RETURNING *",str(incident_id),str(incident['project_id']),diagnosis['diagnosis_id'],request.explanation,json.dumps(steps))
            await conn.execute("UPDATE approvals SET status='EXPIRED' WHERE incident_id=$1 AND status IN ('PENDING','APPROVED')",str(incident_id))
            await conn.execute("INSERT INTO incident_reviews(incident_id) VALUES($1) ON CONFLICT(incident_id) DO UPDATE SET state='NEW',proposal_id=NULL,approval_id=NULL,message_id=NULL,chat_id=NULL,snapshot_hash=NULL,review_document=NULL,result_text=NULL,expires_at=NOW()+INTERVAL '24 hours',next_attempt_at=NOW(),updated_at=NOW()",str(incident_id))
    return {'proposal_id':str(proposal['proposal_id']),'diagnosis_id':str(diagnosis['diagnosis_id']),'steps':steps,'status':'AWAITING_REVIEW'}
