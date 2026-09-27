#!/usr/bin/env python3
"""Emit /etc/netplan/41-dsv41-ring.yaml for each rank of the four-node switchless ring.

TP rank order follows the cabling: rank i's f0 port is cabled to rank (i+1)'s f1 port.
Cable i uses 10.10.i.0/24 on the first PCIe domain (enp1s0f*) and 10.11.i.0/24 on the
second (enP2p1s0f*); .10 is rank i's f0 end, .11 is rank (i+1)'s f1 end.
"""
import sys
from pathlib import Path

RANKS = ["spark-r0", "spark-r1", "gx10-r1", "gx10-r0"]
PLANES = {"10.10": ("enp1s0f0np0", "enp1s0f1np1"), "10.11": ("enP2p1s0f0np0", "enP2p1s0f1np1")}


def iface(name, addr, route_to, via):
    return (f"    {name}:\n      addresses: [{addr}/24]\n      dhcp4: false\n      dhcp6: false\n"
            f"      link-local: [ipv6]\n      mtu: 9000\n      optional: true\n"
            f"      routes:\n      - to: {route_to}/24\n        via: {via}\n")


def render(i):
    n = len(RANKS)
    out = ["# Managed by dsv41-ring (gen_netplan.py). Rank %d of %s.\n" % (i, " -> ".join(RANKS)),
           "network:\n  version: 2\n  renderer: NetworkManager\n  ethernets:\n"]
    for net, (f0, f1) in PLANES.items():
        nxt, prv, opp = i, (i - 1) % n, (i - 2) % n
        # f0: this rank is the .10 end of cable i; cable i+1 is one hop further via rank i+1
        out.append(iface(f0, f"{net}.{nxt}.10", f"{net}.{(i + 1) % n}.0", f"{net}.{nxt}.11"))
        # f1: this rank is the .11 end of cable i-1; cable i-2 is one hop further via rank i-1
        out.append(iface(f1, f"{net}.{prv}.11", f"{net}.{opp}.0", f"{net}.{prv}.10"))
    return "".join(out)


if __name__ == "__main__":
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    for i, host in enumerate(RANKS):
        (outdir / f"41-dsv41-ring.{host}.yaml").write_text(render(i))
