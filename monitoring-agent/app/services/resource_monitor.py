"""Read-only Linux resource sampling using one bounded SSH command."""
import json
import math
import shlex
from app.db import fetch_one,execute,execute_returning
from app.services.ssh_service import ssh_service
from app.services.error_scanner import _load_connection

DEFAULTS={'cpu':{'warning':80,'critical':95},'memory':{'warning':80,'critical':95},'disk':{'warning':75,'critical':90},'inodes':{'warning':80,'critical':95}}
CATEGORIES={'cpu':'CPU_OVERLOAD','memory':'MEMORY_EXHAUSTION','disk':'DISK_FULL','inodes':'DISK_FULL'}


def resource_command(path):
    path=path or '~'
    quoted='"$HOME"' if path=='~' else '"$HOME"/'+shlex.quote(path[2:]) if path.startswith('~/') else shlex.quote(path)
    return """export LC_ALL=C
first=$(awk '/^cpu /{for(i=2;i<=9;i++)t+=$i;print t,$5+$6}' /proc/stat)
sleep 1
second=$(awk '/^cpu /{for(i=2;i<=9;i++)t+=$i;print t,$5+$6}' /proc/stat)
awk -v a="$first" -v b="$second" 'BEGIN{split(a,x);split(b,y);t=y[1]-x[1];if(t<=0)exit 1;printf "cpu=%.4f\\n",100*(1-(y[2]-x[2])/t)}' || exit 1
awk '/^MemTotal:/{t=$2}/^MemAvailable:/{a=$2;found=1}END{if(!found||t<=0)exit 1;printf "memory=%.4f\\n",100*(t-a)/t}' /proc/meminfo || exit 1
"""+f"df -Pk -- {quoted} | awk 'NR==2{{gsub(/%/,\"\",$5);print \"disk=\"$5}}'\n"+f"df -Pi -- {quoted} | awk 'NR==2{{gsub(/%/,\"\",$5);print \"inodes=\"$5}}'"


def parse_metrics(output):
    rows=dict(line.split('=',1) for line in output.splitlines() if '=' in line)
    metrics={}
    for key in DEFAULTS:
        try: value=float(rows[key])
        except (KeyError,ValueError): raise ValueError('Missing or invalid '+key+' measurement')
        if not math.isfinite(value) or not 0<=value<=100: raise ValueError('Out-of-range '+key+' measurement')
        metrics[key]=value
    return metrics


def conditions(metrics,config):
    thresholds=config.get('thresholds') or DEFAULTS
    result=[]
    for key,value in metrics.items():
        limits=thresholds.get(key,DEFAULTS[key])
        severity='CRITICAL' if value>=limits['critical'] else 'MEDIUM' if value>=limits['warning'] else None
        if severity: result.append({'key':'resource:'+key,'category':CATEGORIES[key],'severity':severity,'value':value,'thresholds':limits})
    return result


async def check_resources(project_id, *, project_snapshot=None, connection_snapshot=None):
    project=project_snapshot if project_snapshot is not None else await fetch_one('SELECT * FROM projects WHERE project_id=$1',project_id)
    if not project: raise ValueError('Project missing')
    connection=connection_snapshot if connection_snapshot is not None else await _load_connection(dict(project))
    if not connection: raise ValueError('No SSH connection available')
    result=await ssh_service.execute_command(**connection,command=resource_command(project['project_path']),timeout=15)
    if not result['success']: raise RuntimeError('Resource SSH probe failed')
    metrics=parse_metrics(result['output'])
    config=json.loads(project['monitoring_config']) if isinstance(project['monitoring_config'],str) else project['monitoring_config']
    findings=conditions(metrics,config.get('resources',{}))
    status='CRITICAL' if any(f['severity']=='CRITICAL' for f in findings) else 'WARNING' if findings else 'HEALTHY'
    await execute("INSERT INTO monitoring_checks(project_id,client_id,check_type,status,disk_usage_percent,cpu_usage_percent,memory_usage_percent,details) VALUES ($1,$2,'resources',$3,$4,$5,$6,$7::jsonb)",project_id,project['client_id'],status,round(metrics['disk'],2),round(metrics['cpu'],2),round(metrics['memory'],2),json.dumps(metrics))
    return {'status':status,'metrics':metrics,'conditions':findings}


async def evaluate_resources(project_id,result):
    from app.services.condition_service import observe
    await observe(project_id,'resources',result['conditions'])
