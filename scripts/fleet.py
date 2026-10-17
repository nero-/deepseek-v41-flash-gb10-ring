"""Workstation SSH helpers for read-only inspection and benchmark orchestration."""
import concurrent.futures
import shlex
import subprocess

HOSTS = ("192.168.50.219", "192.168.50.129", "192.168.50.192", "192.168.50.23")
ALIASES = ("spark-r0", "spark-r1", "gx10-r1", "gx10-r0")


def remote(rank, command, data=None, check=True):
    result = subprocess.run([
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-o", "HostName=" + HOSTS[rank], "-o", "ProxyCommand=none",
        ALIASES[rank], shlex.join(command),
    ], input=data, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(f"Rank {rank} {command[:3]} failed: {result.stderr[-2000:]}")
    return result


def parallel(fn):
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        return list(pool.map(fn, range(4)))
