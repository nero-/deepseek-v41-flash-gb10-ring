import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/Users/jg/Agent/Builds/deepseek-v41-flash-ring/scripts')
from fleet import remote
image=json.loads((ROOT/'candidate-image.json').read_text())['Id']
code=r'''import hashlib,json,pathlib,struct,subprocess
root=pathlib.Path('/cache/deepseek-v41-flash-1017-runtime1015-tests/b12x_compile_cache_dir')
out=pathlib.Path('/receipts/native-sass-extracted');out.mkdir(exist_ok=True)
records=[]
for p in sorted(root.rglob('*.o')):
 b=p.read_bytes();records_one=[];offset=0
 while True:
  offset=b.find(b'\x7fELF',offset)
  if offset<0:break
  start=offset;offset+=4
  if b[start+4:start+6]!=b'\x02\x01' or struct.unpack_from('<H',b,start+18)[0]!=190:continue
  shoff=struct.unpack_from('<Q',b,start+40)[0];shentsize,shnum=struct.unpack_from('<HH',b,start+58)
  if not (0<shnum<10000 and shentsize==64 and start+shoff+shnum*64<=len(b)):continue
  phoff=struct.unpack_from('<Q',b,start+32)[0];phentsize,phnum=struct.unpack_from('<HH',b,start+54)
  size=max(shoff+shnum*64,phoff+phentsize*phnum)
  for i in range(phnum):
   ph=struct.unpack_from('<IIQQQQQQ',b,start+phoff+i*phentsize)
   size=max(size,ph[2]+ph[5])
  for i in range(shnum):
   sh=struct.unpack_from('<IIQQQQIIQQ',b,start+shoff+i*64)
   if sh[1]!=8:size=max(size,sh[4]+sh[5])
  assert start+size<=len(b)
  cubin=b[start:start+size];dest=out/(p.stem+f'-{len(records_one)}.cubin');dest.write_bytes(cubin)
  r=subprocess.run(['/usr/local/cuda-13.4/bin/cuobjdump','--dump-sass',str(dest)],capture_output=True,text=True)
  sass=r.stdout;(dest.with_suffix('.sass')).write_text(sass)
  records_one.append({'offset':start,'bytes':size,'cubin_sha256':hashlib.sha256(cubin).hexdigest(),'exit':r.returncode,'stderr':r.stderr[-1000:],'sass_sha256':hashlib.sha256(sass.encode()).hexdigest(),'functions':[l.strip() for l in sass.splitlines() if 'Function :' in l],'fence_instructions':[l.strip() for l in sass.splitlines() if 'FENCE' in l or 'MEMBAR' in l]})
 records.append({'object':str(p),'sha256':hashlib.sha256(b).hexdigest(),'cache_metadata':json.loads(p.with_suffix('.json').read_text()) if p.with_suffix('.json').exists() else None,'embedded_cubins':records_one})
print(json.dumps(records))
'''
r=remote(2,['docker','run','--rm','--network','none','--cpus','1','--memory','2g','-v','/srv/sparkring/sparkring/cache:/cache:ro','-v','/home/nero/builds/ds41-runtime-20261017/receipts:/receipts','--entrypoint','python3',image,'-c',code])
records=json.loads(r.stdout);(ROOT/'native-sass-extracted-r2.json').write_text(json.dumps(records,indent=2)+'\n')
for row in records:
 for c in row['embedded_cubins']:print(row['object'].split('/')[-1],c['exit'],c['functions'][:1],c['fence_instructions'][:3])
print('objects',len(records),'cubins',sum(len(r['embedded_cubins']) for r in records))
