"""Run only against the disposable audit database, never TEST_BASE_URL/live data."""
import os
from uuid import uuid4
import json
import pytest
import pytest_asyncio
import httpx

pytestmark=pytest.mark.skipif(os.environ.get('PM_ISOLATED_DATABASE')!='1',reason='Requires disposable database')

@pytest_asyncio.fixture
async def setup_db():
    from app import db
    from app.auth import create_token
    from app.services.rbac_service import RBACService
    client_ids=[str(uuid4()),str(uuid4())]
    users=[]
    for i,cid in enumerate(client_ids):
        await db.execute('INSERT INTO clients (client_id,client_name) VALUES ($1,$2)',cid,'Audit tenant '+str(i))
    for role,cid in [('admin',client_ids[0]),('user',client_ids[0]),('user',client_ids[1])]:
        uid=str(uuid4());email=uid+'@audit.invalid'
        await db.execute("INSERT INTO users (user_id,client_id,email,name,password_hash,role) VALUES ($1,$2,$3,'Audit User',$4,$5)",uid,cid,email,RBACService()._hash_password('audit-password-123'),role)
        users.append({'id':uid,'email':email,'token':create_token(uid,email,role),'client_id':cid})
    yield users
    await db.close_pool()

@pytest.mark.asyncio
async def test_http_roles_tenants_hashes_and_login(setup_db):
    from app.main import app
    from app import db
    admin,a,b=setup_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        for u in (a,b):
            r=await client.post('/api/v1/projects',headers={'Authorization':'Bearer '+admin['token']},json={'client_id':u['client_id'],'project_name':'tenant project'})
            assert r.status_code==201,r.text
            u['project_id']=r.json()['project_id']
        headers={'Authorization':'Bearer '+a['token']}
        r=await client.put('/api/v1/users/'+a['id'],headers=headers,params={'role':'admin'})
        assert r.status_code==403,r.text
        r=await client.get('/api/v1/projects',headers=headers)
        assert r.status_code==200,r.text
        assert all(x['client_id']==a['client_id'] for x in r.json())
        r=await client.get('/api/v1/projects/'+b['project_id'],headers=headers)
        assert r.status_code==404,r.text
        r=await client.get('/api/v1/users',headers={'Authorization':'Bearer '+admin['token']})
        assert r.status_code==200 and all('password_hash' not in x for x in r.json())
        r=await client.post('/api/v1/auth/login',json={'email':a['email'],'password':'audit-password-123'})
        assert r.status_code==200,r.text
        await db.execute("UPDATE users SET status='deleted' WHERE user_id=$1",a['id'])
        r=await client.get('/api/v1/projects',headers=headers)
        assert r.status_code==401,r.text

@pytest.mark.asyncio
async def test_settings_client_contracts_and_expired_keys(setup_db):
    from app.main import app
    from app import db
    import hashlib
    admin=setup_db[0];headers={'Authorization':'Bearer '+admin['token']}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        r=await client.post('/api/v1/clients',headers=headers,params={'client_name':'New client','contact_email':'client@audit.invalid','company_name':'First'})
        assert r.status_code==201,r.text
        cid=r.json()['client_id']
        r=await client.put('/api/v1/clients/'+cid,headers=headers,params={'company_name':'Changed','plan':'enterprise','address':'Test'})
        assert r.status_code==200 and r.json()['company']=='Changed',r.text
        assert r.json()['settings']['plan']=='enterprise'
        r=await client.get('/api/v1/clients',headers=headers,params={'plan':'enterprise'})
        assert r.status_code==200 and any(x['client_id']==cid for x in r.json()),r.text
        r=await client.put('/api/v1/settings/notifications.telegram_enabled',headers=headers,json={'value':False})
        assert r.status_code==200,r.text
        r=await client.get('/api/v1/settings',headers=headers)
        assert r.json()['notifications.telegram_enabled'] is False,r.text
        key='audit-'+str(uuid4())
        await db.execute("INSERT INTO api_keys (user_id,client_id,name,key_hash,expires_at) VALUES ($1,$2,'audit',$3,NOW()-INTERVAL '1 day')",admin['id'],admin['client_id'],hashlib.sha256(key.encode()).hexdigest())
        r=await client.get('/api/v1/projects',headers={'X-API-Key':key})
        assert r.status_code==401,r.text

@pytest.mark.asyncio
async def test_tenant_dashboard_and_disabled_project_filter(setup_db):
    from app.main import app
    from app import db
    admin,a,b=setup_db
    for user in [a,b]:
        await db.execute("INSERT INTO projects (project_id,client_id,project_name,monitoring_enabled) VALUES ($1,$2,'disabled',false)",str(uuid4()),user['client_id'])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        r=await client.get('/api/v1/projects?monitoring_enabled=true',headers={'Authorization':'Bearer '+a['token']})
        assert r.status_code==200 and r.json()==[],r.text
        for path in ['/analytics/dashboard','/analytics/incident-trends','/analytics/remediation-stats']:
            r=await client.get('/api/v1'+path,headers={'Authorization':'Bearer '+a['token']})
            assert r.status_code==200,r.text
        r=await client.get('/api/v1/analytics/dashboard?client_id='+b['client_id'],headers={'Authorization':'Bearer '+a['token']})
        assert r.status_code==404,r.text

@pytest.mark.asyncio
async def test_approval_target_and_single_execution(setup_db,monkeypatch):
    from app.main import app
    from app import db
    from app.api import routes
    from app.services.remediation_engine import remediation_engine
    from unittest.mock import AsyncMock
    admin=setup_db[0];headers={'Authorization':'Bearer '+admin['token']}
    pid,iid,did=[str(uuid4()) for _ in range(3)]
    await db.execute("INSERT INTO projects (project_id,client_id,project_name,remediation_enabled) VALUES ($1,$2,'remediation test',true)",pid,admin['client_id'])
    await db.execute("INSERT INTO incidents (incident_id,project_id,client_id,category,severity) VALUES ($1,$2,$3,'HTTP_ERROR','HIGH')",iid,pid,admin['client_id'])
    await db.execute("INSERT INTO ai_diagnoses (diagnosis_id,incident_id,project_id,diagnosis,commands_required,proposed_fix) VALUES ($1,$2,$3,'{}','[\"uname -a\"]','Inspect server')",did,iid,pid)
    execute=AsyncMock(return_value={'success':True,'executed_actions':1,'results':[]})
    monkeypatch.setattr(remediation_engine,'execute_plan',execute)
    monkeypatch.setattr(routes,'_resolve_ssh_target',AsyncMock(return_value=({'remediation_enabled':True,'project_id':pid},{'host':'test.invalid','port':22,'username':'audit'},None)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        r=await client.post('/api/v1/remediation/plan',headers=headers,json={'incident_id':iid,'diagnosis_id':did})
        assert r.status_code==200,r.text
        plan=r.json();assert plan['total_actions']==1 and plan['actions'][0]['command']=='uname -a'
        body={'incident_id':iid,'plan_id':plan['plan_id']}
        r=await client.post('/api/v1/remediation/execute',headers=headers,json=body)
        assert r.status_code==409,r.text
        execute.assert_not_called()
        r=await client.post('/api/v1/approvals',headers=headers,json={'incident_id':iid,'diagnosis_id':did,'action':'approve'})
        assert r.status_code==200,r.text
        assert r.json()['approved_at'] is not None
        r=await client.post('/api/v1/remediation/execute',headers=headers,json={**body,'server_connection':{'host':'other.invalid'}})
        assert r.status_code==422,r.text
        r=await client.post('/api/v1/remediation/execute',headers=headers,json=body)
        assert r.status_code==200 and r.json()['rolled_back'] is False,r.text
        r=await client.post('/api/v1/remediation/execute',headers=headers,json=body)
        assert r.status_code==409,r.text
        assert execute.await_count==1

@pytest.mark.asyncio
async def test_monitoring_deduplicates_and_resolves_only_its_own_incidents(setup_db,monkeypatch):
    from app import db
    from app.services import scan_service
    from unittest.mock import AsyncMock
    admin=setup_db[0];pid=str(uuid4())
    await db.execute("INSERT INTO projects (project_id,client_id,project_name) VALUES ($1,$2,'scan test')",pid,admin['client_id'])
    state={'status':'DOWN'}
    async def health(project_id):
        return {'status':state['status'] if project_id==pid else 'HEALTHY','http_status_code':503}
    monkeypatch.setattr(scan_service,'run_http_health_check',health)
    prepare=AsyncMock();monkeypatch.setattr(scan_service,'prepare_incident',prepare)
    await scan_service.evaluate_http(pid,state)
    await scan_service.evaluate_http(pid,state)
    rows=await db.fetch_all('SELECT * FROM incidents WHERE project_id=$1',pid)
    assert len(rows)==1 and rows[0]['occurrence_count']==2
    assert len(await db.fetch_all('SELECT * FROM incident_reviews WHERE incident_id=$1',rows[0]['incident_id']))==1
    state.update(status='HEALTHY',http_status_code=200,response_time_ms=100,ssl_days_remaining=72)
    for _ in range(2): await scan_service.evaluate_http(pid,state)
    row=await db.fetch_one('SELECT * FROM incidents WHERE project_id=$1',pid)
    assert row['status']=='RESOLVED' and row['resolved_at'] is not None

@pytest.mark.asyncio
async def test_disabled_client_blocks_tenant_but_keeps_platform_admin(setup_db):
    from app.main import app
    from app import db
    admin, tenant, other = setup_db
    await db.execute("UPDATE clients SET status='inactive' WHERE client_id=$1", admin['client_id'])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        for user, expected in [(admin,200),(tenant,401),(other,200)]:
            response=await client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+user['token']})
            assert response.status_code==expected,response.text
