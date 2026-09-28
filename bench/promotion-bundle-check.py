#!/usr/bin/env python3
"""Exercise deployment bundle recovery in temporary directories, without SSH."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root_repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('promotion', root_repo / 'scripts/promote-research.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as td:
    root = Path(td).resolve()
    (root / 'old.txt').write_text('old')
    code = module.BUNDLE_WRITER.replace("Path('/bundle')", 'Path(' + repr(str(root)) + ')')

    def run(action, tag, payload=None):
        return subprocess.run([sys.executable, '-c', code, action, tag],
                              input=json.dumps(payload) if payload else None,
                              text=True, capture_output=True)

    doc = {'files': {'old.txt': 'new', 'new.txt': 'added'},
           'expected': {'old.txt': hashlib.sha256(b'old').hexdigest()}}
    assert run('install', '.before-test', doc).returncode == 0
    assert (root / 'old.txt').read_text() == 'new'
    assert (root / 'new.txt').read_text() == 'added'
    assert run('rollback', '.before-test').returncode == 0
    assert (root / 'old.txt').read_text() == 'old' and not (root / 'new.txt').exists()
    mismatch = {**doc, 'expected': {'old.txt': 'wrong'}}
    assert run('install', '.before-mismatch', mismatch).returncode != 0
    assert (root / 'old.txt').read_text() == 'old' and not (root / '.before-mismatch').exists()
    with tempfile.TemporaryDirectory() as outside:
        target = Path(outside) / 'untouched'
        target.write_text('protected')
        (root / 'escape').symlink_to(target)
        assert run('install', '.before-escape', {'files': {'escape': 'bad'}, 'expected': {}}).returncode != 0
        assert target.read_text() == 'protected'
    assert run('install', '.before-edit', doc).returncode == 0
    (root / 'new.txt').write_text('operator change')
    assert run('rollback', '.before-edit').returncode != 0
    assert (root / 'old.txt').read_text() == 'new'
    assert (root / 'new.txt').read_text() == 'operator change'
print('PASS: install/rollback byte restoration, removal of additions, stale-state rejection, symlink escape rejection, and rollback prevalidation')
print('writer_sha256=' + hashlib.sha256(module.BUNDLE_WRITER.encode()).hexdigest())
