import concurrent.futures,importlib.util,json,subprocess,time
from pathlib import Path
ROOT=Path('/Users/jg/Agent/Builds/deepseek-v41-flash-ring');F=ROOT/'results/20260930-maintenance';F.mkdir(exist_ok=True)
s=importlib.util.spec_from_file_location('t',ROOT/'scripts/research-trial.py');t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
IMAGE='sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf'
def root(rank,argv):
 if rank in (2,3):return t.remote(rank,['sudo','-n',*argv],check=False)
 return t.remote(rank,['docker','run','--rm','--privileged','--pid=host','--network=host','--env','LD_PRELOAD=','--env','LD_LIBRARY_PATH=','--entrypoint','nsenter',IMAGE,'--target','1','--mount','--uts','--ipc','--net','--pid','--',*argv],check=False)
def record(rank,name,argv,admin=False):
 r=root(rank,argv) if admin else t.remote(rank,argv,check=False)
 (F/f'{name}-r{rank}.json').write_text(json.dumps({'argv':argv,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n');return r
if __name__=='__main__':
 def inspect(rank):
  r=record(rank,'root-check',['id','-u'],True);assert r.returncode==0 and r.stdout.strip()=='0'
  r=record(rank,'apt-refresh',['apt-get','update'],True);assert r.returncode==0
  r=record(rank,'fw-refresh',['fwupdmgr','refresh','--force'],True)
  r=record(rank,'apt-plan',['apt-get','--simulate','dist-upgrade'],True);assert r.returncode==0
  r=record(rank,'fw-plan',['fwupdmgr','get-updates','--json']);print(rank,'firmware',r.stdout[:300],flush=True)
  r=record(rank,'packages',['sh','-c',"dpkg-query -W -f='${Package} ${Version}\\n' 'linux-image*' 'linux-headers*' 'dgx*' 'nvidia-driver*' 2>/dev/null" ]);print(rank,'done',flush=True)
 with concurrent.futures.ThreadPoolExecutor(4) as pool:list(pool.map(inspect,range(4)))
