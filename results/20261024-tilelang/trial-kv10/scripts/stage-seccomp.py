#!/usr/bin/env python3
"""Copy each rank's production SparkRing seccomp profile to a trial file.

Reads HostConfig.SecurityOpt from the canonical ds41-optimized-rN container
(running or stopped) and writes the identical JSON to the path render.py
names. Changes nothing else; refuses differing profiles across ranks.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "Agent/Builds/deepseek-v41-flash-spark/scripts"))
import fleet  # noqa: E402

DIRECTORY = "/home/nero/ds41f-tilelang-20261024"


def stage(rank):
    container = json.loads(fleet.remote(rank, ["docker", "inspect", f"ds41-optimized-r{rank}"]).stdout)[0]
    profiles = [o.split("=", 1)[1] for o in container["HostConfig"]["SecurityOpt"] if o.startswith("seccomp=")]
    assert len(profiles) == 1, profiles
    profile = json.loads(profiles[0])
    assert any("io_uring_setup" in group["names"] for group in profile["syscalls"]), "no io_uring in profile"
    text = json.dumps(profile, indent=1) + "\n"
    fleet.remote(rank, ["bash", "-c", f"mkdir -p {DIRECTORY} && cat > {DIRECTORY}/seccomp.json.tmp && "
                        f"mv {DIRECTORY}/seccomp.json.tmp {DIRECTORY}/seccomp.json"], data=text)
    written = fleet.remote(rank, ["sha256sum", f"{DIRECTORY}/seccomp.json"]).stdout.split()[0]
    assert written == hashlib.sha256(text.encode()).hexdigest()
    return written


digests = fleet.parallel(stage)
assert len(set(digests)) == 1, digests
print("seccomp profile staged on all ranks:", digests[0])
