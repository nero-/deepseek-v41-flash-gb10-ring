#!/usr/bin/env python3
"""Build, compare and reversibly select Fastokens on the corrected fleet."""
import argparse,base64,copy,hashlib,importlib.util,json,time,urllib.request
from pathlib import Path
def load(name,file):
 s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
k=load('kk','kk926-trial.py');p=load('promotion','promote-research.py')
k.F=k.ROOT/'results/20260929-fastokens';k.F.mkdir(exist_ok=True);k.REMOTE='/home/nero/fastokens-20260929'
F=k.F;R=k.REMOTE
def read(n):return json.loads((F/n).read_text())
def build():
 assert not (F/'selected-before.json').exists(),'Do not overwrite existing campaign'
 before=k.t.remote(0,['cat',p.CONFIG_DIR+'/optimized-specs.json']).stdout
 selected=json.loads(before);assert selected['runtime_correction']['name']=='kk926-compressor-ring'
 assert all(d['environment'].get('VLLM_USE_FASTOKENS','0')=='0' for d in selected['specs'])
 (F/'selected-before.json').write_text(before)
 meta=json.loads((k.ROOT/'results/20260929-kk926/fastokens-package.json').read_text());wheel=next(w for w in meta['aarch64_wheels'] if 'manylinux' in w['filename'])
 data=urllib.request.urlopen(wheel['url'],timeout=60).read();assert hashlib.sha256(data).hexdigest()==wheel['sha256']
 manifest={'version':meta['version'],**wheel};(k.ROOT/'image/fastokens/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 files={x.name:base64.b64encode(x.read_bytes()).decode() for x in (k.ROOT/'image/fastokens').iterdir() if x.is_file()};files[wheel['filename']]=base64.b64encode(data).decode()
 stage="import json,sys,base64;from pathlib import Path\np=Path(sys.argv[1]);p.mkdir(parents=True,exist_ok=True)\nfor name,data in json.load(sys.stdin).items():(p/name).write_bytes(base64.b64decode(data))"
 def one(rank):
  parent=selected['specs'][rank]['image_id'];info=json.loads(k.t.remote(rank,['docker','inspect',f'ds41-optimized-r{rank}']).stdout)[0]
  assert info['Image']==parent and info['State']['Running']
  k.t.remote(rank,['python3','-c',stage,R+'/build'],json.dumps(files));k.t.remote(rank,['docker','tag',parent,'dsv41-pinned-base:fastokens'])
  k.run(f'build-r{rank}',rank,['docker','build','--network','none','--pull=false','-t','dsv41-sparkring:kk926-fastokens-032',R+'/build'])
  image=k.t.remote(rank,['docker','image','inspect','--format','{{.Id}}','dsv41-sparkring:kk926-fastokens-032']).stdout.strip()
  k.run(f'verify-r{rank}',rank,['docker','run','--rm','--network','none','--entrypoint','python3',image,'/opt/sparkring/toolchain/toolchain.py','verify'])
  return {'rank':rank,'parent_image':parent,'image_id':image}
 images=k.t.parallel(one);(F/'images.json').write_text(json.dumps(images,indent=2));print('BUILT ALL',flush=True)
def stage():
 writer="import sys;from pathlib import Path;p=Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(sys.stdin.read())"
 for name in ['functional.py','long-functional.py','mixed_traffic.py','tokenizer-serving.py']:
  k.t.remote(0,['python3','-c',writer,R+'/'+name],(k.ROOT/'bench'/name).read_text())
def job(name,args,output=None):
 try:k.run(name,0,['python3','-u',*args])
 finally:
  if output:
   r=k.t.remote(0,['cat',R+'/'+output],check=False)
   if r.returncode==0:(F/output).write_text(r.stdout)
def benchmark(label):
 stage()
 job(label+'-functional',[R+'/functional.py','http://127.0.0.1:8015/v1'])
 api_args=[R+'/tokenizer-serving.py','--label',label,'--output',R+'/'+label+'-api.json']
 if label=='fastokens':api_args.extend(['--nonce',read('hf-api.json')['nonce'],'--prompt-label','hf'])
 job(label+'-api',api_args,label+'-api.json')
 k.screen(label+'-screen',duration=30)
 if label=='fastokens':
  job('fastokens-long-functional',[R+'/long-functional.py','--suite',R+'/functional.py','--output',R+'/fastokens-long-functional.json'],'fastokens-long-functional.json')
  job('fastokens-mixed',[R+'/mixed_traffic.py','fastokens','--integrity','--prefill-records','6144','--min-uncached-tokens','65536','--rounds','1','--output',R+'/fastokens-mixed.json'],'fastokens-mixed.json')
def switch():
 text=k.t.remote(0,['cat',p.CONFIG_DIR+'/optimized-specs.json']).stdout;assert json.loads(text)==read('selected-before.json')
 before=json.loads(text);after=copy.deepcopy(before);images=read('images.json')
 for rank,d in enumerate(after['specs']):
  d['image_id']=images[rank]['image_id'];d['environment']['VLLM_USE_FASTOKENS']='1';d['labels']['io.local.fastokens']='0.3.2'
 after['tokenizer_backend']={'name':'fastokens','version':'0.3.2','receipt':str(F)}
 (F/'selected-candidate.json').write_text(json.dumps(after,indent=2)+'\n')
 tag='.before-fastokens-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());state={'tag':tag,'renamed':[],'installed':False};(F/'switch-state.json').write_text(json.dumps(state))
 k.run('stop-hf',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','down'])
 try:
  for rank in range(4):
   name=f'ds41-optimized-r{rank}';old=f'ds41-before-fastokens-r{rank}'
   assert k.t.remote(rank,['docker','inspect',old],check=False).returncode!=0
   info=json.loads(k.t.remote(rank,['docker','inspect',name]).stdout)[0];assert not info['State']['Running'] and info['Image']==before['specs'][rank]['image_id']
   k.t.remote(rank,['docker','rename',name,old]);state['renamed'].append(rank);(F/'switch-state.json').write_text(json.dumps(state))
  p.bundle(0,p.CONFIG_DIR,tag,'install',{'optimized-specs.json':json.dumps(after,indent=2)+'\n'},{'optimized-specs.json':hashlib.sha256(text.encode()).hexdigest()})
  state['installed']=True;(F/'switch-state.json').write_text(json.dumps(state))
  k.run('start-fastokens',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','up'])
  activation=[]
  for rank in range(4):
   info=json.loads(k.t.remote(rank,['docker','inspect',f'ds41-optimized-r{rank}']).stdout)[0]
   assert info['Image']==images[rank]['image_id'] and info['State']['Running']
   env=dict(v.split('=',1) for v in info['Config']['Env']);assert env['VLLM_USE_FASTOKENS']=='1'
   activation.append({'rank':rank,'image':info['Image'],'flag':env['VLLM_USE_FASTOKENS']})
  log=k.t.remote(0,['docker','logs','ds41-optimized-r0']);lines=[line for line in (log.stdout+log.stderr).splitlines() if '[fastokens]' in line]
  assert any('successfully patched' in line for line in lines),'No successful API tokenizer patch observed'
  (F/'activation.json').write_text(json.dumps({'ranks':activation,'api_log':lines},indent=2))
 except BaseException:rollback();raise
def rollback():
 state=read('switch-state.json');images=read('images.json')
 current=k.t.remote(0,['cat',p.CONFIG_DIR+'/optimized-specs.json']).stdout
 assert current in [(F/'selected-before.json').read_text(),(F/'selected-candidate.json').read_text()],'Selection changed since this campaign; refusing rollback'
 for rank in state['renamed']:
  old=json.loads(k.t.remote(rank,['docker','inspect',f'ds41-before-fastokens-r{rank}']).stdout)[0]
  assert not old['State']['Running'] and old['Image']==images[rank]['parent_image']
 for rank in state['renamed']:
  name=f'ds41-optimized-r{rank}';r=k.t.remote(rank,['docker','inspect',name],check=False)
  if r.returncode==0:
   info=json.loads(r.stdout)[0];assert info['Image']==images[rank]['image_id'] and info['Config']['Labels'].get('io.local.fastokens')=='0.3.2'
   k.t.remote(rank,['docker','stop','--time','15',name]);k.t.remote(rank,['docker','rm',name])
 p.bundle(0,p.CONFIG_DIR,state['tag'],'rollback')
 for rank in state['renamed']:k.t.remote(rank,['docker','rename',f'ds41-before-fastokens-r{rank}',f'ds41-optimized-r{rank}'])
 k.run('restore-hf',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','up'])
 (F/'restored.json').write_text(json.dumps({'restored':True,'tag':state['tag']}))
def select():
 decision=read('decision.json');assert decision['decision']=='selected' and decision['performance_reviewed']
 for name in ['fastokens-functional','fastokens-api','fastokens-screen','fastokens-long-functional','fastokens-mixed']:
  assert read(name+'-status.json')['exit_code']==0,name
 if (F/'fastokens-c8-repeat-status.json').exists():
  assert read('fastokens-c8-repeat-status.json')['exit_code']==0
  repeat=read('fastokens-c8-repeat.json')['results'];assert len(repeat)==2
  assert all(not r['loop_detected'] and not r['failure_reason'] and not r['capacity_limited'] and not r['num_errors'] for r in repeat)
 api=read('fastokens-api.json');assert len(api['cases'])==3
 assert [c['prompt_sha256'] for c in api['cases']]==[c['prompt_sha256'] for c in read('hf-api.json')['cases']]
 for case in api['cases']:
  assert case['cold']['usage']['prompt_tokens_details']['cached_tokens']==0
  assert len(case['cached_c1'])==5 and len(case['cached_c8'])==8
  for q in [case['cold'],case['warmup'],*case['cached_c1'],*case['cached_c8']]:assert 'RING-7825-COBALT' in q['answer']
 assert read('fastokens-long-functional.json')['all_long_prefills']
 assert all(r['summary']['needle_pass'] and not r['summary']['errors'] for r in read('fastokens-mixed.json')['rounds'])
 screen=read('fastokens-screen.json');assert len(screen['results'])==6
 assert all(not r['loop_detected'] and not r['failure_reason'] and not r['capacity_limited'] for r in screen['results'])
 assert json.loads(k.t.remote(0,['cat',p.CONFIG_DIR+'/optimized-specs.json']).stdout)==read('selected-candidate.json')
 images=read('images.json');ranks=[]
 for rank in range(4):
  name=f'ds41-optimized-r{rank}';info=json.loads(k.t.remote(rank,['docker','inspect',name]).stdout)[0]
  assert info['Image']==images[rank]['image_id'] and info['State']['Running']
  code="import hashlib,json,os;from pathlib import Path;from importlib.metadata import distribution,version\nassert os.environ['VLLM_USE_FASTOKENS']=='1';assert version('fastokens')=='0.3.2'\nm=json.loads(Path('/opt/kk926/manifest.json').read_text())\nfor name,pin in m['files'].items():assert hashlib.sha256((Path('/usr/local/lib/python3.12/dist-packages')/name).read_bytes()).hexdigest()==pin['after']\nd=distribution('fastokens');receipt=json.loads(Path('/opt/fastokens/installed.json').read_text())\nfor name,sha in receipt['installed_files'].items():assert hashlib.sha256(d.locate_file(name).read_bytes()).hexdigest()==sha,name\nprint(json.dumps({'fastokens':'0.3.2','flag':os.environ['VLLM_USE_FASTOKENS'],'compressor_hashes_verified':True,'tokenizer_hashes_verified':True}))"
  result=k.run(f'selected-verify-r{rank}',rank,['docker','exec',name,'python3','-c',code]);ranks.append({'rank':rank,'image':info['Image'],**json.loads(result.stdout)})
 k.run('selected-status',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','status'])
 (F/'deployment.json').write_text(json.dumps({'selected':'kk926-fastokens-0.3.2','ranks':ranks,'rollback':read('switch-state.json'),'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())},indent=2));print('SELECTED FASTOKENS',flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['build','baseline','switch','candidate','rollback','select']);a=parser.parse_args()
 if a.action=='build':build()
 elif a.action=='baseline':benchmark('hf')
 elif a.action=='switch':switch()
 elif a.action=='candidate':benchmark('fastokens')
 elif a.action=='select':select()
 else:rollback()
