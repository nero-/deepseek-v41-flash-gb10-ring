#!/usr/bin/env python3
"""Record and verify the decision to retain corrected HF after the serving trial."""
import importlib.util,json,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('f',root/'scripts/fastokens-serving.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
decision={'decision':'retain-corrected-hf','performance_reviewed':True,'reason':'Fastokens improves cached long-prompt TTFT, but both C8 runs are below both HF runs. Preserve decode/concurrency priority.','caveats':['Small sequential campaign, not randomized statistical proof','Different generated continuations and speculative acceptance','No full 40-cell benchmark was repeated'],'candidate':'fastokens-0.3.2','flag_enabled':False}
(f.F/'decision.json').write_text(json.dumps(decision,indent=2)+'\n')
assert json.loads(f.k.t.remote(0,['cat',f.p.CONFIG_DIR+'/optimized-specs.json']).stdout)==f.read('selected-before.json')
ranks=[]
for rank,spec in enumerate(f.read('selected-before.json')['specs']):
 name=f'ds41-optimized-r{rank}';info=json.loads(f.k.t.remote(rank,['docker','inspect',name]).stdout)[0]
 assert info['State']['Running'] and info['Image']==spec['image_id']
 env=dict(x.split('=',1) for x in info['Config']['Env']);assert env.get('VLLM_USE_FASTOKENS','0')=='0'
 code="import hashlib,json,os;from pathlib import Path\nassert os.environ.get('VLLM_USE_FASTOKENS','0')=='0'\nm=json.loads(Path('/opt/kk926/manifest.json').read_text())\nfor name,pin in m['files'].items():assert hashlib.sha256((Path('/usr/local/lib/python3.12/dist-packages')/name).read_bytes()).hexdigest()==pin['after']\nprint(json.dumps({'compressor_hashes_verified':True,'fastokens_enabled':False}))"
 f.k.run(f'final-hf-verify-r{rank}',rank,['docker','exec',name,'python3','-c',code]);ranks.append({'rank':rank,'image':info['Image'],'compressor_hashes_verified':True,'fastokens_enabled':False})
f.job('final-hf-functional',[f.R+'/functional.py','http://127.0.0.1:8015/v1'])
f.k.run('final-hf-status',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','status'])
(f.F/'deployment.json').write_text(json.dumps({'selected':'kk926-corrected-hf','ranks':ranks,'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'candidate_retained_as_images':True,'rollback_completed':f.read('restored.json')},indent=2)+'\n')
