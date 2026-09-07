"""Explicit HTTP application contracts and opt-in staging journeys."""
import json
from urllib.parse import urlsplit,urlunsplit
import httpx
from app.db import fetch_one,execute,execute_returning
from app.services.credential_service import get_decrypted_credential

MAX_BODY=1048576


def json_path(value,path):
    for part in path.split('.'):
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value


async def bounded_response(response):
    data=bytearray()
    async for chunk in response.aiter_bytes(chunk_size=65536):
        data.extend(chunk)
        if len(data)>MAX_BODY: raise ValueError('Application response exceeds limit')
    return bytes(data)


async def run_contracts(project,config,credential=None,transport=None):
    target=project.get('health_check_url') or project.get('domain')
    if not target: raise ValueError('Application base URL missing')
    parsed=urlsplit(target if '://' in target else 'https://'+target)
    if parsed.username or parsed.password or parsed.scheme not in ('http','https'): raise ValueError('Invalid application base URL')
    base=urlunsplit((parsed.scheme,parsed.netloc,'','',''))
    if any(s['method']=='POST' for s in config['checks']) and (not config.get('allow_mutations') or project['environment'] not in ('staging','test','development')):
        raise ValueError('Synthetic mutations require explicit opt-in and a staging project')
    if parsed.scheme!='https' and any(s.get('use_credentials') or s.get('capture_token_path') or s.get('use_bearer_from_previous') for s in config['checks']):
        raise ValueError('Authentication steps require HTTPS')
    results=[];token=None
    async with httpx.AsyncClient(timeout=10,follow_redirects=False,transport=transport) as client:
        for step in config['checks']:
            headers={};payload=step.get('body')
            if step.get('use_credentials'):
                if not credential or not credential.get('password'): raise ValueError('Encrypted HTTP credential missing')
                if parsed.scheme!='https': raise ValueError('Credentials require HTTPS')
                payload={**(payload or {}),step.get('username_field','email'):credential.get('username',''),step.get('password_field','password'):credential['password']}
            if step.get('use_bearer_from_previous'):
                if not token: raise ValueError('Previous step did not provide a token')
                headers['Authorization']='Bearer '+token
            try:
                async with client.stream(step['method'],base+step['path'],json=payload,headers=headers) as response:
                    raw=await bounded_response(response)
                    passed=response.status_code==step['expected_status']
                    reason='Expected status matched' if passed else 'Unexpected HTTP status'
                    if passed and step.get('contains') and step['contains'] not in raw.decode('utf-8',errors='replace'):
                        passed=False;reason='Expected content missing'
                    if passed and (step.get('json_equals') or step.get('capture_token_path')):
                        try:
                            data=json.loads(raw)
                            for path,expected in step.get('json_equals',{}).items():
                                actual=json_path(data,path)
                                if type(actual)!=type(expected) or actual!=expected:
                                    passed=False;reason='JSON contract failed';break
                            if passed and step.get('capture_token_path'):
                                token=json_path(data,step['capture_token_path'])
                                if not isinstance(token,str) or not token: raise ValueError('Token missing')
                        except (ValueError,KeyError,IndexError,TypeError):
                            passed=False;reason='Expected JSON data missing or invalid'
                    results.append({'name':step['name'],'passed':passed,'reason':reason,'http_status':response.status_code})
            except (httpx.HTTPError,ValueError):
                results.append({'name':step['name'],'passed':False,'reason':'Application request failed or exceeded response limit'})
            if not results[-1]['passed']:
                results.extend({'name':rest['name'],'passed':False,'reason':'Not run: an earlier step failed'} for rest in config['checks'][len(results):])
                break
    return {'status':'HEALTHY' if all(r['passed'] for r in results) and results else 'DEGRADED','checks':results}


async def check_application(project_id):
    project=await fetch_one('SELECT * FROM projects WHERE project_id=$1',project_id)
    if not project: raise ValueError('Project missing')
    config=json.loads(project['monitoring_config']) if isinstance(project['monitoring_config'],str) else project['monitoring_config']
    config=config['application']
    credential=await get_decrypted_credential(project_id,'http') if any(c.get('use_credentials') for c in config['checks']) else None
    result=await run_contracts(dict(project),config,credential)
    await execute("INSERT INTO monitoring_checks(project_id,client_id,check_type,status,details) VALUES ($1,$2,'application',$3,$4::jsonb)",project_id,project['client_id'],result['status'],json.dumps(result))
    return result


async def evaluate_application(project_id,result):
    from app.services.condition_service import observe
    findings=[] if result['status']=='HEALTHY' else [{'key':'application:contract','category':'APPLICATION_ERROR','severity':'HIGH','checks':result['checks']}]
    await observe(project_id,'application',findings)
