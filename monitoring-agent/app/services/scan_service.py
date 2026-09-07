"""Scheduled monitoring with per-project locks and incident deduplication."""
import logging
from uuid import uuid4
from app.db import fetch_all, fetch_one, execute, execute_returning, get_pool
from app.services.monitoring_service import run_http_health_check

log = logging.getLogger(__name__)


async def run_cycle(force=False):
    from app.services.scheduler_service import run_due
    return await run_due(force)


async def evaluate_http(pid,health):
    from app.services.condition_service import observe,http_conditions
    from app.services.scheduler_service import config_for
    project=await fetch_one('SELECT * FROM projects WHERE project_id=$1',pid)
    findings=http_conditions(health,config_for(project))
    observed={'http:availability'}
    if health.get('response_time_ms') is not None: observed.add('http:latency')
    if health.get('ssl_days_remaining') is not None: observed.update(('http:certificate','http:certificate-check'))
    elif health.get('details',{}).get('ssl_check_error'): observed.add('http:certificate-check')
    legacy=await fetch_all("SELECT c.condition_key,i.category,i.severity FROM incident_conditions c JOIN incidents i USING(incident_id) WHERE c.project_id=$1 AND c.check_kind='http' AND c.condition_key LIKE 'http:legacy:%' AND c.incident_id IS NOT NULL",pid)
    if legacy:
        if findings:
            from app.services.condition_service import RANK
            severity=max((f['severity'] for f in findings),key=RANK.get)
            findings=[{'key':item['condition_key'],'category':item['category'],'severity':severity,'immediate':True,'observations':findings} for item in legacy]
        if health['status']=='HEALTHY': observed.update(item['condition_key'] for item in legacy)
    await observe(pid,'http',findings,observed)



async def prepare_incident(incident):
    from app.services.incident_review_service import enqueue
    await enqueue(incident)
