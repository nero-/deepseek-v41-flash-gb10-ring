#!/usr/bin/env python3
"""Serial functional/performance screening of one ready installer variant."""
import argparse
import json
import re
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument("variant")
p.add_argument("--quality", action="store_true")
a = p.parse_args()
if not a.variant.replace("-", "").isalnum():
    raise SystemExit("Invalid variant label")
root = Path.home() / "sparkring-migration-20260927"
out = root / ("measure-" + a.variant)
out.mkdir(exist_ok=True)
deadline = time.monotonic() + 3600
while True:
    log = (root / (a.variant + "-start.log")).read_text()
    if "READY " + a.variant + " " in log:
        break
    if "Traceback (most recent call last)" in log:
        raise RuntimeError("Trial startup failed; inspect its log")
    if time.monotonic() > deadline:
        raise TimeoutError("Trial did not become ready")
    time.sleep(5)


statuses = {}


def run(name, args):
    (out / (name + "-command.json")).write_text(json.dumps(args, indent=2))
    with (out / (name + ".log")).open("w") as stream:
        r = subprocess.run(args, cwd=out, stdout=stream, stderr=subprocess.STDOUT)
    print(name, r.returncode, flush=True)
    statuses[name] = r.returncode
    (out / "statuses.json").write_text(json.dumps(statuses, indent=2))
    return r.returncode


if run("functional", ["python3", str(root / "probes/functional.py"), "http://127.0.0.1:8015/v1"]):
    raise SystemExit("Functional check failed")
if a.variant == "engram-qkv-split":
    log = subprocess.run(["docker", "logs", "ds41-trial-engram-qkv-split-r0"],
                         text=True, capture_output=True, check=True)
    content = log.stdout + log.stderr
    counts = {"enabled": content.count("bit-exact=ON"), "disabled": content.count("bit-exact=OFF")}
    (out / "exactness.json").write_text(json.dumps(counts, indent=2))
    if not counts["enabled"]:
        print("REJECTED: no projection passed the exactness guard; fallback functional checks passed", flush=True)
        raise SystemExit(0)
run("smoke", ["python3", str(root / "smoke.py"), "--url", "http://127.0.0.1:8015",
               "--model", "DeepSeek-V4.1-Flash-TP4"] + (["--needle", "128000"] if a.variant == "engram-indexer-tp" else []))
if a.variant == "engram-indexer-tp" and not re.search(r"needle \d+ tokens: PASS", (out / "smoke.log").read_text()):
    raise SystemExit("Indexer trial failed its required long-context needle check")
if a.variant == "engram-indexer-tp":
    log = subprocess.run(["docker", "logs", "ds41-trial-engram-indexer-tp-r0"], text=True, capture_output=True, check=True)
    content = log.stdout + log.stderr
    counts = {"enabled": content.count("bit-exact=ON"), "disabled": content.count("bit-exact=OFF")}
    if not counts["enabled"]:
        (out / "rejected.json").write_text(json.dumps({**counts, "decision": "No indexer case enabled"}, indent=2))
        print("REJECTED: no indexer case passed its exactness guard", flush=True)
        raise SystemExit(0)
    (out / "rejected.json").unlink(missing_ok=True)
run("tune", ["ssh", "gx10-r0", "PORT=8015 MODEL=DeepSeek-V4.1-Flash-TP4 bash ~/bench/lilbench.sh installer-" + a.variant + " tune"])
run("prompt-decode", ["python3", str(root / "probes/decode_probe.py"), "http://127.0.0.1:8015/v1", "512", "3"])
if a.quality:
    run("qeval", ["env", "PYTHONPATH=" + str(root / "baseline"),
        "python3", "-u", str(root / "baseline/qeval.py"), "run", a.variant,
        "--url", "http://127.0.0.1:8015/v1/chat/completions"])
if a.variant == "engram-indexer-tp":
    log = subprocess.run(["docker", "logs", "ds41-trial-engram-indexer-tp-r0"], text=True, capture_output=True, check=True)
    lines = [line for line in (log.stdout + log.stderr).splitlines() if "[local-indexer-tp]" in line]
    (out / "indexer-guards.log").write_text("\n".join(lines) + "\n")
if any(code for name, code in statuses.items() if name != "smoke"):
    raise SystemExit("A required measurement failed; inspect statuses.json")
print("MEASUREMENT COMPLETE", flush=True)
