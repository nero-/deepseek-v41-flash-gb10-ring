#!/usr/bin/env python3
"""CPU recovery proof: original file bytes, unclamped scales, failure isolation."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile

import numpy as np

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery', root / 'image/csf/restore-original.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def make_file(tensors):
    fields, data = {}, bytearray()
    for name, dtype, shape, value in tensors:
        start = len(data)
        data.extend(value)
        fields[name] = {'dtype': dtype, 'shape': shape, 'data_offsets': [start, len(data)]}
    text = json.dumps(fields, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 8)
    header = struct.pack('<Q', len(text)) + text
    return header + data, header


with tempfile.TemporaryDirectory() as temporary:
    r.OLD = Path(temporary) / 'old'
    r.NEW = Path(temporary) / 'new'
    r.OLD.mkdir()
    (r.NEW / 'tensors').mkdir(parents=True)
    (r.NEW / 'receipts').mkdir()
    for columns in (9, 18, 160):
        rows = 32
        bases = np.arange(rows, dtype=np.uint8) + 220
        bits = (np.arange(rows * columns).reshape(rows, columns) % 2).astype(np.uint8)
        logical = bases[:, None] + bits
        positions = np.array([0, rows * columns - 1], dtype=np.uint32)
        values = np.array([255, 7], dtype=np.uint32)
        logical.ravel()[positions] = values
        selectors = np.packbits(bits, axis=1, bitorder='little')
        fixed = np.concatenate((bases.reshape(-1, 16), selectors.reshape(rows // 16, -1)), axis=1)
        words = positions | (values << 24)
        payload = bytes(range(100))
        original, source_header = make_file([
            ('weight', 'U8', [100], payload),
            ('scale', 'F8_E8M0', [rows, columns], logical.tobytes()),
        ])
        compressed, _ = make_file([
            ('scale.mxfp4_csf_fixed', 'U8', list(fixed.shape), fixed.tobytes()),
            ('weight', 'U8', [100], payload),
            ('scale.mxfp4_csf_exceptions', 'U32', [2], words.astype('<u4').tobytes()),
        ])
        name = f'model-{columns}.safetensors'
        row = {'file': name, 'source_file_bytes': len(original), 'source_sha256': hashlib.sha256(original).hexdigest(),
               'target_file_bytes': len(compressed), 'target_sha256': hashlib.sha256(compressed).hexdigest()}
        receipt = dict(row, source_header_base64=base64.b64encode(source_header).decode(), scales={
            'scale': {'dtype': 'F8_E8M0', 'shape': [rows, columns], 'fixed_bytes': fixed.nbytes,
                      'exception_bytes': words.nbytes, 'source_bytes': logical.nbytes,
                      'source_sha256': hashlib.sha256(logical.tobytes()).hexdigest()}})
        (r.NEW / 'tensors' / name).write_bytes(compressed)
        (r.NEW / 'receipts' / (name + '.json')).write_text(json.dumps(receipt))
        restored, candidate, created = r.restore_one(row)
        assert created and restored.read_bytes() == original
        assert candidate.read_bytes() == compressed
        assert not r.restore_one(row)[2]
        restored.unlink()
        receipt['scales']['scale']['source_sha256'] = '0' * 64
        (r.NEW / 'receipts' / (name + '.json')).write_text(json.dumps(receipt))
        try:
            r.restore_one(row)
        except AssertionError:
            pass
        else:
            raise AssertionError('Corrupted restoration must fail')
        assert not restored.exists() and candidate.read_bytes() == compressed
        print('PASS', columns, 'columns: exact source bytes, no clamp, existing-source verification, corrupt-source rejection')
print('RESTORE CPU PROOF PASS')
