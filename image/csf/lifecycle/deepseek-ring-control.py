#!/usr/bin/python3
"""Root-owned, fixed-action lifecycle helper for this four-node ring.

Install on spark-r0 as /usr/local/sbin/deepseek-ring-control, owned by root.
The controller's existing SSH configuration pins the four host identities.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys

HOSTS = ("192.168.50.219", "192.168.50.129", "192.168.50.192", "192.168.50.23")
MESH = "sparkring-sparkring-deepseek-v41-flash-adaefa-mesh.service"
OPTIMIZED = "/usr/local/lib/deepseek-ring/optimized_vllm.py"
SELECTED = Path("/etc/deepseek-ring/optimized-specs.json")


def optimized(action):
    if SELECTED.exists():
        subprocess.run(["/usr/bin/python3", OPTIMIZED, action], check=True)


def stock_retired():
    return SELECTED.exists() and json.loads(SELECTED.read_text()).get("stock_checkpoint_retired", False)


def fleet(*arguments):
    def one(host):
        subprocess.run(["/usr/bin/ssh", "-o", "BatchMode=yes", "root@" + host,
                        "/usr/bin/systemctl", *arguments], check=True)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        list(pool.map(one, HOSTS))


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise SystemExit("Use sudo deepseek-ring-control up|stock-up|down|mesh-off|status")
    action = sys.argv[1]
    os.environ["PATH"] = "/usr/sbin:/usr/bin:/sbin:/bin"
    os.chdir("/root")
    if action == "up":
        if SELECTED.exists():
            if not stock_retired():
                subprocess.run(["/usr/bin/sparkring", "down", "--execute"], check=True)
            fleet("enable", "--now", MESH)
            optimized("up")
        else:
            fleet("enable", "--now", MESH)
            subprocess.run(["/usr/bin/sparkring", "up", "--execute"], check=True)
    elif action == "stock-up":
        if stock_retired():
            raise SystemExit("The original checkpoint was retired after the CSF upgrade. Use deepseek-ring-control up.")
        optimized("down")
        fleet("enable", "--now", MESH)
        subprocess.run(["/usr/bin/sparkring", "up", "--execute"], check=True)
    elif action == "down":
        optimized("down")
        if not stock_retired():
            subprocess.run(["/usr/bin/sparkring", "down", "--execute"], check=True)
    elif action == "mesh-off":
        fleet("disable", "--now", MESH)
    elif action == "status":
        optimized("status")
        if stock_retired():
            print("Original stock checkpoint retired; selected CSF deployment shown above.")
        else:
            subprocess.run(["/usr/bin/sparkring", "status", "--refresh"], check=True)
    else:
        raise SystemExit("Unknown action")


if __name__ == "__main__":
    main()
