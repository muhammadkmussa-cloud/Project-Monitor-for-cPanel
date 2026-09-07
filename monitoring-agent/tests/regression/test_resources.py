import pytest
from app.services.resource_monitor import parse_metrics,conditions,resource_command
from app.api.routes import ResourceLimit

def test_resource_metrics_and_thresholds():
    metrics=parse_metrics('cpu=85\nmemory=40\ndisk=91\ninodes=98\n')
    findings=conditions(metrics,{})
    assert {(r['key'],r['severity']) for r in findings}=={('resource:cpu','MEDIUM'),('resource:disk','CRITICAL'),('resource:inodes','CRITICAL')}
    custom={'thresholds':{'cpu':{'warning':90,'critical':99}}}
    assert all(r['key']!='resource:cpu' for r in conditions(metrics,custom))

@pytest.mark.parametrize('output',['','cpu=0\nmemory=0\ndisk=0','cpu=nan\nmemory=0\ndisk=0\ninodes=0','cpu=0\nmemory=0\ndisk=-1\ninodes=0'])
def test_missing_invalid_metrics_never_healthy(output):
    with pytest.raises(ValueError): parse_metrics(output)

def test_threshold_order_and_quoted_path():
    with pytest.raises(ValueError): ResourceLimit(warning=90,critical=80)
    assert "'/a path/$(touch evil)'" in resource_command('/a path/$(touch evil)')

def test_linux_sample_command_runs():
    import subprocess
    result=subprocess.run(resource_command('/tmp'),shell=True,capture_output=True,text=True,timeout=10,check=True)
    assert set(parse_metrics(result.stdout))=={'cpu','memory','disk','inodes'}

@pytest.mark.asyncio
async def test_resource_persistence_incident_recovery_and_ssh_failure(monkeypatch):
    import os,json
    if os.environ.get('PM_ISOLATED_DATABASE')!='1': pytest.skip('Disposable database required')
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from app import db
    from app.services import resource_monitor as resources
    cid,pid=str(uuid4()),str(uuid4())
    await db.execute("INSERT INTO clients(client_id,client_name) VALUES ($1,'resources')",cid)
    await db.execute("INSERT INTO projects(project_id,client_id,project_name,project_path) VALUES ($1,$2,'resources','/tmp')",pid,cid)
    monkeypatch.setattr(resources,'_load_connection',AsyncMock(return_value={'host':'test','port':22,'username':'test'}))
    remote=AsyncMock(return_value={'success':True,'output':'cpu=85\nmemory=40\ndisk=91\ninodes=98\n'})
    monkeypatch.setattr(resources.ssh_service,'execute_command',remote)
    result=await resources.check_resources(pid)
    for _ in range(2): await resources.evaluate_resources(pid,result)
    assert result['status']=='CRITICAL'
    assert len(await db.fetch_all('SELECT * FROM incidents WHERE project_id=$1',pid))==3
    row=await db.fetch_one("SELECT details FROM monitoring_checks WHERE project_id=$1 AND check_type='resources'",pid)
    assert json.loads(row['details'])['inodes']==98
    for _ in range(2): await resources.evaluate_resources(pid,{'conditions':[]})
    assert all(r['status']=='RESOLVED' for r in await db.fetch_all('SELECT status FROM incidents WHERE project_id=$1',pid))
    remote.return_value={'success':False,'output':''}
    with pytest.raises(RuntimeError): await resources.check_resources(pid)
    assert (await db.fetch_one('SELECT COUNT(*) n FROM monitoring_checks WHERE project_id=$1',pid))['n']==1
    await db.close_pool()

def test_connection_budget_closes_client_before_opening_channel(monkeypatch):
    from unittest.mock import MagicMock
    from app.services import ssh_service as module
    now=[0.0];client=MagicMock()
    client.connect.side_effect=lambda **kwargs:now.__setitem__(0,16.0)
    monkeypatch.setattr(module,'create_ssh_client',lambda:client)
    monkeypatch.setattr(module.time,'monotonic',lambda:now[0])
    result=module.ssh_service._execute_sync('test',22,'test','uptime',None,'test-password',None,15)
    assert not result['success']
    assert client.connect.call_args.kwargs['channel_timeout']<=15/4
    client.exec_command.assert_not_called()
    client.close.assert_called_once()

def test_stalled_channel_closes_client(monkeypatch):
    from unittest.mock import MagicMock
    from app.services import ssh_service as module
    client=MagicMock();client.exec_command.side_effect=TimeoutError('channel stalled')
    monkeypatch.setattr(module,'create_ssh_client',lambda:client)
    result=module.ssh_service._execute_sync('test',22,'test','uptime',None,'test-password',None,15)
    assert not result['success']
    assert client.exec_command.call_args.kwargs['timeout']<=15
    client.close.assert_called_once()
