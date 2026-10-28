#!/usr/bin/env python3
"""Read-only GID 3 check of all eight switched rails, run from the workstation.

The same check as `deepseek-ring-control fabric-check`, without root: it runs
scripts/fabric_repair.py in `check` mode on every rank over SSH, with the
fabric definition from spark-r0's /etc/deepseek-ring/optimized-specs.json.
Exits 1 if any rail's IPv4 RoCEv2 GID is not at index 3.
"""
import json
from pathlib import Path
import sys

import fleet

SELECTED = "/etc/deepseek-ring/optimized-specs.json"


def main():
    fabric = json.loads(fleet.remote(0, ["cat", SELECTED]).stdout)["fabric"]
    code = (Path(__file__).with_name("fabric_repair.py")).read_text()
    results = fleet.parallel(lambda rank: json.loads(
        fleet.remote(rank, ["python3", "-c", code, str(rank), json.dumps(fabric), "check"]).stdout))
    for result in results:
        rails = "  ".join(f"{rail['interface']} {rail['gid3']}" for rail in result["rails"])
        print(f"rank {result['rank']} {fleet.ALIASES[result['rank']]:<9} {rails}")
    if any(rail["gid3"] != "ok" for result in results for rail in result["rails"]):
        print("GID 3 is wrong on a switched rail: stop FLARE, then use 'repair fabric'", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
