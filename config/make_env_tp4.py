#!/usr/bin/env python3
"""Write .env.tp4 for this four-node switchless ring from Mia's .env.tp4.example.

  config/make_env_tp4.py <mia-checkout>/.env.tp4.example <out> [ring-mesh env.txt]

Every knob not listed here keeps the value Mia measured. The ring-mesh line comes from
scripts/ring_mesh/plan.py (peer maps depend on cabling and rank order); without it the
production line runs RoCEnante off and all collectives on the patched NCCL.
"""
import re
import sys
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
mesh = Path(sys.argv[3]).read_text().split() if len(sys.argv) > 3 else None

# The v2.1 production EXTRA_CONTAINER_ENV is the last commented EXTRA_CONTAINER_ENV line.
prod = [l for l in src.read_text().splitlines() if l.startswith('#EXTRA_CONTAINER_ENV="DSV41_INDEXER_CHUNKED=1')][-1]
env = dict(kv.split("=", 1) for kv in prod[len('#EXTRA_CONTAINER_ENV="'):-1].split())
# Both CX7 planes on the ring (sparkring dual-PCI-domain NCCL): publish four listener GIDs and
# keep substitution inside a PCI root. docs/switchless-ring.md "Raising the cap".
env.update(NCCL_IB_EXTENDED_IPV4_GIDS="1", NCCL_IB_PRESERVE_PCI_DOMAIN="1",
           NCCL_IB_ROUTE_DIAGNOSTICS="1", NCCL_IB_QPS_PER_CONNECTION="1")
if mesh:
    env.update(kv.split("=", 1) for kv in mesh)
else:  # no opposite-node path: RoCEnante cannot reach rank i+2
    env["SGLANG_ROCE_ALLREDUCE"] = "0"
    for k in ("DSV41_ROCE_GATHER", "SGLANG_ROCE_MAX_SIZE"):
        env.pop(k, None)
    env["B12X_ROCE_HCA"] = "rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1"

SET = {
    "HEAD_IP": "192.168.50.219",                      # spark-r0, TP rank 0 (LAN)
    "WORKER_IPS": '"192.168.50.129 192.168.50.192 192.168.50.23"',
    "WORKER_HOSTS": '"spark-r1 gx10-r1 gx10-r0"',     # ranks 1..3 in ring order
    "WORKER_USER": "nero",
    "SSH_IDENTITY": "$HOME/.ssh/id_ed25519_ring",
    "FABRIC_IFACE": "enp1s0f0np0",
    "IB_HCA": "rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1",
    "NCCL_MAX_NCHANNELS": "4",
    "NFS_SHARE": "0",                                 # full local copy on every rank
    "NFS_VOLUME": "dsv41-local-weights",
    "NFS_SERVER_IPS": '""',
    "NFS_CLIENTS": '""',
    "EP_SIZE": "1",
    "IMAGE": "dsv41-4x-spark:canary-roce-ring",  # image/Dockerfile.ring over canary-roce
    "WORKER_DIR": "/home/$WORKER_USER/dsv41-4x-spark",
    "EXTRA_CONTAINER_ENV": '"' + " ".join(f"{k}={v}" for k, v in env.items()) + '"',
}
RING = {  # the ring block of the example, uncommented
    "NCCL_SWITCHLESS_RING_ONLY": "1", "NCCL_ALGO": "Ring", "NCCL_IB_SUBNET_PREFIX_LEN": "24",
    "NCCL_MIN_NCHANNELS": "4", "NCCL_P2P_LEVEL": "SYS", "NCCL_IB_GID_INDEX": "3",
    "BUILD_DOCKERFILE": "Dockerfile.canary-roce",
}
lines, seen = [], set()
for line in src.read_text().splitlines():
    m = re.match(r"^([A-Z0-9_]+)=", line)
    if m and m.group(1) in SET:
        k = m.group(1)
        if k in seen:
            continue
        seen.add(k)
        line = f"{k}={SET[k]}"
    lines.append(line)
missing = set(SET) - seen
lines.append("\n# ─── this fleet: switchless ring spark-r0 -> spark-r1 -> gx10-r1 -> gx10-r0 ─────")
lines += [f"{k}={v}" for k, v in RING.items()] + [f"{k}={SET[k]}" for k in sorted(missing)]
out.write_text("\n".join(lines) + "\n")
print(f"wrote {out}: {len(env)} container env vars, mesh={'yes' if mesh else 'no'}, appended {sorted(missing) + list(RING)}")
