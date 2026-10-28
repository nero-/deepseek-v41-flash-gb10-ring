#!/usr/bin/python3
"""Restore a switched rail's IPv4 RoCEv2 GID to index 3.

After a switch-side link drop the address can re-register at GID 4 and leave
index 3 empty; the running engine then fails with RDMA retry errors and the
switched gate refuses to start. Bouncing the rail's netplan NetworkManager
profile re-registers it in order. Only rails whose GID 3 is wrong are bounced.
Run as root on one rank with the fleet stopped; `check` changes nothing.
"""
import ipaddress
import json
from pathlib import Path
import subprocess
import sys
import time

HCAS = {
    "enp1s0f1np1": "rocep1s0f1",
    "enP2p1s0f1np1": "roceP2p1s0f1",
}


def gid3_ok(iface, hca, address):
    port = Path("/sys/class/infiniband") / hca / "ports/1"
    try:
        mapped = ipaddress.IPv6Address((port / "gids/3").read_text().strip()).ipv4_mapped
        return ("ACTIVE" in (port / "state").read_text() and mapped == address
                and (port / "gid_attrs/types/3").read_text().strip() == "RoCE v2"
                and (port / "gid_attrs/ndevs/3").read_text().strip() == iface)
    except OSError:
        # An empty GID slot has no type or netdev and reads as EINVAL.
        return False


def bounce(rank, iface, hca, address):
    profile = subprocess.check_output(
        ["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", iface], text=True).strip()
    if profile != "netplan-" + iface:
        raise RuntimeError(f"Rank {rank}: {iface} is on profile {profile!r}, expected "
                           f"netplan-{iface}; check the cable and switch port")
    subprocess.run(["nmcli", "connection", "down", "id", profile], check=True, capture_output=True)
    subprocess.run(["nmcli", "connection", "up", "id", profile], check=True, capture_output=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if gid3_ok(iface, hca, address):
            return
        time.sleep(1)
    raise RuntimeError(f"Rank {rank}: GID 3 on {hca} is still wrong after bouncing {profile}")


def main(rank, fabric, repair):
    if fabric.get("type") != "switched-roce-v1" or fabric.get("gid_index") != 3:
        raise ValueError("Expected this fleet's switched fabric at GID 3")
    expected = fabric["ranks"][rank]
    if expected["rank"] != rank or set(expected["addresses"]) != set(HCAS):
        raise ValueError("Switched interface/rank mapping differs")
    rails = []
    for iface, hca in HCAS.items():
        address = ipaddress.IPv4Interface(expected["addresses"][iface]).ip
        if gid3_ok(iface, hca, address):
            state = "ok"
        elif repair:
            bounce(rank, iface, hca, address)
            state = "repaired"
        else:
            state = "wrong"
        rails.append({"interface": iface, "hca": hca, "gid3": state})
    return {"rank": rank, "rails": rails}


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[3] not in ("check", "repair"):
        raise SystemExit("fabric_repair.py RANK FABRIC_JSON check|repair")
    print(json.dumps(main(int(sys.argv[1]), json.loads(sys.argv[2]), sys.argv[3] == "repair")))
