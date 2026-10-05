#!/usr/bin/python3
"""Lifecycle for a separately recorded, qualified local SparkRing configuration.

Install root-owned under /usr/local/lib/deepseek-ring. The official installer
deployment and its receipts stay intact; this controller owns different names.
"""
import concurrent.futures as cf
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, "/usr/lib/sparkring")
from runtime.common.container_spec import Bind, ContainerSpec, docker_create, expected_inspection
from scripts.installer_runner import Runner

CONFIG = Path("/etc/deepseek-ring/optimized-specs.json")
DEPLOYMENT = Path("/var/lib/sparkring/controller/deployments/deepseek-v41-flash-tp4-iba1b36389e5d")
HOSTS = ("192.168.50.219", "192.168.50.129", "192.168.50.192", "192.168.50.23")
PLUGINS = "/usr/local/lib/deepseek-ring/plugins"


def remote(rank, argv):
    return subprocess.check_output(["/usr/bin/ssh", "-o", "BatchMode=yes",
        "root@" + HOSTS[rank], shlex.join(argv)], text=True)


def parallel(fn):
    with cf.ThreadPoolExecutor(4) as pool:
        return list(pool.map(fn, range(4)))


def verify_plugins(document):
    manifest = document.get("plugin_manifest", {})
    if not manifest:
        return
    code = """import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); manifest=json.loads(sys.argv[2])
for name,expected in manifest.items():
    relative=Path(name)
    if relative.is_absolute() or '..' in relative.parts: raise ValueError('Invalid plugin path')
    p=root/relative; stat=p.stat()
    if stat.st_uid != 0 or stat.st_mode & 0o022: raise RuntimeError('Plugin must be root-owned: '+name)
    if hashlib.sha256(p.read_bytes()).hexdigest() != expected: raise RuntimeError('Plugin hash differs: '+name)
print('Plugin manifest verified')
"""
    parallel(lambda rank: remote(rank, ["python3", "-c", code, PLUGINS, json.dumps(manifest)]))


def specifications():
    stat = CONFIG.stat()
    if stat.st_uid != 0 or stat.st_mode & 0o022:
        raise RuntimeError("Selected configuration must be root-owned and not writable by others")
    document = json.loads(CONFIG.read_text())
    if len(document["specs"]) != 4:
        raise ValueError("Expected four rank specifications")
    specs = []
    for rank, raw in enumerate(document["specs"]):
        fields = dict(raw)
        if fields["name"] != f"ds41-optimized-r{rank}":
            raise ValueError("Unexpected optimized container name")
        fields["mounts"] = tuple(Bind(**m) for m in fields["mounts"])
        for key in ("entrypoint", "command", "devices", "cap_add", "security_opt", "health_command"):
            fields[key] = tuple(fields[key])
        specs.append(ContainerSpec(**fields))
    return document, specs


def inspect(rank, spec):
    names = remote(rank, ["docker", "ps", "-a", "--format", "{{.Names}}"] ).splitlines()
    if spec.name not in names:
        return None
    info = json.loads(remote(rank, ["docker", "inspect", spec.name]))[0]
    image = json.loads(remote(rank, ["docker", "image", "inspect", spec.image_id]))[0]
    expected = expected_inspection(spec, image)
    config = info["Config"]
    env = dict(item.split("=", 1) for item in config["Env"])
    mounts = {m["Destination"]: {k: m[k] for k in ("Source", "Type", "RW")} for m in info["Mounts"]}
    actual_argv = (config["Entrypoint"] or []) + (config["Cmd"] or [])
    expected_argv = list(expected["entrypoint"]) + list(expected["cmd"])
    if (info["Image"] != spec.image_id or actual_argv != expected_argv or env != expected["env"]
            or mounts != expected["mounts"] or info["HostConfig"]["Privileged"]
            or any(config["Labels"].get(k) != v for k, v in spec.labels.items())):
        raise RuntimeError(f"Rank {rank}: existing optimized container differs from its recorded configuration")
    return info


def ensure_gpu_cdi():
    # Match SparkRing's host prerequisite: enable refresh across reboots and
    # require CDI before Docker starts a model, while every rank is stopped.
    code = """import subprocess
unit='nvidia-cdi-refresh.service'
def run(args,check=True):return subprocess.run(args,text=True,capture_output=True,check=check)
if run(['systemctl','is-enabled',unit],False).stdout.strip()!='enabled':
    run(['systemctl','enable',unit])
if 'nvidia.com/gpu=all' not in run(['nvidia-ctk','cdi','list']).stdout.split():
    run(['systemctl','start',unit])
if 'nvidia.com/gpu=all' not in run(['nvidia-ctk','cdi','list']).stdout.split():
    raise RuntimeError('NVIDIA CDI refresh did not expose nvidia.com/gpu=all')
"""
    parallel(lambda rank: remote(rank, ['python3', '-c', code]))


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("up", "down", "status"):
        raise SystemExit("optimized_vllm.py up|down|status")
    action = sys.argv[1]
    if not CONFIG.exists() and action in ("down", "status"):
        return
    document, specs = specifications()
    states = parallel(lambda rank: inspect(rank, specs[rank]))
    if action == "status":
        print(json.dumps({"profile": document["profile"], "nodes": [
            {"host": h, "name": s.name, "state": info["State"] if info else "absent"}
            for h, s, info in zip(HOSTS, specs, states)]}, indent=2))
        return
    if action == "down":
        parallel(lambda r: remote(r, ["docker", "stop", "--time", "15", specs[r].name])
                 if states[r] and states[r]["State"]["Running"] else None)
        return
    verify_plugins(document)
    for rank, spec in enumerate(specs):
        running = remote(rank, ["docker", "ps", "--format", "{{.Names}}"] ).splitlines()
        if any(name != spec.name for name in running):
            raise RuntimeError(f"Rank {rank}: stop the existing workload before starting DeepSeek: {running}")
    if any(s and s["State"]["Running"] for s in states):
        if all(s and s["State"]["Running"] for s in states):
            with urllib.request.urlopen("http://127.0.0.1:8015/health", timeout=10):
                print("Optimized DeepSeek is already healthy")
                return
        raise RuntimeError("Partially running deployment; run down before restarting")
    ensure_gpu_cdi()
    runner = Runner(DEPLOYMENT)
    parallel(lambda rank: runner.remote(rank, "mesh-gate"))
    for rank, spec in enumerate(specs):
        if states[rank] is None:
            remote(rank, docker_create(spec))
    parallel(lambda rank: remote(rank, ["sh", "-c", "sync && sysctl -w vm.drop_caches=3 && sysctl -w vm.compact_memory=1"]))
    parallel(lambda rank: remote(rank, ["docker", "start", specs[rank].name]))
    deadline = time.monotonic() + 2400
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8015/health", timeout=5):
                print("Optimized DeepSeek ready: http://192.168.50.219:8015/v1")
                return
        except OSError:
            pass
        status = parallel(lambda r: remote(r, ["docker", "inspect", "--format", "{{.State.Status}}", specs[r].name]).strip())
        if any(s != "running" for s in status):
            raise RuntimeError(f"A rank stopped during startup: {status}; inspect Docker logs")
        recent = subprocess.run(["/usr/bin/ssh", "-o", "BatchMode=yes", "root@" + HOSTS[0],
            shlex.join(["docker", "logs", "--tail", "160", specs[0].name])], text=True, capture_output=True)
        if any(message in recent.stdout + recent.stderr for message in (
                "Engine core initialization failed", "b12x preparation failed on rank",
                "torch.OutOfMemoryError", "CUDA out of memory")):
            raise RuntimeError("Engine initialization failed; inspect Docker logs before restarting")
        time.sleep(10)
    raise TimeoutError("Model did not become ready; inspect Docker logs")


if __name__ == "__main__":
    main()
