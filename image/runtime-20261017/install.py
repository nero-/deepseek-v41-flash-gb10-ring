"""Seal the exact new framework and the retained SparkRing integration.

The new immutable image remains a candidate until fleet qualification passes.
No old framework receipt is reused or rewritten to imply identical binaries.
"""
import base64
import csv
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import sys

ROOT = Path('/opt/sparkring')
CONTEXT = ROOT / 'runtime-20261017'
SITE = Path('/usr/local/lib/python3.12/dist-packages')
composition = json.loads((CONTEXT / 'composition.json').read_text())
assert platform.machine() == 'aarch64'
assert not (ROOT / 'receipts/external-base-installed.json').exists()

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

for name, expected in composition['versions'].items():
    assert metadata.version(name) == expected, (name, metadata.version(name), expected)
try:
    metadata.distribution('b12x')
except metadata.PackageNotFoundError:
    pass
else:
    raise RuntimeError('Standalone B12x distribution conflicts with FlashInfer provider')

target = SITE / 'vllm/tokenizers/deepseek_v41_encoding.py'
assert sha(target) == composition['prompt_before_sha256']
assert sha(CONTEXT / 'candidate-encoding.py') == composition['prompt_after_sha256']
for name, expected in composition['parser_sha256'].items():
    assert sha(SITE / 'vllm/parser' / name) == expected
shutil.copyfile(CONTEXT / 'candidate-encoding.py', target)
for bytecode in target.parent.glob('__pycache__/deepseek_v41_encoding.*.pyc'):
    bytecode.unlink()

(SITE / 'sparkring_transport.pth').write_text((ROOT / 'transports/sparkring_transport.pth').read_text())
(SITE / 'sparkring_runtime_status.pth').write_text('/opt/sparkring/python\n')

spec = importlib.util.spec_from_file_location('external', ROOT / 'bin/external-base.py')
external = importlib.util.module_from_spec(spec)
spec.loader.exec_module(external)
record_path, digest = external.record_distribution('vllm', SITE / 'vllm')
distribution_records = {record_path: digest}

# Keep the patched pure-Python status package's RECORD internally consistent.
status_record = ROOT / 'python/sparkring_runtime_status-0.3.2.dist-info/RECORD'
with status_record.open('w', newline='') as f:
    writer = csv.writer(f, lineterminator='\n')
    for p in sorted((ROOT / 'python').rglob('*')):
        if not p.is_file() or p == status_record:
            continue
        digest = base64.urlsafe_b64encode(bytes.fromhex(sha(p))).rstrip(b'=').decode()
        writer.writerow([str(p.relative_to(ROOT / 'python')), 'sha256=' + digest, p.stat().st_size])
    writer.writerow([str(status_record.relative_to(ROOT / 'python')), '', ''])

files = {}
for name in external.PACKAGE_NAMES:
    files.update(external.inventory_package(SITE / name))
for root in [ROOT / 'transports', ROOT / 'python', ROOT / 'bin', CONTEXT]:
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.suffix != '.pyc':
            files[str(p)] = sha(p)
for name in ['sparkring_transport.pth', 'sparkring_runtime_status.pth']:
    files[str(SITE / name)] = sha(SITE / name)

# Include the provider's native libraries and RECORD in addition to B12x sources.
for name in ['flashinfer-python', 'torch']:
    d = metadata.distribution(name)
    for item in d.files or ():
        p = Path(d.locate_file(item))
        if p.is_file() and ('.so' in p.name or str(item).endswith('.dist-info/RECORD')):
            if p.is_symlink():
                continue
            files[str(p)] = sha(p)
            if str(item).endswith('.dist-info/RECORD'):
                distribution_records[str(p)] = files[str(p)]

python_roots = {str(ROOT / 'python'): {
    str(Path(name).relative_to(ROOT / 'python')): digest
    for name, digest in files.items() if Path(name).is_relative_to(ROOT / 'python')
}}
receipt = {
    'schema': 'sparkring-external-installed/v1',
    'base': composition['base'], 'composition_sha256': sha(CONTEXT / 'composition.json'),
    'sources': composition['sources'], 'versions': composition['versions'],
    'files': files, 'distribution_records': distribution_records,
    'native_files': {name:digest for name,digest in files.items() if '.so' in Path(name).name},
    'removed_files': [], 'symlinks': {}, 'python_roots': python_roots,
    'capabilities': {
        'runtime_status': {'version': '0.3.2', 'python_root': '/opt/sparkring/python'},
        'transport_profile': 'tp2-rocenante-adaptive-prepared',
        'transport_manifest_sha256': composition['transport_manifest_sha256'],
    },
    'local_corrections': ['1017 tool-turn boundary', 'FlashInfer provider binding for retained ring transport'],
    'serving_qualified': False,
}
(ROOT / 'receipts').mkdir(exist_ok=True)
(ROOT / 'receipts/external-base-installed.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
print(json.dumps(external.verify()), flush=True)
