"""Bounded repair templates and exact, hash-guarded JSON file replacements."""
import asyncio
import difflib
import hashlib
import json
import posixpath
import re
import stat
from pathlib import Path
from uuid import uuid4
from app.services.ssh_service import create_ssh_client,_connect_kwargs
from app.services.credential_service import encrypt_value,decrypt_value
from app.config import get_settings

MAX_FILE=65536
CACHE={'cache:clear','config:clear','route:clear','view:clear','optimize:clear'}

def digest(data): return hashlib.sha256(data).hexdigest()


def validate_json(content):
    if not isinstance(content,str) or len(content.encode())>MAX_FILE: raise ValueError('JSON file exceeds 64 KiB')
    return json.loads(content,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Non-finite JSON value')))


def template_actions(project,template,service=None,cache='optimize:clear'):
    from app.services.remediation_engine import RemediationAction,SafetyLevel
    if template=='restart_service':
        metadata=project.get('metadata') or {}
        if isinstance(metadata,str): metadata=json.loads(metadata)
        if not service or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}',service) or service not in metadata.get('repair_services',[]):
            raise ValueError('Service must be explicitly listed in project metadata.repair_services')
        command='systemctl restart '+service
    elif template=='laravel_cache_clear':
        if 'laravel' not in (project.get('framework') or '').lower() or not project.get('project_path') or cache not in CACHE:
            raise ValueError('Laravel cache repair requires a Laravel project, stored path and supported cache action')
        command='php artisan '+cache
    else: raise ValueError('Unsupported repair template')
    return [RemediationAction('run_command',template.replace('_',' '),command=command,requires_approval=True,safety_level=SafetyLevel.RISKY)]


def approved_action(action,project):
    from app.services.remediation_engine import remediation_engine
    if action.action_type=='json_patch':
        try:
            validate_json(action.content)
            return bool(action.file_path and action.file_path.endswith('.json') and re.fullmatch('[a-f0-9]{64}',action.original_sha256 or ''))
        except (TypeError,ValueError): return False
    if action.action_type!='run_command' or not action.command: return False
    if remediation_engine._assess_command_safety(action.command)=='safe': return True
    import shlex
    args=shlex.split(action.command)
    try:
        if args[:2]==['systemctl','restart'] and len(args)==3: template_actions(project,'restart_service',service=args[2]);return True
        if args[:2]==['php','artisan'] and len(args)==3: template_actions(project,'laravel_cache_clear',cache=args[2]);return True
    except ValueError: pass
    return False


def target_path(sftp,root,relative):
    if not root or not relative or len(relative)>256 or relative.count('/')>12 or relative.startswith('/') or any(p in ('..','') for p in relative.split('/')) or '\\' in relative or '\x00' in relative:
        raise ValueError('A relative file path inside the stored project is required')
    if root=='~': root=sftp.normalize('.')
    elif root.startswith('~/'): root=posixpath.join(sftp.normalize('.'),root[2:])
    if not root.startswith('/'): raise ValueError('Stored project path must be absolute or home-relative')
    root=posixpath.normpath(root);target=posixpath.join(root,relative)
    current='/'
    for part in target.split('/')[1:]:
        current=posixpath.join(current,part)
        info=sftp.lstat(current)
        if stat.S_ISLNK(info.st_mode): raise ValueError('Symlink paths cannot be patched')
    info=sftp.lstat(target)
    if not stat.S_ISREG(info.st_mode) or info.st_size>MAX_FILE: raise ValueError('Only regular files up to 64 KiB can be patched')
    return target,info


def read_file(sftp,path):
    with sftp.open(path,'rb') as stream: data=stream.read(MAX_FILE+1)
    if len(data)>MAX_FILE: raise ValueError('File exceeds 64 KiB')
    validate_json(data.decode('utf-8'))
    return data


def replace(sftp,path,data,info,expected_hash):
    temp=path+'.pm-'+uuid4().hex
    try:
        with sftp.open(temp,'wx') as stream: stream.write(data);stream.flush()
        sftp.chmod(temp,stat.S_IMODE(info.st_mode))
        sftp.chown(temp,info.st_uid,info.st_gid)
        owner=sftp.lstat(temp)
        if (owner.st_uid,owner.st_gid)!=(info.st_uid,info.st_gid): raise ValueError('File ownership could not be preserved')
        if read_file(sftp,temp)!=data: raise ValueError('Temporary file validation failed')
        current=sftp.lstat(path)
        if stat.S_ISLNK(current.st_mode) or digest(read_file(sftp,path))!=expected_hash: raise ValueError('File changed while replacement was prepared')
        sftp.posix_rename(temp,path)
        if read_file(sftp,path)!=data: raise ValueError('Replacement validation failed')
    finally:
        try: sftp.remove(temp)
        except OSError: pass


def session(connection,operation):
    import time
    from app.services.incremental_logs import DeadlineSFTP
    deadline=time.monotonic()+45
    ssh=create_ssh_client();sftp=None
    try:
        kwargs=_connect_kwargs(**{k:v for k,v in connection.items() if k in ('host','port','username','key_path','password','private_key')})
        kwargs.update(timeout=5,auth_timeout=5,banner_timeout=5,channel_timeout=5)
        ssh.connect(**kwargs)
        sftp=ssh.open_sftp();sftp.get_channel().settimeout(5)
        return operation(DeadlineSFTP(sftp,deadline))
    finally:
        if sftp: sftp.close()
        ssh.close()


async def propose_patch(connection,relative,content,rollback):
    validate_json(content)
    if not relative.endswith('.json'): raise ValueError('Automatic file repairs currently support JSON files only')
    def read(sftp):
        path,info=target_path(sftp,connection.get('project_path'),relative)
        return read_file(sftp,path)
    before=await asyncio.to_thread(session,connection,read)
    from app.services.incident_review_service import clean
    if clean(validate_json(before.decode()))!=validate_json(before.decode()) or clean(validate_json(content))!=validate_json(content) or clean(before.decode())!=before.decode() or clean(content)!=content: raise ValueError('File contains sensitive values; use a manual repair without sending secrets for review')
    if before==content.encode(): raise ValueError('Proposed file has no changes')
    return {'action_type':'json_patch','description':'Replace reviewed JSON file: '+relative,'file_path':relative,'content':content,'original_sha256':digest(before),'requires_approval':True,'safety_level':'risky','rollback_on_failure':rollback,'reviewed_diff':''.join(difflib.unified_diff(before.decode().splitlines(True),content.splitlines(True),fromfile=relative+' (before)',tofile=relative+' (after)'))}


async def apply_patch(action,connection,run_id=None):
    loop=asyncio.get_running_loop()
    recovery={}
    def apply(sftp):
        path,info=target_path(sftp,connection.get('project_path'),action.file_path)
        original=read_file(sftp,path);new=action.content.encode()
        validate_json(action.content)
        if digest(original)!=action.original_sha256: raise ValueError('File changed since review; no changes applied')
        backup_id='patch_'+uuid4().hex
        folder=Path(get_settings().local_backup_path)/'reviewed-patches';folder.mkdir(parents=True,exist_ok=True)
        payload={'path':action.file_path,'before':original.decode(),'before_sha256':digest(original),'after_sha256':digest(new),'project_path':connection['project_path'],'host':connection['host'],'username':connection['username'],'port':connection.get('port',22)}
        encrypted=encrypt_value(json.dumps(payload))
        backup=folder/(backup_id+'.enc')
        with backup.open('x') as stream: stream.write(encrypted);stream.flush();__import__('os').fsync(stream.fileno())
        backup.chmod(0o600)
        restored=json.loads(decrypt_value(backup.read_text()))
        if digest(restored['before'].encode())!=digest(original): raise ValueError('Backup restoration rehearsal failed')
        recovery.update(backup_id=backup_id,rollback_on_failure=action.rollback_on_failure,mutation_phase='prepared')
        if run_id:
            from app.db import execute
            checkpoint=[{'action':action.to_dict(),'status':'pending','result':dict(recovery)}]
            asyncio.run_coroutine_threadsafe(execute('UPDATE remediation_runs SET steps_executed=$2::jsonb WHERE run_id=$1',str(run_id),json.dumps(checkpoint)),loop).result(timeout=10)
        # Recheck immediately before atomic replacement.
        if digest(read_file(sftp,path))!=action.original_sha256: raise ValueError('File changed during preparation')
        replace(sftp,path,new,info,action.original_sha256)
        recovery['mutation_phase']='replaced'
        return {'success':True,'mutation_phase':'replaced','backup_id':backup_id,'before_sha256':digest(original),'after_sha256':digest(new),'rollback_on_failure':action.rollback_on_failure}
    try: return await asyncio.to_thread(session,connection,apply)
    except Exception as exc: return {'success':False,'error':str(exc),**recovery}


async def rollback_patch(backup_id,connection):
    if not re.fullmatch('patch_[a-f0-9]{32}',backup_id): return {'success':False,'error':'Invalid backup id'}
    def restore(sftp):
        backup=Path(get_settings().local_backup_path)/'reviewed-patches'/(backup_id+'.enc')
        payload=json.loads(decrypt_value(backup.read_text()))
        if any(payload[k]!=connection[k] for k in ('host','username','project_path')) or payload['port']!=connection.get('port',22): raise ValueError('Rollback target changed')
        path,info=target_path(sftp,connection['project_path'],payload['path'])
        if digest(read_file(sftp,path))!=payload['after_sha256']: raise ValueError('File changed after repair; rollback refused')
        data=payload['before'].encode()
        if digest(data)!=payload['before_sha256']: raise ValueError('Backup integrity failed')
        replace(sftp,path,data,info,payload['after_sha256'])
        return {'success':True,'restored_sha256':digest(data)}
    try: return await asyncio.to_thread(session,connection,restore)
    except Exception as exc: return {'success':False,'error':str(exc)}
