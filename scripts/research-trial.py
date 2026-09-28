#!/usr/bin/env python3
"""Run isolated research containers using the selected deployment's exact spec.

Invoked from the workstation. Requires existing SSH and Docker access; retains
the permanent selected containers/configuration and shared checkpoint intact.
"""
import argparse
import concurrent.futures as cf
import copy
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "sparkring-installer"))
from runtime.common.container_spec import Bind, ContainerSpec, docker_create

HOSTS = ("192.168.50.219", "192.168.50.129", "192.168.50.192", "192.168.50.23")
ALIASES = ("spark-r0", "spark-r1", "gx10-r1", "gx10-r0")
REMOTE = "/home/nero/dsv41-research-20260928"
RESULTS = ROOT / "results/20260928-research"
PLUGINS = ROOT / "image/vllm-local-plugins"
VARIANTS = {"context-cost": "dsv41_context_cost", "timed-prefill": "dsv41_timed_prefill",
            "context-indexer": "dsv41_context_indexer", "engram-readahead": "dsv41_engram_readahead",
            "engram-buffered": "dsv41_adaptive_prefill", "markov-shortlist": "dsv41_markov_shortlist",
            "owned-mhc": "dsv41_owned_mhc", "context-indexer-local": "dsv41_context_indexer",
            "query-indexer-local": "dsv41_indexer_tp", "owned-residual": "dsv41_owned_mhc",
            "markov-shortlist128": "dsv41_markov_shortlist", "query-indexer-values": "dsv41_indexer_tp",
            "query-indexer-values-auto": "dsv41_indexer_tp", "context-indexer-local-auto": "dsv41_context_indexer"}


def remote(rank, command, data=None, check=True):
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-o", "HostName=" + HOSTS[rank], "-o", "ProxyCommand=none", ALIASES[rank], shlex.join(command)],
        input=data, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(f"Rank {rank} {command[:3]} failed: {result.stderr[-2000:]}")
    return result


def parallel(fn):
    with cf.ThreadPoolExecutor(4) as pool:
        return list(pool.map(fn, range(4)))


def stop():
    active = RESULTS / "active.json"
    if not active.exists():
        return
    state = json.loads(active.read_text())
    folder = Path(state["folder"])
    def one(rank):
        name = state["names"][rank]
        info = remote(rank, ["docker", "inspect", name], check=False)
        if info.returncode:
            return
        doc = json.loads(info.stdout)[0]
        if doc["Config"]["Labels"].get("io.local.deepseek-research") != state["variant"]:
            raise RuntimeError("Refusing to remove a container without this trial's label")
        remote(rank, ["docker", "stop", "--time", "15", name])
        logs = remote(rank, ["docker", "logs", name], check=False)
        (folder / f"rank{rank}.log").write_text(logs.stdout + logs.stderr)
        remote(rank, ["docker", "rm", name])
    parallel(one)
    active.unlink()


def start(variant):
    selected = json.loads(remote(0, ["cat", "/etc/deepseek-ring/optimized-specs.json"]).stdout)
    RESULTS.mkdir(parents=True, exist_ok=True)
    folder = RESULTS / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + variant)
    folder.mkdir()
    (folder / "selected.json").write_text(json.dumps(selected, indent=2))
    plugin = VARIANTS[variant]
    active_plugins = list(dict.fromkeys(["dsv41_adaptive_prefill", plugin])) if variant != "timed-prefill" else [plugin]
    files = {name + ".py": (PLUGINS / (name + ".py")).read_text() for name in active_plugins}
    files["dsv41_research-0.1.dist-info/METADATA"] = "Metadata-Version: 2.1\nName: dsv41-research\nVersion: 0.1\n"
    files["dsv41_research-0.1.dist-info/entry_points.txt"] = "[vllm.general_plugins]\n" + "".join(
        f"{name} = {name}:register\n" for name in active_plugins)
    # Docker's client reads this profile before contacting its daemon. The
    # installed source tree is root-only; copy the same pinned upstream policy.
    installer = ROOT.parent / "sparkring-installer"
    revision = subprocess.check_output(["git", "-C", str(installer), "rev-parse", "HEAD"], text=True).strip()
    if revision != "8b152d65c701f557f62ae6a9a1c3db90771c1df3":
        raise RuntimeError("Unexpected installer revision for seccomp policy")
    files["loader-seccomp.json"] = subprocess.check_output(["git", "-C", str(installer), "show",
        revision + ":runtime/common/loader-seccomp.json"], text=True)
    (folder / "plugin-sha256.json").write_text(json.dumps({k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()}, indent=2))
    for name in active_plugins:
        (folder / (name + ".py")).write_text(files[name + ".py"])
    destination = REMOTE + "/" + folder.name + "/plugins"
    writer = "import json,sys;from pathlib import Path\nr=Path(sys.argv[1])\nfor n,s in json.load(sys.stdin).items():\n p=r/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)"
    parallel(lambda r: remote(r, ["python3", "-c", writer, destination], json.dumps(files)))
    documents = copy.deepcopy(selected["specs"])
    specs = []
    for rank, doc in enumerate(documents):
        doc["name"] = f"ds41-research-{variant}-r{rank}"
        doc["labels"] = {"io.local.deepseek-research": variant, "io.local.rank": str(rank)}
        # These campaign variants replace the selected local plugin bundle.
        # Do not inherit another experiment's dispatch flags after promotion.
        for name in ("DSV41_INDEXER_ARM_ON_REQUEST", "DSV41_QUERY_MIN_ROWS",
                     "DSV41_QUERY_LOCAL_GUARD", "DSV41_QUERY_VALUE_GUARD", "DSV41_INDEXER_GUARD",
                     "DSV41_RETAIN_OWNED_RESIDUALS", "DSV41_MARKOV_SHORTLIST", "B12X_DISK_TABLE_BUFFERED_IO"):
            doc["environment"].pop(name, None)
        doc["environment"]["VLLM_PLUGINS"] = "b12x_loader,sparkring_status," + ",".join(active_plugins)
        if variant.startswith("engram-"):
            doc["environment"]["B12X_DISK_TABLE_BUFFERED_IO"] = "1"
        if variant.startswith("context-indexer-local"):
            doc["environment"]["DSV41_INDEXER_GUARD"] = "local-scores"
        if variant.startswith("query-indexer-"):
            doc["environment"]["DSV41_QUERY_LOCAL_GUARD"] = "1"
        if variant.startswith("query-indexer-values"):
            doc["environment"]["DSV41_QUERY_VALUE_GUARD"] = "1"
        if variant.endswith("-auto"):
            doc["environment"]["DSV41_INDEXER_ARM_ON_REQUEST"] = "1"
        if variant == "query-indexer-values-auto":
            doc["environment"]["DSV41_QUERY_MIN_ROWS"] = "128"
        if variant == "owned-residual":
            doc["environment"]["DSV41_RETAIN_OWNED_RESIDUALS"] = "1"
        if variant == "markov-shortlist128":
            doc["environment"]["DSV41_MARKOV_SHORTLIST"] = "128"
        doc["security_opt"] = ["seccomp=" + destination + "/loader-seccomp.json"]
        for mount in doc["mounts"]:
            if mount["target"] == "/opt/dsv41-local-plugins":
                mount["source"] = destination
        fields = dict(doc)
        fields["mounts"] = tuple(Bind(**m) for m in fields["mounts"])
        for key in ("entrypoint", "command", "devices", "cap_add", "security_opt", "health_command"):
            fields[key] = tuple(fields[key])
        specs.append(ContainerSpec(**fields))
    (folder / "specs.json").write_text(json.dumps(documents, indent=2))
    stop()
    remote(0, ["sudo", "-n", "/usr/local/sbin/deepseek-ring-control", "down"])
    for rank in range(4):
        if remote(rank, ["docker", "ps", "-q"]).stdout.strip():
            raise RuntimeError(f"Rank {rank} is not idle; refusing trial startup")
    (RESULTS / "active.json").write_text(json.dumps({"variant": variant, "folder": str(folder), "names": [s.name for s in specs]}, indent=2))
    parallel(lambda r: remote(r, docker_create(specs[r])))
    parallel(lambda r: remote(r, ["docker", "start", specs[r].name]))
    print("STARTED", variant, folder, flush=True)
    deadline = time.monotonic() + 2400
    while time.monotonic() < deadline:
        states = parallel(lambda r: remote(r, ["docker", "inspect", "--format", "{{.State.Status}}", specs[r].name]).stdout.strip())
        if any(s != "running" for s in states):
            raise RuntimeError(f"Trial startup stopped: {states}; use stop to preserve logs")
        health = remote(0, ["curl", "-fsS", "--max-time", "3", "http://127.0.0.1:8015/health"], check=False)
        if health.returncode == 0:
            if variant in ("context-indexer", "context-indexer-local", "owned-mhc", "owned-residual", "query-indexer-local", "query-indexer-values"):
                flag_name = "context-indexer" if variant.startswith("context-indexer") else variant
                if variant.startswith("query-indexer-"):
                    flag_name = "indexer-tp"
                if variant == "owned-residual":
                    flag_name = "owned-mhc"
                parallel(lambda r: remote(r, ["touch", destination + "/" + flag_name + ".enabled"]))
            print("READY", variant, flush=True)
            return
        log = remote(0, ["docker", "logs", "--tail", "100", specs[0].name], check=False)
        if any(s in log.stdout + log.stderr for s in ("Engine core initialization failed", "CUDA out of memory", "b12x preparation failed on rank")):
            raise RuntimeError("Trial initialization failed; stop to retain logs")
        time.sleep(10)
    raise TimeoutError("Trial startup timeout")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=[*VARIANTS, "stop", "restore"])
    args = parser.parse_args()
    if args.variant in ("stop", "restore"):
        stop()
        if args.variant == "restore":
            print(remote(0, ["sudo", "-n", "/usr/local/sbin/deepseek-ring-control", "up"]).stdout)
    else:
        start(args.variant)
