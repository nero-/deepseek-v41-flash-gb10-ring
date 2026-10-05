#!/usr/bin/env python3
"""Apply pinned upstream files and bind them to the unchanged B12x API."""
import hashlib,json,pathlib,shutil
SOURCE=pathlib.Path('/tmp/sparkring-update');ROOT=pathlib.Path('/opt/sparkring/transports');CSF=pathlib.Path('/opt/dsv41-csf');SITE=pathlib.Path('/usr/local/lib/python3.12/dist-packages')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source_manifest=json.loads((SOURCE/'source-manifest.json').read_text())
for name,digest in source_manifest['files'].items():assert sha(SOURCE/name)==digest,name
old=ROOT/'tp2-rocenante-adaptive-prepared-csf';new=ROOT/(old.name+'-peerwait');assert not new.exists()
binding=json.loads((CSF/'transport-binding.json').read_text());assert binding['manifest_sha256']==sha(old/'manifest.json')
m=json.loads((old/'manifest.json').read_text());upstream=json.loads((SOURCE/'transport/manifest.json').read_text())
for name,digest in m['files'].items():assert sha(old/name)==digest,name
assert set(m['files'])==set(upstream['files']);shutil.copytree(old,new,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
changes={}
for name,digest in upstream['files'].items():
 assert sha(SOURCE/'transport'/name)==digest,name
 if m['files'][name]!=digest:changes[name]={'before':m['files'][name],'after':digest};shutil.copyfile(SOURCE/'transport'/name,new/name)
assert len(changes)==6
m['name']=new.name;m['parent_manifest_sha256']=sha(old/'manifest.json');m['files']=upstream['files'];m['adaptation']=upstream['adaptation'];m['source_origins']['sparkring_peer_wait']=source_manifest['sparkring'];m['qualification']={'cpu':'pending','gpu_rdma':'pending','serving':'pending','proxy_abi':5}
(new/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
selector=ROOT/'sparkring_transport_selector.py';text=selector.read_text();token='PROFILES = frozenset((PROFILE, PREPARED_PROFILE, CSF_PROFILE))';assert text.count(token)==1
text=text.replace(token,f'CSF_PEERWAIT_PROFILE = "{new.name}"\nPROFILES = frozenset((PROFILE, PREPARED_PROFILE, CSF_PROFILE, CSF_PEERWAIT_PROFILE))').replace('if name in (PREPARED_PROFILE, CSF_PROFILE):','if name in (PREPARED_PROFILE, CSF_PROFILE, CSF_PEERWAIT_PROFILE):');selector.write_text(text)
policy=json.loads((SOURCE/'tool-policy.json').read_text());serving=SITE/'vllm/entrypoints/openai/chat_completion/serving.py';assert sha(serving)==policy['INHERITED'];text=serving.read_text();assert text.count(policy['END'])==1;serving.write_text(text.replace(policy['END'],policy['INSTALL']));assert sha(serving)==policy['RESULT'];shutil.copyfile(SOURCE/'contract.py',serving.with_name('sparkring_tool_choice_contract.py'))
python_root=pathlib.Path('/opt/sparkring/python');assert (python_root/'sparkring_runtime_status/__init__.py').is_file()
shutil.rmtree(python_root/'sparkring_runtime_status')
for d in python_root.glob('sparkring_runtime_status-*.dist-info'):assert d.name.endswith('.dist-info');shutil.rmtree(d)
for name in ['sparkring_runtime_status','sparkring_runtime_status-0.3.3.dist-info']:shutil.copytree(pathlib.Path('/tmp/status-install')/name,python_root/name)
profile={'profile':new.name,'manifest_sha256':sha(new/'manifest.json'),'parent_manifest_sha256':sha(old/'manifest.json'),'wire_files_unchanged':False,'proxy_abi':5}
(CSF/'transport-binding.json').write_text(json.dumps(profile,indent=2)+'\n')
manifest=json.loads((CSF/'manifest.json').read_text());manifest['sparkring_update']={'revision':source_manifest['sparkring'],'tool_choice':policy['RESULT'],'contract':policy['MODULE_SHA256'],'runtime_status':'0.3.3','transport':profile,'transport_changes':changes}
(CSF/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');shutil.copyfile(SOURCE/'source-manifest.json',CSF/'sparkring-update-source.json')
# The package root is already inventoried; additionally record its version.
runtime=CSF/'runtime.py';text=runtime.read_text();token="['vllm','b12x','torch','nvidia-cutlass-dsl']";assert text.count(token)==1;runtime.write_text(text.replace(token,"['vllm','b12x','torch','nvidia-cutlass-dsl','sparkring-runtime-status']"))
(CSF/'installed.json').rename(CSF/'installed-parent-csf.json')
print(json.dumps(profile))
