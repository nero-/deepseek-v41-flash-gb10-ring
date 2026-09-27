# Results

All measurements on this fleet: 2× DGX Spark + 2× ASUS Ascent GX10 (GB10, 121.7 GiB unified
memory each), DGX OS 7.2.3 / OTA 7.5–7.6, kernel `7.0.0-1019-nvidia`, driver 580.178.04,
Docker 29.6.2. Dates are UTC.

## Fabric (2026-09-27)

Direct neighbours, `ring/rdma_links.sh` (`ib_write_bw`, 1 MiB messages, 4 QPs, 3 s):

| Cable | Plane A | Plane B |
|---|---:|---:|
| 0: spark-r0 → spark-r1 | 13,333 MB/s | 13,333 MB/s |
| 1: spark-r1 → gx10-r1 | 13,333 MB/s | 13,333 MB/s |
| 2: gx10-r1 → gx10-r0 | 13,329 MB/s | 13,333 MB/s |
| 3: gx10-r0 → spark-r0 | 13,333 MB/s | 13,333 MB/s |

Opposite nodes through the neighbour's ConnectX-7 hairpin (sparkring `cx7_hairpin_diagonal`,
installed as Mia's `dsv41-mesh.service`, hairpin queue 8192), `ring/mesh_paths.sh`
(`ib_write_lat`, 60 KB, flow label 16383 on both ends):

| Path | Latency (avg) |
|---|---:|
| spark-r0 → gx10-r1, plane A via spark-r1 / plane B via gx10-r0 | 10.10 / 10.08 µs |
| spark-r1 → gx10-r0, plane A via gx10-r1 / plane B via spark-r0 | 10.06 / 10.15 µs |
| gx10-r1 → spark-r0, plane A via spark-r1 / plane B via gx10-r0 | 10.01 / 10.13 µs |
| gx10-r0 → spark-r1, plane A via gx10-r1 / plane B via spark-r0 | 10.09 / 10.10 µs |
| direct neighbour, for reference | 8.2 µs |

The neighbour's `skip_sw` tc rule counted the packets and the kernel's `IpForwDatagrams` did not
move: no CPU forwarding.

## Qwen3.8 TP2 on the ring cable (2026-09-27)

GX10 pair, `hc-k20+cg4+m5500h`, one DAC (cable 2), RoCEnante on `rocep1s0f1,roceP2p1s0f1`:
smoke `17×23 = 391` passed; short prose prompt, 512 tokens, temperature 0, thinking off, three runs:
81.8 / 76.7 / 78.8 tok/s decode. Spark pair preflight passes on cable 0.

## DeepSeek-V4.1-Flash TP4

Pending.

## Gotchas found on this fleet

- **`netplan apply` on the GX10s** stops NetworkManager and then fails, because
  `systemd-networkd` is masked there. The config is written; `sudo systemctl start NetworkManager`
  brings the links up.
- **Docker sets the `FORWARD` policy to `DROP`.** Nothing in serving needs kernel forwarding
  (bootstrap is on the LAN and the mesh forwards RDMA in NIC hardware), but a TCP tool pointed
  at an opposite node's fabric address hangs. Use LAN addresses for control channels.
- **Both ends of an opposite-node RDMA test need `--flow_label=16383`.** Otherwise the replies are
  unmarked and the transit NIC drops them; queue pairs connect and then stall.
- **`mesh-up.sh` is not re-runnable by hand on this iproute2.** Its "rule already present?" check
  misses existing flower filters, so a second run stops at `Filter already exists` before the
  route step. `systemctl restart dsv41-mesh` works (stop removes everything first).
- **`ip route` prints host routes without `/32`.** Grep for the address, not for `/32`.
