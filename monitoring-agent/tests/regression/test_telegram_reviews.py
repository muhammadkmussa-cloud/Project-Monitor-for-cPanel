import json
import os
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from app.services import incident_review_service as review
from app.services.log_service import log_service


def test_exception_detection_and_metadata_redaction():
    assert log_service._parse_log_line('Unhandled Exception: checkout failed')['level']=='error'
    data=review.clean({'metadata':{'password':'secret','nested':{'api_key':'secret'}},'server_host':'192.0.2.1','url':'https://user:secret@example.invalid/path'})
    assert 'secret' not in json.dumps(data)
    assert data['server_host']=='192.0.2.1'


@pytest_asyncio.fixture
async def pending(monkeypatch):
    if os.environ.get('PM_ISOLATED_DATABASE')!='1': pytest.skip('Disposable DB required')
    from app import db
    cid,pid,iid,did,prop=[str(uuid4()) for _ in range(5)]
    await db.execute("INSERT INTO clients(client_id,client_name) VALUES ($1,'Review test')",cid)
    await db.execute("INSERT INTO projects(project_id,client_id,project_name,remediation_enabled,server_host) VALUES ($1,$2,'Test project',true,'example.invalid')",pid,cid)
    await db.execute("INSERT INTO incidents(incident_id,project_id,client_id,category,severity) VALUES ($1,$2,$3,'HTTP_ERROR','HIGH')",iid,pid,cid)
    await db.execute("INSERT INTO ai_diagnoses(diagnosis_id,incident_id,project_id,diagnosis,proposed_fix,commands_required) VALUES ($1,$2,$3,'{}','Inspect server','[\"uname -a\"]')",did,iid,pid)
    await db.execute("INSERT INTO fix_proposals(proposal_id,incident_id,diagnosis_id,project_id,proposal_summary,detailed_steps) VALUES ($1,$2,$3,$4,'Inspect server','[{\"action_type\":\"run_command\",\"description\":\"Inspect\",\"command\":\"uname -a\",\"requires_approval\":true,\"safety_level\":\"safe\"}]')",prop,iid,did,pid)
    await review.enqueue({'incident_id':iid})
    await review.enqueue({'incident_id':iid})
    row=await db.fetch_one('SELECT * FROM incident_reviews WHERE incident_id=$1',iid)
    await review.prepare(row)
    monkeypatch.setattr(review.telegram_service,'chat_id','123')
    monkeypatch.setattr(review.telegram_service,'send_review',AsyncMock(return_value={'success':True,'message_id':99}))
    row=await db.fetch_one('SELECT * FROM incident_reviews WHERE incident_id=$1',iid)
    await review.deliver(row)
    row=await db.fetch_one('SELECT * FROM incident_reviews WHERE incident_id=$1',iid)
    yield dict(row)
    await db.close_pool()

def query(row,action='a',owner=123,message=99):
    return {'id':'test','data':'pm:'+action+':'+str(row['review_id']),'from':{'id':owner},'message':{'message_id':message,'chat':{'id':123,'type':'private'}}}

@pytest.mark.asyncio
async def test_owner_message_binding_and_single_decision(pending):
    from app import db
    row=pending
    assert 'Only' in await review.decide(query(row,owner=999))
    assert 'does not match' in await review.decide(query(row,message=98))
    assert 'Approved' in await review.decide(query(row))
    assert 'already handled' in await review.decide(query(row))
    assert 'already handled' in await review.decide(query(row,action='r'))
    result=await db.fetch_one('SELECT COUNT(*) n FROM approvals WHERE proposal_id=$1',str(row['proposal_id']))
    assert result['n']==1

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['expired','resolved','target','proposal'])
async def test_invalid_review_never_approves(pending,change):
    from app import db
    row=pending
    if change=='expired': await db.execute("UPDATE incident_reviews SET expires_at=NOW()-INTERVAL '1 minute' WHERE review_id=$1",str(row['review_id']))
    if change=='resolved': await db.execute("UPDATE incidents SET status='RESOLVED' WHERE incident_id=$1",str(row['incident_id']))
    if change=='target': await db.execute("UPDATE projects SET server_host='changed.invalid' WHERE project_id=(SELECT project_id FROM incidents WHERE incident_id=$1)",str(row['incident_id']))
    if change=='proposal': await db.execute("UPDATE fix_proposals SET proposal_summary='changed' WHERE proposal_id=$1",str(row['proposal_id']))
    assert not (await review.decide(query(row))).startswith('Approved')
    assert not await db.fetch_one('SELECT * FROM approvals WHERE proposal_id=$1',str(row['proposal_id']))

@pytest.mark.asyncio
async def test_rejection_does_not_execute(pending,monkeypatch):
    from app import db
    from app.api import routes
    executor=AsyncMock();monkeypatch.setattr(routes,'execute_remediation',executor)
    assert 'Rejected' in await review.decide(query(pending,action='r'))
    row=await db.fetch_one('SELECT * FROM incident_reviews WHERE review_id=$1',str(pending['review_id']))
    monkeypatch.setattr(review.telegram_service,'send_message',AsyncMock(return_value={'success':True}))
    await review.process_one(row)
    executor.assert_not_called()

@pytest.mark.asyncio
async def test_delivery_failure_remains_retryable(pending,monkeypatch):
    from app import db
    row=pending
    await db.execute("UPDATE incident_reviews SET state='READY' WHERE review_id=$1",str(row['review_id']))
    monkeypatch.setattr(review.telegram_service,'send_review',AsyncMock(return_value={'success':False}))
    with pytest.raises(RuntimeError): await review.deliver(row)
    fresh=await db.fetch_one('SELECT state FROM incident_reviews WHERE review_id=$1',str(row['review_id']))
    assert fresh['state']=='READY'

@pytest.mark.asyncio
async def test_approved_plan_executes_once(pending,monkeypatch):
    from app import db
    from app.api import routes
    from app.services.remediation_engine import remediation_engine
    executor=AsyncMock(return_value={'success':True,'executed_actions':1,'results':[]})
    monkeypatch.setattr(remediation_engine,'execute_plan',executor)
    monkeypatch.setattr(routes,'_resolve_ssh_target',AsyncMock(return_value=({'remediation_enabled':True,'project_id':str((await db.fetch_one('SELECT project_id FROM incidents WHERE incident_id=$1',str(pending['incident_id'])))['project_id'])},{'host':'example.invalid','username':'test'},None)))
    await review.decide(query(pending))
    row=await db.fetch_one('SELECT * FROM incident_reviews WHERE review_id=$1',str(pending['review_id']))
    await review.run_approved(row)
    await review.run_approved(row)
    assert executor.await_count==1


@pytest.mark.asyncio
async def test_manual_proposal_never_executes(pending,monkeypatch):
    from app import db
    from app.api import routes
    document=review.decoded(pending['review_document']);document['executable']=False
    await db.execute('UPDATE incident_reviews SET review_document=$2::jsonb WHERE review_id=$1',str(pending['review_id']),json.dumps(document))
    assert 'manual work' in await review.decide(query(pending))
    row=await db.fetch_one('SELECT * FROM incident_reviews WHERE review_id=$1',str(pending['review_id']))
    executor=AsyncMock();monkeypatch.setattr(routes,'execute_remediation',executor)
    await review.run_approved(row)
    executor.assert_not_called()

@pytest.mark.asyncio
async def test_log_paths_are_shell_quoted(monkeypatch):
    from app.services.ssh_service import ssh_service
    execute=AsyncMock(return_value={'success':True,'output':''})
    monkeypatch.setattr(ssh_service,'execute_command',execute)
    await log_service.read_project_error_log('test',22,'test','$(touch /tmp/injected)','/a path/$(id)',lines=5)
    command=execute.call_args.args[3]
    import shlex
    assert shlex.quote('/a path/$(id)/error_log') in command
    assert "'logs/$(touch /tmp/injected).error.log'" in command

@pytest.mark.asyncio
async def test_execution_uses_reviewed_project_directory(monkeypatch):
    from app.services.ssh_service import ssh_service
    from app.services.remediation_engine import remediation_engine
    execute=AsyncMock(return_value={'success':True,'output':'','error':'','exit_code':0})
    monkeypatch.setattr(ssh_service,'execute_command',execute)
    await remediation_engine._execute_remote_command('php artisan cache:clear',{'host':'example.invalid','username':'test','project_path':'/a path/$(id)'})
    assert execute.call_args.kwargs['command']=="cd -- '/a path/$(id)' && php artisan cache:clear"
    assert 'project_path' not in execute.call_args.kwargs

@pytest.mark.asyncio
async def test_plain_text_telegram_omits_parse_mode(monkeypatch):
    import httpx
    from app.services.telegram_service import TelegramService
    from app.services import settings_service
    service=TelegramService();service.enabled=True;service.bot_token='test-only';service.chat_id='123'
    monkeypatch.setattr(settings_service,'read_setting',AsyncMock(return_value=True))
    payloads=[]
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200,json={'ok':True,'result':{'message_id':99}})
    factory=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:factory(transport=httpx.MockTransport(handler),**kwargs))
    assert (await service.send_message('Literal <text>',parse_mode=None))['success']
    assert 'parse_mode' not in payloads[0]
    assert payloads[0]['text']=='Literal <text>'
