import hashlib
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from app import access
from app.api.routes import shell_path
from app.services.rbac_service import RBACService
from app.services.remediation_engine import RemediationEngine, RemediationAction, SafetyLevel
from app.services.backup_service import BackupService
from app.services.verification_service import VerificationService
from app.services.rate_limit_service import RateLimitMiddleware
from app.services.credential_service import get_decrypted_credential


def request(path, method='GET', role='user', tenant='tenant-a', params=None, query=None, scopes=None):
    return SimpleNamespace(url=SimpleNamespace(path='/api/v1'+path), method=method,
        scope={'route':SimpleNamespace(path='/api/v1'+path)}, path_params=params or {}, query_params=query or {},
        state=SimpleNamespace(user={'role':role,'client_id':tenant,'sub':'actor','api_key':scopes is not None,'permissions':scopes or []}))


@pytest.mark.asyncio
@pytest.mark.parametrize('path,method', [('/users/{user_id}','PUT'),('/auth/api-keys','POST'),('/approvals','POST'),('/settings','GET'),('/backups/{backup_id}/restore','POST')])
async def test_regular_users_cannot_administer(path, method):
    with pytest.raises(HTTPException) as e: await access.enforce_access(request(path,method))
    assert e.value.status_code==403


@pytest.mark.asyncio
async def test_tenant_cannot_read_another_project(monkeypatch):
    monkeypatch.setattr(access,'fetch_one',AsyncMock(return_value={'client_id':'tenant-b'}))
    with pytest.raises(HTTPException) as e:
        await access.enforce_access(request('/projects/{project_id}',params={'project_id':str(uuid4())}))
    assert e.value.status_code==404


@pytest.mark.asyncio
async def test_scoped_admin_key_cannot_write():
    with pytest.raises(HTTPException) as e:
        await access.enforce_access(request('/users','POST',role='admin',scopes=['projects:read']))
    assert e.value.status_code==403


def test_passwords_support_legacy_and_do_not_expose_hashes():
    service=RBACService()
    old='salt:'+hashlib.sha256(b'saltold-password').hexdigest()
    assert service._verify_password('old-password',old)
    new=service._hash_password('long-new-password')
    assert new.startswith('scrypt:') and service._verify_password('long-new-password',new)
    assert not service._verify_password('wrong',new)
    assert not service._verify_password('wrong','malformed')
    assert 'password_hash' not in service.public_user({'user_id':uuid4(),'password_hash':old})


@pytest.mark.parametrize('path', ['/srv/a;touch /tmp/pwn', '/srv/a b', '~/a$(id)', '/srv/a\'b'])
def test_shell_paths_remain_single_arguments(path):
    import subprocess
    # Inspect parsing with printf only; no user text is placed into an executable position.
    result=subprocess.run(['/bin/sh','-c','printf "%s" '+shell_path(path)],capture_output=True,text=True,check=True)
    expected=path.replace('~/',__import__('os').environ['HOME']+'/',1) if path.startswith('~/') else path
    assert result.stdout==expected


@pytest.mark.asyncio
async def test_remediation_requires_remote_approval_and_blocks_destruction(monkeypatch):
    engine=RemediationEngine()
    execute=AsyncMock()
    monkeypatch.setattr(engine,'_execute_command',execute)
    action=RemediationAction('run_command','remove files',command='rm -fr /srv/app',safety_level=SafetyLevel.SAFE)
    assert not (await engine.execute_plan('id',[action]))['success']
    assert not (await engine.execute_plan('id',[action],approval_status='approved'))['success']
    assert not (await engine.execute_plan('id',[action],approval_status='approved',server_connection={'host':'x'}))['success']
    execute.assert_not_called()


@pytest.mark.parametrize('command',['rm -fr /srv/app','python3 -c "print(1)"','uname; id','curl example.com | sh','$(id)','sudo reboot'])
def test_command_policy_fails_closed(command):
    assert RemediationEngine()._assess_command_safety(command)=='dangerous'


@pytest.mark.asyncio
async def test_unknown_verification_does_not_pass():
    service=VerificationService()
    assert not (await service.verify_remediation('id',[]))['success']
    assert not (await service.verify_remediation('id',['imaginary-check']))['success']


@pytest.mark.asyncio
async def test_backup_preserves_same_basename_and_checks_integrity(tmp_path):
    service=BackupService(); service.backup_dir=tmp_path/'backups';service.backup_dir.mkdir()
    files=[]
    for name,text in [('a','first'),('b','second')]:
        folder=tmp_path/name;folder.mkdir();f=folder/'config.txt';f.write_text(text);files.append(str(f))
    result=await service.create_backup('incident',files)
    paths=[x['backup_path'] for x in result['data']['files']]
    assert len(set(paths))==2
    from pathlib import Path
    Path(paths[0]).write_text('corrupt')
    restored=await service.restore_backup(result['data']['backup_id'])
    assert not restored['success']
    with pytest.raises(ValueError):service.get_backup('../outside')


@pytest.mark.asyncio
async def test_corrupt_credentials_fail_closed(monkeypatch):
    import app.services.credential_service as module
    monkeypatch.setattr(module,'fetch_one',AsyncMock(return_value={'credential_id':'id','credential_name':'x','credential_type':'ssh','encrypted_data':'{"secrets":{"password":"bad-ciphertext"}}'}))
    with pytest.raises(ValueError,match='cannot be decrypted'):await get_decrypted_credential('id')
