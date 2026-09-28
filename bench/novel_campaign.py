#!/usr/bin/env python3
"""Serial one-factor screens, with explicit logs and no automatic selection."""
import argparse
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument("variants", nargs="+", choices=["engram-adaptive4k-graphs", "engram-top20", "engram-fair4k", "engram-graphs", "engram-cost125", "engram-cost075", "engram-indexer-tp", "engram-adaptive4k"])
p.add_argument("--after-qkv", action="store_true")
p.add_argument("--after-campaign", action="store_true")
a = p.parse_args()
root = Path.home() / "sparkring-migration-20260927"
if a.after_campaign:
    deadline = time.monotonic() + 7200
    while True:
        content = (root / "novel-campaign.log").read_text()
        if "CAMPAIGN COMPLETE" in content:
            break
        if "Traceback" in content:
            raise RuntimeError("Prior campaign failed; inspect before continuing")
        if time.monotonic() > deadline:
            raise TimeoutError("Prior campaign did not finish")
        time.sleep(5)
if a.after_qkv:
    deadline = time.monotonic() + 2400
    while True:
        log = root / "engram-qkv-split-measure.log"
        if log.exists():
            content = log.read_text()
            if "MEASUREMENT COMPLETE" in content or "REJECTED:" in content:
                break
            if "Functional check failed" in content or "Traceback" in content:
                raise RuntimeError("QKV trial did not complete safely")
        if time.monotonic() > deadline:
            raise TimeoutError("QKV trial did not finish")
        time.sleep(5)
for variant in a.variants:
    print("START", variant, flush=True)
    commands = [
        (variant + "-start", ["sudo", "-n", "python3", str(root / "installer_variant.py"), variant]),
        (variant + "-measure", ["python3", "-u", str(root / "installer_measure.py"), variant, "--quality"]),
    ]
    if variant in ("engram-adaptive4k-graphs", "engram-fair4k", "engram-adaptive4k", "engram-indexer-tp"):
        commands.append(("mixed-" + variant, ["python3", "-u", str(root / "mixed_traffic.py"), variant,
            "--output", str(root / ("mixed-" + variant + ".json"))]))
    if variant in ("engram-adaptive4k-graphs", "engram-adaptive4k", "engram-indexer-tp"):
        commands.append(("integrity-" + variant, ["python3", "-u", str(root / "mixed_traffic.py"), variant,
            "--integrity", "--rounds", "1", "--output", str(root / ("integrity-" + variant + ".json"))]))
    for name, command in commands:
        if name.startswith(("mixed-", "integrity-")) and (root / ("measure-" + variant) / "rejected.json").exists():
            print("SKIP", name, "because the optimization was rejected", flush=True)
            continue
        (root / (name + "-command.json")).write_text(json.dumps(command, indent=2))
        with (root / (name + ".log")).open("w") as out:
            subprocess.run(command, stdout=out, stderr=subprocess.STDOUT, check=True)
        print("DONE", name, flush=True)
print("CAMPAIGN COMPLETE; selection requires review of results", flush=True)
