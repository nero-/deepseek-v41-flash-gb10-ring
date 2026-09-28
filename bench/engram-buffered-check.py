#!/usr/bin/env python3
"""Compare buffered/direct native row reads against checkpoint bytes (read-only)."""
import json
import os
from pathlib import Path
import struct
import numpy as np
from b12x.loader._native import load

root = Path("/models/target")
index = json.loads((root / "model.safetensors.index.json").read_text())["weight_map"]
names = [n for n in index if "engram" in n and n.endswith("embed.weight")]
assert names, "No Engram source in checkpoint index"
native = load()
checks = 0
for name in names:
    path = root / index[name]
    with path.open("rb") as f:
        header_length = struct.unpack("<Q", f.read(8))[0]
        item = json.loads(f.read(header_length))[name]
    rows, width = item["shape"]
    assert width == 256
    offset = 8 + header_length + item["data_offsets"][0]
    ids = np.asarray([0, 1, 15, 16, rows - 1, 0] + np.random.default_rng(74).integers(0, rows, 58).tolist(), dtype=np.int64)
    expected = bytearray()
    fd = os.open(path, os.O_RDONLY)
    for row in ids:
        expected.extend(os.pread(fd, 256, offset + int(row) * 256))
    os.close(fd)
    for buffered in (False, True):
        os.environ["B12X_DISK_TABLE_BUFFERED_IO"] = str(int(buffered))
        reader = native.ple_reader(rows, rows, 0, rows, width, 0, len(ids), 16)
        native.ple_reader_add(reader, 0, str(path), offset, False)
        output = np.zeros((len(ids), width), dtype=np.uint8)
        native.ple_reader_run(reader, memoryview(ids), memoryview(output), None, len(ids))
        assert output.tobytes() == bytes(expected), (name, buffered)
        checks += len(ids)
        print(json.dumps({"tensor": name, "buffered": buffered, "rows_exact": len(ids)}), flush=True)
        del reader
print(json.dumps({"status": "PASS", "row_checks": checks}))
