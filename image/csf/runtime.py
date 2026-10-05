#!/usr/bin/env python3
"""Verify this derived software image and retain the pinned SparkRing toolchain."""
import hashlib,importlib.util,json,os,subprocess,sys
from pathlib import Path
ROOT=Path('/opt/dsv41-csf');SITE=Path('/usr/local/lib/python3.12/dist-packages')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def toolchain():
 spec=importlib.util.spec_from_file_location('srtool','/opt/sparkring/toolchain/toolchain.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def inventory():
 files={}
 for directory in [SITE/'vllm',SITE/'b12x',Path('/opt/sparkring/transports'),Path('/opt/sparkring/python'),ROOT]:
  for p in sorted(directory.rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='installed.json':files[str(p)]=sha(p)
 for name,expected in json.loads((ROOT/'manifest.json').read_text())['native_vllm_abi']['parent_native_files'].items():
  assert sha(Path(name))==expected,'Inherited vLLM native ABI changed: '+name
 native=json.loads(Path('/opt/sparkring/toolchain/installed.json').read_text())
 for name,expected in native['files'].items():
  observed=sha(Path(name));assert observed==expected,'Inherited toolchain changed: '+name;files[name]=observed
 import importlib.metadata as metadata
 return {'schema':'dsv41-csf-derived-image/v1','files':files,'versions':{p:metadata.version(p) for p in ['vllm','b12x','torch','nvidia-cutlass-dsl']},'sources':json.loads((ROOT/'manifest.json').read_text())}
def main():
 action=sys.argv[1] if len(sys.argv)>1 else 'verify';assert action in ['seal','verify','serve']
 m=toolchain();lock=json.loads(Path('/opt/sparkring/toolchain/toolchain.json').read_text());env=m.configure_environment(lock,os.environ)
 if any(os.environ.get(k)!=v for k,v in env.items()):os.execve(sys.executable,[sys.executable,__file__,*sys.argv[1:]],env)
 state=inventory();installed=ROOT/'installed.json'
 if action=='seal':assert not installed.exists();installed.write_text(json.dumps(state,indent=2)+'\n')
 else:assert json.loads(installed.read_text())==state,'Derived software image differs from its receipt'
 print(json.dumps({k:v for k,v in state.items() if k!='files'}),flush=True)
 if action=='serve':os.execve('/usr/local/bin/vllm',['vllm','serve',*sys.argv[2:]],env)
if __name__=='__main__':main()
