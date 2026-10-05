#!/usr/bin/env python3
"""Replicate published CSF files, verifying before any old-shard deletion."""
import argparse,hashlib,json,os,shutil,subprocess,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--delete-old',action='store_true');a=p.parse_args()
REV='c5c41fe301c4c1d24fc09376883d9168e521dc66';DEST=Path('/srv/sparkring/sparkring/checkpoints/local-inference-lab--DeepSeek-V4.1-Flash-lossless-CSF')/REV
OLD=Path('/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277');SOURCE=a.source.rstrip('/')+'/'
if a.delete_old:assert not subprocess.check_output(['docker','ps','-q']).strip(),'Old-shard replacement requires idle node'
DEST.mkdir(parents=True,exist_ok=True)
def get(name):return json.load(urllib.request.urlopen(SOURCE+name,timeout=30))
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
api=get('hub-file-manifest.json');assert api['sha']==REV
(DEST/'hub-file-manifest.json').write_text(json.dumps(api,indent=2));manifest=get('manifest.json');orig={x['file']:x for x in manifest['shards']}
receipts=[]
for x in api['siblings']:
 name=x['rfilename'];target=DEST/name;expected=x.get('lfs',{}).get('sha256');size=x.get('size');target.parent.mkdir(parents=True,exist_ok=True)
 if not (target.exists() and target.stat().st_size==size and (not expected or sha(target)==expected)):
  tmp=target.with_suffix(target.suffix+'.partial');deadline=time.monotonic()+10800
  while time.monotonic()<deadline:
   log=tmp.with_suffix(tmp.suffix+'.transfer.log')
   with log.open('a') as out:
    r=subprocess.run(['curl','-fLsS','--connect-timeout','10','--max-time','1200','-C','-','--output',str(tmp),SOURCE+name],stdout=out,stderr=out)
   if r.returncode==0:break
   time.sleep(10)
  else:raise TimeoutError(name)
  assert tmp.stat().st_size==size,(name,tmp.stat().st_size,size)
  if expected:assert sha(tmp)==expected,name
  tmp.replace(target)
 if a.delete_old and name.startswith('tensors/'):
  old=OLD/target.name
  if old.exists():
   assert not old.is_symlink() and old.stat().st_size==orig[target.name]['source_file_bytes'],str(old)
   assert target.stat().st_size==size and sha(target)==expected,name
   old.unlink()
 receipts.append({'file':name,'size':size,'sha256':expected,'old_deleted':a.delete_old and name.startswith('tensors/')})
 print(json.dumps(receipts[-1]),flush=True)
serving=DEST/'serving';serving.mkdir(exist_ok=True)
for src in (DEST/'metadata').iterdir():
 dst=serving/src.name
 if dst.exists():dst.unlink()
 os.link(src,dst)
config=json.loads((serving/'config.json').read_text());config['quantization_config'].update(quant_method='mxfp4_csf',format_version=1,checkpoint_root='/models/csf')
(serving/'config.json').unlink();(serving/'config.json').write_text(json.dumps(config,indent=2)+'\n')
(DEST/'verified-shards.json').write_text(json.dumps({'revision':REV,'receipts':receipts},indent=2))
print('CHECKPOINT VERIFIED',flush=True)
