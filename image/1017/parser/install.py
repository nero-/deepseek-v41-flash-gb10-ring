"""Install the exact upstream Python DSML fix and refresh image receipts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import py_compile
import shutil

ctx = Path('/opt/ds41-1017-parser')
site = Path('/usr/local/lib/python3.12/dist-packages')
manifest = json.loads((ctx / 'manifest.json').read_text())
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
receipt = Path('/opt/sparkring/receipts/external-base-installed.json')
toolchain = Path('/opt/sparkring/toolchain/installed.json')
record = json.loads(receipt.read_text())
tc = json.loads(toolchain.read_text())
assert tc['parent_receipt_sha256'] == sha(receipt)
backup = ctx / 'parent'
backup.mkdir()
for source in (receipt, toolchain):
    shutil.copy2(source, backup / source.name)
for relative, hashes in manifest['files'].items():
    target = site / relative
    candidate = ctx / relative
    assert sha(target) == hashes['before'] and sha(candidate) == hashes['after']
    assert record['files'][str(target)] == hashes['before']
    dest = backup / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, dest)
    shutil.copyfile(candidate, target)
    target.chmod(0o644)
    py_compile.compile(str(target), doraise=True)
    record['files'][str(target)] = sha(target)
spec = importlib.util.spec_from_file_location('external', '/opt/sparkring/bin/external-base.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
record_path, digest = mod.record_distribution('vllm', site / 'vllm')
assert record_path in record['distribution_records']
record['distribution_records'][record_path] = digest
record.setdefault('local_corrections', []).append({
    'name': 'deepseek-dsml-optional-string', 'upstream': manifest['source'],
    'receipt': '/opt/sparkring/receipts/derived-ds41-parser921.json'})
receipt.write_text(json.dumps(record, indent=2) + '\n')
tc['parent_receipt_sha256'] = sha(receipt)
toolchain.write_text(json.dumps(tc, indent=2) + '\n')
Path('/opt/sparkring/receipts/derived-ds41-parser921.json').write_text(json.dumps({
    **manifest, 'external_receipt_sha256': sha(receipt),
    'toolchain_receipt_sha256': sha(toolchain),
    'native_libraries_changed': False, 'serving_qualified': False}, indent=2) + '\n')
print(json.dumps(mod.verify()))
