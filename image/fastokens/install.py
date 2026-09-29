"""Install only the pinned ARM64 tokenizer wheel; preserve the verified stack."""
import hashlib,importlib.metadata,json,subprocess,sys
from pathlib import Path
root=Path('/opt/fastokens');m=json.loads((root/'manifest.json').read_text());wheel=root/m['filename']
assert hashlib.sha256(wheel.read_bytes()).hexdigest()==m['sha256']
try:importlib.metadata.version('fastokens')
except importlib.metadata.PackageNotFoundError:pass
else:raise RuntimeError('Parent unexpectedly contains fastokens')
subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps','--no-cache-dir',str(wheel)],check=True)
assert importlib.metadata.version('fastokens')=='0.3.2'
dist=importlib.metadata.distribution('fastokens')
files={str(f):hashlib.sha256(dist.locate_file(f).read_bytes()).hexdigest() for f in dist.files if dist.locate_file(f).is_file()}
(root/'installed.json').write_text(json.dumps({'wheel':m,'installed_files':files,'vllm_code_changed':False},indent=2))
