#!/usr/bin/env python3
"""Bind the unchanged SparkRing wire transport to this B12X preparation API."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path('/opt/sparkring/transports');OLD='tp2-rocenante-adaptive-prepared';NEW=OLD+'-csf';EXPECTED='2eef276d54030a71c4774b92c89008dd563104b791734f6f588a3ca34a7c4943'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
parent=ROOT/OLD;manifest=parent/'manifest.json';assert sha(manifest)==EXPECTED
m=json.loads(manifest.read_text())
for relative,expected in m['files'].items():assert sha(parent/relative)==expected,relative
new=ROOT/NEW;shutil.copytree(parent,new,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
m['name']=NEW;m['parent_manifest_sha256']=EXPECTED;m['image_source_preimages']={name:sha(Path(name)) for name in m['image_source_preimages']}
m['source_origins']['csf_preparation_binding']={'b12x':'4bc601a42d9938fc1b33392b5e69b2f2485b4872','vllm':'00a33e23142097f99fef95b1ecab6da4ea271e2e'}
m['qualification']={'cpu':'pending on this derived image','gpu_rdma':'pending on this derived image','serving':'pending on this derived image','transport_payload':'byte-identical to parent manifest '+EXPECTED}
(new/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
p=ROOT/'sparkring_transport_selector.py';source=p.read_text();assert 'PROFILES = frozenset((PROFILE, PREPARED_PROFILE))' in source
source=source.replace('PROFILES = frozenset((PROFILE, PREPARED_PROFILE))',f'CSF_PROFILE = "{NEW}"\nPROFILES = frozenset((PROFILE, PREPARED_PROFILE, CSF_PROFILE))').replace('if name == PREPARED_PROFILE:', 'if name in (PREPARED_PROFILE, CSF_PROFILE):')
p.write_text(source)
# The same correction is now in the source owner, so retire its old guarded hook.
(Path('/usr/local/lib/python3.12/dist-packages')/'sparkring_b12x_selection_cache.pth').unlink()
Path('/opt/dsv41-csf/transport-binding.json').write_text(json.dumps({'profile':NEW,'manifest_sha256':sha(new/'manifest.json'),'parent_manifest_sha256':EXPECTED,'wire_files_unchanged':True},indent=2)+'\n')
