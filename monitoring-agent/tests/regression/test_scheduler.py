import asyncio
import os
import json
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from app.services import scheduler_service as scheduler

@pytest_asyncio.fixture
async def project():
    if os.environ.get('PM_ISOLATED_DATABASE')!='1': pytest.skip('Disposable database required')
    from app import db
    cid,pid=str(uuid4()),str(uuid4())
    await db.execute("UPDATE projects SET monitoring_enabled=false")
    await db.execute("UPDATE project_check_state SET lease_until=NULL")
    await db.execute("INSERT INTO clients(client_id,client_name) VALUES ($1,'scheduler')",cid)
    await db.execute("INSERT INTO projects(project_id,client_id,project_name,monitoring_config) VALUES ($1,$2,'scheduler','{\"http\":{\"enabled\":true,\"interval\":30},\"logs\":{\"enabled\":false,\"interval\":60},\"resources\":{\"enabled\":false}}')",pid,cid)
    yield pid
    await db.close_pool()

@pytest.mark.asyncio
async def test_schedule_due_and_no_overlap(project,monkeypatch):
    from app import db
    probe=AsyncMock(return_value={'status':'HEALTHY','http_status_code':200,'response_time_ms':100,'ssl_days_remaining':72})
    monkeypatch.setattr(scheduler,'probe',probe)
    results=await asyncio.gather(scheduler.run_due(),scheduler.run_due())
    assert sum(len(r['projects']) for r in results)==1
    assert probe.await_count==1
    assert (await scheduler.run_due())['projects']==[]
    state=await db.fetch_one('SELECT * FROM project_check_state WHERE project_id=$1',project)
    assert state['last_success_at'] and state['lease_until'] is None

@pytest.mark.asyncio
async def test_collector_retry_and_alert(project,monkeypatch):
    from app import db
    probe=AsyncMock(side_effect=OSError('down'));monkeypatch.setattr(scheduler,'probe',probe)
    await scheduler.run_due(force=True)
    await scheduler.run_due(force=True)
    assert probe.await_count==4
    assert await db.fetch_one("SELECT * FROM incidents WHERE project_id=$1 AND error_signature='monitoring-unavailable:http'",project)
    monkeypatch.setattr(scheduler,'probe',AsyncMock(return_value={'status':'HEALTHY','http_status_code':200,'response_time_ms':100,'ssl_days_remaining':72}))
    await scheduler.run_due(force=True)
    assert (await db.fetch_one("SELECT status FROM incidents WHERE project_id=$1 AND error_signature='monitoring-unavailable:http'",project))['status']=='RESOLVED'

@pytest.mark.asyncio
async def test_expired_lease_reclaimed_and_old_completion_fenced(project,monkeypatch):
    from app import db
    await scheduler.sync_schedules();old=await scheduler.claim()
    await db.execute("UPDATE project_check_state SET lease_until=NOW()-INTERVAL '1 second' WHERE project_id=$1",project)
    current=await scheduler.claim()
    assert old['lease_token']!=current['lease_token']
    monkeypatch.setattr(scheduler,'probe',AsyncMock(return_value={'status':'HEALTHY','http_status_code':200,'response_time_ms':100,'ssl_days_remaining':72}))
    assert (await scheduler.run_job(old))['status']=='superseded'
    assert (await scheduler.run_job(current))['status']=='HEALTHY'

@pytest.mark.asyncio
async def test_bounded_global_claims(project):
    from app import db
    cid=(await db.fetch_one('SELECT client_id FROM projects WHERE project_id=$1',project))['client_id']
    for _ in range(8): await db.execute("INSERT INTO projects(client_id,project_name) VALUES ($1,'parallel')",cid)
    await scheduler.sync_schedules()
    jobs=await asyncio.gather(*(scheduler.claim() for _ in range(12)))
    assert sum(job is not None for job in jobs)==scheduler.CONCURRENCY

@pytest.mark.asyncio
async def test_config_api_validation(project):
    from app.api.routes import MonitoringConfig,set_monitoring_config,monitoring_status
    from pydantic import ValidationError
    with pytest.raises(ValidationError): MonitoringConfig(http={'interval':0})
    config=MonitoringConfig(http={'interval':45},logs={'enabled':False,'interval':90})
    await set_monitoring_config(project,config,user={'role':'admin'})
    result=await monitoring_status(project)
    assert result['config']['http']['interval']==45

@pytest.mark.asyncio
async def test_disabled_backlog_does_not_starve_enabled_job(project):
    from app import db
    cid=(await db.fetch_one('SELECT client_id FROM projects WHERE project_id=$1',project))['client_id']
    for _ in range(105):
        p=await db.fetch_one("INSERT INTO projects(client_id,project_name,monitoring_config) VALUES ($1,'disabled','{\"http\":{\"enabled\":false},\"logs\":{\"enabled\":false},\"resources\":{\"enabled\":false}}') RETURNING project_id",cid)
        await db.execute("INSERT INTO project_check_state(project_id,check_kind,next_due_at) VALUES ($1,'http',NOW()-INTERVAL '1 day')",p['project_id'])
    await scheduler.sync_schedules()
    assert str((await scheduler.claim())['project_id'])==project

@pytest.mark.asyncio
async def test_lease_covers_processing_and_processing_failure(project,monkeypatch):
    from app import db
    from app.services import scan_service
    monkeypatch.setattr(scheduler,'probe',AsyncMock(return_value={'status':'HEALTHY','http_status_code':200,'response_time_ms':100,'ssl_days_remaining':72}))
    async def evaluation(pid,result):
        assert await scheduler.claim(force=True) is None
        raise RuntimeError('incident processing failed')
    monkeypatch.setattr(scan_service,'evaluate_http',evaluation)
    assert (await scheduler.run_due())['projects'][0]['status']=='error'
    row=await db.fetch_one('SELECT * FROM project_check_state WHERE project_id=$1',project)
    assert row['last_error'] and row['last_success_at'] is None

@pytest.mark.asyncio
async def test_missing_heartbeat_alerts_and_effective_config(project):
    from app import db
    from app.api.routes import monitoring_status,MonitoringConfig,set_monitoring_config
    await db.execute('DELETE FROM monitoring_worker_state')
    await scheduler.check_scheduler_health()
    assert await db.fetch_one("SELECT * FROM incidents WHERE project_id=$1 AND error_signature='monitoring-unavailable:scheduler'",project)
    await db.execute("UPDATE projects SET monitoring_config='{}',check_interval=120 WHERE project_id=$1",project)
    before=await monitoring_status(project)
    assert before['config']['http']['interval']==120
    await set_monitoring_config(project,MonitoringConfig(**before['config']),user={'role':'admin'})
    assert (await monitoring_status(project))['config']['http']['interval']==120

@pytest.mark.asyncio
async def test_timeout_releases_lease_and_reports_failure(project,monkeypatch):
    from app import db
    async def hang(*args): await asyncio.sleep(10)
    monkeypatch.setattr(scheduler,'TIMEOUT',0.02)
    monkeypatch.setattr(scheduler,'probe',hang)
    assert (await scheduler.run_due())['projects'][0]['status']=='error'
    row=await db.fetch_one('SELECT * FROM project_check_state WHERE project_id=$1',project)
    assert row['lease_until'] is None and row['last_error'].startswith('TimeoutError')

def test_sftp_deadline_blocks_further_io():
    from app.services.incremental_logs import DeadlineSFTP
    import time
    with pytest.raises(TimeoutError): DeadlineSFTP(object(),time.monotonic()-1).stat('log')
