"""Durable proposal delivery and Telegram decisions. No execution before approval."""
import asyncio
import hashlib
import json
import logging
from uuid import UUID

from app.db import fetch_one, fetch_all, execute, get_pool
from app.services.telegram_service import telegram_service, TelegramPollingConflict
from app.services.settings_service import read_setting
from app.services.remediation_engine import remediation_engine
from app.utils.redactor import redactor

log = logging.getLogger(__name__)
CLOSED = {'RESOLVED', 'IGNORED', 'ROLLED_BACK'}


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def clean(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if any(x in k.lower() for x in ('password','secret','token','private_key','credential','api_key')) else clean(v) for k,v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        import re
        value = re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@', r'\1[REDACTED]@', value)
        # Preserve operational addresses; remove secrets from arbitrary metadata.
        for pattern, replacement in redactor.PATTERNS:
            if replacement not in ('IP.REDACTED','EMAIL@REDACTED.com'):
                value = pattern.sub(replacement, value)
        return value
    return value


async def enqueue(incident):
    await execute('INSERT INTO incident_reviews (incident_id) VALUES ($1) ON CONFLICT (incident_id) DO NOTHING',str(incident['incident_id']))


async def snapshot(proposal, project,connection=None):
    reader=connection.fetch if connection is not None else fetch_all
    credentials = await reader('SELECT credential_id, encrypted_data FROM project_credentials WHERE project_id=$1 ORDER BY credential_id',str(project['project_id']))
    target = {k:project.get(k) for k in ('project_id','server_host','ssh_port','ssh_username','project_path','remediation_enabled','domain','health_check_url','monitoring_config','environment','metadata','framework')}
    for key in ('metadata','monitoring_config'): target[key]=decoded(target.get(key))
    data = {'proposal':dict(proposal), 'target':target, 'credentials':[dict(r) for r in credentials]}
    return hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()


async def prepare(row):
    from app.api.routes import diagnose_incident, create_remediation_plan
    from app.api.schemas import DiagnosisRequest, RemediationPlanRequest
    incident = await fetch_one('SELECT * FROM incidents WHERE incident_id=$1',str(row['incident_id']))
    if incident['status'] in CLOSED:
        await execute("UPDATE incident_reviews SET state='CLOSED' WHERE review_id=$1",str(row['review_id']))
        return
    # Reuse a successfully persisted diagnosis/plan following a worker restart.
    proposal = await fetch_one('SELECT * FROM fix_proposals WHERE incident_id=$1 ORDER BY created_at DESC LIMIT 1',str(incident['incident_id']))
    if not proposal:
        diagnosis = await diagnose_incident(DiagnosisRequest(incident_id=incident['incident_id'],include_logs=True,include_server_stats=True,include_git_info=False))
        plan = await create_remediation_plan(RemediationPlanRequest(incident_id=incident['incident_id'],diagnosis_id=diagnosis.diagnosis_id),user={'role':'admin','sub':'scheduler'})
        proposal = await fetch_one('SELECT * FROM fix_proposals WHERE proposal_id=$1',str(plan.plan_id))
    diagnosis = await fetch_one('SELECT * FROM ai_diagnoses WHERE diagnosis_id=$1',str(proposal['diagnosis_id']))
    project = dict(await fetch_one('SELECT * FROM projects WHERE project_id=$1',str(incident['project_id'])))
    client = await fetch_one('SELECT client_name FROM clients WHERE client_id=$1',str(project['client_id']))
    steps = decoded(proposal['detailed_steps']) or []
    from app.services.repair_service import approved_action
    from app.services.remediation_engine import RemediationAction,SafetyLevel
    try:
        executable=bool(steps) and bool(project['remediation_enabled']) and proposal['safety_level']!='BLOCKED' and all(approved_action(RemediationAction(**{k:v for k,v in s.items() if k!='safety_level'},safety_level=SafetyLevel(s.get('safety_level','risky'))),project) for s in steps)
    except (TypeError,ValueError): executable=False

    for key in ('metadata','thresholds','log_locations'):
        project[key] = decoded(project.get(key))
    from app.services.incident_verification import specification
    verification_spec=specification(dict(incident),project)
    document = clean({'verification_checks':verification_spec,'project':project,'client_name':client['client_name'], 'incident':dict(incident),
                      'proposal_id':str(proposal['proposal_id']), 'executable':executable,
                      'fix_explanation':proposal['proposal_summary'], 'steps':steps,
                      'file_validation':'JSON syntax, exact reviewed hash and ownership; application recovery is checked separately. Automatic rollback only when rollback_on_failure is explicitly true.',
                      'root_cause':diagnosis['root_cause'], 'evidence':decoded(diagnosis['evidence']),
                      'risk':diagnosis['risk_level'],'confidence':diagnosis['confidence'],
                      'rollback':diagnosis['rollback_plan'],'verification':decoded(diagnosis['verification_plan']),
                      'expires_at':row['expires_at']})
    digest = await snapshot(proposal,project)
    await execute("UPDATE incident_reviews SET proposal_id=$2,snapshot_hash=$3,review_document=$4::jsonb,state='READY',updated_at=NOW() WHERE review_id=$1",str(row['review_id']),str(proposal['proposal_id']),digest,json.dumps(document,default=str))
    await execute("UPDATE incidents SET status='AWAITING_APPROVAL',updated_at=NOW() WHERE incident_id=$1 AND status NOT IN ('RESOLVED','IGNORED','ROLLED_BACK')",str(incident['incident_id']))


async def deliver(row):
    document = decoded(row['review_document'])
    result = await telegram_service.send_review(str(row['review_id']),document)
    if not result.get('success'):
        raise RuntimeError('Telegram proposal delivery failed')
    await execute("UPDATE incident_reviews SET state='SENT',message_id=$2,chat_id=$3,updated_at=NOW() WHERE review_id=$1",str(row['review_id']),result['message_id'],str(telegram_service.chat_id))


def authorized(query):
    message = query.get('message') or {}
    chat = message.get('chat') or {}
    return (chat.get('type')=='private' and str(chat.get('id'))==str(telegram_service.chat_id)
            and str((query.get('from') or {}).get('id'))==str(telegram_service.chat_id))


async def decide(query):
    if not authorized(query):
        return 'Only the configured private-chat owner can decide.'
    try:
        prefix,action,rid = query.get('data','').split(':')
        if prefix != 'pm' or action not in ('a','r'): raise ValueError()
        if rid == 'test': return 'Test '+('approval' if action=='a' else 'rejection')+' received. No incident or server was changed.'
        rid=str(UUID(rid))
    except (ValueError,TypeError):
        return 'This button is not a current proposal.'
    pool=await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row=await conn.fetchrow('SELECT * FROM incident_reviews WHERE review_id=$1 FOR UPDATE',rid)
            if not row or row['state']!='SENT': return 'This review was already handled or is unavailable.'
            if row['message_id']!=query['message'].get('message_id') or row['chat_id']!=str(query['message']['chat']['id']):
                return 'This button does not match the delivered review.'
            incident=await conn.fetchrow('SELECT * FROM incidents WHERE incident_id=$1 FOR UPDATE',row['incident_id'])
            valid=await conn.fetchval('SELECT $1::timestamptz>NOW()',row['expires_at'])
            if not valid or incident['status'] in CLOSED: return 'The incident is closed or this review has expired.'
            proposal=await conn.fetchrow('SELECT * FROM fix_proposals WHERE proposal_id=$1',row['proposal_id'])
            project=await conn.fetchrow('SELECT * FROM projects WHERE project_id=$1',incident['project_id'])
            if await snapshot(proposal,dict(project),conn)!=row['snapshot_hash']:
                return 'The proposal or target changed. Review it again in the dashboard.'
            status='APPROVED' if action=='a' else 'REJECTED'
            approval=await conn.fetchrow("INSERT INTO approvals (proposal_id,incident_id,project_id,client_id,status,approved_by,approval_method,responded_at,expires_at,review_hash) VALUES ($1,$2,$3,$4,$5,'telegram:'||$6::text,'telegram',NOW(),$7,$8) RETURNING approval_id",row['proposal_id'],row['incident_id'],incident['project_id'],incident['client_id'],status,str(query['from']['id']),row['expires_at'],row['snapshot_hash'])
            await conn.execute('UPDATE incident_reviews SET state=$2,approval_id=$3,actor_id=$4,updated_at=NOW() WHERE review_id=$1',rid,status,approval['approval_id'],str(query['from']['id']))
            await conn.execute("UPDATE incidents SET status=$2,updated_at=NOW() WHERE incident_id=$1",row['incident_id'],'APPROVED' if action=='a' else 'IGNORED')
    return ('Approved. Queued for safety checks and execution.' if decoded(row['review_document'])['executable'] else 'Approval recorded. This plan requires manual work; no commands will run.') if action=='a' else 'Rejected. This proposal will not run.'


def outcome_text(success,outcome,rollback=None):
    return ('Commands completed. ' if success else 'Execution failed; remaining actions were stopped. ')+{'VERIFIED':'Original incident condition verified healthy.','STILL_FAILING':'The original incident condition is still failing.','UNAVAILABLE':'Recovery could not be verified; manual verification is required.'}[outcome]+(' Reviewed file rollback succeeded.' if rollback and rollback.get('success') else ' Rollback needs manual inspection.' if rollback else ' Automatic rollback was not performed.')


async def recover_run(run):
    """Resume verification or report recorded outcome; never repeat commands."""
    verification=await fetch_one('SELECT * FROM verification_runs WHERE run_id=$1',str(run['run_id']))
    if verification: return outcome_text(bool(run['commands_succeeded']),verification['notes'],decoded(verification['checks_performed']).get('rollback'))
    if run.get('execution_finished_at') and run.get('verification_context'):
        from app.services.incident_verification import verify,finish
        context=decoded(run['verification_context'])
        result=await verify(context['incident'],context['project'])
        result=await finish(run,context['incident'],context['project'],result,bool(run['commands_succeeded']))
        return outcome_text(bool(run['commands_succeeded']),result['outcome'],result.get('rollback'))
    from datetime import datetime,timezone
    if run['status']=='IN_PROGRESS' and (datetime.now(timezone.utc)-run['started_at']).total_seconds()<900:
        raise RuntimeError('Execution outcome is still pending; commands will not be repeated')
    await execute("UPDATE remediation_runs SET status='FAILED',completed_at=NOW(),error_log='Execution interrupted; manual inspection required, commands not replayed' WHERE run_id=$1",str(run['run_id']))
    await execute("UPDATE incidents SET status='FAILED',verification_status='SKIPPED',updated_at=NOW() WHERE incident_id=$1 AND status='REMEDIATING'",str(run['incident_id']))
    return 'Execution outcome unavailable after interruption. Commands were not repeated. Inspect the server before creating another proposal.'


async def run_approved(row):
    from app.api.routes import execute_remediation
    from app.api.schemas import RemediationExecuteRequest
    from fastapi import HTTPException
    doc=decoded(row['review_document'])
    existing=await fetch_one('SELECT * FROM remediation_runs WHERE proposal_id=$1',str(row['proposal_id']))
    if existing:
        text=await recover_run(dict(existing))
        await execute("UPDATE incident_reviews SET state='RESULT',result_text=$2 WHERE review_id=$1",str(row['review_id']),text)
        return
    if not doc['executable']:
        text='Approval recorded. This proposal requires manual work; no remote commands were run.'
    else:
        proposal=await fetch_one('SELECT * FROM fix_proposals WHERE proposal_id=$1',str(row['proposal_id']))
        project=await fetch_one('SELECT * FROM projects WHERE project_id=$1',str(proposal['project_id']))
        if await snapshot(proposal,dict(project))!=row['snapshot_hash']:
            text='Execution blocked: the reviewed plan or target changed.'
        else:
            try:
                result=await execute_remediation(RemediationExecuteRequest(plan_id=row['proposal_id'],incident_id=row['incident_id'],approval_id=row['approval_id']),user={'role':'admin','sub':'telegram:'+row['actor_id']})
                text=outcome_text(result.success,result.verification_outcome,result.verification_details.get("rollback"))
            except HTTPException as exc:
                text='Execution blocked: '+str(exc.detail)
    await execute("UPDATE incident_reviews SET state='RESULT',result_text=$2 WHERE review_id=$1",str(row['review_id']),text)


async def process_one(row):
    if row['state']=='NEW': await prepare(row)
    elif row['state']=='READY': await deliver(row)
    elif row['state']=='APPROVED': await run_approved(row)
    elif row['state'] in ('REJECTED','RESULT'):
        message=row['result_text'] or 'Rejected. No commands were run.'
        result=await telegram_service.send_message('Project: '+decoded(row['review_document'])['project']['project_name']+'\nProposal: '+str(row['proposal_id'])+'\n'+message,parse_mode=None)
        if not result.get('success'): raise RuntimeError('Telegram result delivery failed')
        await execute("UPDATE incident_reviews SET state='DONE' WHERE review_id=$1",str(row['review_id']))


async def recover_pending_runs():
    rows=await fetch_all("SELECT * FROM remediation_runs WHERE status='IN_PROGRESS' AND ((execution_finished_at IS NOT NULL AND execution_finished_at<NOW()-INTERVAL '90 seconds') OR started_at<NOW()-INTERVAL '15 minutes') ORDER BY started_at LIMIT 4")
    for run in rows:
        await recover_run(dict(run))


async def review_worker():
    while True:
        try:
            pool=await get_pool()
            async with pool.acquire() as conn:
                if await conn.fetchval("SELECT pg_try_advisory_lock(70702061)"):
                    try:
                        await recover_pending_runs()
                        await execute("INSERT INTO incident_reviews(incident_id) SELECT incident_id FROM incidents WHERE status IN ('OPEN','INVESTIGATING','AWAITING_APPROVAL') ON CONFLICT(incident_id) DO NOTHING")
                        rows=await fetch_all("SELECT * FROM incident_reviews WHERE state IN ('NEW','READY','APPROVED','REJECTED','RESULT') AND next_attempt_at<=NOW() ORDER BY created_at LIMIT 10")
                        for row in rows:
                            try: await process_one(row)
                            except Exception:
                                log.exception('Review processing failed for %s',row['review_id'])
                                await execute("UPDATE incident_reviews SET attempts=attempts+1,last_error='Processing failed; retry scheduled',next_attempt_at=NOW()+INTERVAL '60 seconds' WHERE review_id=$1",str(row['review_id']))
                    finally: await conn.execute('SELECT pg_advisory_unlock(70702061)')
        except Exception: log.exception('Review worker failed')
        await asyncio.sleep(2)


async def telegram_poll():
    # Outbound polling works on localhost; no public unauthenticated webhook.
    while True:
        try:
            if not telegram_service.enabled or not telegram_service.bot_token or not await read_setting("telegram.polling_enabled", True):
                await asyncio.sleep(30); continue
            pool=await get_pool()
            async with pool.acquire() as conn:
                if not await conn.fetchval('SELECT pg_try_advisory_lock(70702062)'):
                    await asyncio.sleep(5); continue
                try:
                    offset=await read_setting('telegram.update_offset',0)
                    data=await telegram_service.bot_call('getUpdates',{'offset':offset,'timeout':20,'allowed_updates':['callback_query']})
                    for update in data:
                        query=update.get('callback_query')
                        if query:
                            answer=await decide(query)
                            try:
                                await telegram_service.bot_call('answerCallbackQuery',{'callback_query_id':query['id'],'text':answer[:190]})
                            except Exception:
                                log.warning('Could not acknowledge Telegram button; decision remains recorded')
                        await execute("INSERT INTO platform_settings(setting_key,setting_value) VALUES ('telegram.update_offset',$1::jsonb) ON CONFLICT(setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value",json.dumps(update['update_id']+1))
                finally: await conn.execute('SELECT pg_advisory_unlock(70702062)')
        except TelegramPollingConflict:
            await execute("INSERT INTO platform_settings(setting_key,setting_value) VALUES ('telegram.polling_enabled','false'::jsonb) ON CONFLICT(setting_key) DO UPDATE SET setting_value='false'::jsonb")
            log.error('Telegram polling paused: bot already has another consumer. Configure a shared relay or dedicated bot.')
        except Exception:
            log.warning('Telegram polling unavailable; retrying (check bot configuration)')
            await asyncio.sleep(15)
