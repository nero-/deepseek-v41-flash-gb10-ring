#!/usr/bin/env python3
"""Apply experiment overrides to a Mia .env.tp4.

  env_override.py BASE OUT KEY=VAL [KEY+=VAL ...]

KEY=VAL replaces a top-level assignment if the file has one, otherwise sets KEY inside
EXTRA_CONTAINER_ENV (replacing an existing entry). KEY+=VAL appends VAL to a quoted top-level
value (for example EXTRA_SGLANG_ARGS+=--cuda-graph-bs ...). KEY=- removes a container-env entry.
"""
import re
import sys
from pathlib import Path

base, out, *ops = sys.argv[1:]
lines = Path(base).read_text().splitlines()
top = {m.group(1): i for i, l in enumerate(lines) if (m := re.match(r"^([A-Z0-9_]+)=", l))}
ei = top["EXTRA_CONTAINER_ENV"]
extra = dict(kv.split("=", 1) for kv in lines[ei].split("=", 1)[1].strip('"').split())
for op in ops:
    if "+=" in op:
        k, v = op.split("+=", 1)
        cur = lines[top[k]].split("=", 1)[1].strip('"')
        lines[top[k]] = f'{k}="{cur} {v}"'
        continue
    k, v = op.split("=", 1)
    if k in top and k != "EXTRA_CONTAINER_ENV":
        lines[top[k]] = f"{k}={v}"
    elif v == "-":
        extra.pop(k, None)
    else:
        extra[k] = v
lines[ei] = 'EXTRA_CONTAINER_ENV="' + " ".join(f"{k}={v}" for k, v in extra.items()) + '"'
Path(out).write_text("\n".join(lines) + "\n")
