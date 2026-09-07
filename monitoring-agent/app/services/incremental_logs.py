"""Bounded SFTP reads with persistent byte positions; no remote shell required."""
import asyncio
import hashlib
import posixpath
import time
from app.services.ssh_service import create_ssh_client, _connect_kwargs

MAX_BYTES = 262144
MAX_LINES = 200


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_file(sftp, path, previous=None, limit=MAX_LINES, terminal=False):
    stat = sftp.stat(path)
    size = stat.st_size
    with sftp.open(path, 'rb') as stream:
        # First observation establishes a baseline, avoiding historical alerts.
        if previous is None:
            offset = size
            baseline = True
            reset = False
        else:
            offset = previous['offset']
            baseline = False
            reset = size < offset
            if not reset and previous.get('anchor_length'):
                stream.seek(offset - previous['anchor_length'])
                reset = digest(stream.read(previous['anchor_length'])) != previous['anchor_hash']
            if not reset and previous.get('head_length'):
                stream.seek(0)
                reset = digest(stream.read(previous['head_length'])) != previous['head_hash']
            if reset: offset = 0
        start = offset
        stream.seek(start)
        data = stream.read(min(MAX_BYTES, max(0,size-start))) if not baseline else b''
        complete = data.rfind(b'\n') + 1
        if terminal and start+len(data)==size: complete=len(data)
        if data and not complete and len(data) == MAX_BYTES:
            raise ValueError('Log line exceeds bounded read size; cursor not advanced')
        if complete:
            complete = sum(len(line) for line in data[:complete].splitlines(keepends=True)[:limit])
        consumed = data[:complete]
        offset += complete
        # On first observation, skip any incomplete historical line on next read.
        skip_fragment = bool(previous and previous.get('skip_fragment')) and not reset
        if baseline and size:
            stream.seek(size-1)
            skip_fragment = stream.read(1) != b'\n'
        entries = consumed.decode('utf-8',errors='replace').splitlines()
        if skip_fragment and entries:
            entries = entries[1:]
            skip_fragment = False
        head_length=min(offset,128)
        stream.seek(0)
        head=stream.read(head_length)
        anchor_length=min(offset,128)
        stream.seek(offset-anchor_length)
        anchor=stream.read(anchor_length)
        cursor={'offset':offset,'head_length':head_length,'head_hash':digest(head),
                'anchor_length':anchor_length,'anchor_hash':digest(anchor),'skip_fragment':skip_fragment,'last_read':time.time()}
        return {'path':path,'entries':entries,'cursor':cursor,'baseline':baseline,'reset':reset,'backlog_bytes':max(0,size-offset)}


def paths_for(project, home):
    import json
    from urllib.parse import urlsplit
    domain=project.get('domain') or ''
    domain=urlsplit(domain if '://' in domain else '//'+domain).hostname or ''
    root=project.get('project_path') or home
    def expand(path):
        if path=='~': return home
        if path.startswith('~/'): return posixpath.join(home,path[2:])
        return path if path.startswith('/') else posixpath.join(home,path)
    root=expand(root)
    configured=project.get('log_locations') or []
    if isinstance(configured,str): configured=json.loads(configured)
    candidates=configured or [f'{home}/logs/{domain}.error.log',f'{home}/logs/{domain}.php.error.log',f'{home}/logs/{domain}/error.log',f'{home}/logs/error.log',f'{root}/error_log',f'{root}/logs/error.log',f'{root}/storage/logs/laravel.log',f'{home}/.logs/{domain}.error.log',f'{home}/php.error.log']
    if not isinstance(candidates,list) or any(not isinstance(p,str) for p in candidates):
        raise ValueError('Log locations must be a list of paths')
    if len(candidates)>32: raise ValueError('At most 32 log files are supported per project')
    return list(dict.fromkeys(expand(path) for path in candidates))


def matches(sftp,path,cursor):
    try:
        if sftp.stat(path).st_size<cursor['offset']: return False
        with sftp.open(path,'rb') as stream:
            stream.seek(0)
            if digest(stream.read(cursor['head_length']))!=cursor['head_hash']: return False
            stream.seek(cursor['offset']-cursor['anchor_length'])
            return digest(stream.read(cursor['anchor_length']))==cursor['anchor_hash']
    except FileNotFoundError: return False


def read_rotating(sftp,path,previous,limit=MAX_LINES):
    predecessor=previous.get('predecessor_path') if previous else None
    if previous and (predecessor or not matches(sftp,path,previous)):
        if predecessor and not matches(sftp,predecessor,previous): predecessor=None
        if not predecessor:
            directory,name=posixpath.split(path)
            candidates=sorted(n for n in sftp.listdir(directory) if n.startswith(name+'.') and not n.endswith(('.gz','.zip')))
            predecessor=next((posixpath.join(directory,n) for n in candidates if matches(sftp,posixpath.join(directory,n),previous)),None)
        if predecessor:
            old=read_file(sftp,predecessor,previous,limit,terminal=True)
            if old['reset']: raise ValueError('Rotated predecessor changed before it could be consumed')
            if old['backlog_bytes']:
                old['path']=path
                old['cursor']['predecessor_path']=predecessor
                return old
            remaining=limit-len(old['entries'])
            zero={'offset':0,'head_length':0,'anchor_length':0}
            if remaining==0:
                old['path']=path
                old['cursor']['predecessor_path']=predecessor
                return old
            current=read_file(sftp,path,zero,remaining)
            current['entries']=old['entries']+current['entries']
            current['reset']=True
            return current
        current=read_file(sftp,path,{'offset':0,'head_length':0,'anchor_length':0},limit)
        current['reset']=True
        current['coverage_warning']='Log was replaced/truncated; its unread predecessor is unavailable'
        return current
    return read_file(sftp,path,previous,limit)


class DeadlineSFTP:
    def __init__(self,sftp,deadline): self.sftp,self.deadline=sftp,deadline
    def check(self):
        left=self.deadline-time.monotonic()
        if left<=0: raise TimeoutError('Log scan deadline exceeded')
        self.sftp.get_channel().settimeout(min(left,10))
    def __getattr__(self,name):
        def call(*args,**kwargs):
            self.check()
            value=getattr(self.sftp,name)(*args,**kwargs)
            return DeadlineFile(value,self) if name=='open' else value
        return call

class DeadlineFile:
    def __init__(self,file,owner): self.file,self.owner=file,owner
    def __enter__(self): return self
    def __exit__(self,*args): self.file.close()
    def __getattr__(self,name):
        def call(*args,**kwargs):
            self.owner.check()
            return getattr(self.file,name)(*args,**kwargs)
        return call


def read_remote(project, connection, cursors):
    client=create_ssh_client()
    deadline=time.monotonic()+45
    try:
        kwargs=_connect_kwargs(**connection)
        kwargs.update(timeout=10,auth_timeout=10,banner_timeout=10,channel_timeout=10)
        client.connect(**kwargs)
        with client.open_sftp() as raw_sftp:
            sftp=DeadlineSFTP(raw_sftp,deadline)
            files=[]
            candidates=paths_for(project,sftp.normalize('.'))
            if project.get('log_locations') not in (None,[], '[]'):
                for path in candidates: sftp.stat(path)
            candidates.sort(key=lambda path:cursors.get(path,{}).get('last_read',0))
            remaining=MAX_LINES
            for path in candidates:
                if remaining<=0: break
                try:
                    result=read_rotating(sftp,path,cursors.get(path),remaining)
                    files.append(result)
                    remaining-=len(result['entries'])
                except FileNotFoundError:
                    if project.get('log_locations') not in (None,[], '[]'):
                        raise FileNotFoundError('A configured log is missing')
                    continue
            if not files: raise FileNotFoundError('No configured application log could be read')
            return files
    finally: client.close()


async def read_incremental(project, connection, cursors):
    return await asyncio.to_thread(read_remote,project,connection,cursors)
