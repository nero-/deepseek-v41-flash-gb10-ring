#!/usr/bin/env python3
"""Restore original shards from CSF bytes; publish only after exact source hashes.

This fleet-specific recovery uses the published original headers and CPU byte
codec. It never requantizes tensors. Run only with every model container stopped.
On constrained nodes --replace-candidate removes a compressed shard only after
its original is fsynced, published and SHA-256 verified. Remaining candidate
metadata is retained for a later guarded cleanup after serving is restored.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time

import numpy as np

OLD_REV = 'dba1be0a40aa45a94ad051997016db3960a90277'
NEW_REV = 'c5c41fe301c4c1d24fc09376883d9168e521dc66'
OLD = Path('/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash') / OLD_REV
NEW = Path('/srv/sparkring/sparkring/checkpoints/local-inference-lab--DeepSeek-V4.1-Flash-lossless-CSF') / NEW_REV
BLOCK = 16 << 20


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def header(source):
    raw = source.read(8)
    assert len(raw) == 8
    length = struct.unpack('<Q', raw)[0]
    assert 0 < length < 32 << 20
    data = source.read(length)
    assert len(data) == length
    fields = json.loads(data)
    fields.pop('__metadata__', None)
    return fields, 8 + length


def decode_scale(fixed_bytes, exception_bytes, rows, columns):
    assert rows > 0 and rows % 16 == 0 and columns > 0
    selectors = (columns + 7) // 8
    fixed = np.frombuffer(fixed_bytes, dtype=np.uint8).reshape(rows // 16, 16 * (1 + selectors))
    bases = fixed[:, :16].reshape(rows, 1)
    bits = np.unpackbits(fixed[:, 16:].reshape(rows, selectors), axis=1, bitorder='little')[:, :columns]
    # Arithmetic on original UE8M0 bytes, without the serving kernel's clamp.
    output = (bases + bits).astype(np.uint8)
    assert len(exception_bytes) % 4 == 0
    words = np.frombuffer(exception_bytes, dtype='<u4')
    positions = words & 0xFFFFFF
    assert np.all(positions < rows * columns)
    output.ravel()[positions] = words >> 24
    return output.tobytes()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def restore_one(row):
    name = row['file']
    receipt = json.loads((NEW / 'receipts' / (name + '.json')).read_text())
    for key in ('file', 'source_file_bytes', 'source_sha256', 'target_file_bytes', 'target_sha256'):
        assert receipt[key] == row[key], (name, key)
    source_header = base64.b64decode(receipt['source_header_base64'], validate=True)
    assert struct.unpack('<Q', source_header[:8])[0] == len(source_header) - 8
    original = json.loads(source_header[8:])
    original.pop('__metadata__', None)
    target = OLD / name
    compressed = NEW / 'tensors' / name
    assert not target.is_symlink() and not compressed.is_symlink()
    expected = row['source_sha256']
    if target.exists():
        assert target.is_file() and target.stat().st_nlink == 1
        assert target.stat().st_size == row['source_file_bytes'] and digest(target) == expected
        return target, compressed, False
    assert compressed.is_file() and compressed.stat().st_nlink == 1
    assert compressed.stat().st_size == row['target_file_bytes']
    assert shutil.disk_usage(OLD).free >= row['source_file_bytes'] + (8 << 30), name
    temporary = target.with_name(name + '.restore-partial')
    assert not temporary.is_symlink()
    assert not temporary.exists() or (temporary.is_file() and temporary.stat().st_nlink == 1)
    accumulator = hashlib.sha256()
    with compressed.open('rb') as source, temporary.open('wb') as destination:
        stored, base = header(source)
        destination.write(source_header)
        accumulator.update(source_header)
        offset = 0
        scales = receipt['scales']
        for tensor, description in sorted(original.items(), key=lambda item: item[1]['data_offsets'][0]):
            start, end = description['data_offsets']
            assert start == offset and end >= start, tensor
            length = end - start
            if tensor in stored:
                value = stored[tensor]
                assert value['dtype'] == description['dtype'] and value['shape'] == description['shape']
                a, b = value['data_offsets']
                assert b - a == length
                source.seek(base + a)
                remaining = length
                while remaining:
                    block = source.read(min(BLOCK, remaining))
                    assert block, tensor
                    destination.write(block)
                    accumulator.update(block)
                    remaining -= len(block)
            else:
                information = scales[tensor]
                assert description['dtype'] == information['dtype'] == 'F8_E8M0'
                assert description['shape'] == information['shape'] and len(description['shape']) == 2
                components = []
                for suffix, dtype, expected_bytes in (
                    ('mxfp4_csf_fixed', 'U8', information['fixed_bytes']),
                    ('mxfp4_csf_exceptions', 'U32', information['exception_bytes']),
                ):
                    part = stored[tensor + '.' + suffix]
                    assert part['dtype'] == dtype
                    a, b = part['data_offsets']
                    assert b - a == expected_bytes
                    source.seek(base + a)
                    data = source.read(expected_bytes)
                    assert len(data) == expected_bytes
                    components.append(data)
                data = decode_scale(*components, *description['shape'])
                assert len(data) == length == information['source_bytes']
                assert hashlib.sha256(data).hexdigest() == information['source_sha256'], tensor
                destination.write(data)
                accumulator.update(data)
            offset = end
        destination.flush()
        os.fsync(destination.fileno())
    assert temporary.stat().st_size == row['source_file_bytes']
    assert accumulator.hexdigest() == expected, name
    temporary.replace(target)
    sync_directory(OLD)
    # Verify the published on-disk file before removing its compressed source.
    assert digest(target) == expected, name
    return target, compressed, True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--original-manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--replace-candidate', action='store_true')
    parser.add_argument('--recovery-container')
    args = parser.parse_args()
    running = subprocess.check_output(['docker', 'ps', '-q'], text=True).split()
    if running:
        assert args.recovery_container and len(running) == 1, 'Fleet rank must be idle'
        info = json.loads(subprocess.check_output(['docker', 'inspect', running[0]], text=True))[0]
        assert info['Name'] == '/' + args.recovery_container
        assert info['Config']['Labels'].get('io.local.deepseek-recovery') == 'csf-20261004'
        assert not info['HostConfig']['Privileged']
        assert not info['HostConfig']['DeviceRequests'] and not info['HostConfig']['Devices']
    assert OLD.resolve() == OLD and NEW.resolve() == NEW and OLD != NEW
    manifest = json.loads((NEW / 'manifest.json').read_text())
    assert manifest['codec'] == 'row-base-offset1-u24-exceptions/1'
    assert manifest['source_revision'] == OLD_REV
    published = json.loads(Path(args.original_manifest).read_text())
    assert published['sha'] == OLD_REV
    source_files = {x['rfilename']: x for x in published['siblings']}
    shards = manifest['shards']
    assert len(shards) == 48
    for row in shards:
        assert Path(row['file']).name == row['file']
        entry = source_files[row['file']]
        assert entry['lfs']['sha256'] == row['source_sha256']
        assert entry['size'] == row['source_file_bytes']
    OLD.mkdir(parents=True, exist_ok=True)
    records = []
    for row in shards:
        started = time.monotonic()
        target, compressed, restored = restore_one(row)
        removed = False
        if args.replace_candidate and compressed.exists():
            assert compressed.is_file() and not compressed.is_symlink() and compressed.stat().st_nlink == 1
            assert compressed.stat().st_size == row['target_file_bytes']
            compressed.unlink()
            sync_directory(compressed.parent)
            removed = True
        records.append({'file': row['file'], 'sha256': row['source_sha256'],
                        'bytes': row['source_file_bytes'], 'restored': restored,
                        'candidate_removed': removed, 'seconds': time.monotonic() - started})
        Path(args.output).write_text(json.dumps({'revision': OLD_REV, 'complete': False, 'shards': records}, indent=2) + '\n')
        print(json.dumps(records[-1]), flush=True)
    assert len(list(OLD.glob('*.safetensors'))) == 48
    Path(args.output).write_text(json.dumps({'revision': OLD_REV, 'complete': True, 'shards': records}, indent=2) + '\n')
    print('ORIGINAL CHECKPOINT VERIFIED', flush=True)


if __name__ == '__main__':
    main()
