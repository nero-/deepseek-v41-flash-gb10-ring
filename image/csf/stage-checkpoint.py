#!/usr/bin/env python3
"""Download immutable HF CSF files; reuse unchanged local tensor payloads.

Every published shard must match the official LFS SHA-256. Reuse is only allowed
when both headers describe exactly the same tensor names/types/shapes/offsets.
"""
import concurrent.futures as cf,hashlib,json,os,struct,subprocess,time,urllib.request
from pathlib import Path
ID='local-inference-lab/DeepSeek-V4.1-Flash-lossless-CSF';REV='c5c41fe301c4c1d24fc09376883d9168e521dc66'
OLD=Path('/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277')
DEST=Path('/srv/sparkring/sparkring/checkpoints/local-inference-lab--DeepSeek-V4.1-Flash-lossless-CSF')/REV
BASE='https://huggingface.co/'+ID+'/resolve/'+REV+'/'
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(16<<20),b''):h.update(b)
 return h.hexdigest()
def download(name,p,size=None):
 p.parent.mkdir(parents=True,exist_ok=True)
 with open(str(p)+'.curl.log','a') as log:
  subprocess.run(['curl','--http1.1','-fL','--retry','8','--retry-all-errors','--retry-delay','5','--connect-timeout','30','--speed-time','120','--speed-limit','1024','-C','-','--output',str(p),BASE+name],check=True,stdout=subprocess.DEVNULL,stderr=log)
 if size is not None:assert p.stat().st_size==size,(name,p.stat().st_size,size)
def reuse_payload(name,p,size,expected):
 old=OLD/Path(name).name
 if not old.exists():return False
 header=p.with_suffix('.header')
 r=subprocess.run(['curl','-fLsS','--retry','3','--range','0-1048575','--max-filesize','2097152','-o',str(header),BASE+name],capture_output=True)
 if r.returncode:return False
 data=header.read_bytes();n=struct.unpack('<Q',data[:8])[0]
 if n>len(data)-8:return False
 target=json.loads(data[8:8+n]);target.pop('__metadata__',None)
 with old.open('rb') as src:
  sn=struct.unpack('<Q',src.read(8))[0];source=json.loads(src.read(sn));source.pop('__metadata__',None)
  if source!=target or old.stat().st_size-(sn+8)!=size-(n+8):return False
  h=hashlib.sha256()
  with p.open('wb') as out:
   out.write(data[:n+8]);h.update(data[:n+8])
   for block in iter(lambda:src.read(16<<20),b''):out.write(block);h.update(block)
   out.flush();os.fsync(out.fileno())
 assert p.stat().st_size==size and h.hexdigest()==expected,(name,h.hexdigest())
 header.unlink();return True
def main():
 DEST.mkdir(parents=True,exist_ok=True)
 api=json.load(urllib.request.urlopen('https://huggingface.co/api/models/'+ID+'/revision/'+REV+'?blobs=true'))
 (DEST/'hub-file-manifest.json').write_text(json.dumps(api,indent=2))
 def one(x):
  name=x['rfilename'];p=DEST/name;size=x.get('size');expected=x.get('lfs',{}).get('sha256')
  if p.exists() and p.stat().st_size==size and (not expected or digest(p)==expected):return
  tmp=p.with_suffix(p.suffix+'.partial');tmp.parent.mkdir(parents=True,exist_ok=True)
  reused=False
  # These shards have unchanged tensors but a new safetensors metadata header.
  if name.startswith('tensors/') and int(Path(name).name.split('-')[1]) in [1,2,43,44,45,46,47,48]:
   reused=reuse_payload(name,tmp,size,expected)
  if not reused:
   download(name,tmp,size)
   if expected:assert digest(tmp)==expected,name
  tmp.replace(p);print(json.dumps({'file':name,'bytes':size,'sha256':expected,'reused_payload':reused,'utc':time.time()}),flush=True)
 small=[x for x in api['siblings'] if not x['rfilename'].startswith('tensors/')]
 large=[x for x in api['siblings'] if x['rfilename'].startswith('tensors/')]
 with cf.ThreadPoolExecutor(4) as pool:list(pool.map(one,small));list(pool.map(one,large))
 serving=DEST/'serving';serving.mkdir(exist_ok=True)
 for p in (DEST/'metadata').iterdir():
  target=serving/p.name
  if target.exists():target.unlink()
  os.link(p,target)
 config=json.loads((serving/'config.json').read_text());config['quantization_config'].update(quant_method='mxfp4_csf',format_version=1,checkpoint_root='/models/csf')
 (serving/'config.json').unlink();(serving/'config.json').write_text(json.dumps(config,indent=2)+'\n')
 (DEST/'verified-shards.json').write_text(json.dumps({'revision':REV,'files':[{k:x.get(k) for k in ['rfilename','size','lfs']} for x in large]},indent=2))
 print('CHECKPOINT VERIFIED',flush=True)
if __name__=='__main__':main()
