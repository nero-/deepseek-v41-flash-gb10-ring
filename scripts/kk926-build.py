#!/usr/bin/env python3
"""Build the minimal correction on each node without changing its service."""
import hashlib,importlib.util,json,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('trial',Path(__file__).with_name('research-trial.py'));t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
root=Path(__file__).resolve().parents[1];folder=root/'results/20260929-kk926';folder.mkdir(exist_ok=True)
ctx=root/'image/kk926';manifest=json.loads((ctx/'manifest.json').read_text());base=manifest['base_image'];remote='/home/nero/kk926-20260929/build'
files={p.relative_to(ctx).as_posix():p.read_text() for p in ctx.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
writer="import json,sys;from pathlib import Path\nr=Path(sys.argv[1])\nfor n,s in json.load(sys.stdin).items():\n p=r/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)"
selected=t.remote(0,['cat','/etc/deepseek-ring/optimized-specs.json']).stdout
(folder/'selected-before.json').write_text(selected)
def one(rank):
 info=json.loads(t.remote(rank,['docker','inspect',f'ds41-optimized-r{rank}']).stdout)[0]
 assert info['Image']==base and info['State']['Running']
 (folder/f'before-rank{rank}.json').write_text(json.dumps({'name':info['Name'],'image':info['Image'],'started_at':info['State']['StartedAt']},indent=2))
 t.remote(rank,['python3','-c',writer,remote],json.dumps(files))
 t.remote(rank,['docker','tag',base,'dsv41-pinned-base:kk926'])
 result=t.remote(rank,['docker','build','--network','none','--pull=false','-t','dsv41-sparkring:kk926-20260929',remote],check=False)
 (folder/f'build-rank{rank}.txt').write_text(result.stdout+result.stderr)
 assert result.returncode==0,rank
 image=t.remote(rank,['docker','image','inspect','--format','{{.Id}}','dsv41-sparkring:kk926-20260929']).stdout.strip()
 result=t.remote(rank,['docker','run','--rm','--network','none','--entrypoint','python3',image,'/opt/sparkring/toolchain/toolchain.py','verify'],check=False)
 (folder/f'verify-image-rank{rank}.txt').write_text(result.stdout+result.stderr)
 assert result.returncode==0,('verify',rank)
 print('BUILT',rank,image,flush=True)
 return {'rank':rank,'image_id':image,'source_manifest_sha256':hashlib.sha256((ctx/'manifest.json').read_bytes()).hexdigest(),'toolchain_verified':True}
results=t.parallel(one);(folder/'images.json').write_text(json.dumps(results,indent=2)+'\n');print('ALL IMAGES BUILT',flush=True)
