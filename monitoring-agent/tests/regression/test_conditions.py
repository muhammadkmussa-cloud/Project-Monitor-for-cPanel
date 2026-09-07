import os,json
from uuid import uuid4
import pytest
import pytest_asyncio
from app.services.condition_service import observe,http_conditions

@pytest_asyncio.fixture
async def project():
    if os.environ.get('PM_ISOLATED_DATABASE')!='1': pytest.skip('Disposable DB required')
    from app import db
    cid,pid=str(uuid4()),str(uuid4())
    await db.execute("INSERT INTO clients(client_id,client_name) VALUES ($1,'conditions')",cid)
    await db.execute("INSERT INTO projects(project_id,client_id,project_name) VALUES ($1,$2,'conditions')",pid,cid)
    yield pid
    await db.close_pool()

def slow(): return [{'key':'http:latency','category':'HTTP_ERROR','severity':'MEDIUM','response_time_ms':2200}]

@pytest.mark.asyncio
async def test_consecutive_failures_escalation_and_stable_recovery(project):
    from app import db
    await observe(project,'http',slow())
    await observe(project,'http',[])
    await observe(project,'http',slow())
    assert not await db.fetch_one('SELECT * FROM incidents WHERE project_id=$1',project)
    await observe(project,'http',slow())
    row=await db.fetch_one('SELECT * FROM incidents WHERE project_id=$1',project)
    assert row['severity']=='MEDIUM'
    for _ in range(3): await observe(project,'http',slow())
    assert (await db.fetch_one('SELECT severity FROM incidents WHERE project_id=$1',project))['severity']=='HIGH'
    await observe(project,'http',[])
    assert (await db.fetch_one('SELECT status FROM incidents WHERE project_id=$1',project))['status']!='RESOLVED'
    await observe(project,'http',[])
    assert (await db.fetch_one('SELECT status FROM incidents WHERE project_id=$1',project))['status']=='RESOLVED'

@pytest.mark.asyncio
async def test_rejected_episode_stays_suppressed_until_recovery(project):
    from app import db
    for _ in range(2): await observe(project,'http',slow())
    await db.execute("UPDATE incidents SET status='IGNORED' WHERE project_id=$1",project)
    for _ in range(4): await observe(project,'http',slow())
    assert (await db.fetch_one('SELECT COUNT(*) n FROM incidents WHERE project_id=$1',project))['n']==1
    for _ in range(2): await observe(project,'http',[])
    for _ in range(2): await observe(project,'http',slow())
    assert (await db.fetch_one('SELECT COUNT(*) n FROM incidents WHERE project_id=$1',project))['n']==2

@pytest.mark.asyncio
async def test_unavailable_ssl_does_not_resolve_certificate(project):
    from app import db
    from app.services.scan_service import evaluate_http
    await evaluate_http(project,{'status':'CRITICAL','http_status_code':200,'response_time_ms':100,'ssl_days_remaining':3})
    for _ in range(2): await evaluate_http(project,{'status':'DOWN','http_status_code':None,'ssl_days_remaining':None})
    row=await db.fetch_one("SELECT status FROM incidents WHERE project_id=$1 AND error_signature='http:certificate'",project)
    assert row['status']!='RESOLVED'

@pytest.mark.asyncio
async def test_legacy_incident_recovers_without_duplicate(project):
    from app import db
    from app.services.scan_service import evaluate_http
    cid=(await db.fetch_one('SELECT client_id FROM projects WHERE project_id=$1',project))['client_id']
    incident=await db.fetch_one("INSERT INTO incidents(project_id,client_id,category,severity,error_signature,raw_error_reference) VALUES ($1,$2,'HTTP_ERROR','HIGH','monitor:WARNING:200','monitoring-cycle') RETURNING incident_id",project,cid)
    await db.execute("INSERT INTO incident_conditions(project_id,check_kind,condition_key,failure_count,incident_id) VALUES ($1,'http',$2,1,$3)",project,'http:legacy:'+str(incident['incident_id']),incident['incident_id'])
    await evaluate_http(project,{'status':'WARNING','http_status_code':200,'response_time_ms':2200,'ssl_days_remaining':72})
    assert (await db.fetch_one('SELECT COUNT(*) n FROM incidents WHERE project_id=$1',project))['n']==1
    for _ in range(2): await evaluate_http(project,{'status':'HEALTHY','http_status_code':200,'response_time_ms':100,'ssl_days_remaining':72})
    assert (await db.fetch_one('SELECT status FROM incidents WHERE incident_id=$1',incident['incident_id']))['status']=='RESOLVED'

def test_conditions_separate_availability_latency_and_ssl():
    rows=http_conditions({'status':'WARNING','http_status_code':200,'response_time_ms':2100,'ssl_days_remaining':6},{})
    assert {r['key'] for r in rows}=={'http:latency','http:certificate'}
    assert next(r for r in rows if r['key']=='http:latency')['severity']=='MEDIUM'

@pytest.mark.asyncio
async def test_website_probe_does_not_buffer_response_body(monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from app.services import monitoring_service as module
    class Huge(httpx.AsyncByteStream):
        async def __aiter__(self): raise AssertionError('Availability probe must not consume the body');yield b''
    client=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:client(transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=Huge())),**kwargs))
    monkeypatch.setattr(module,'fetch_one',AsyncMock(return_value={'project_id':str(uuid4()),'client_id':str(uuid4()),'domain':'http://test.invalid','monitoring_config':{}}))
    monkeypatch.setattr(module,'execute',AsyncMock())
    result=await module.run_http_health_check(str(uuid4()))
    assert result['http_status_code']==200 and result['status']=='HEALTHY'

@pytest.mark.asyncio
async def test_recovery_preserves_running_fix_link(project):
    from app import db
    for _ in range(2): await observe(project,'http',slow())
    await db.execute("UPDATE incidents SET status='REMEDIATING' WHERE project_id=$1",project)
    for _ in range(2): await observe(project,'http',[])
    incident=await db.fetch_one('SELECT * FROM incidents WHERE project_id=$1',project)
    condition=await db.fetch_one('SELECT * FROM incident_conditions WHERE project_id=$1',project)
    assert incident['status']=='REMEDIATING'
    assert condition['incident_id']==incident['incident_id'] and condition['recovery_count']==2
