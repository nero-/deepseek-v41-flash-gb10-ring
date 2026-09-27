#!/usr/bin/env python3
"""Compare ringbench JSON files: python3 ringcompare.py base.json other.json [...]"""
import json
import sys

runs = [(p.rsplit("/", 1)[-1].replace("-ring.json", ""), json.load(open(p))) for p in sys.argv[1:]]
base = runs[0][1]
print("cell".ljust(16) + "".join(n[:14].rjust(16) for n, _ in runs))
for kind in base["decode"]:
    for c in base["decode"][kind]:
        cell = lambda d: d["decode"][kind][c]["median" if c == "c1" else "aggregate"]
        b = cell(base)
        print(f"{kind} {c}".ljust(16) + "".join(f"{cell(d):8.1f} ({100 * (cell(d) / b - 1):+5.1f}%)".rjust(16) for _, d in runs))
for i, p in enumerate(base.get("prefill", [])):
    b = p["tok_s"]
    print(f"prefill {p['target'] // 1024}k".ljust(16) + "".join(f"{d['prefill'][i]['tok_s']:8d} ({100 * (d['prefill'][i]['tok_s'] / b - 1):+5.1f}%)".rjust(16) for _, d in runs))
