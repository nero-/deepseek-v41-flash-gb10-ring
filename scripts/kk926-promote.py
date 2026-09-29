#!/usr/bin/env python3
"""Select the qualified KK926 image, preserving old containers and config."""
import copy,hashlib,importlib.util,json,time
from pathlib import Path
def load(name,file):
 s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
k=load('kk','kk926-trial.py');p=load('promotion','promote-research.py');F=k.F
def read(name):return json.loads((F/name).read_text())
def main():
 statuses=read('qualification-statuses.json')
 for n in ['functional','corrected-consistency','corrected-screen','long-functional','mixed-integrity','cold-1m','corrected-128k-repeat','guards']:assert statuses.get(n)==0,n
 for r in range(4):
  for n in ['corrected-ring-slots','upstream-tests']:assert read(f'{n}-r{r}-status.json')['exit_code']==0
 before_bins=read('baseline-consistency.json')['bins'];after_bins=read('corrected-consistency.json')['bins']
 assert len(read('corrected-consistency.json')['requests'])==8
 assert after_bins[-1]['coarsened_kl'] < before_bins[-1]['coarsened_kl']*.5,'Drift improvement gate'
 assert after_bins[-1]['top1_agreement'] > before_bins[-1]['top1_agreement']
 cold=read('cold-1m.json');assert cold['needle_pass'] and cold['cold_confirmed'] and cold['usage']['prompt_tokens']>=1000000
 assert read('long-functional.json')['all_long_prefills']
 for r in read('mixed-integrity.json')['rounds']:assert r['summary']['needle_pass'] and not r['summary']['errors']
 decision=read('promotion-decision.json');assert decision['decision']=='promote' and decision['performance_reviewed']
 text=k.t.remote(0,['cat','/etc/deepseek-ring/optimized-specs.json']).stdout
 before=json.loads(text);assert before==read('selected-before.json')
 images=read('images.json');after=copy.deepcopy(before)
 after['source_receipt']=str(F);after['runtime_correction']={'name':'kk926-compressor-ring','manifest':read('../../image/kk926/manifest.json')}
 for rank,d in enumerate(after['specs']):
  assert d['image_id']==k.BASE
  d['image_id']=images[rank]['image_id'];d['labels']['io.local.deepseek-correction']='kk926'
 tag='.before-kk926-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
 (F/'selected-corrected.json').write_text(json.dumps(after,indent=2)+'\n')
 (F/'promotion-backup.json').write_text(json.dumps({'tag':tag,'old_containers':[f'ds41-before-kk926-r{r}' for r in range(4)]},indent=2))
 for rank in range(4):
  info=json.loads(k.t.remote(rank,['docker','inspect',f'ds41-optimized-r{rank}']).stdout)[0]
  assert not info['State']['Running'] and info['Image']==k.BASE
  assert k.t.remote(rank,['docker','inspect',f'ds41-before-kk926-r{rank}'],check=False).returncode!=0
 renamed=[];installed=False
 try:
  k.stop_trial()
  for rank in range(4):
   k.t.remote(rank,['docker','rename',f'ds41-optimized-r{rank}',f'ds41-before-kk926-r{rank}']);renamed.append(rank)
  p.bundle(0,p.CONFIG_DIR,tag,'install',{'optimized-specs.json':json.dumps(after,indent=2)+'\n'},{'optimized-specs.json':hashlib.sha256(text.encode()).hexdigest()});installed=True
  k.run('permanent-start',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','up'])
  k.run('permanent-functional',0,['python3','-u',k.REMOTE+'/functional.py','http://127.0.0.1:8015/v1'])
  verify="import hashlib,json,sys;from pathlib import Path\nm=json.load(sys.stdin);result={}\nfor name,pins in m['files'].items():\n p=Path('/usr/local/lib/python3.12/dist-packages')/name;actual=hashlib.sha256(p.read_bytes()).hexdigest();assert actual==pins['after'],name;result[name]=actual\nprint(json.dumps(result))"
  for rank in range(4):
   info=json.loads(k.t.remote(rank,['docker','inspect',f'ds41-optimized-r{rank}']).stdout)[0]
   assert info['State']['Running'] and info['Image']==images[rank]['image_id']
   k.run(f'permanent-source-r{rank}',rank,['docker','exec','-i',f'ds41-optimized-r{rank}','python3','-c',verify],json.dumps(after['runtime_correction']['manifest']))
  k.run('permanent-status',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','status'])
 except BaseException:
  for rank in renamed:
   name=f'ds41-optimized-r{rank}';r=k.t.remote(rank,['docker','inspect',name],check=False)
   if r.returncode==0:
    info=json.loads(r.stdout)[0];assert info['Image']==images[rank]['image_id'] and info['Config']['Labels'].get('io.local.deepseek-correction')=='kk926'
    k.t.remote(rank,['docker','stop','--time','15',name]);k.t.remote(rank,['docker','rm',name])
  if installed:p.bundle(0,p.CONFIG_DIR,tag,'rollback')
  else:
   # A writer interrupted after creating its backup may have partially installed.
   exists=k.t.remote(0,['test','-f',p.CONFIG_DIR+'/'+tag+'/receipt.json'],check=False)
   if exists.returncode==0:p.bundle(0,p.CONFIG_DIR,tag,'rollback')
  for rank in renamed:k.t.remote(rank,['docker','rename',f'ds41-before-kk926-r{rank}',f'ds41-optimized-r{rank}'])
  k.run('promotion-rollback',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','up']);raise
 (F/'deployment.json').write_text(json.dumps({'selected':'kk926','healthy':True,'backup_tag':tag,'images':images,'profile':after['profile'],'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())},indent=2))
 print('PROMOTED',flush=True)
if __name__=='__main__':main()
