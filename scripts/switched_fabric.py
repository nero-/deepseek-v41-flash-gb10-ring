#!/usr/bin/python3
"""Read-only preflight for this fleet's two-rail switched RoCE fabric."""
import ipaddress
import json
from pathlib import Path
import subprocess
import sys

HCAS = {
    "enp1s0f1np1": "rocep1s0f1",
    "enP2p1s0f1np1": "roceP2p1s0f1",
}
LEGACY_UNITS = (
    "sparkring-fabric.service", "sparkring-hairpin.service",
    "sparkring-agent.service",
    "sparkring-sparkring-deepseek-v41-flash-adaefa-mesh.service",
    "sparkring-sparkring-deepseek-v41-flash-adaefa-model.service",
)


def output(argv):
    return subprocess.check_output(argv, text=True).strip()


def check(rank, fabric):
    if fabric.get("type") != "switched-roce-v1" or len(fabric["ranks"]) != 4:
        raise ValueError("Expected this fleet's four-rank switched fabric")
    if not 0 <= rank < 4 or fabric.get("gid_index") != 3:
        raise ValueError("Unsupported rank or GID selection")
    expected = fabric["ranks"][rank]
    if expected["rank"] != rank or set(expected["addresses"]) != set(HCAS):
        raise ValueError("Switched interface/rank mapping differs")
    addresses = {item["ifname"]: item for item in json.loads(output(["ip", "-j", "addr"]))}
    checks = []
    for iface, hca in HCAS.items():
        cidr = ipaddress.IPv4Interface(expected["addresses"][iface])
        live = addresses[iface]
        observed = {f"{item['local']}/{item['prefixlen']}"
                    for item in live["addr_info"] if item["family"] == "inet"}
        if observed != {str(cidr)} or live["mtu"] != 9000 or live["operstate"] != "UP":
            raise RuntimeError(f"Rank {rank}: switched address/MTU/link differs on {iface}")
        net = Path("/sys/class/net") / iface
        if int((net / "speed").read_text()) != 200000:
            raise RuntimeError(f"Rank {rank}: {iface} is not a 200G link")
        port = Path("/sys/class/infiniband") / hca / "ports/1"
        if "ACTIVE" not in (port / "state").read_text():
            raise RuntimeError(f"Rank {rank}: RDMA port inactive: {hca}")
        gid = str(fabric["gid_index"])
        mapped = ipaddress.IPv6Address((port / "gids" / gid).read_text().strip()).ipv4_mapped
        if mapped != cidr.ip or (port / "gid_attrs/types" / gid).read_text().strip() != "RoCE v2":
            raise RuntimeError(f"Rank {rank}: IPv4 RoCEv2 GID differs on {hca}")
        if (port / "gid_attrs/ndevs" / gid).read_text().strip() != iface:
            raise RuntimeError(f"Rank {rank}: GID netdev differs on {hca}")
        for peer in fabric["ranks"]:
            if peer["rank"] == rank:
                continue
            destination = str(ipaddress.IPv4Interface(peer["addresses"][iface]).ip)
            route = json.loads(output(["ip", "-j", "route", "get", destination,
                                       "from", str(cidr.ip), "oif", iface]))[0]
            if route["dev"] != iface or "gateway" in route:
                raise RuntimeError(f"Rank {rank}: expected a direct switched route to {destination}")
            subprocess.run(
                ["ping", "-I", iface, "-M", "do", "-s", "8972", "-c", "1",
                 "-W", "2", destination], check=True, capture_output=True, text=True,
            )
        checks.append({"interface": iface, "hca": hca, "address": str(cidr),
                       "gid_index": 3, "mtu": 9000, "speed_mbps": 200000})
    for iface in ("enp1s0f0np0", "enP2p1s0f0np0"):
        if any(item["family"] == "inet" for item in addresses[iface]["addr_info"]):
            raise RuntimeError(f"Rank {rank}: unused port still has IPv4 addressing: {iface}")
    for unit in LEGACY_UNITS:
        active = subprocess.run(["systemctl", "is-active", unit], text=True, capture_output=True)
        enabled = subprocess.run(["systemctl", "is-enabled", unit], text=True, capture_output=True)
        if active.stdout.strip() not in ("inactive", "failed", "unknown"):
            raise RuntimeError(f"Rank {rank}: legacy unit is active: {unit}")
        if enabled.stdout.strip() not in ("disabled", "masked", "not-found"):
            raise RuntimeError(f"Rank {rank}: legacy unit can auto-start: {unit}")
    if output(["systemctl", "is-active", "gb10-gpu-clock-cap.service"]) != "active":
        raise RuntimeError(f"Rank {rank}: clock-cap service is inactive")
    return {"rank": rank, "passed": True, "rails": checks}


if __name__ == "__main__":
    print(json.dumps(check(int(sys.argv[1]), json.loads(sys.argv[2]))))
