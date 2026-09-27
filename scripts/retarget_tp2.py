#!/usr/bin/env python3
"""Point a qwen-tp2 cluster-config.json at the pair's ring cable.

  retarget_tp2.py <cluster-config.json> spark|gx10

On the ring each pair shares exactly one DAC, so cable modes 1 and 2 both select that
cable's two HCAs (one per PCIe root). peer_ssh uses the LAN host alias.
"""
import json, sys
from pathlib import Path

F0 = [{"interface": "enp1s0f0np0", "hca": "rocep1s0f0"}, {"interface": "enP2p1s0f0np0", "hca": "roceP2p1s0f0"}]
F1 = [{"interface": "enp1s0f1np1", "hca": "rocep1s0f1"}, {"interface": "enP2p1s0f1np1", "hca": "roceP2p1s0f1"}]
PAIRS = {  # rank0, rank1: (ssh, ip, rails). Cable 0: spark-r0 f0 <-> spark-r1 f1; cable 2: gx10-r1 f0 <-> gx10-r0 f1.
    "spark": [("spark-r0", "10.10.0.10", F0), ("spark-r1", "10.10.0.11", F1)],
    "gx10": [("gx10-r0", "10.10.2.11", F1), ("gx10-r1", "10.10.2.10", F0)],
}
path, pair = Path(sys.argv[1]), sys.argv[2]
cfg = json.loads(path.read_text())
for rank, (host, ip, rails) in zip(cfg["ranks"], PAIRS[pair]):
    assert rank["ssh"] == host, (rank["ssh"], host)
    rank.update(ip=ip, socket_interface=rails[0]["interface"], peer_ssh=host,
                cables={"1": rails, "2": rails})
cfg["default_cables"] = 1
path.write_text(json.dumps(cfg, indent=2) + "\n")
print(pair, [(r["ssh"], r["ip"], r["socket_interface"]) for r in cfg["ranks"]])
