#!/usr/bin/env python3
"""Convert a rendered spark-ds41f launch into the root controller's selection.

Input: the directory written by render.py (one docker-run argv per rank) and
the currently installed /etc/deepseek-ring/optimized-specs.json (for the
switched fabric, clock and checkpoint records it already carries). Output: a
new selection document whose four ContainerSpec entries reproduce the rendered
containers under the controller's canonical ds41-optimized-rN names.

Every docker-run flag is mapped explicitly; an unknown flag is an error, so
the selection cannot silently drop a recipe setting. Performs no SSH or
Docker action and installs nothing.
"""
import argparse
import hashlib
import json
from pathlib import Path

PROFILE = "tilelang-ds41f1022-1017-kv20-images999-switch-draft5"
CAMPAIGN = "ds41f-tilelang-20261024"
# The production loader profile: the same JSON the trial's staged copy was taken from.
SECCOMP = ("/srv/sparkring/sparkring/deepseek-v41-flash-tp4-iba1b36389e5d/source-8b152d65c701/"
           "runtime/common/loader-seccomp.json")
# ContainerSpec only sets memlock; the recipe also pins stack and core limits.
LIMITS = 'ulimit -s 65536 && ulimit -c 0 && exec vllm serve "$@"'
GIB = 1024 ** 3
KEPT = ("fabric", "clock_policy", "checkpoint", "host_memory_policy")


def size(text: str) -> int:
    if not text.endswith("g"):
        raise SystemExit(f"unexpected size {text!r}")
    return int(text[:-1]) * GIB


def convert(argv: list[str], rank: int, image: str, production: dict) -> dict:
    if argv[:3] != ["docker", "run", "-d"]:
        raise SystemExit("expected a detached docker run")
    spec = {"name": f"ds41-optimized-r{rank}", "image_id": image, "platform": "linux/arm64", "pull_policy": "never",
            "restart_policy": "no", "init": False, "gpu_count": -1, "network_mode": None, "ipc_mode": None,
            "memlock": None, "devices": [], "memory": None, "memory_swap": None, "shm_size": None, "cap_add": [],
            "security_opt": [], "user": None, "working_dir": None, "cpuset_cpus": None, "environment": {},
            "mounts": [], "labels": {"io.local.deepseek-optimized": PROFILE, "io.local.rank": str(rank),
                                     "io.local.deepseek-campaign": CAMPAIGN}}
    for key in ("health_command", "health_interval", "health_timeout", "health_start_period", "health_retries",
                "health_mode"):
        spec[key] = production[key]
    ulimits = {}
    i = 3
    while i < len(argv) and argv[i] != image:
        flag = argv[i]
        if flag in ("--name", "--env", "--volume"):
            value, i = argv[i + 1], i + 2
        else:
            flag, _, value = flag.partition("=")
            i += 1
        if flag == "--name":
            continue
        elif flag == "--network":
            spec["network_mode"] = value
        elif flag == "--ipc":
            spec["ipc_mode"] = value
        elif flag == "--gpus":
            assert value == "all"
        elif flag == "--device":
            host, container, permissions = value.split(":")
            assert host == container and permissions == "rwm", value
            spec["devices"].append(host)
        elif flag == "--cap-add":
            spec["cap_add"].append(value)
        elif flag == "--ulimit":
            name, limits = value.split("=")
            ulimits[name] = limits
        elif flag == "--security-opt":
            spec["security_opt"].append(f"seccomp={SECCOMP}" if value.startswith("seccomp=") else value)
        elif flag == "--shm-size":
            spec["shm_size"] = size(value)
        elif flag == "--memory":
            spec["memory"] = size(value)
        elif flag == "--memory-swap":
            spec["memory_swap"] = size(value)
        elif flag == "--mount":
            fields = dict(part.split("=", 1) for part in value.split(","))
            # The DRM card for the display carve-out (off at TP4): pass the node itself.
            assert fields["type"] == "bind" and fields["target"] == "/dev/dri/card0", value
            spec["devices"].append("/dev/dri/card0")
        elif flag == "--device-cgroup-rule":
            assert value == "c 226:* rw", value  # covered by the card0 device above
        elif flag == "--cpuset-cpus":
            spec["cpuset_cpus"] = value
        elif flag == "--env":
            key, _, content = value.partition("=")
            spec["environment"][key] = content
        elif flag == "--volume":
            source, target, mode = value.split(":")
            spec["mounts"].append({"source": source, "target": target, "read_only": mode == "ro"})
        else:
            raise SystemExit(f"rank {rank}: unmapped docker run flag {flag!r}")
    if i >= len(argv):
        raise SystemExit("image not found in the rendered argv")
    if ulimits != {"memlock": "-1:-1", "stack": "67108864:67108864", "core": "0"}:
        raise SystemExit(f"unexpected ulimits {ulimits}")
    spec["memlock"] = -1
    spec["entrypoint"] = ["/bin/bash", "-c", LIMITS, "vllm-serve"]
    spec["command"] = argv[i + 1:]
    return spec


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", type=Path, required=True, help="render.py output directory")
    parser.add_argument("--current", type=Path, required=True, help="copy of the installed selection")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.launch / "manifest.json").read_text())
    current_text = args.current.read_text()
    current = json.loads(current_text)
    specs = []
    for rank in range(4):
        argv = json.loads((args.launch / f"rank{rank}.json").read_text())
        specs.append(convert(argv, rank, manifest["image"], current["specs"][rank]))
    document = {
        "profile": PROFILE,
        "source_receipt": "image/tilelang-ds41f/README.md",
        "previous_selection_sha256": hashlib.sha256(current_text.encode()).hexdigest(),
        "previous_profile": current["profile"],
        "runtime_composition": {"recipe": manifest["source"], "image": manifest["image"],
                                "site_changes": manifest["site_changes"],
                                "process_limits": "stack 64 MiB and no core files via the entrypoint wrapper"},
        "plugin_manifest": {},
        "multimodal_selection": {"limit_mm_per_prompt": {"image": 999}},
        **{key: current[key] for key in KEPT},
        "specs": specs,
    }
    args.output.write_text(json.dumps(document, indent=2) + "\n")
    print(args.output, hashlib.sha256(args.output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
