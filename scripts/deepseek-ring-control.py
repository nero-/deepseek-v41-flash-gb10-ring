#!/usr/bin/python3
"""Root-owned, fixed-action lifecycle helper for this four-node ring.

Install on spark-r0 as /usr/local/sbin/deepseek-ring-control, owned by root.
The controller's existing SSH configuration pins the four host identities.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

HOSTS = ("192.168.50.219", "192.168.50.129", "192.168.50.192", "192.168.50.23")
MESH = "sparkring-sparkring-deepseek-v41-flash-adaefa-mesh.service"
OPTIMIZED = "/usr/local/lib/deepseek-ring/optimized_vllm.py"
FABRIC_REPAIR = Path("/usr/local/lib/deepseek-ring/fabric_repair.py")
SELECTED = Path("/etc/deepseek-ring/optimized-specs.json")


def optimized(action):
    if SELECTED.exists():
        subprocess.run(["/usr/bin/python3", OPTIMIZED, action], check=True)


def fleet(*arguments):
    def one(host):
        subprocess.run(["/usr/bin/ssh", "-o", "BatchMode=yes", "root@" + host,
                        "/usr/bin/systemctl", *arguments], check=True)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        list(pool.map(one, HOSTS))


def fabric_gid(fabric, mode):
    """Check, or with the fleet stopped repair, GID 3 on every switched rail."""
    def remote(rank, argv):
        return subprocess.run(["/usr/bin/ssh", "-o", "BatchMode=yes", "root@" + HOSTS[rank],
                               shlex.join(argv)], check=True, stdout=subprocess.PIPE, text=True).stdout
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        if mode == "repair":
            # Containers (vLLM) or native FLARE ranks both hold RDMA connections.
            running = list(pool.map(lambda rank: remote(rank, [
                "sh", "-c", "docker ps -q; pgrep -f 'flare run' || true"]).split(), range(4)))
            busy = [HOSTS[rank] for rank in range(4) if running[rank]]
            if busy:
                raise SystemExit(f"Stop the workload before repairing the fabric; it runs on {busy}")
        code = FABRIC_REPAIR.read_text()
        results = list(pool.map(lambda rank: json.loads(remote(rank, [
            "python3", "-c", code, str(rank), json.dumps(fabric), mode])), range(4)))
    print(json.dumps({"fabric_gid3": results}), flush=True)
    if any(rail["gid3"] == "wrong" for result in results for rail in result["rails"]):
        raise SystemExit("GID 3 is wrong on a switched rail; run fabric-repair with the fleet stopped")


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise SystemExit("Use sudo deepseek-ring-control up|stock-up|down|mesh-off|status|fabric-check|fabric-repair")
    action = sys.argv[1]
    if action in ("up", "stock-up"):
        raise SystemExit("vLLM serving is retired: FLARE (Orbit group ds41-flare) serves this fleet and the "
                         "GX10 1017 checkpoints were removed on 2026-10-27. Use ./cluster.sh up; see OPERATIONS.md.")
    os.environ["PATH"] = "/usr/sbin:/usr/bin:/sbin:/bin"
    os.chdir("/root")
    switched = False
    if SELECTED.exists():
        state = SELECTED.stat()
        if state.st_uid != 0 or state.st_mode & 0o022:
            raise RuntimeError("Selected configuration must be root-owned and protected")
        fabric = json.loads(SELECTED.read_text()).get("fabric")
        if fabric is not None:
            if fabric.get("type") != "switched-roce-v1":
                raise RuntimeError("Unknown selected fabric")
            switched = True
    if action == "up":
        if switched:
            optimized("up")
        elif SELECTED.exists():
            subprocess.run(["/usr/bin/sparkring", "down", "--execute"], check=True)
            fleet("enable", "--now", MESH)
            optimized("up")
        else:
            fleet("enable", "--now", MESH)
            subprocess.run(["/usr/bin/sparkring", "up", "--execute"], check=True)
    elif action == "stock-up":
        if switched:
            raise SystemExit("The stock installer uses the retired physical ring; it cannot run on this switch.")
        optimized("down")
        fleet("enable", "--now", MESH)
        subprocess.run(["/usr/bin/sparkring", "up", "--execute"], check=True)
    elif action == "down":
        optimized("down")
        if not switched:
            subprocess.run(["/usr/bin/sparkring", "down", "--execute"], check=True)
    elif action == "mesh-off":
        fleet("disable", "--now", MESH)
    elif action == "status":
        optimized("status")
        if switched:
            print("Fabric: switched RoCE; legacy ring mesh stays disabled.")
        else:
            subprocess.run(["/usr/bin/sparkring", "status", "--refresh"], check=True)
    elif action in ("fabric-check", "fabric-repair"):
        if not switched:
            raise SystemExit("GID 3 repair applies only to the switched fabric selection")
        fabric_gid(json.loads(SELECTED.read_text())["fabric"], action.removeprefix("fabric-"))
    else:
        raise SystemExit("Unknown action")


if __name__ == "__main__":
    main()
