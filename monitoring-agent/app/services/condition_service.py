"""Transactional incident episodes with debounce, escalation and stable recovery."""
import json
from app.db import get_pool

RANK={'LOW':0,'MEDIUM':1,'HIGH':2,'CRITICAL':3}
DEFAULT_POLICY={'failure_checks':2,'recovery_checks':2,'escalate_after':5}


async def observe(project_id,kind,findings,observed_keys=None):
    pool=await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,9))',project_id+':'+kind)
            project=await conn.fetchrow('SELECT * FROM projects WHERE project_id=$1',project_id)
            if not project: raise ValueError('Project missing')
            config=json.loads(project['monitoring_config']) if isinstance(project['monitoring_config'],str) else project['monitoring_config']
            policy={**DEFAULT_POLICY,**config.get('policy',{})}
            active={f['key']:f for f in findings}
            previous=await conn.fetch('SELECT * FROM incident_conditions WHERE project_id=$1 AND check_kind=$2',project_id,kind)
            states={r['condition_key']:r for r in previous}
            for key in set(states)|set(active):
                old=states.get(key)
                if key not in active:
                    if observed_keys is not None and key not in observed_keys: continue
                    if not old or (not old['failure_count'] and not old['incident_id']): continue
                    recovered=old['recovery_count']+1
                    linked=await conn.fetchrow('SELECT status FROM incidents WHERE incident_id=$1 FOR UPDATE',old['incident_id']) if old['incident_id'] else None
                    if linked and linked['status']=='REMEDIATING':
                        await conn.execute('UPDATE incident_conditions SET failure_count=0,recovery_count=$4,last_observed_at=NOW() WHERE project_id=$1 AND check_kind=$2 AND condition_key=$3',project_id,kind,key,recovered)
                        continue
                    if recovered>=policy['recovery_checks']:
                        if old['incident_id']:
                            await conn.execute("UPDATE incidents SET status='RESOLVED',resolved_at=NOW(),updated_at=NOW() WHERE incident_id=$1 AND status NOT IN ('IGNORED','RESOLVED','ROLLED_BACK','REMEDIATING')",old['incident_id'])
                        await conn.execute('UPDATE incident_conditions SET failure_count=0,recovery_count=0,incident_id=NULL,first_failure_at=NULL,last_observed_at=NOW() WHERE project_id=$1 AND check_kind=$2 AND condition_key=$3',project_id,kind,key)
                    else:
                        await conn.execute('UPDATE incident_conditions SET failure_count=0,recovery_count=$4,last_observed_at=NOW() WHERE project_id=$1 AND check_kind=$2 AND condition_key=$3',project_id,kind,key,recovered)
                    continue
                finding=active[key]
                count=(old['failure_count'] if old else 0)+1
                severity=finding['severity']
                if count>=policy['escalate_after'] and RANK[severity]<RANK['HIGH']: severity='HIGH'
                incident_id=old['incident_id'] if old else None
                incident=await conn.fetchrow('SELECT * FROM incidents WHERE incident_id=$1',incident_id) if incident_id else None
                needed=1 if finding.get('immediate') else policy['failure_checks']
                if not incident and count>=needed:
                    # Adopt an existing unclosed episode from before this migration.
                    incident=await conn.fetchrow("SELECT * FROM incidents WHERE project_id=$1 AND error_signature=$2 AND status NOT IN ('RESOLVED','IGNORED','ROLLED_BACK') ORDER BY created_at DESC LIMIT 1",project_id,key)
                    if not incident:
                        incident=await conn.fetchrow("INSERT INTO incidents(project_id,client_id,category,severity,error_signature,affected_component,raw_error_reference,occurrence_count) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *",project_id,project['client_id'],finding['category'],severity,key,kind,json.dumps(finding,default=str),count)
                        await conn.execute('INSERT INTO incident_reviews(incident_id) VALUES ($1) ON CONFLICT DO NOTHING',incident['incident_id'])
                    incident_id=incident['incident_id']
                elif incident and incident['status'] not in ('RESOLVED','IGNORED','ROLLED_BACK'):
                    severity=max((incident['severity'],severity),key=RANK.get)
                    await conn.execute('UPDATE incidents SET severity=$2,occurrence_count=occurrence_count+1,last_seen=NOW(),updated_at=NOW() WHERE incident_id=$1',incident_id,severity)
                await conn.execute('INSERT INTO incident_conditions(project_id,check_kind,condition_key,failure_count,recovery_count,incident_id,first_failure_at,last_evidence) VALUES ($1,$2,$3,$4,0,$5,NOW(),$6::jsonb) ON CONFLICT(project_id,check_kind,condition_key) DO UPDATE SET failure_count=EXCLUDED.failure_count,recovery_count=0,incident_id=EXCLUDED.incident_id,first_failure_at=COALESCE(incident_conditions.first_failure_at,NOW()),last_observed_at=NOW(),last_evidence=EXCLUDED.last_evidence',project_id,kind,key,count,incident_id,json.dumps(finding,default=str))


def http_conditions(health,config):
    thresholds=config.get('http',{})
    warn=thresholds.get('warning_ms',2000);critical=thresholds.get('critical_ms',5000)
    ssl_warn=thresholds.get('ssl_warning_days',30);ssl_critical=thresholds.get('ssl_critical_days',7)
    status=health.get('http_status_code');latency=health.get('response_time_ms');ssl_days=health.get('ssl_days_remaining')
    result=[]
    if status is None or status>=400 or health.get('status')=='DOWN':
        result.append({'key':'http:availability','category':'HTTP_ERROR' if status else 'NETWORK_ERROR','severity':'CRITICAL' if status is None or status>=500 else 'HIGH','immediate':status is None or status>=500,'http_status':status,'error':health.get('details',{}).get('error')})
    if latency is not None and latency>warn:
        result.append({'key':'http:latency','category':'HTTP_ERROR','severity':'HIGH' if latency>critical else 'MEDIUM','response_time_ms':latency,'warning_ms':warn,'critical_ms':critical})
    if ssl_days is not None and ssl_days<=ssl_warn:
        result.append({'key':'http:certificate','category':'SSL_ERROR','severity':'CRITICAL' if ssl_days<=ssl_critical else 'MEDIUM','immediate':ssl_days<=ssl_critical,'days_remaining':ssl_days})
    if health.get('details',{}).get('ssl_check_error'):
        result.append({'key':'http:certificate-check','category':'SSL_ERROR','severity':'HIGH','error':'Certificate check unavailable'})
    return result
