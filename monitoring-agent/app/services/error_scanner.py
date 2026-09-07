from uuid import uuid4

from app.db import execute, execute_returning, fetch_all, fetch_one
from app.services import credential_service
from app.services.log_service import log_service


def _severity(level: str, message: str) -> str:
    text = f"{level} {message}".lower()
    if "fatal" in text or "critical" in text:
        return "HIGH"
    if "exception" in text or "error" in text:
        return "MEDIUM"
    if "warning" in text or "warn" in text:
        return "LOW"
    return "LOW"


async def _load_connection(project_row, database=None):
    """Return connection kwargs (host/port/username + auth) or None."""
    cred = await credential_service.get_decrypted_credential(str(project_row["project_id"]), "ssh", connection=database)
    host = cred.get("host") if cred and cred.get("host") else project_row["server_host"]
    port = int(cred.get("port") if cred and cred.get("port") else (project_row["ssh_port"] or 22))
    username = cred.get("username") if cred and cred.get("username") else project_row["ssh_username"]
    if not host or not username:
        return None
    kwargs = {"host": host, "port": port, "username": username}
    if cred:
        if cred.get("password"):
            kwargs["password"] = cred["password"]
        if cred.get("private_key"):
            kwargs["private_key"] = cred["private_key"]
        elif cred.get("key_path"):
            kwargs["key_path"] = cred["key_path"]
    return kwargs


async def scan_project(project_id: str) -> dict:
    """Atomically ingest only new complete log lines and persist their cursors."""
    import json
    from app.db import get_pool
    from app.services.incremental_logs import read_incremental
    pool=await get_pool()
    async with pool.acquire() as db:
        async with db.transaction():
            if not await db.fetchval("SELECT pg_try_advisory_xact_lock(hashtextextended($1,1))",project_id):
                return {"success":True,"status":"already_running","created":0}
            project=await db.fetchrow('SELECT * FROM projects WHERE project_id=$1',project_id)
            if not project or not project['monitoring_enabled']:
                return {"success":False,"error":"Project missing or monitoring disabled"}
            connection=await _load_connection(dict(project), db)
            if not connection: return {"success":False,"error":"No SSH connection configured"}
            rows=await db.fetch('SELECT file_path,cursor_data FROM log_cursors WHERE project_id=$1',project_id)
            cursors={r['file_path']:json.loads(r['cursor_data']) if isinstance(r['cursor_data'],str) else r['cursor_data'] for r in rows}
            try: files=await read_incremental(dict(project),connection,cursors)
            except Exception as exc:
                return {"success":False,"error":type(exc).__name__+": log reading failed"}
            created=occurrences=0
            for file in files:
                for line in file['entries']:
                    item=log_service._parse_log_line(line)
                    if item['level'] not in ('error','warning'): continue
                    signature=log_service._generate_error_signature(line)
                    existing=await db.fetchrow("SELECT incident_id FROM incidents WHERE project_id=$1 AND error_signature=$2 AND status NOT IN ('RESOLVED','IGNORED','ROLLED_BACK') ORDER BY created_at DESC LIMIT 1",project_id,signature)
                    if existing:
                        await db.execute('UPDATE incidents SET occurrence_count=occurrence_count+1,last_seen=NOW(),updated_at=NOW() WHERE incident_id=$1',existing['incident_id'])
                    else:
                        from app.utils.redactor import redactor
                        incident=await db.fetchrow("INSERT INTO incidents(project_id,client_id,category,severity,status,error_signature,affected_component,raw_error_reference) VALUES ($1,$2,'APPLICATION_ERROR',$3,'OPEN',$4,'app-log',$5) RETURNING incident_id",project_id,project['client_id'],_severity(item['level'],line),signature,redactor.redact(line)[:1000])
                        await db.execute('INSERT INTO incident_reviews(incident_id) VALUES ($1) ON CONFLICT DO NOTHING',incident['incident_id'])
                        created+=1
                    occurrences+=1
                await db.execute('INSERT INTO log_cursors(project_id,file_path,cursor_data) VALUES ($1,$2,$3::jsonb) ON CONFLICT(project_id,file_path) DO UPDATE SET cursor_data=EXCLUDED.cursor_data,updated_at=NOW()',project_id,file['path'],json.dumps(file['cursor']))
            return {"success":not any(f.get("coverage_warning") for f in files),"warnings":[f["coverage_warning"] for f in files if f.get("coverage_warning")],"created":created,"entries":occurrences,"files":[f['path'] for f in files],"baseline_files":sum(f['baseline'] for f in files),"backlog_bytes":sum(f['backlog_bytes'] for f in files)}


async def scan_all_enabled() -> dict:
    rows = await fetch_all(
        "SELECT project_id FROM projects WHERE monitoring_enabled = true ORDER BY created_at"
    )
    results = []
    for r in rows:
        try:
            res = await scan_project(str(r["project_id"]))
            results.append({"project_id": str(r["project_id"]), **res})
        except Exception as e:
            results.append({"project_id": str(r["project_id"]), "success": False, "error": str(e)})
    return {"projects": len(rows), "results": results}
