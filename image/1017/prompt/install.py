"""Apply one upstream prompt-boundary fix with checked source receipts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import py_compile
import shutil

ctx = Path('/opt/ds41-1017-prompt')
site = Path('/usr/local/lib/python3.12/dist-packages')
target = site / 'vllm/tokenizers/deepseek_v41_encoding.py'
manifest = json.loads((ctx / 'manifest.json').read_text())
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(target) == manifest['before_sha256']
assert sha(ctx / 'candidate-encoding.py') == manifest['after_sha256']
receipt = Path('/opt/sparkring/receipts/external-base-installed.json')
toolchain = Path('/opt/sparkring/toolchain/installed.json')
record = json.loads(receipt.read_text())
tc = json.loads(toolchain.read_text())
assert tc['parent_receipt_sha256'] == sha(receipt)
assert record['files'][str(target)] == manifest['before_sha256']
backup = ctx / 'parent'
backup.mkdir()
for source in (target, receipt, toolchain):
    shutil.copy2(source, backup / source.name)
shutil.copyfile(ctx / 'candidate-encoding.py', target)
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
    'name': 'deepseek-1017-tool-turn-boundary', 'upstream': manifest['source'],
    'receipt': '/opt/sparkring/receipts/derived-ds41-1017-prompt.json'})
receipt.write_text(json.dumps(record, indent=2) + '\n')
tc['parent_receipt_sha256'] = sha(receipt)
toolchain.write_text(json.dumps(tc, indent=2) + '\n')
Path('/opt/sparkring/receipts/derived-ds41-1017-prompt.json').write_text(json.dumps({
    **manifest, 'external_receipt_sha256': sha(receipt), 'toolchain_receipt_sha256': sha(toolchain),
    'native_libraries_changed': False, 'serving_qualified': False}, indent=2) + '\n')
print(json.dumps(mod.verify()))
