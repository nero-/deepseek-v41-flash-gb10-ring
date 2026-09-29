#!/usr/bin/env python3
"""Stage and run a rollback-capable KK926 image trial on the existing fleet."""
import argparse,base64,copy,hashlib,importlib.util,json,subprocess,time,zipfile
from pathlib import Path
s=importlib.util.spec_from_file_location('trial',Path(__file__).with_name('research-trial.py'));t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
ROOT=Path(__file__).resolve().parents[1];F=ROOT/'results/20260929-kk926';REMOTE='/home/nero/kk926-20260929';BASE=json.loads((ROOT/'image/kk926/manifest.json').read_text())['base_image']
NAMES=[f'ds41-kk926-r{i}' for i in range(4)]
def run(name,rank,argv,data=None,expected=0):
 (F/(name+'-command.json')).write_text(json.dumps({'rank':rank,'argv':argv},indent=2))
 print('START',name,flush=True);r=t.remote(rank,argv,data,check=False);(F/(name+'.txt')).write_text(r.stdout+r.stderr)
 (F/(name+'-status.json')).write_text(json.dumps({'exit_code':r.returncode,'expected_exit_code':expected},indent=2))
 print('DONE',name,r.returncode,flush=True);assert r.returncode==expected,(name,r.returncode)
 return r

def screen(name, focused=False):
 out=REMOTE+'/'+name+'.json'
 argv=['/home/nero/bench/.venv/bin/python','-u','/home/nero/bench/lil_matched.py','/home/nero/bench/llm-inference-bench/llm_decode_bench.py','--host','192.168.50.219','--port','8015','--model','DeepSeek-V4.1-Flash-TP4','--no-hw-monitor','--display-mode','plain','--no-resume','--temperature','1','--contexts','8192,131072','--concurrency','1,8,16','--duration','20','--max-tokens','2048','--standalone-prefill','--prefill-contexts','8k,128k','--output',out]
 if focused:
  argv[argv.index('--contexts')+1]='131072';argv[argv.index('--concurrency')+1]='2,16';argv[argv.index('--duration')+1]='30'
  argv.remove('--standalone-prefill');i=argv.index('--prefill-contexts');del argv[i:i+2]
  argv.extend(['--skip-prefill','--run-burst','--burst-requests-per-concurrency','1','--burst-warmup-request-count','1'])
 launcher="import json,subprocess,sys\na=json.load(sys.stdin)\nwith open(sys.argv[1],'w') as f:r=subprocess.run(a,input='n'+chr(10),text=True,stdout=f,stderr=subprocess.STDOUT)\nraise SystemExit(r.returncode)"
 t.remote(3,['mkdir','-p',REMOTE]);(F/(name+'-argv.json')).write_text(json.dumps(argv,indent=2))
 run(name,3,['python3','-c',launcher,out+'.log'],json.dumps(argv))
 for remote,local in [(out,name+'.json'),(out.replace('.json','.matched-request.json'),name+'.matched-request.json'),(out+'.log',name+'.txt')]:
  (F/local).write_text(t.remote(3,['cat',remote]).stdout)

def stage_tests():
 data={}
 for p in (ROOT/'bench/upstream/kk926').glob('*.py'):data[p.name]=base64.b64encode(p.read_bytes()).decode()
 for name in ['compressor-ring-slots.py','kk926-test-launch.py']:data[name]=base64.b64encode((ROOT/'bench'/name).read_bytes()).decode()
 for whl in Path('/tmp/kk926-wheels').glob('*.whl'):
  with zipfile.ZipFile(whl) as z:
   for name in z.namelist():
    if not name.endswith('/'):data['deps/'+name]=base64.b64encode(z.read(name)).decode()
 code="import json,sys,base64;from pathlib import Path\nr=Path(sys.argv[1])\nfor n,b in json.load(sys.stdin).items():\n p=r/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(b))"
 t.parallel(lambda rank:t.remote(rank,['python3','-c',code,REMOTE+'/tests'],json.dumps(data)))
 (F/'test-dependency-sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/tmp/kk926-wheels').glob('*.whl')},indent=2))

def gpu_tests():
 assert (F/'baseline-screen.json').exists()
 run('stop-selected',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','down'])
 stage_tests()
 images=json.loads((F/'images.json').read_text())
 def command(image,args):return ['docker','run','--rm','--gpus','all','--network','none','--shm-size','1g','--mount','type=bind,src='+REMOTE+'/tests,dst=/tests,readonly','--entrypoint','python3',image,'/tests/kk926-test-launch.py',*args]
 run('baseline-ring-slots',0,command(BASE,['/tests/compressor-ring-slots.py']),expected=1)
 def one(rank):
  image=images[rank]['image_id'];run('corrected-ring-slots-r'+str(rank),rank,command(image,['/tests/compressor-ring-slots.py']))
  run('upstream-tests-r'+str(rank),rank,command(image,['-m','pytest','-q','-p','no:cacheprovider','/tests/test_gpu_block_table.py','/tests/test_deepseek_v4_1_compressor.py']))
 t.parallel(one)

def start():
 before=json.loads((F/'selected-before.json').read_text());assert json.loads(t.remote(0,['cat','/etc/deepseek-ring/optimized-specs.json']).stdout)==before
 images=json.loads((F/'images.json').read_text());docs=copy.deepcopy(before['specs'])
 policy=(ROOT.parent/'sparkring-installer/runtime/common/loader-seccomp.json').read_text()
 writer="import sys;from pathlib import Path;p=Path(sys.argv[1]);p.parent.mkdir(exist_ok=True,parents=True);p.write_text(sys.stdin.read())"
 t.parallel(lambda r:t.remote(r,['python3','-c',writer,REMOTE+'/loader-seccomp.json'],policy))
 specs=[]
 for rank,d in enumerate(docs):
  assert not t.remote(rank,['docker','ps','-q']).stdout.strip(),'Non-idle node'
  d['name']=NAMES[rank];d['image_id']=images[rank]['image_id'];d['labels']={'io.local.deepseek-correction':'kk926','io.local.rank':str(rank)};d['security_opt']=['seccomp='+REMOTE+'/loader-seccomp.json']
  fields=dict(d);fields['mounts']=tuple(t.Bind(**m) for m in fields['mounts'])
  for k in ('entrypoint','command','devices','cap_add','security_opt','health_command'):fields[k]=tuple(fields[k])
  specs.append(t.ContainerSpec(**fields))
 (F/'trial-specs.json').write_text(json.dumps(docs,indent=2))
 t.parallel(lambda r:t.remote(r,t.docker_create(specs[r])));t.parallel(lambda r:t.remote(r,['docker','start',NAMES[r]]));print('TRIAL STARTED',flush=True)
 deadline=time.monotonic()+1800
 while time.monotonic()<deadline:
  state=t.parallel(lambda r:t.remote(r,['docker','inspect','--format','{{.State.Status}}',NAMES[r]]).stdout.strip());assert all(x=='running' for x in state),state
  if t.remote(0,['curl','-fsS','--max-time','3','http://127.0.0.1:8015/health'],check=False).returncode==0:
   (F/'trial-ready.json').write_text(json.dumps({'ready':True,'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}));print('TRIAL READY',flush=True);return
  time.sleep(10)
 raise TimeoutError('Trial startup timeout')

def stop_trial():
 def one(rank):
  name=NAMES[rank];r=t.remote(rank,['docker','inspect',name],check=False)
  if r.returncode:return
  doc=json.loads(r.stdout)[0]
  assert doc['Config']['Labels'].get('io.local.deepseek-correction')=='kk926'
  t.remote(rank,['docker','stop','--time','15',name])
  log=t.remote(rank,['docker','logs',name],check=False)
  (F/f'trial-rank{rank}.log').write_text(log.stdout+log.stderr)
  t.remote(rank,['docker','rm',name])
 t.parallel(one)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['baseline-screen','corrected-screen','corrected-screen-repeat','gpu-tests','start','restore']);a=p.parse_args()
 try:
  if a.action in ('baseline-screen','corrected-screen','corrected-screen-repeat'):screen(a.action)
  elif a.action=='gpu-tests':gpu_tests()
  elif a.action=='restore':
   stop_trial();run('restore-selected',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','up'])
  else:start()
 except BaseException:
  if a.action in ('gpu-tests','start'):
   stop_trial();run('automatic-rollback',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','up'])
  raise
