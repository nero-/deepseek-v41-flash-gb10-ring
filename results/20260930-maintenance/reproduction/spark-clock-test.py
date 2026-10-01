import argparse,importlib.util,json,time
from pathlib import Path
s=importlib.util.spec_from_file_location('m','/tmp/spark-maintenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
s=importlib.util.spec_from_file_location('k',m.ROOT/'scripts/kk926-trial.py');k=importlib.util.module_from_spec(s);s.loader.exec_module(k)
k.F=m.F;k.REMOTE='/home/nero/maintenance-20260930'
p=argparse.ArgumentParser();p.add_argument('phase',choices=['stock','2300','stock-repeat','2300-repeat']);a=p.parse_args();phase=a.phase
assert not (m.F/(phase+'-screen.json')).exists(),'Do not overwrite completed evidence'
for rank in range(4):
 argv=['nvidia-smi','-lgc','0,2300'] if phase.startswith('2300') else ['nvidia-smi','-rgc']
 r=m.record(rank,phase+'-clock',argv,True);assert r.returncode==0,(rank,r.stdout,r.stderr)
 m.t.remote(rank,['mkdir','-p',k.REMOTE])
telemetry=[]
try:
 for rank in range(4):
  out=k.REMOTE+'/'+phase+f'-telemetry-r{rank}.csv'
  code="import subprocess,sys\nf=open(sys.argv[1],'w');p=subprocess.Popen(['timeout','1200','nvidia-smi','--query-gpu=timestamp,clocks.sm,power.draw,temperature.gpu,utilization.gpu,clocks_event_reasons.active','--format=csv','--loop=1'],stdout=f,stderr=subprocess.STDOUT,start_new_session=True);print(p.pid)"
  pid=int(m.t.remote(rank,['python3','-c',code,out]).stdout.strip());telemetry.append((rank,pid,out))
 time.sleep(10)
 (m.F/(phase+'-start.json')).write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'telemetry':telemetry}))
 if phase=='2300-repeat':
  name=phase+'-screen';out=k.REMOTE+'/'+name+'.json'
  argv=json.loads((m.F/'stock-screen-argv.json').read_text())
  for flag,value in [('--contexts','8192'),('--concurrency','8'),('--duration','60'),('--output',out)]:argv[argv.index(flag)+1]=value
  argv.remove('--standalone-prefill');i=argv.index('--prefill-contexts');del argv[i:i+2];argv.append('--skip-prefill')
  (m.F/(name+'-argv.json')).write_text(json.dumps(argv,indent=2))
  launcher="import json,subprocess,sys\na=json.load(sys.stdin)\nwith open(sys.argv[1],'w') as f:r=subprocess.run(a,input='n'+chr(10),text=True,stdout=f,stderr=subprocess.STDOUT)\nraise SystemExit(r.returncode)"
  k.run(name,3,['python3','-c',launcher,out+'.log'],json.dumps(argv))
  for remote,local in [(out,name+'.json'),(out.replace('.json','.matched-request.json'),name+'.matched-request.json'),(out+'.log',name+'.txt')]:
   (m.F/local).write_text(m.t.remote(3,['cat',remote]).stdout)
 else:k.screen(phase+'-screen',duration=30)
finally:
 for rank,pid,out in telemetry:
  code="import os,signal,sys;from pathlib import Path\npid=int(sys.argv[1]);p=Path('/proc')/str(pid)/'cmdline'\nif p.exists():\n c=p.read_bytes();assert b'nvidia-smi' in c and b'timeout' in c;os.killpg(pid,signal.SIGTERM)"
  m.t.remote(rank,['python3','-c',code,str(pid)],check=False)
  r=m.t.remote(rank,['cat',out],check=False);(m.F/(phase+f'-telemetry-r{rank}.csv')).write_text(r.stdout)
 if phase.startswith('2300'):
  for rank in range(4):
   r=m.record(rank,'reset-after-test',['nvidia-smi','-rgc'],True);assert r.returncode==0
print('COMPLETE',phase,flush=True)
