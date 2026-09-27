#!/usr/bin/env python3
"""Summarise llm-inference-bench JSON and qeval logs for one or more tags.

    python3 summarize.py RESULTS_DIR [TAG ...]      (all tags when none given)

Prints, per tag: qeval pass count and median tok/s, LIL decode aggregate tok/s per
(context, concurrency) with the server's DSpark accept length, standalone prefill tok/s, and
Coding Peak mean. Values are copied from the saved files, never recomputed.
"""
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
tags = sys.argv[2:] or sorted({p.name.split("-")[0] for p in root.glob("*.json")} |
                              {p.name.split("-")[0] for p in root.glob("*-qeval.log")})
for tag in tags:
    print(f"== {tag}")
    q = root / f"{tag}-qeval.log"
    if q.exists():
        m = re.search(r"(\d+)/(\d+) passed.*?median ([\d.]+) tok/s", q.read_text(), re.S)
        print("  qeval:", f"{m.group(1)}/{m.group(2)} passed, median {m.group(3)} tok/s" if m else "(no summary line)")
    for case in ("quick", "matrix", "c16", "full"):
        f = root / f"{tag}-{case}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        rows = []
        for r in d.get("results", []):
            rows.append(f"{r['context_tokens'] // 1024}k c{r['concurrency']}: {r.get('aggregate_tps', 0):.1f} agg "
                        f"({r.get('output_tps_per_user_avg') or 0:.1f}/user, accept {r.get('server_spec_accept_length') or 0:.2f}, "
                        f"err {r.get('num_errors', 0)})")
        print(f"  {case} decode:", *rows, sep="\n    ")
        pf = d.get("prefill") or {}
        if pf:
            print(f"  {case} prefill:", ", ".join(f"{int(k) // 1024}k {v.get('tok_per_sec', 0):.0f} tok/s"
                                                 for k, v in sorted(pf.items(), key=lambda kv: int(kv[0]))))
    f = root / f"{tag}-coding.json"
    if f.exists():
        s = json.loads(f.read_text()).get("coding_peak", {}).get("summary", {})
        print(f"  coding peak: mean {s.get('mean_generation_tok_s', 0):.1f} tok/s "
              f"(min {s.get('min_generation_tok_s', 0):.1f}, max {s.get('max_generation_tok_s', 0):.1f})")
