#!/usr/bin/env python3
"""Run isolated CPU tokenizer probes after the model benchmark has completed."""
import base64,hashlib,importlib.util,json,urllib.request
from pathlib import Path
s=importlib.util.spec_from_file_location('kk',Path(__file__).with_name('kk926-trial.py'));k=importlib.util.module_from_spec(s);s.loader.exec_module(k)
assert (k.F/'corrected-screen-repeat.json').exists(),'Do not overlap the GPU benchmark'
meta=json.loads((k.F/'fastokens-package.json').read_text());wheel=next(w for w in meta['aarch64_wheels'] if 'manylinux' in w['filename']);wheel_path=Path('/tmp')/wheel['filename']
if not wheel_path.exists():wheel_path.write_bytes(urllib.request.urlopen(wheel['url'],timeout=60).read())
data=wheel_path.read_bytes();assert hashlib.sha256(data).hexdigest()==wheel['sha256']
root=k.REMOTE+'/fastokens-probe'
files={'wheel':base64.b64encode(data).decode(),'probe':(k.ROOT/'bench/fastokens-probe.py').read_text(),'launcher':(k.ROOT/'bench/kk926-test-launch.py').read_text()}
stage="import sys,json,base64,zipfile,io;from pathlib import Path\np=Path(sys.argv[1]);p.mkdir(parents=True,exist_ok=True);d=json.load(sys.stdin)\nzipfile.ZipFile(io.BytesIO(base64.b64decode(d['wheel']))).extractall(p/'deps');(p/'probe.py').write_text(d['probe']);(p/'launch.py').write_text(d['launcher'])"
k.t.remote(1,['python3','-c',stage,root],json.dumps(files))
image=json.loads((k.F/'images.json').read_text())[1]['image_id'];selected=json.loads((k.F/'selected-before.json').read_text());model=next(m['source'] for m in selected['specs'][1]['mounts'] if m['target']=='/models/target')
for enabled,name in [(0,'hf'),(1,'fastokens')]:
 args=['docker','run','--rm','--runtime','runc','--network','none','--cpus','2','--memory','4g','--read-only','--tmpfs','/tmp:rw,size=512m','--env','NVIDIA_VISIBLE_DEVICES=void','--env','CUDA_VISIBLE_DEVICES=','--env','HF_HUB_OFFLINE=1','--env','HF_HOME=/tmp/hf','--env','RAYON_NUM_THREADS=2','--env','TOKENIZERS_PARALLELISM=false','--env','PYTHONDONTWRITEBYTECODE=1','--mount',f'type=bind,src={root},dst=/tests','--mount',f'type=bind,src={model},dst=/models/target,readonly','--entrypoint','python3',image,'/tests/launch.py','/tests/probe.py','--enabled',str(enabled),'--output',f'/tests/{name}.json']
 k.run('tokenizer-'+name,1,args)
 (k.F/f'tokenizer-{name}.json').write_text(k.t.remote(1,['cat',root+'/'+name+'.json']).stdout)
b=json.loads((k.F/'tokenizer-hf.json').read_text());a=json.loads((k.F/'tokenizer-fastokens.json').read_text())
assert a['parity']==b['parity'],'Token/template/stream parity mismatch'
assert a['stream']['output_sha256']==b['stream']['output_sha256']
summary={'parity_passed':True,'parity_cases':len(a['parity']),'timings':[],'stream_speedup':b['stream']['median_seconds']/a['stream']['median_seconds'],'serving_enabled':False}
for x,y in zip(b['timings'],a['timings']):
 assert x['ids_sha256']==y['ids_sha256'] and x['decoded_sha256']==y['decoded_sha256']
 summary['timings'].append({'label':x['label'],'tokens':x['tokens'],'hf_encode_s':x['encode']['median_seconds'],'fastokens_encode_s':y['encode']['median_seconds'],'encode_speedup':x['encode']['median_seconds']/y['encode']['median_seconds'],'decode_speedup':x['decode']['median_seconds']/y['decode']['median_seconds']})
(k.F/'fastokens-assessment.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
