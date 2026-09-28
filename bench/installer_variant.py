#!/usr/bin/env python3
"""Run bounded, reversible variants of the installed SparkRing container spec.

Run with sudo on spark-r0 after the installer has completed. Original containers,
package files and deployment specifications are retained. Trial containers omit
the installer's runtime identity binding and are explicitly labeled as trials.
"""
import argparse
import concurrent.futures as cf
import copy
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, "/usr/lib/sparkring")
from runtime.common.container_spec import Bind, ContainerSpec, docker_create

HOSTS = ["192.168.50.219", "192.168.50.129", "192.168.50.192", "192.168.50.23"]
DEPLOYMENT = Path("/var/lib/sparkring/controller/deployments/deepseek-v41-flash-tp4-iba1b36389e5d")
EVIDENCE = Path("/home/nero/sparkring-migration-20260927/variants")


def remote(rank, argv, *, check=True):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", f"root@{HOSTS[rank]}", shlex.join(argv)],
                          text=True, capture_output=True, check=check)


def parallel(fn):
    with cf.ThreadPoolExecutor(4) as pool:
        return list(pool.map(fn, range(4)))


def stop_trials():
    state = EVIDENCE / "active.json"
    if not state.exists():
        return
    active = json.loads(state.read_text())
    folder = Path(active["evidence"])
    def stop(rank):
        name = active["names"][rank]
        if not name.startswith("ds41-trial-") or not name.endswith(f"-r{rank}"):
            raise ValueError("Refusing an unexpected container name")
        remote(rank, ["docker", "stop", "--time", "15", name], check=False)
        logs = remote(rank, ["docker", "logs", name], check=False)
        (folder / f"rank{rank}.log").write_text(logs.stdout + logs.stderr)
        remote(rank, ["docker", "rm", name], check=False)
    parallel(stop)
    state.unlink()


def modify(doc, variant):
    cmd = doc["command"]
    def argument(flag, update):
        index = cmd.index(flag) + 1
        cmd[index] = update(cmd[index])
    if variant == "engram-adaptive4k-graphs":
        modify(doc, "engram-adaptive4k")
        modify(doc, "graphs")
        return doc
    plugins = {"engram-qkv-split": "dsv41_decode_split", "engram-indexer-tp": "dsv41_indexer_tp",
               "engram-adaptive4k": "dsv41_adaptive_prefill", "engram-top20": "dsv41_draft_topk"}
    if variant in plugins:
        modify(doc, "engram-tp")
        path = "/opt/dsv41-local-plugins"
        plugin = plugins[variant]
        doc["environment"]["PYTHONPATH"] = path + ":" + doc["environment"].get("PYTHONPATH", "")
        doc["environment"]["VLLM_PLUGINS"] = doc["environment"].get("VLLM_PLUGINS", "") + "," + plugin
        doc["mounts"].append({"source": "/home/nero/sparkring-migration-20260927/vllm-local-plugins", "target": path, "read_only": True})
        return doc
    if variant in ("engram-cost075", "engram-cost125"):
        modify(doc, "engram-tp")
        modify(doc, variant.removeprefix("engram-"))
        return doc
    if variant == "engram-fair4k":
        modify(doc, "engram-tp")
        cmd.extend(["--prefill-compute-share", "auto", "--prefill-compute-half-life", "responsive",
                    "--max-num-prefill-tokens-per-step", "4096"])
        return doc
    if variant == "engram16k":
        modify(doc, "engram-tp")
        argument("--max-num-batched-tokens", lambda _: "16384")
        return doc
    if variant in ("engram-graphs", "engram16k-graphs"):
        modify(doc, "engram16k" if variant == "engram16k-graphs" else "engram-tp")
        modify(doc, "graphs")
        return doc
    if variant in ("engram-tp", "engram-deterministic"):
        argument("--engram-config", lambda s: json.dumps({**json.loads(s), "projection_tp": True}))
        if variant == "engram-deterministic":
            doc["environment"]["B12X_DYNAMIC_DETERMINISTIC_OUTPUT"] = "1"
    elif variant == "deterministic":
        doc["environment"]["B12X_DYNAMIC_DETERMINISTIC_OUTPUT"] = "1"
    elif variant == "graphs":
        def graphs(s):
            config = json.loads(s)
            config["cudagraph_capture_sizes"] = sorted(set(config["cudagraph_capture_sizes"]) | set(range(1, 33)))
            return json.dumps(config)
        argument("--compilation-config", graphs)
    elif variant in ("cost075", "cost125"):
        argument("--speculative-config", lambda s: json.dumps({**json.loads(s),
                 "adaptive_verification_cost_scale": .75 if variant == "cost075" else 1.25}))
    elif variant == "prefill4k":
        argument("--max-num-batched-tokens", lambda _: "4096")
    elif variant == "prefill16k":
        argument("--max-num-batched-tokens", lambda _: "16384")
    elif variant == "threads1":
        doc["environment"]["OMP_NUM_THREADS"] = "1"
        doc["environment"]["MKL_NUM_THREADS"] = "1"
    elif variant != "baseline":
        raise ValueError(variant)
    return doc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("variant", choices=["engram-adaptive4k-graphs", "engram-top20", "baseline", "engram-tp", "engram16k", "engram-qkv-split", "engram-indexer-tp", "engram-adaptive4k", "engram-graphs", "engram-fair4k", "engram-cost075", "engram-cost125", "engram16k-graphs", "engram-deterministic", "deterministic", "graphs", "cost075", "cost125", "prefill4k", "prefill16k", "threads1", "stop"])
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if args.variant == "stop":
        if not args.plan:
            stop_trials()
        return
    documents = []
    for rank in range(4):
        doc = modify(copy.deepcopy(json.loads((DEPLOYMENT / f"rank{rank}/container.json").read_text())), args.variant)
        doc["name"] = f"ds41-trial-{args.variant}-r{rank}"
        doc["labels"] = {"io.local.deepseek-trial": args.variant, "io.local.rank": str(rank)}
        doc["environment"].pop("SPARKRING_RUNTIME_BINDING", None)
        doc["mounts"] = [m for m in doc["mounts"] if m["target"] != "/run/sparkring/runtime-binding.json"]
        documents.append(doc)
    specs = []
    for doc in documents:
        fields = dict(doc)
        fields["mounts"] = tuple(Bind(**m) for m in fields["mounts"])
        for field in ("entrypoint", "command", "devices", "cap_add", "security_opt", "health_command"):
            fields[field] = tuple(fields[field])
        specs.append(ContainerSpec(**fields))
    if args.plan:
        print(json.dumps(documents, indent=2))
        return
    plugin_hashes = None
    plugins = {"engram-qkv-split": "dsv41_decode_split.py", "engram-indexer-tp": "dsv41_indexer_tp.py",
               "engram-adaptive4k": "dsv41_adaptive_prefill.py", "engram-adaptive4k-graphs": "dsv41_adaptive_prefill.py",
               "engram-top20": "dsv41_draft_topk.py"}
    if args.variant in plugins:
        plugin_file = plugins[args.variant]
        plugin_hashes = parallel(lambda rank: remote(rank, ["sha256sum",
            "/home/nero/sparkring-migration-20260927/vllm-local-plugins/" + plugin_file]).stdout.split()[0])
        if len(set(plugin_hashes)) != 1:
            raise RuntimeError("Local plugin differs across ranks")
    subprocess.run(["/usr/bin/sparkring", "down", "--execute"], check=True)
    stop_trials()
    # Confirm every node is free of serving containers before memory reclamation.
    for rank in range(4):
        running = remote(rank, ["docker", "ps", "--format", "{{.Names}}"] ).stdout.strip()
        if running:
            raise RuntimeError(f"Rank {rank} has running containers: {running}")
    folder = EVIDENCE / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + args.variant)
    folder.mkdir()
    (folder / "specs.json").write_text(json.dumps(documents, indent=2))
    if plugin_hashes:
        (folder / "plugin-sha256.json").write_text(json.dumps(plugin_hashes, indent=2))
        (folder / plugin_file).write_text(Path(
            "/home/nero/sparkring-migration-20260927/vllm-local-plugins/" + plugin_file).read_text())
    (EVIDENCE / "active.json").write_text(json.dumps({"names": [s.name for s in specs], "evidence": str(folder)}))
    for rank, spec in enumerate(specs):
        remote(rank, docker_create(spec))
    if args.variant == "engram-indexer-tp":
        parallel(lambda rank: remote(rank, ["rm", "-f", "/home/nero/sparkring-migration-20260927/vllm-local-plugins/indexer-tp.enabled"]))
    parallel(lambda rank: remote(rank, ["sh", "-c", "sync && sysctl -w vm.drop_caches=3 && sysctl -w vm.compact_memory=1"]))
    parallel(lambda rank: remote(rank, ["docker", "start", specs[rank].name]))
    deadline = time.monotonic() + 2400
    while time.monotonic() < deadline:
        for rank, spec in enumerate(specs):
            status = remote(rank, ["docker", "inspect", "--format", "{{.State.Status}}", spec.name]).stdout.strip()
            if status != "running":
                print(f"Rank {rank} stopped; preserving logs in {folder}", flush=True)
                stop_trials()
                raise RuntimeError(f"Rank {rank}: {status}")
        try:
            with urllib.request.urlopen("http://127.0.0.1:8015/health", timeout=5) as response:
                if response.status == 200:
                    if args.variant == "engram-indexer-tp":
                        parallel(lambda rank: remote(rank, ["touch", "/home/nero/sparkring-migration-20260927/vllm-local-plugins/indexer-tp.enabled"]))
                    print(f"READY {args.variant} {folder}", flush=True)
                    return
        except OSError:
            pass
        recent = remote(0, ["docker", "logs", "--tail", "160", specs[0].name], check=False)
        combined = recent.stdout + recent.stderr
        if any(message in combined for message in (
                "Engine core initialization failed", "b12x preparation failed on rank",
                "torch.OutOfMemoryError", "CUDA out of memory")):
            stop_trials()
            raise RuntimeError(f"Trial startup failed; logs preserved in {folder}")
        time.sleep(10)
    stop_trials()
    raise TimeoutError("Trial did not become ready")


if __name__ == "__main__":
    main()
