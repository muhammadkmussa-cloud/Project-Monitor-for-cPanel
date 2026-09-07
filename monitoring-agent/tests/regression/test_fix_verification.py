import pytest
from unittest.mock import AsyncMock
from app.services import incident_verification as v

@pytest.mark.asyncio
async def test_requires_stable_original_condition(monkeypatch):
    project={'project_id':'test','monitoring_config':{}}
    sample=AsyncMock(side_effect=[(True,{}),(False,{})]);monkeypatch.setattr(v,'sample',sample)
    monkeypatch.setattr(v.asyncio,'sleep',AsyncMock())
    result=await v.verify({'error_signature':'http:latency'},project)
    assert result['outcome']=='STILL_FAILING' and sample.await_count==2
    sample.side_effect=[(True,{}),(True,{})]
    assert (await v.verify({'error_signature':'http:latency'},project))['outcome']=='VERIFIED'

@pytest.mark.asyncio
async def test_missing_measurement_and_log_reproduction_unavailable(monkeypatch):
    from app.services import monitoring_service
    monkeypatch.setattr(monitoring_service,'run_http_health_check',AsyncMock(return_value={'status':'DOWN','http_status_code':None}))
    assert (await v.verify({'error_signature':'http:certificate'},{'project_id':'test'}))['outcome']=='UNAVAILABLE'
    assert (await v.verify({'error_signature':'a-log-hash'},{'project_id':'test'}))['outcome']=='UNAVAILABLE'

@pytest.mark.asyncio
async def test_frozen_http_target_and_thresholds(monkeypatch):
    from app.services import monitoring_service
    probe=AsyncMock(return_value={'status':'WARNING','http_status_code':200,'response_time_ms':2500})
    monkeypatch.setattr(monitoring_service,'run_http_health_check',probe)
    project={'project_id':'test','health_check_url':'https://reviewed.invalid','monitoring_config':{'http':{'warning_ms':2000}}}
    result=await v.verify({'error_signature':'http:latency'},project)
    assert result['outcome']=='STILL_FAILING'
    assert probe.call_args.kwargs['project_snapshot']==project

@pytest.mark.asyncio
async def test_application_verification_never_reloads_or_posts(monkeypatch):
    from app.services import application_monitor as app
    monkeypatch.setattr(app,'fetch_one',AsyncMock(side_effect=AssertionError('Must not reload mutable config')))
    probe=AsyncMock(return_value={'status':'HEALTHY'});monkeypatch.setattr(app,'run_contracts',probe)
    project={'project_id':'test','monitoring_config':{'application':{'checks':[{'method':'GET'}]}}}
    monkeypatch.setattr(v.asyncio,'sleep',AsyncMock())
    assert (await v.verify({'error_signature':'application:contract'},project))['outcome']=='VERIFIED'
    assert probe.call_args.args[1]['checks'][0]['method']=='GET'
    project['monitoring_config']['application']['checks'][0]['method']='POST'
    probe.reset_mock()
    assert (await v.verify({'error_signature':'application:contract'},project))['outcome']=='UNAVAILABLE'
    probe.assert_not_called()

@pytest.mark.asyncio
async def test_stops_after_failed_action(monkeypatch):
    from app.services.remediation_engine import remediation_engine as engine,RemediationAction
    remote=AsyncMock(return_value={'success':False,'error':'failed'})
    monkeypatch.setattr(engine,'_execute_command',remote)
    result=await engine.execute_plan('test',[RemediationAction('run_command','test',command='uptime'),RemediationAction('run_command','test',command='df -h')],approval_status='approved',server_connection={'host':'test'})
    assert not result['success'] and remote.await_count==1
    assert result['results'][1]['status']=='not_run'

from tests.regression.test_telegram_reviews import pending,query

@pytest.mark.asyncio
async def test_baseline_already_healthy_skips_commands(pending,monkeypatch):
    from app import db
    from app.api import routes
    from app.services import incident_review_service as review
    from app.services.remediation_engine import remediation_engine
    iid=str(pending['incident_id'])
    incident=await db.fetch_one('SELECT * FROM incidents WHERE incident_id=$1',iid)
    project=dict(await db.fetch_one('SELECT * FROM projects WHERE project_id=$1',str(incident['project_id'])))
    monkeypatch.setattr(routes,'_resolve_ssh_target',AsyncMock(return_value=(project,{'host':'test'},None)))
    monkeypatch.setattr(v,'verify',AsyncMock(return_value={'outcome':'VERIFIED','evidence':[{},{}]}))
    executor=AsyncMock();monkeypatch.setattr(remediation_engine,'execute_plan',executor)
    await review.decide(query(pending))
    row=await db.fetch_one('SELECT * FROM incident_reviews WHERE review_id=$1',str(pending['review_id']))
    await review.run_approved(row)
    executor.assert_not_called()
    run=await db.fetch_one('SELECT * FROM remediation_runs WHERE incident_id=$1',iid)
    assert run['baseline'] and run['status']=='COMPLETED'
    assert (await db.fetch_one('SELECT status FROM incidents WHERE incident_id=$1',iid))['status']=='RESOLVED'

@pytest.mark.asyncio
async def test_closed_state_race_blocks_commands(pending,monkeypatch):
    from app import db
    from app.api import routes
    from app.services import incident_review_service as review
    from app.services.remediation_engine import remediation_engine
    iid=str(pending['incident_id'])
    incident=await db.fetch_one('SELECT * FROM incidents WHERE incident_id=$1',iid)
    project=dict(await db.fetch_one('SELECT * FROM projects WHERE project_id=$1',str(incident['project_id'])))
    async def changed(pid):
        await db.execute("UPDATE incidents SET status='RESOLVED' WHERE incident_id=$1",iid)
        return project,{'host':'test'},None
    monkeypatch.setattr(routes,'_resolve_ssh_target',changed)
    executor=AsyncMock();monkeypatch.setattr(remediation_engine,'execute_plan',executor)
    await review.decide(query(pending))
    row=await db.fetch_one('SELECT * FROM incident_reviews WHERE review_id=$1',str(pending['review_id']))
    await review.run_approved(row)
    executor.assert_not_called()
    assert (await db.fetch_one('SELECT status FROM incidents WHERE incident_id=$1',iid))['status']=='RESOLVED'

@pytest.mark.asyncio
async def test_atomic_record_failure_and_restart_verification_only(pending,monkeypatch):
    import json
    from app import db
    from app.services import incident_review_service as review
    iid=str(pending['incident_id'])
    incident=dict(await db.fetch_one('SELECT * FROM incidents WHERE incident_id=$1',iid))
    project=dict(await db.fetch_one('SELECT * FROM projects WHERE project_id=$1',str(incident['project_id'])))
    await db.execute("UPDATE incidents SET status='REMEDIATING' WHERE incident_id=$1",iid)
    run=await db.fetch_one("INSERT INTO remediation_runs(incident_id,project_id,proposal_id,status,started_at,execution_finished_at,commands_succeeded,verification_context) VALUES($1,$2,$3,'IN_PROGRESS',NOW(),NOW(),true,$4::jsonb) RETURNING *",iid,str(project['project_id']),str(pending['proposal_id']),json.dumps({'incident':incident,'project':project},default=str))
    result={'outcome':'VERIFIED','evidence':[{},{}]}
    await db.execute("CREATE FUNCTION step6_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Injected completion failure'; END $$")
    await db.execute("CREATE TRIGGER step6_fail BEFORE UPDATE ON remediation_runs FOR EACH ROW EXECUTE FUNCTION step6_fail()")
    try:
        with pytest.raises(Exception,match='Injected completion failure'): await v.record(run,incident,project,result,True)
        assert not await db.fetch_one('SELECT * FROM verification_runs WHERE run_id=$1',str(run['run_id']))
        assert (await db.fetch_one('SELECT status FROM incidents WHERE incident_id=$1',iid))['status']=='REMEDIATING'
    finally:
        await db.execute('DROP TRIGGER step6_fail ON remediation_runs')
        await db.execute('DROP FUNCTION step6_fail()')
    probe=AsyncMock(return_value=result);monkeypatch.setattr(v,'verify',probe)
    assert 'verified healthy' in await review.recover_run(dict(run))
    assert 'verified healthy' in await review.recover_run(dict(run))
    assert probe.await_count==1
    assert (await db.fetch_one('SELECT status FROM remediation_runs WHERE run_id=$1',str(run['run_id'])))['status']=='COMPLETED'

@pytest.mark.asyncio
async def test_resource_verifies_exact_encrypted_connection(monkeypatch):
    import json
    from app.services import resource_monitor as resources
    from app.services.credential_service import encrypt_value
    frozen={'host':'reviewed.invalid','username':'reviewed','password':'not-printed'}
    probe=AsyncMock(return_value={'metrics':{'cpu':90},'conditions':[{'key':'resource:cpu'}]})
    monkeypatch.setattr(resources,'check_resources',probe)
    project={'project_id':'test','_verification_connection':encrypt_value(json.dumps(frozen))}
    assert (await v.verify({'error_signature':'resource:cpu'},project))['outcome']=='STILL_FAILING'
    assert probe.call_args.kwargs['connection_snapshot']==frozen

@pytest.mark.asyncio
async def test_orphan_recovery_and_conflicting_duplicate_preserves_first(pending,monkeypatch):
    import json
    from app import db
    from app.services import incident_review_service as review
    iid=str(pending['incident_id'])
    incident=dict(await db.fetch_one('SELECT * FROM incidents WHERE incident_id=$1',iid))
    project=dict(await db.fetch_one('SELECT * FROM projects WHERE project_id=$1',str(incident['project_id'])))
    await db.execute('DELETE FROM incident_reviews WHERE incident_id=$1',iid)
    await db.execute("UPDATE incidents SET status='REMEDIATING' WHERE incident_id=$1",iid)
    run=await db.fetch_one("INSERT INTO remediation_runs(incident_id,project_id,proposal_id,status,started_at,execution_finished_at,commands_succeeded,verification_context) VALUES($1,$2,$3,'IN_PROGRESS',NOW()-INTERVAL '2 minutes',NOW()-INTERVAL '2 minutes',true,$4::jsonb) RETURNING *",iid,str(project['project_id']),str(pending['proposal_id']),json.dumps({'incident':incident,'project':project},default=str))
    monkeypatch.setattr(v,'verify',AsyncMock(return_value={'outcome':'STILL_FAILING','evidence':[]}))
    await review.recover_pending_runs()
    assert (await db.fetch_one('SELECT status FROM incidents WHERE incident_id=$1',iid))['status']=='FAILED'
    result=await v.record(run,incident,project,{'outcome':'VERIFIED','evidence':[]},True)
    assert result['outcome']=='STILL_FAILING'
    assert (await db.fetch_one('SELECT verification_status FROM incidents WHERE incident_id=$1',iid))['verification_status']=='FAILED'

@pytest.mark.asyncio
async def test_concurrent_rollback_loser_does_not_finalize(monkeypatch):
    from app.services import incident_verification as module
    from app import db
    run={'run_id':'run','steps_executed':[{'action':{'action_type':'json_patch','rollback_on_failure':True},'result':{'backup_id':'patch_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}}]}
    monkeypatch.setattr(db, 'execute_returning', AsyncMock(return_value=None))
    monkeypatch.setattr(db, 'fetch_one', AsyncMock(side_effect=[{'steps_executed':run['steps_executed'],'rollback_result':None}]+[{'rollback_result':None}]*10))
    monkeypatch.setattr(module.asyncio, 'sleep', AsyncMock())
    with pytest.raises(RuntimeError, match='Rollback is still in progress'):
        await module.finish(run, {'incident_id':'incident'}, {'_verification_connection':'x'}, {'outcome':'STILL_FAILING'}, True)

@pytest.mark.asyncio
async def test_verified_loser_also_waits_for_rollback(monkeypatch):
    from app.services import incident_verification as module
    from app import db
    from datetime import datetime, timezone
    run={'run_id':'run','steps_executed':[]}
    fresh={'steps_executed':[], 'rollback_started_at':datetime.now(timezone.utc), 'rollback_result':None}
    monkeypatch.setattr(db, 'fetch_one', AsyncMock(return_value=fresh))
    monkeypatch.setattr(module.asyncio, 'sleep', AsyncMock())
    with pytest.raises(RuntimeError, match='Rollback is still in progress'):
        await module.finish(run, {'incident_id':'incident'}, {}, {'outcome':'VERIFIED'}, True)

@pytest.mark.asyncio
async def test_stale_rollback_becomes_manual_unavailable(monkeypatch):
    from app.services import incident_verification as module
    from app import db
    from datetime import datetime, timezone, timedelta
    run={'run_id':'run','steps_executed':[]}
    fresh={'steps_executed':[], 'rollback_started_at':datetime.now(timezone.utc)-timedelta(minutes=20), 'rollback_result':None}
    monkeypatch.setattr(db, 'fetch_one', AsyncMock(return_value=fresh))
    monkeypatch.setattr(module, 'record', AsyncMock(side_effect=lambda *args, **kwargs: args[3]))
    result=await module.finish(run, {'incident_id':'incident'}, {}, {'outcome':'VERIFIED'}, True)
    assert result['outcome']=='UNAVAILABLE'
