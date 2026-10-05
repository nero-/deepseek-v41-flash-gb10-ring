#!/usr/bin/env python3
"""Exercise checkpoint deletion boundaries without Docker or fleet access."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cleanup', repo / 'scripts/csf-cleanup-candidate.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
real_check_output = subprocess.check_output
original_argv = sys.argv


def execute(root, live=False):
    def output(args, **kwargs):
        if args[:2] == ['docker', 'ps']:
            return 'live' if live else ''
        assert args[:2] == ['docker', 'inspect']
        return json.dumps([{'Mounts': [{'Source': str(root)}]}])
    subprocess.check_output = output
    sys.argv = ['guard-test', str(root)]
    with contextlib.redirect_stdout(io.StringIO()):
        exec(module.DELETE, {})


try:
    with tempfile.TemporaryDirectory() as temporary:
        parent = Path(temporary).resolve()
        root = parent / 'c5c41fe301c4c1d24fc09376883d9168e521dc66'
        neighbor = parent / 'original'
        neighbor.mkdir()
        keep = neighbor / 'weights'
        keep.write_bytes(b'original remains intact')
        for kind in ('live-mount', 'symlink', 'outside-hardlink', 'internal-hardlink'):
            root.mkdir()
            candidate = root / 'metadata'
            candidate.write_bytes(b'candidate')
            if kind == 'symlink':
                (root / 'escape').symlink_to(keep)
            elif kind == 'outside-hardlink':
                os.link(candidate, neighbor / 'alias')
            elif kind == 'internal-hardlink':
                directory = root / 'serving'
                directory.mkdir()
                os.link(candidate, directory / 'metadata')
            rejected = False
            try:
                execute(root, kind == 'live-mount')
            except AssertionError:
                rejected = True
            if kind == 'internal-hardlink':
                assert not rejected and not root.exists()
            else:
                assert rejected and candidate.read_bytes() == b'candidate'
                for child in root.iterdir():
                    child.unlink()
                root.rmdir()
                if kind == 'outside-hardlink':
                    (neighbor / 'alias').unlink()
            assert keep.read_bytes() == b'original remains intact'
            print('PASS', kind)
finally:
    subprocess.check_output = real_check_output
    sys.argv = original_argv
print('RECOVERY GUARDS PASS')
