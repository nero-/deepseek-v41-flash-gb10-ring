#!/usr/bin/env python3
"""Assemble the pinned SparkRing reliability layer over a sealed CSF image."""
import argparse,ast,hashlib,json,pathlib,shutil,subprocess
HERE=pathlib.Path(__file__).resolve().parent
PIN='721db585e2050bef93518c6cced1dae57ff43af4'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('destination',type=pathlib.Path);p.add_argument('--source',type=pathlib.Path);a=p.parse_args();dst=a.destination.resolve();assert not dst.exists();dst.mkdir(parents=True)
source=a.source
if source is None:
 source=dst/'checkout';subprocess.run(['git','clone','--filter=blob:none','https://github.com/FujitsuPolycom/sparkring.git',str(source)],check=True);subprocess.run(['git','-C',str(source),'checkout',PIN],check=True)
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==PIN
assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
transport=source/'integrations/vllm/rocenante_prepared';manifest=json.loads((transport/'manifest.json').read_text())
for name,digest in manifest['files'].items():assert sha(transport/name)==digest;target=dst/'transport'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(transport/name,target)
shutil.copyfile(transport/'manifest.json',dst/'transport/manifest.json')
shutil.copytree(source/'integrations/vllm/runtime_status',dst/'status',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(source/'integrations/vllm/tool_choice_contract/contract.py',dst/'contract.py')
values={}
for node in ast.parse((source/'runtime/images/derive_tool_choice_contract.py').read_text()).body:
 if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name):
  name=node.targets[0].id
  if isinstance(node.value,ast.Constant):values[name]=node.value.value
  elif name=='INSTALL':values[name]=values['END']+node.value.right.value
assert sha(dst/'contract.py')==values['MODULE_SHA256']
(dst/'tool-policy.json').write_text(json.dumps({k:values[k] for k in ['INHERITED','RESULT','MODULE_SHA256','END','INSTALL']},indent=2))
for name in ['Dockerfile','apply.py']:shutil.copyfile(HERE/name,dst/name)
if a.source is None:shutil.rmtree(source)
files={str(x.relative_to(dst)):sha(x) for x in dst.rglob('*') if x.is_file()}
(dst/'source-manifest.json').write_text(json.dumps({'sparkring':PIN,'files':files},indent=2)+'\n')
print(dst)
