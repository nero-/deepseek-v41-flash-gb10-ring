#!/usr/bin/env python3
"""Qualify the corrected live trial; save raw evidence after every stage."""
import argparse,importlib.util,json
from pathlib import Path
s=importlib.util.spec_from_file_location('kk',Path(__file__).with_name('kk926-trial.py'));k=importlib.util.module_from_spec(s);s.loader.exec_module(k)
p=argparse.ArgumentParser();p.add_argument('--resume',action='store_true');a=p.parse_args()
R=k.REMOTE; F=k.F; statuses=json.loads((F/'qualification-statuses.json').read_text()) if a.resume else {}
writer="import sys;from pathlib import Path;p=Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(sys.stdin.read())"
for name in ['functional.py','long-functional.py','mixed_traffic.py','cold-needle.py','decode-prefill-consistency.py']:
 k.t.remote(0,['python3','-c',writer,R+'/'+name],(k.ROOT/'bench'/name).read_text())
def job(name,args,output=None):
 if statuses.get(name)==0:
  print('SKIP PASSED',name,flush=True);return
 try:
  k.run(name,0,['python3','-u',*args]);statuses[name]=0
 except BaseException:
  statuses[name]=1;raise
 finally:
  (F/'qualification-statuses.json').write_text(json.dumps(statuses,indent=2))
  if output:
   r=k.t.remote(0,['cat',R+'/'+output],check=False)
   if r.returncode==0:(F/output).write_text(r.stdout)
job('functional',[R+'/functional.py','http://127.0.0.1:8015/v1'])
job('corrected-consistency',[R+'/decode-prefill-consistency.py','--output',R+'/corrected-consistency.json','--tokens','2048','--limit','8'],'corrected-consistency.json')
import base64
for i in range(8):
 name=f'corrected-consistency-prompt{i}.json.gz'
 encoded=k.t.remote(0,['python3','-c','import base64,sys;print(base64.b64encode(open(sys.argv[1],"rb").read()).decode())',R+'/'+name]).stdout
 (F/name).write_bytes(base64.b64decode(encoded))
if statuses.get('corrected-screen')!=0:k.screen('corrected-screen');statuses['corrected-screen']=0
job('long-functional',[R+'/long-functional.py','--suite',R+'/functional.py','--output',R+'/long-functional.json'],'long-functional.json')
job('mixed-integrity',[R+'/mixed_traffic.py','kk926','--integrity','--prefill-records','6144','--min-uncached-tokens','65536','--rounds','1','--output',R+'/mixed-integrity.json'],'mixed-integrity.json')
job('cold-1m',[R+'/cold-needle.py','--tokens','1048576','--output',R+'/cold-1m.json'],'cold-1m.json')
if statuses.get('corrected-128k-repeat')!=0:k.screen('corrected-128k-repeat',focused=True);statuses['corrected-128k-repeat']=0
logs=k.t.remote(0,['docker','logs',k.NAMES[0]])
lines=[l for l in (logs.stdout+logs.stderr).splitlines() if '[local-indexer-tp]' in l]
guards={'enabled':sum('exact=ON' in l for l in lines),'disabled':sum('exact=OFF' in l for l in lines),'lines':lines}
startup=next((i for i,l in enumerate(lines) if 'worker startup complete' in l),None)
first=next((i for i,l in enumerate(lines) if 'first real request observed' in l),None)
guard=next((i for i,l in enumerate(lines) if 'exact=' in l),None)
guards['startup_gated']=all(i is not None for i in [startup,first,guard]) and startup<first<guard
(F/'guards-final.json').write_text(json.dumps(guards,indent=2))
assert guards['enabled']>0 and guards['disabled']==0 and guards['startup_gated'],guards
statuses['guards']=0
(F/'qualification-statuses.json').write_text(json.dumps(statuses,indent=2))
print('QUALIFICATION COMPLETE',flush=True)
