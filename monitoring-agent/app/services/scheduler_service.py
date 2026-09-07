"""Persistent schedules with cluster-wide leases and bounded workers."""
import asyncio
import json
import logging
from uuid import uuid4
from app.db import get_pool,fetch_all,fetch_one,execute

log=logging.getLogger(__name__)
CONCURRENCY=4
TIMEOUT=60
KINDS=('http','logs','resources','application')


def config_for(project):
    value=project.get('monitoring_config') or {}
    return json.loads(value) if isinstance(value,str) else value


def interval_for(project,kind):
    return config_for(project).get(kind,{}).get('interval',project['check_interval'] if kind=='http' else 600 if kind=='logs' else 300)


def enabled(project,kind):
    return project['monitoring_enabled'] and config_for(project).get(kind,{}).get('enabled',kind in ('http','logs','resources'))


async def sync_schedules():
    projects=await fetch_all('SELECT * FROM projects WHERE monitoring_enabled=true')
    for p in projects:
        for kind in KINDS:
            if enabled(p,kind):
                await execute('INSERT INTO project_check_state(project_id,check_kind) VALUES ($1,$2) ON CONFLICT DO NOTHING',p['project_id'],kind)


async def claim(force=False, excluded=None):
    pool=await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock(70702070)')
            count=await conn.fetchval('SELECT COUNT(*) FROM project_check_state WHERE lease_until>NOW()')
            if count>=CONCURRENCY: return None
            rows=await conn.fetch("SELECT s.*,p.monitoring_config,p.check_interval,p.monitoring_enabled FROM project_check_state s JOIN projects p USING(project_id) WHERE p.monitoring_enabled=true AND s.check_kind=ANY($2::text[]) AND COALESCE((p.monitoring_config->s.check_kind->>'enabled')::boolean,s.check_kind IN ('http','logs','resources')) AND (s.lease_until IS NULL OR s.lease_until<=NOW()) AND ($1::boolean OR s.next_due_at<=NOW()) ORDER BY s.next_due_at LIMIT 100",force,list(KINDS))
            for row in rows:
                key=(str(row['project_id']),row['check_kind'])
                if key in (excluded or set()) or row['check_kind'] not in KINDS or not enabled(row,row['check_kind']): continue
                token=uuid4()
                await conn.execute("UPDATE project_check_state SET lease_token=$3,lease_until=NOW()+INTERVAL '90 seconds',last_started_at=NOW() WHERE project_id=$1 AND check_kind=$2",row['project_id'],row['check_kind'],token)
                return {**dict(row),'lease_token':token}
    return None


async def probe(project_id,kind):
    if kind=='http':
        from app.services.monitoring_service import run_http_health_check
        return await run_http_health_check(project_id)
    if kind=='logs':
        from app.services.error_scanner import scan_project
        return await scan_project(project_id)
    if kind=='resources':
        from app.services.resource_monitor import check_resources
        return await check_resources(project_id)
    if kind=='application':
        from app.services.application_monitor import check_application
        return await check_application(project_id)
    raise ValueError('Unknown check kind')


async def report_collector_error(job,error):
    pid=str(job['project_id']);signature='monitoring-unavailable:'+job['check_kind']
    pool=await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,7))',pid+signature)
            incident=await conn.fetchrow("SELECT incident_id FROM incidents WHERE project_id=$1 AND error_signature=$2 AND status NOT IN ('RESOLVED','IGNORED','ROLLED_BACK')",pid,signature)
            if not incident:
                project=await conn.fetchrow('SELECT client_id FROM projects WHERE project_id=$1',pid)
                incident=await conn.fetchrow("INSERT INTO incidents(project_id,client_id,category,severity,error_signature,affected_component,raw_error_reference) VALUES ($1,$2,'UNKNOWN','HIGH',$3,$4,$5) RETURNING *",pid,project['client_id'],signature,'monitoring:'+job['check_kind'],error)
                await conn.execute('INSERT INTO incident_reviews(incident_id) VALUES ($1) ON CONFLICT DO NOTHING',incident['incident_id'])


async def run_job(job):
    pid=str(job['project_id']);kind=job['check_kind']
    result={};error=None
    async def work():
        nonlocal result
        last=None
        attempt_limit=1 if kind=='application' else 2
        for attempt in range(attempt_limit):
            try:
                result=await probe(pid,kind)
                if result.get('success') is False or result.get('status')=='UNKNOWN': raise RuntimeError('Check unavailable')
                if result.get('status')=='DOWN' and attempt+1<attempt_limit:
                    await asyncio.sleep(1); continue
                break
            except Exception as exc:
                last=exc
                if attempt+1<attempt_limit: await asyncio.sleep(1)
                else: raise last
        current=await fetch_one('SELECT lease_token,lease_until>NOW() AS valid FROM project_check_state WHERE project_id=$1 AND check_kind=$2',pid,kind)
        if not current or current['lease_token']!=job['lease_token'] or not current['valid']: return False
        if kind=='http':
            from app.services.scan_service import evaluate_http
            await evaluate_http(pid,result)
        if kind=='resources':
            from app.services.resource_monitor import evaluate_resources
            await evaluate_resources(pid,result)
        if kind=='application':
            from app.services.application_monitor import evaluate_application
            await evaluate_application(pid,result)
        await execute("UPDATE incidents SET status='RESOLVED',resolved_at=NOW(),updated_at=NOW() WHERE project_id=$1 AND error_signature=$2 AND status NOT IN ('RESOLVED','IGNORED','ROLLED_BACK')",pid,'monitoring-unavailable:'+kind)
        return True
    try:
        valid=await asyncio.wait_for(work(),timeout=TIMEOUT)
        if not valid: return {'project_id':pid,'kind':kind,'status':'superseded'}
    except Exception as exc:
        error=type(exc).__name__+': '+kind+' monitoring unavailable'
        current=await fetch_one('SELECT lease_token,lease_until>NOW() AS valid FROM project_check_state WHERE project_id=$1 AND check_kind=$2',pid,kind)
        if not current or current['lease_token']!=job['lease_token'] or not current['valid']: return {'project_id':pid,'kind':kind,'status':'superseded'}
        if job['consecutive_errors']+1>=2:
            try: await asyncio.wait_for(report_collector_error(job,error),timeout=5)
            except Exception: log.warning('Could not report collector failure; health watcher will retry')
    row=await fetch_one("UPDATE project_check_state SET lease_until=NULL,lease_token=NULL,next_due_at=NOW()+make_interval(secs=>$4),last_completed_at=NOW(),last_success_at=CASE WHEN $5::text IS NULL THEN NOW() ELSE last_success_at END,consecutive_errors=CASE WHEN $5::text IS NULL THEN 0 ELSE consecutive_errors+1 END,last_error=$5,last_result=$6::jsonb WHERE project_id=$1 AND check_kind=$2 AND lease_token=$3 RETURNING *",pid,kind,job['lease_token'],interval_for(job,kind),error,json.dumps(result,default=str))
    if not row: return {'project_id':pid,'kind':kind,'status':'superseded'}
    return {'project_id':pid,'kind':kind,'status':'error' if error else result.get('status','completed')}


async def run_due(force=False):
    await sync_schedules()
    seen=set();results=[]
    # One bounded batch per invocation; later checks remain due for the next tick.
    for _ in range(CONCURRENCY):
        job=await claim(force,seen)
        if not job: break
        seen.add((str(job['project_id']),job['check_kind']))
        results.append(job)
    return {'status':'completed','projects':await asyncio.gather(*(run_job(job) for job in results))}


async def scheduler_loop():
    while True:
        try:
            await execute("INSERT INTO monitoring_worker_state(worker_name) VALUES ('scheduler') ON CONFLICT(worker_name) DO UPDATE SET last_heartbeat=NOW()")
            await run_due()
        except Exception: log.exception('Monitoring scheduler failed')
        await asyncio.sleep(5)


async def check_scheduler_health():
    state=await fetch_one("SELECT NOW()-last_heartbeat>INTERVAL '90 seconds' AS stale FROM monitoring_worker_state WHERE worker_name='scheduler'")
    if not state or state['stale']:
        for project in await fetch_all('SELECT project_id FROM projects WHERE monitoring_enabled=true'):
            await report_collector_error({'project_id':project['project_id'],'check_kind':'scheduler'},'Scheduler heartbeat is stale')
    elif state:
        await execute("UPDATE incidents SET status='RESOLVED',resolved_at=NOW(),updated_at=NOW() WHERE error_signature='monitoring-unavailable:scheduler' AND status NOT IN ('RESOLVED','IGNORED','ROLLED_BACK')")

    failures=await fetch_all("SELECT s.*,p.monitoring_enabled,p.monitoring_config FROM project_check_state s JOIN projects p USING(project_id) WHERE p.monitoring_enabled=true AND (consecutive_errors>=2 OR (next_due_at<NOW()-INTERVAL '90 seconds' AND (lease_until IS NULL OR lease_until<NOW())))")
    for job in failures:
        if enabled(job,job['check_kind']): await report_collector_error(job,job['last_error'] or 'Monitoring unavailable')
