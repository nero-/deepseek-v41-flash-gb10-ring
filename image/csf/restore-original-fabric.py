#!/usr/bin/env python3
"""Fill remaining original shards over fabric from a hash-verified Spark copy."""
import argparse,concurrent.futures,hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--manifest',required=True);p.add_argument('--proof',required=True);a=p.parse_args()
OLD=Path('/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277')
assert not subprocess.check_output(['docker','ps','-q']).strip(),'Rank must be idle'
assert OLD.resolve()==OLD
api=json.loads(Path(a.manifest).read_text());assert api['sha']==OLD.name
remote=json.load(urllib.request.urlopen(a.source+'/manifest.json',timeout=20));assert remote==api
proof=Path(a.proof);prior=json.loads(proof.read_text());assert prior['revision']==OLD.name
records={x['file']:x for x in prior['shards']}
rows=[x for x in api['siblings'] if x['rfilename'].endswith('.safetensors')];assert len(rows)==48
for x in rows:
 name=x['rfilename'];assert Path(name).name==name
 partial=OLD/(name+'.restore-partial')
 if partial.exists():
  assert partial.is_file() and not partial.is_symlink() and partial.stat().st_nlink==1;partial.unlink()
 if name in records:
  f=OLD/name;assert f.is_file() and not f.is_symlink() and f.stat().st_size==x['size'] and f.stat().st_nlink==1
  assert records[name]['sha256']==x['lfs']['sha256']
def fetch(x):
 name=x['rfilename'];f=OLD/name;assert not f.is_symlink();start=time.monotonic()
 if not f.exists():
  tmp=OLD/(name+'.fabric-partial');assert not tmp.exists() and not tmp.is_symlink()
  subprocess.run(['curl','-fLsS','--connect-timeout','10','--max-time','1800','--output',str(tmp),a.source+'/'+name],check=True)
  assert tmp.stat().st_size==x['size'] and tmp.stat().st_nlink==1
  with tmp.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==x['lfs']['sha256'],name
  with tmp.open('rb') as stream:os.fsync(stream.fileno())
  tmp.replace(f)
  fd=os.open(OLD,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 else:
  assert f.is_file() and f.stat().st_size==x['size'] and f.stat().st_nlink==1
  with f.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==x['lfs']['sha256'],name
 return {'file':name,'bytes':x['size'],'sha256':x['lfs']['sha256'],'restored':False,'fabric_transferred':True,'seconds':time.monotonic()-start}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 futures=[pool.submit(fetch,x) for x in rows if x['rfilename'] not in records]
 for future in concurrent.futures.as_completed(futures):
  row=future.result();records[row['file']]=row
  proof.write_text(json.dumps({'revision':OLD.name,'complete':False,'shards':list(records.values()),'method':'reconstruction-then-fabric'},indent=2)+'\n');print(json.dumps(row),flush=True)
assert len(records)==48 and len(list(OLD.glob('*.safetensors')))==48
proof.write_text(json.dumps({'revision':OLD.name,'complete':True,'shards':list(records.values()),'method':'reconstruction-then-fabric'},indent=2)+'\n')
print('ORIGINAL CHECKPOINT RECOVERED',flush=True)
