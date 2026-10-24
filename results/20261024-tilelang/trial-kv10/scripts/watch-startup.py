#!/usr/bin/env python3
"""Bounded host-memory/SSH/kernel audit during a coordinated startup.

Stop by creating results/20261024-trial/startup-LABEL.stop. Do not run during
final benchmarks. Uses read-only, time-limited SSH calls; no GPU sampling job.
"""
import argparse
import concurrent.futures
import datetime
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import urllib.request
from common import RESULTS, TRIAL_CONTAINER

HOSTS=('192.168.50.219','192.168.50.129','192.168.50.192','192.168.50.23')
ALIASES=('spark-r0','spark-r1','gx10-r1','gx10-r0')
CODE='''import json,time,pathlib
m={l.split()[0].rstrip(':'):int(l.split()[1]) for l in pathlib.Path('/proc/meminfo').read_text().splitlines()}
print(json.dumps({'utc_epoch':time.time(),'used_gib':(m['MemTotal']-m['MemAvailable'])/1024**2,
'available_gib':m['MemAvailable']/1024**2,'free_gib':m['MemFree']/1024**2,
'swap_used_gib':(m['SwapTotal']-m['SwapFree'])/1024**2,
'memory_pressure':pathlib.Path('/proc/pressure/memory').read_text(),
'uptime':pathlib.Path('/proc/uptime').read_text().strip()}))
'''
p=argparse.ArgumentParser();p.add_argument('label');p.add_argument('--seconds',type=int,default=2400)
p.add_argument('--guard-gib',type=float,default=0.0,help='stop the trial containers if any rank falls below this MemAvailable (0 disables)')
a=p.parse_args()
assert re.fullmatch('[a-zA-Z0-9-]+',a.label) and 0<a.seconds<=3600
prefix=RESULTS/('startup-'+a.label);stop=Path(str(prefix)+'.stop')
assert not stop.exists()
started=time.time();samples=[];first_healthy=None;guard_tripped=None

def ssh(rank,args,timeout=8):
    cmd=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=4','-o','ServerAliveInterval=2','-o','ServerAliveCountMax=2',
         '-o','HostName='+HOSTS[rank],'-o','ProxyCommand=none',ALIASES[rank],shlex.join(args)]
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
        return {'rank':rank,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    except subprocess.TimeoutExpired:
        return {'rank':rank,'returncode':124,'stdout':'','stderr':'SSH command timed out'}

def observe(rank):
    t=time.monotonic();r=ssh(rank,['python3','-c',CODE]);r['ssh_seconds']=time.monotonic()-t
    if r['returncode']==0:
        r['sample']=json.loads(r.pop('stdout'))
    return r

with Path(str(prefix)+'.jsonl').open('x') as f, concurrent.futures.ThreadPoolExecutor(4) as pool:
    print('WATCHING_STARTUP',a.label,'stop_file',str(stop),flush=True)
    while time.time()-started<a.seconds and not stop.exists():
        begin=time.monotonic();rows=list(pool.map(observe,range(4)));samples.append(rows)
        t=time.monotonic()
        try:
            with urllib.request.urlopen('http://192.168.50.219:8015/health',timeout=3) as response:
                api={'status':response.status,'seconds':time.monotonic()-t}
                if first_healthy is None:first_healthy=time.time()
        except Exception as error:
            api={'status':None,'seconds':time.monotonic()-t,'error':str(error)}
        f.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'nodes':rows,'api':api})+'\n');f.flush()
        low=[r['rank'] for r in rows if r['returncode']==0 and r['sample']['available_gib']<a.guard_gib]
        if low:
            # Fail closed, as the recipe's own startup guard does: stop every rank of the trial.
            stops=list(pool.map(lambda rank:ssh(rank,['docker','stop','--time','10',TRIAL_CONTAINER.format(rank=rank)],timeout=40),range(4)))
            f.write(json.dumps({'guard_tripped':low,'guard_gib':a.guard_gib,'stops':stops})+'\n');f.flush()
            print('MEMORY_GUARD_TRIPPED',low,flush=True)
            guard_tripped=low
            break
        time.sleep(max(0,2-(time.monotonic()-begin)))
    kernels=list(pool.map(lambda rank:ssh(rank,['journalctl','-k','--since','@'+str(int(started)),'--no-pager'],timeout=15),range(4)))
summary=[]
for rank,kernel in enumerate(kernels):
    Path(str(prefix)+f'-kernel-r{rank}.log').write_text(kernel['stdout']+kernel['stderr'])
    rows=[s[rank] for s in samples];ok=[r['sample'] for r in rows if r['returncode']==0]
    events=[x for x in kernel['stdout'].splitlines() if re.search(r'out of memory|oom-kill|killed process|NVRM|Xid|page allocation failure',x,re.I)]
    summary.append({'rank':rank,'samples':len(rows),'ssh_failures':[r for r in rows if r['returncode']],
                    'max_ssh_seconds':max((r['ssh_seconds'] for r in rows),default=None),
                    'peak_used_gib':max((r['used_gib'] for r in ok),default=None),
                    'minimum_available_gib':min((r['available_gib'] for r in ok),default=None),
                    'peak_swap_used_gib':max((r['swap_used_gib'] for r in ok),default=None),
                    'kernel_events':events,'kernel_read_returncode':kernel['returncode']})
result={'label':a.label,'started_epoch':started,'ended_epoch':time.time(),'first_api_healthy_epoch':first_healthy,'stop_requested':stop.exists(),'guard_gib':a.guard_gib,'guard_tripped':guard_tripped,'nodes':summary}
with Path(str(prefix)+'-summary.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(summary,indent=2),flush=True)
