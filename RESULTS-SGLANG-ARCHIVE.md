# Historical SGLang results

The SGLang runtime and its setup scripts are retired. Paths below describe the former deployment. Current vLLM results are in [RESULTS.md](RESULTS.md).

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

### Bring-up (2026-09-27)

- Checkpoint `fb2764a5` on every rank: 52/52 LFS files match Hugging Face's sha256 on all four.
- Image `dsv41-4x-spark:canary-roce` (`0c28b7b35803`) plus `image/Dockerfile.ring` on all ranks.
  The later migration audit found different per-node image IDs: the first 98 layers and the
  final layer's modified loading-timeout file match. See `MIGRATION-20260927.md` for the recorded identities and content check.
- Boot log: `NCCL_SWITCHLESS_RING_ONLY` with Tree/PAT transport setup disabled; NCCL `ListenerRouting
  advertised=4 observed=4` and substitutions `preserving PCI root` (both planes carry traffic);
  `RoCEnante ready: world=4` on all four HCAs at the 262144-byte cap; Engram `packed=True`; every
  production adapter armed (b12x MoE EP1 deterministic, shared-expert K pad on 43 layers, fp8 `wo_a`
  twins, replicated splits, fused HC bit-identical, block verification, chunked indexer, prefill SP).
- KV pool 6,644,224 tokens at 1M context.
- Smoke (`bench/smoke.py`): 19+23=42, greedy byte-identical x3, tool call, thinking mode, and a
  125,219-token needle PASS in 29.0 s.

### Weight loading on the GX10s

The first boot failed at SGLang's post-load barrier: `TP rank 0 could finish the model loading, but
there are other ranks that didn't finish`. The barrier gives the slowest rank 480 s after the first
finishes (`UNBALANCED_MODEL_LOADING_TIMEOUT_S`). Measured `Load weight end` per rank:

| Boot | spark-r0 | spark-r1 | gx10-r1 | gx10-r0 |
|---|---:|---:|---:|---:|
| 1 (cold, right after replication) | 312 s | 144 s | 814 s | >830 s |
| 2 | 65 s | 61 s | 223 s | — |

The GX10s' drives (1 TB Phison `ESL01TBTLCZ`) read 4.4 GB/s sequential direct against 12 GB/s on the
Sparks' Samsung 4 TB, and 4.3-4.7 GB/s against 5.8 GB/s with 16-64 threads of 8 MB buffered `pread`.
Host-to-device copies are identical (57-60 GB/s). `image/Dockerfile.ring` raises the barrier to
1800 s so a cold GX10 load can no longer fail the boot.

### Baseline: Mia's production line on the ring (LIL v0.6.2, 2026-09-27)

`bench/lilbench.sh base matrix,coding` from gx10-r0: 30 s windows, 2,048 max tokens, temperature
unset (server default), standalone prefill. Quality: `scripts/qeval.py`, 75 tasks, c1, greedy.

| Context | C1 tok/s | C8 aggregate tok/s | Prefill tok/s |
|---|---:|---:|---:|
| 8k | 72.0 | 156.2 | 4,680 |
| 32k | 66.7 | 151.7 | 5,063 |
| 64k | 62.7 | 150.6 | 4,970 |

Coding Peak 97.5 tok/s (95.6-100.1). qeval 72/75 (the three tasks Mia's stock profile also fails),
median 80.4 tok/s. Evidence in `results/20260927/`.

### Where a decode step goes (torch profiler on rank 0, Mia's `analyze_steps.py`)

| | C1 (1 request) | C16 (16 requests, 96 verify rows) |
|---|---:|---:|
| step wall, median | 35.7 ms | 155.1 ms |
| routed MoE (b12x) | 14.7 ms | 94.1 ms |
| other (includes RoCEnante one-shot waits) | 13.8 ms | 10.7 ms |
| bf16 GEMM | 10.0 ms | 17.9 ms |
| NCCL | 0.0 ms | 19.7 ms |
| hyper-connections / attention | 3.3 / 1.5 ms | 6.1 / 5.9 ms |
| Engram | 0.0 ms (prefetch hides it; 2% of all-reduce wait) | 0.1 ms |

C1 matches Mia's ring figure (33-37 ms). At C16 the MoE streams most of every rank's expert slice
(bandwidth-bound) and the ~983 KB all-reduces fall back to NCCL.

### RoCEnante size cap

A decode all-reduce is rows x 5,120 x 2 B, with 6 verify rows per request (DSpark k=5): C1 61 KB,
C4 246 KB, **C8 491,520 B**, C16 983 KB. The planner's 262,144-byte cap sends C5-C8 to NCCL.
Raising `SGLANG_ROCE_MAX_SIZE` and `DSV41_ROCE_GATHER` to 491,520 moved C8 onto RoCEnante: C8
aggregate 156.2 / 151.7 / 150.6 -> 162.0 / 150.9 / 155.2 tok/s (8k/32k/64k), prefill +0.3-1.3%, qeval
72/75 unchanged, and no `out_of_sequence`, `packet_seq_err` or `rx_out_of_buffer` on any of the 16
functions afterwards. Adopted.

C16 cannot follow: `mlx5_core: Maximum hairpin queue size is 8192`, and Mia measured drops and
go-back-N retransmits at ~1 MB with 8192-packet queues.

### Final configuration, full LIL run (2026-09-27)

Mia's production line + ring mesh + RoCEnante cap 491,520 B + 8192-token prefill chunks
(`config/make_env_tp4.py`). `bench/lilbench.sh final full,coding` from gx10-r0; 0 errors in every cell.

| Context | C1 | C2 | C4 | C8 | C16 | Prefill tok/s |
|---|---:|---:|---:|---:|---:|---:|
| 8k | 67.7 | 96.4 | 129.8 | 160.1 | 224.5 | 5,151 |
| 32k | 64.9 | 91.0 | 125.1 | 145.8 | 196.8 | 5,613 |
| 64k | 66.8 | 94.6 | 129.3 | 154.2 | 198.5 | 4,877 |
| 128k | 62.7 | 94.4 | 124.1 | 153.1 | 191.3 | 5,414 |

Decode columns are aggregate tok/s. Coding Peak 104.6 tok/s (100.1-108.4; 97.5 on the baseline).
qeval 72/75, median 81.6 tok/s. KV pool 5,606,400 tokens at 1M context. Raw files in `results/20260927/final-*`.


Each candidate is one boot of the production line with one change (`bench/experiment.sh`), a
smoke test, qeval (75 tasks), and `bench/ringbench.py` (greedy, thinking off, 256 tokens; four prompt
types x C1-C16; cold real-text prefill after an untimed warm-up pass). Re-running the unchanged
baseline on a fresh boot moved individual cells by up to +/-5-8% (batch composition changes greedy
text at C>1, and the earlier reference ran after a long LIL session), so only consistent effects
larger than that count.

| Change | Result | Decision |
|---|---|---|
| RoCEnante cap 262,144 -> 491,520 B | C8 moves from NCCL to RoCEnante; LIL C8 +3.7% / -0.5% / +3.1%; zero drops or sequence errors | **adopted** |
| `CHUNKED_PREFILL_SIZE` 4096 -> 8192 | cold prefill +8.5 / +7.6 / +11.9 / +10.7% at 16k/32k/64k/128k; decode within noise; qeval 72/75; 251k and 1,000,169-token needles PASS (1M in 247.6 s vs 305 s on Mia's ring), head MemAvailable low-water 3.2 GiB | **adopted** |
| `DSV41_VERIFY_CAP` conf:0.1 -> 0.2 / 0.3 | indistinguishable from a fresh-boot repeat of the baseline | kept 0.1 |
| `DSPARK_BLOCK_SIZE` 5 -> 7 | engine fails at warm-up: `mat1 and mat2 shapes cannot be multiplied (80x7424 and 5376x1)` | not supported |
| `SPARK_PREFILL_TP_MIN_CONTEXT` 32768 -> 8192 | adapter refuses: `if context<32768 ... raise ValueError` | not supported |
| hairpin queue 8192 -> 16384 (for C16 on RoCEnante) | `mlx5_core: Maximum hairpin queue size is 8192` | not possible |
| CPU governor / GPU clocks | already `performance`, identical clocks, no throttle reasons on all four | nothing to change |

### Why these numbers sit below Mia's headline figures

Mia's 87.7 prose C1 and ~240 prose C8 are sparkDash 1.8.8 on a **switched** fabric: one short prose
prompt, 256 tokens, temperature 0. Her own ring run of the same line measured 80.9 and 221.3. On
varied prompts the same image does 58-94 tok/s at C1, and 66-67 tok/s sampled at T=1 (her docs).
LIL leaves temperature at the server default and runs 8k-128k of context with up to 2,048 new
tokens, which lowers DSpark acceptance per step and lengthens each step. The engine itself runs at
parity: a C1 decode step is 35.7 ms here against 35.2 ms on Mia's ring.

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
