import io
import json
import os
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from app.services.incremental_logs import read_file

class File(io.BytesIO):
    def __exit__(self,*args): pass
class SFTP:
    def __init__(self,data): self.data=data
    def stat(self,path): return SimpleNamespace(st_size=len(self.data))
    def open(self,path,mode): return File(self.data)

def test_baseline_append_partial_and_restart():
    sftp=SFTP(b'old ERROR\n')
    first=read_file(sftp,'app.log')
    assert first['baseline'] and first['entries']==[]
    sftp.data+=b'new Exception: failure\npartial'
    second=read_file(sftp,'app.log',first['cursor'])
    assert second['entries']==['new Exception: failure']
    assert read_file(sftp,'app.log',json.loads(json.dumps(second['cursor'])))['entries']==[]
    sftp.data+=b' ERROR complete\n'
    assert read_file(sftp,'app.log',second['cursor'])['entries']==['partial ERROR complete']

@pytest.mark.parametrize('replacement',[b'ERROR short\n',b'ERROR replacement longer than original text\n'])
def test_rotation_or_truncation(replacement):
    sftp=SFTP(b'old old old ERROR\n')
    cursor=read_file(sftp,'app.log')['cursor']
    sftp.data=replacement
    result=read_file(sftp,'app.log',cursor)
    assert result['reset'] and result['entries']==replacement.decode().splitlines()

def test_baseline_does_not_emit_historical_partial_line():
    sftp=SFTP(b'old ERROR partial')
    cursor=read_file(sftp,'app.log')['cursor']
    sftp.data+=b' finishes\nnew ERROR\n'
    assert read_file(sftp,'app.log',cursor)['entries']==['new ERROR']

@pytest.mark.asyncio
async def test_cursor_incident_queue_failure_and_new_occurrences(monkeypatch):
    if os.environ.get('PM_ISOLATED_DATABASE')!='1': pytest.skip('Disposable database required')
    from app import db
    from app.services import incremental_logs,error_scanner
    cid,pid=str(uuid4()),str(uuid4())
    await db.execute("INSERT INTO clients(client_id,client_name) VALUES ($1,'cursor test')",cid)
    await db.execute("INSERT INTO projects(project_id,client_id,project_name) VALUES ($1,$2,'cursor test')",pid,cid)
    monkeypatch.setattr(error_scanner,'_load_connection',AsyncMock(return_value={'host':'test'}))
    sftp=SFTP(b'historical ERROR\n')
    async def read(project,connection,cursors): return [read_file(sftp,'app.log',cursors.get('app.log'))]
    monkeypatch.setattr(incremental_logs,'read_incremental',read)
    assert (await error_scanner.scan_project(pid))['created']==0
    sftp.data+=b'new Exception: failure\nnew Exception: failure\n'
    result=await error_scanner.scan_project(pid)
    assert result['created']==1 and result['entries']==2
    incident=await db.fetch_one('SELECT * FROM incidents WHERE project_id=$1',pid)
    assert incident['occurrence_count']==2
    assert await db.fetch_one('SELECT * FROM incident_reviews WHERE incident_id=$1',incident['incident_id'])
    await db.execute("UPDATE incidents SET status='IGNORED' WHERE incident_id=$1",incident['incident_id'])
    assert (await error_scanner.scan_project(pid))['created']==0
    sftp.data+=b'new Exception: failure\n'
    assert (await error_scanner.scan_project(pid))['created']==1
    cursor=await db.fetch_one('SELECT cursor_data FROM log_cursors WHERE project_id=$1',pid)
    monkeypatch.setattr(incremental_logs,'read_incremental',AsyncMock(side_effect=OSError('SSH unavailable')))
    assert not (await error_scanner.scan_project(pid))['success']
    assert (await db.fetch_one('SELECT cursor_data FROM log_cursors WHERE project_id=$1',pid))['cursor_data']==cursor['cursor_data']
    await db.close_pool()

def test_entry_budget_preserves_unprocessed_bytes():
    sftp=SFTP(b'old\n');cursor=read_file(sftp,'log')['cursor']
    sftp.data+=b'ERROR one\nERROR two\nERROR three\n'
    result=read_file(sftp,'log',cursor,limit=2)
    assert result['entries']==['ERROR one','ERROR two']
    assert read_file(sftp,'log',result['cursor'])['entries']==['ERROR three']

def test_utf8_split_keeps_complete_records():
    sftp=SFTP(b'old\n');cursor=read_file(sftp,'log')['cursor']
    data='ERROR café\n'.encode();sftp.data+=data[:-2]
    assert read_file(sftp,'log',cursor)['entries']==[]
    sftp.data+=data[-2:]
    assert read_file(sftp,'log',cursor)['entries']==['ERROR café']

def test_rename_rotation_finishes_unread_predecessor():
    from app.services.incremental_logs import read_rotating
    class Multiple:
        data={'/app.log':b'old\n'}
        def stat(self,path): return SimpleNamespace(st_size=len(self.data[path]))
        def open(self,path,mode): return File(self.data[path])
        def listdir(self,path): return ['app.log','app.log.1']
    sftp=Multiple();cursor=read_file(sftp,'/app.log')['cursor']
    sftp.data={'/app.log.1':b'old\nERROR before rotation\n','/app.log':b'ERROR after rotation\n'}
    first=read_rotating(sftp,'/app.log',cursor,limit=1)
    assert first['entries']==['ERROR before rotation']
    second=read_rotating(sftp,'/app.log',first['cursor'],limit=1)
    assert second['entries']==['ERROR after rotation']

@pytest.mark.asyncio
async def test_concurrent_scans_do_not_exhaust_pool(monkeypatch):
    if os.environ.get('PM_ISOLATED_DATABASE')!='1': pytest.skip('Disposable database required')
    import asyncio
    from app import db
    from app.services import incremental_logs,error_scanner
    cid=str(uuid4());await db.execute("INSERT INTO clients(client_id,client_name) VALUES ($1,'concurrency')",cid)
    ids=[str(uuid4()) for _ in range(12)]
    for pid in ids:
        await db.execute("INSERT INTO projects(project_id,client_id,project_name,server_host,ssh_username) VALUES ($1,$2,'concurrency','test','test')",pid,cid)
    monkeypatch.setattr(incremental_logs,'read_incremental',AsyncMock(return_value=[]))
    results=await asyncio.wait_for(asyncio.gather(*(error_scanner.scan_project(pid) for pid in ids)),timeout=10)
    assert all(r['success'] for r in results)
    await db.close_pool()

@pytest.mark.asyncio
async def test_queue_failure_rolls_back_incident_and_cursor(monkeypatch):
    if os.environ.get('PM_ISOLATED_DATABASE')!='1': pytest.skip('Disposable database required')
    from app import db
    from app.services import incremental_logs,error_scanner
    cid,pid=str(uuid4()),str(uuid4())
    await db.execute("INSERT INTO clients(client_id,client_name) VALUES ($1,'rollback')",cid)
    await db.execute("INSERT INTO projects(project_id,client_id,project_name) VALUES ($1,$2,'rollback')",pid,cid)
    monkeypatch.setattr(error_scanner,'_load_connection',AsyncMock(return_value={'host':'test'}))
    sftp=SFTP(b'old\n')
    async def read(project,connection,cursors): return [read_file(sftp,'app.log',cursors.get('app.log'))]
    monkeypatch.setattr(incremental_logs,'read_incremental',read)
    await error_scanner.scan_project(pid)
    old=(await db.fetch_one('SELECT cursor_data FROM log_cursors WHERE project_id=$1',pid))['cursor_data']
    sftp.data+=b'ERROR new\n'
    await db.execute("CREATE OR REPLACE FUNCTION test_fail_review() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'simulated queue failure'; END $$")
    await db.execute('CREATE TRIGGER test_fail_review BEFORE INSERT ON incident_reviews FOR EACH ROW EXECUTE FUNCTION test_fail_review()')
    try:
        with pytest.raises(Exception,match='simulated queue failure'): await error_scanner.scan_project(pid)
        assert (await db.fetch_one('SELECT cursor_data FROM log_cursors WHERE project_id=$1',pid))['cursor_data']==old
        assert not await db.fetch_one('SELECT incident_id FROM incidents WHERE project_id=$1',pid)
    finally:
        await db.execute('DROP TRIGGER test_fail_review ON incident_reviews')
        await db.execute('DROP FUNCTION test_fail_review()')
    assert (await error_scanner.scan_project(pid))['created']==1
    await db.close_pool()

def test_rotated_terminal_fragment_does_not_block_active_log():
    from app.services.incremental_logs import read_rotating
    class Multiple:
        data={'/app.log':b'old\n'}
        def stat(self,path):
            if path not in self.data: raise FileNotFoundError(path)
            return SimpleNamespace(st_size=len(self.data[path]))
        def open(self,path,mode): return File(self.data[path])
        def listdir(self,path): return [p.lstrip('/') for p in self.data]
    sftp=Multiple();cursor=read_file(sftp,'/app.log')['cursor']
    sftp.data={'/app.log.1':b'old\nERROR terminal fragment','/app.log':b'ERROR current\n'}
    result=read_rotating(sftp,'/app.log',cursor)
    assert result['entries']==['ERROR terminal fragment','ERROR current']
    assert read_rotating(sftp,'/app.log',result['cursor'])['entries']==[]

def test_predecessor_renamed_again_while_draining():
    from app.services.incremental_logs import read_rotating
    class Multiple:
        data={'/app.log':b'old\n'}
        def stat(self,path):
            if path not in self.data: raise FileNotFoundError(path)
            return SimpleNamespace(st_size=len(self.data[path]))
        def open(self,path,mode): return File(self.data[path])
        def listdir(self,path): return [p.lstrip('/') for p in self.data]
    sftp=Multiple();cursor=read_file(sftp,'/app.log')['cursor']
    sftp.data={'/app.log.1':b'old\nERROR one\nERROR two\n','/app.log':b'ERROR current\n'}
    result=read_rotating(sftp,'/app.log',cursor,limit=1)
    assert result['entries']==['ERROR one']
    sftp.data['/app.log.2']=sftp.data.pop('/app.log.1')
    result=read_rotating(sftp,'/app.log',result['cursor'])
    assert result['entries']==['ERROR two','ERROR current']
