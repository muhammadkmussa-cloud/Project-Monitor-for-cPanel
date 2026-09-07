import httpx
import pytest
from app.services.application_monitor import run_contracts
from app.api.routes import ApplicationSchedule

def config(**kw): return ApplicationSchedule(**kw).model_dump()
def project(env='production'): return {'domain':'https://example.invalid','environment':env}

@pytest.mark.asyncio
async def test_http200_with_broken_database_fails():
    cfg=config(enabled=True,checks=[{'name':'Database','path':'/health','json_equals':{'database':'healthy'}}])
    result=await run_contracts(project(),cfg,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'database':'down'})))
    assert result['status']=='DEGRADED' and result['checks'][0]['reason']=='JSON contract failed'

@pytest.mark.asyncio
async def test_staging_login_and_authenticated_flow():
    cfg=config(enabled=True,allow_mutations=True,checks=[{'name':'Login','path':'/login','method':'POST','use_credentials':True,'capture_token_path':'token'},{'name':'Dashboard','path':'/dashboard','use_bearer_from_previous':True,'contains':'Welcome'}])
    requests=[]
    def handler(req):
        requests.append(req)
        if req.url.path=='/login': return httpx.Response(200,json={'token':'test-secret-token'})
        assert req.headers['Authorization']=='Bearer test-secret-token'
        return httpx.Response(200,text='Welcome')
    result=await run_contracts(project('staging'),cfg,{'username':'test','password':'test-password'},httpx.MockTransport(handler))
    assert result['status']=='HEALTHY' and len(requests)==2
    assert 'test-secret-token' not in str(result) and 'test-password' not in str(result)
    with pytest.raises(ValueError): await run_contracts(project(),cfg,{'password':'test'},httpx.MockTransport(handler))

@pytest.mark.parametrize('definition',[{'name':'x','path':'//other.invalid','contains':'ok'},{'name':'x','path':'/health'},{'name':'x','path':'/login','method':'POST','body':{'password':'secret'},'contains':'ok'}])
def test_unsafe_or_ineffective_contracts_rejected(definition):
    with pytest.raises(ValueError): config(enabled=True,allow_mutations=True,checks=[definition])

@pytest.mark.asyncio
async def test_no_redirect_or_later_steps_after_failure():
    cfg=config(enabled=True,checks=[{'name':'One','path':'/one','contains':'ok'},{'name':'Two','path':'/two','contains':'ok'}])
    paths=[]
    def handler(req):
        paths.append(req.url.path)
        return httpx.Response(302,headers={'Location':'https://other.invalid'})
    result=await run_contracts(project(),cfg,transport=httpx.MockTransport(handler))
    assert result['status']=='DEGRADED' and paths==['/one']
    assert result['checks'][1]['reason'].startswith('Not run')

@pytest.mark.asyncio
async def test_plain_http_cannot_capture_or_send_bearer():
    cfg=config(enabled=True,checks=[{'name':'Token','path':'/token','capture_token_path':'token'}])
    with pytest.raises(ValueError,match='HTTPS'):
        await run_contracts({'domain':'http://example.invalid','environment':'staging'},cfg)

@pytest.mark.asyncio
async def test_scheduler_does_not_replay_application_post_on_later_failure(monkeypatch):
    import os,json
    if os.environ.get('PM_ISOLATED_DATABASE')!='1': pytest.skip('Disposable database required')
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from app import db
    from app.services import scheduler_service as scheduler
    cid,pid=str(uuid4()),str(uuid4())
    await db.execute('UPDATE projects SET monitoring_enabled=false')
    await db.execute('UPDATE project_check_state SET lease_until=NULL')
    await db.execute("INSERT INTO clients(client_id,client_name) VALUES ($1,'mutation test')",cid)
    cfg={'http':{'enabled':False},'logs':{'enabled':False},'resources':{'enabled':False},'application':{'enabled':True,'interval':300}}
    await db.execute("INSERT INTO projects(project_id,client_id,project_name,monitoring_config) VALUES ($1,$2,'mutation test',$3::jsonb)",pid,cid,json.dumps(cfg))
    calls=[]
    async def probe(*args):
        calls.append('successful POST')
        raise RuntimeError('later persistence failed')
    monkeypatch.setattr(scheduler,'probe',probe)
    result=await scheduler.run_due()
    assert result['projects'][0]['status']=='error' and calls==['successful POST']
    await db.close_pool()
