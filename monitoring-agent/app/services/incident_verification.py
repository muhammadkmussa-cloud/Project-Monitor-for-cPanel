"""Bounded verification of the original incident, never command exit status."""
import asyncio
import json
from app.db import fetch_one, execute
from app.services.condition_service import http_conditions


def config_of(project):
    value=project.get('monitoring_config') or {}
    return json.loads(value) if isinstance(value,str) else value


def specification(incident,project):
    key=incident.get('error_signature') or ''
    config=config_of(project)
    kind='http' if key.startswith('http:') or incident.get('raw_error_reference')=='monitoring-cycle' else 'resources' if key.startswith('resource:') else 'application' if key=='application:contract' else None
    reason=None
    if kind=='application':
        checks=config.get('application',{}).get('checks',[])
        if not checks or any(c.get('method','GET')!='GET' for c in checks):
            kind=None;reason='Automatic verification requires a configured read-only application contract.'
    if not kind: reason=reason or 'No incident-specific reproduction check is configured; manual verification required.'
    return {'kind':kind,'condition':key,'samples':max(2,config.get('policy',{}).get('recovery_checks',2)), 'interval_seconds':2,'timeout_seconds':60,'unavailable_reason':reason,'rollback':'No automatic rollback for command plans.'}


async def sample(project,spec,config):
    project_id=str(project['project_id'])
    kind=spec['kind'];key=spec['condition']
    if kind=='http':
        from app.services.monitoring_service import run_http_health_check
        result=await run_http_health_check(project_id,project_snapshot=project)
        required={'http:latency':'response_time_ms','http:certificate':'ssl_days_remaining','http:certificate-check':'ssl_days_remaining','http:availability':'http_status_code'}.get(key)
        # Connection failure is evidence of unavailable service, not a missing probe.
        if required and result.get(required) is None and key!='http:availability': return None,{'reason':'Required measurement unavailable'}
        findings=http_conditions(result,config)
        failed=any(f['key']==key for f in findings) if required else bool(findings)
        return not failed,{'status':result.get('status'),'http_status':result.get('http_status_code'),'conditions':findings}
    if kind=='resources':
        from app.services.resource_monitor import check_resources
        from app.services.credential_service import decrypt_value
        frozen=project.get('_verification_connection')
        if not frozen: return None,{'reason':'Reviewed SSH connection unavailable'}
        connection=json.loads(decrypt_value(frozen))
        connection.pop('project_path',None)
        result=await check_resources(project_id,project_snapshot=project,connection_snapshot=connection)
        metric=key.split(':',1)[1]
        if metric not in result.get('metrics',{}): return None,{'reason':'Resource measurement unavailable'}
        return not any(f['key']==key for f in result['conditions']),{'metrics':result['metrics'],'conditions':result['conditions']}
    if kind=='application':
        from app.services.application_monitor import run_contracts
        checks=config.get('application',{}).get('checks',[])
        if not checks or any(c.get('method','GET')!='GET' for c in checks): return None,{'reason':'Read-only verification required'}
        result=await run_contracts(project,config['application'])
        return result['status']=='HEALTHY',result
    return None,{'reason':spec['unavailable_reason']}


async def verify(incident,project):
    spec=specification(incident,project);evidence=[]
    if not spec['kind']: return {'outcome':'UNAVAILABLE','specification':spec,'evidence':[]}
    async def collect():
        for index in range(spec['samples']):
            passed,detail=await sample(project,spec,config_of(project))
            evidence.append(detail)
            if passed is None: return 'UNAVAILABLE'
            if not passed: return 'STILL_FAILING'
            if index+1<spec['samples']: await asyncio.sleep(spec['interval_seconds'])
        return 'VERIFIED'
    try: outcome=await asyncio.wait_for(collect(),timeout=spec['timeout_seconds'])
    except Exception:
        outcome='UNAVAILABLE';evidence.append({'reason':'Verification could not complete within its probe or time limits.'})
    return {'outcome':outcome,'specification':spec,'evidence':evidence}


async def record(run,incident,project,result,commands_succeeded):
    from app.services.incident_review_service import clean
    from app.db import get_pool
    result=clean(result)
    outcome=result['outcome'];status={'VERIFIED':'PASSED','STILL_FAILING':'FAILED','UNAVAILABLE':'SKIPPED'}[outcome]
    pool=await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.fetchrow('SELECT run_id FROM remediation_runs WHERE run_id=$1 FOR UPDATE',str(run['run_id']))
            existing=await conn.fetchrow('SELECT checks_performed FROM verification_runs WHERE run_id=$1',str(run['run_id']))
            if existing:
                return json.loads(existing['checks_performed']) if isinstance(existing['checks_performed'],str) else existing['checks_performed']
            await conn.execute('INSERT INTO verification_runs(run_id,incident_id,project_id,status,checks_performed,notes,verified_at) VALUES ($1,$2,$3,$4,$5::jsonb,$6,NOW()) ON CONFLICT(run_id) DO NOTHING',str(run['run_id']),str(incident['incident_id']),str(project['project_id']),status,json.dumps(result,default=str),outcome)
            await conn.execute("UPDATE incidents SET verification_status=$2,status=$3::incident_status,resolved_at=CASE WHEN $3::incident_status='RESOLVED' THEN NOW() ELSE NULL END,updated_at=NOW() WHERE incident_id=$1 AND status='REMEDIATING'",str(incident['incident_id']),status,'ROLLED_BACK' if result.get('rollback',{}).get('success') else 'RESOLVED' if outcome=='VERIFIED' and commands_succeeded else 'FAILED')
            await conn.execute("UPDATE remediation_runs SET status=$2,completed_at=NOW() WHERE run_id=$1",str(run['run_id']),'COMPLETED' if commands_succeeded else 'FAILED')
    return result


async def finish(run,incident,project,result,commands_succeeded):
    from app.db import fetch_one,execute_returning
    from app.services.credential_service import decrypt_value
    from app.services.repair_service import rollback_patch
    fresh=await fetch_one('SELECT * FROM remediation_runs WHERE run_id=$1',str(run['run_id']))
    if fresh.get('rollback_result'):
        result['rollback']=json.loads(fresh['rollback_result']) if isinstance(fresh['rollback_result'],str) else fresh['rollback_result']
    if fresh.get('rollback_started_at') and not fresh.get('rollback_result'):
        from datetime import datetime, timezone
        started=fresh['rollback_started_at']
        if started.tzinfo is None: started=started.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc)-started).total_seconds() < 900:
            for _ in range(10):
                await asyncio.sleep(1)
                pending=await fetch_one('SELECT rollback_result FROM remediation_runs WHERE run_id=$1',str(run['run_id']))
                if pending and pending.get('rollback_result'):
                    result['rollback']=json.loads(pending['rollback_result']) if isinstance(pending['rollback_result'],str) else pending['rollback_result']
                    break
            if 'rollback' not in result:
                raise RuntimeError('Rollback is still in progress; verification remains pending and commands will not be replayed')
        else:
            result['outcome']='UNAVAILABLE'
            result['rollback']={'success':False,'error':'Rollback worker exceeded its deadline; manual inspection is required'}
    steps=fresh['steps_executed'] or []
    if isinstance(steps,str): steps=json.loads(steps)
    candidates=[s for s in steps if s.get('action',{}).get('action_type')=='json_patch' and s['action'].get('rollback_on_failure') and s.get('result',{}).get('backup_id')]
    if result['outcome']!='VERIFIED' and candidates and 'rollback' not in result:
        previous=fresh.get('rollback_result')
        if previous: result['rollback']=json.loads(previous) if isinstance(previous,str) else previous
        else:
            claimed=await execute_returning('UPDATE remediation_runs SET rollback_started_at=NOW() WHERE run_id=$1 AND rollback_started_at IS NULL RETURNING run_id',str(run['run_id']))
            if claimed:
                rollback=await rollback_patch(candidates[0]['result']['backup_id'],json.loads(decrypt_value(project['_verification_connection'])))
                if rollback.get('success'): rollback['post_rollback_verification']=await verify(incident,project)
                await execute('UPDATE remediation_runs SET rollback_result=$2::jsonb WHERE run_id=$1',str(run['run_id']),json.dumps(rollback))
                result['rollback']=rollback
            else:
                # Another verifier owns rollback.  Do not publish a competing
                # outcome while its backup restore is still in flight; the
                # worker will retry and read the winner's durable result.
                for _ in range(10):
                    await asyncio.sleep(1)
                    pending=await fetch_one('SELECT rollback_result FROM remediation_runs WHERE run_id=$1',str(run['run_id']))
                    if pending and pending.get('rollback_result'):
                        result['rollback']=json.loads(pending['rollback_result']) if isinstance(pending['rollback_result'],str) else pending['rollback_result']
                        break
                if 'rollback' not in result:
                    raise RuntimeError('Rollback is still in progress; verification remains pending and commands will not be replayed')
    return await record(run,incident,project,result,commands_succeeded)
