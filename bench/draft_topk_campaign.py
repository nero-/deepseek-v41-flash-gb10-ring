#!/usr/bin/env python3
"""Qualify Qwen-derived top-20 proposals before a serving performance trial."""
import json
from pathlib import Path
import subprocess
import time

root = Path.home() / "sparkring-migration-20260927"
deadline = time.monotonic() + 7200
while True:
    content = (root / "novel-campaign2.log").read_text()
    if "CAMPAIGN COMPLETE" in content:
        break
    if "Traceback" in content:
        raise RuntimeError("Prior campaign failed; inspect before proceeding")
    if time.monotonic() > deadline:
        raise TimeoutError("Prior campaign did not complete")
    time.sleep(5)
subprocess.run(["sudo", "-n", "python3", str(root / "installer_variant.py"), "stop"], check=True)
image = "sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf"
argv = ["docker", "run", "--rm", "--name", "ds41-top20-qualification", "--gpus", "all", "--ipc", "host",
        "-e", "PYTHONPATH=/evidence/vllm-local-plugins", "-v", str(root) + ":/evidence:ro",
        "--entrypoint", "python3", image, "/evidence/draft_topk_tests/check_topk.py"]
(root / "top20-unit-command.json").write_text(json.dumps(argv, indent=2))
with (root / "top20-unit.log").open("w") as out:
    subprocess.run(argv, stdout=out, stderr=subprocess.STDOUT, check=True)
print("TOP20 GPU UNIT CHECKS PASSED", flush=True)
subprocess.run(["python3", "-u", str(root / "novel_campaign.py"), "engram-top20"], check=True)
