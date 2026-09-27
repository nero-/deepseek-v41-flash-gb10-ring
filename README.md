# DeepSeek-V4.1-Flash on a switchless GB10 ring (2× DGX Spark + 2× ASUS Ascent GX10)

Serve [deepseek-ai/DeepSeek-V4.1-Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash)
at TP4 on four GB10 machines cabled as a ring with four DACs and no switch, and keep the two
Qwen3.8 TP2 pairs that share the same cables runnable.

This repository holds only the site-specific glue. The serving stack comes from the upstream projects
below at pinned commits; nothing from them is vendored here.

| Layer | Source | Pin |
|---|---|---|
| Serving line (SGLang dsv4.1 + adapters, `Dockerfile.canary-roce`, `start-tp4.sh`) | [MiaAI-Lab/DeepSeek-v4.1-Flash-DGX-Sparks](https://github.com/MiaAI-Lab/DeepSeek-v4.1-Flash-DGX-Sparks) (AGPL-3.0) | `cad252b7` |
| Ring transport: patched NCCL 2.30.7, hardware-forwarded opposite-node paths, path-aware RoCEnante | [FujitsuPolycom/sparkring](https://github.com/FujitsuPolycom/sparkring) (Apache-2.0) | `f16b5f43` |
| Kernels: b12x (MXFP8 dense, routed MoE, RoCEnante one-shot collectives) | [local-inference-lab/b12x](https://github.com/local-inference-lab/b12x) (Apache-2.0) | `a7d7d29b` (via Mia's `sources.manifest`) |
| Base image | `lmsysorg/sglang:dev-dsv41` | `sha256:3dbc3130…` |
| NVIDIA NCCL | [NVIDIA/nccl](https://github.com/NVIDIA/nccl) | `73cf1122` + sparkring `nccl-2.30.7-dual-pci-domain.patch` (blob `f4853e84`), built with the image's CUDA 13.0 → `libnccl.so.2.30.7` sha256 `68f91a60…` |
| Serving image | `Dockerfile.canary-roce` built once, `docker save`/`load` to the other ranks | image ID `0c28b7b35803` on all four |
| Checkpoint | `deepseek-ai/DeepSeek-V4.1-Flash` | `fb2764a5` (weights identical to `dba1be0a`) |

Why this stack: Mia's four-node production line is the fastest published DeepSeek-V4.1-Flash
configuration on GB10 (b12x MoE at EP1, RoCEnante collectives, prefill sequence parallel, DSpark k=5),
and its switchless-ring guide measured it on a ring within a few percent of a switched fabric once
sparkring's opposite-node mesh is in place. The sparkring vLLM profile for the same model prefills at
~2k tok/s against ~5k here. Local Inference Lab's Docker configurator targets single-node multi-GPU
boxes and keeps the 190 GiB of Engram tables in RAM, which a 121.7 GiB GB10 cannot hold.

## Topology

```
      spark-r0 (rank 0, head, API :8888)
      f0 ──cable 0── f1  spark-r1 (rank 1)
      f1                 f0
       │                  │
    cable 3            cable 1
       │                  │
      f0                 f1
      gx10-r0 (rank 3) f1 ──cable 2── f0 gx10-r1 (rank 2)
```

Every cable joins rank *i*'s f0 port to rank *i+1*'s f1 port, the orientation sparkring's mesh
planner requires. Each physical port exposes two netdevs on two PCIe roots, so every cable carries
two RoCE planes:

| Cable | Plane A (`enp1s0f*`, `rocep1s0f*`) | Plane B (`enP2p1s0f*`, `roceP2p1s0f*`) |
|---|---|---|
| 0: spark-r0 f0 ↔ spark-r1 f1 | 10.10.0.10 ↔ .11 | 10.11.0.10 ↔ .11 |
| 1: spark-r1 f0 ↔ gx10-r1 f1 | 10.10.1.10 ↔ .11 | 10.11.1.10 ↔ .11 |
| 2: gx10-r1 f0 ↔ gx10-r0 f1 | 10.10.2.10 ↔ .11 | 10.11.2.10 ↔ .11 |
| 3: gx10-r0 f0 ↔ spark-r0 f1 | 10.10.3.10 ↔ .11 | 10.11.3.10 ↔ .11 |

MTU 9000, RoCE v2 GID index 3, and each node routes the two /24s it does not sit on through the
neighbour on that cable. SSH, Gloo/NCCL bootstrap and the API use the management LAN (`enP7s7`).

Measured per link with `ring/rdma_links.sh` (`ib_write_bw`, 1 MiB, 4 QPs): 13.3 GB/s on all eight
plane×cable paths.

## Setup, in order

1. **SSH mesh.** One `id_ed25519_ring` key per node, authorised on all four, and a managed block at
   the top of `~/.ssh/config` mapping the four host names to their LAN addresses
   (`ring/ssh-config-block.txt`).
2. **Fabric addressing.** `ring/gen_netplan.py` writes one `/etc/netplan/41-dsv41-ring.yaml` per node;
   `ring/apply_netplan.sh` snapshots `/etc/netplan`, moves the old fabric files aside and applies it.
   On the GX10s `systemd-networkd` is masked, so `netplan apply` stops NetworkManager and then fails:
   run `sudo systemctl start NetworkManager` afterwards (or `netplan generate` + restart NM).
   Verify with `ring/rdma_links.sh`.
3. **Checkpoint on every rank.** Download once, replicate over the fabric with
   `scripts/dist_model.sh` (~2 GB/s per target), full local copy per rank (`NFS_SHARE=0`).
4. **Patched NCCL.** `nccl/build_nccl.sh ~/sparkring ~/nccl-2.30.7` on one node, then copy the
   library to the same path on all four and compare `sha256sum`.
5. **Serving image.** Mia's `Dockerfile.canary-roce`, built once and loaded on the other ranks.
6. **Packed Engram shards.** `./start-tp4.sh pack` (one per rank, local NVMe).
7. **Opposite-node mesh.** Build sparkring's RDMA-TX marker on every node, run Mia's `scripts/ring_mesh/plan.py` from the head, install `dsv41-mesh.service` everywhere, then re-run `plan.py` so the RoCE cap follows the 8192 hairpin queues (262144 B). Verify with `ring/mesh_paths.sh` (run it on a node; macOS bash lacks associative arrays).
8. **`.env.tp4`.** `config/make_env_tp4.py <mia>/.env.tp4.example .env.tp4 [ring-mesh/env.txt]`.
9. **Serve.** `scripts/ring-mode.sh ds`.

## Qwen TP2 on the same cables

The ring keeps one direct cable inside each pair (cable 0 for the Sparks, cable 2 for the GX10s).
`scripts/ring-mode.sh qwen spark|gx10|both` stops DeepSeek, takes the mesh down on that pair and
starts the pair's own `~/builds/qwen-tp2/cluster.sh`. Both of the pair's HCAs on that one cable are
used (one per PCIe root). Each pair's `cluster-config.json` was retargeted with
`scripts/retarget_tp2.py`; cable modes 1 and 2 now select the same two rails, since only one cable
joins the pair.

## Benchmarks

Speed is measured with [local-inference-lab/llm-inference-bench](https://github.com/local-inference-lab/llm-inference-bench)
v0.6.2 (`ccd9ad8`), the same case definitions as the Qwen TP2 campaign (`bench/lilbench.sh`, run from
gx10-r0). Quality is Mia's `scripts/qeval.py` (75 auto-scored tasks, temperature 0, c1).
`bench/ringbench.py` is a quicker in-house A/B probe.

## Results

See [RESULTS.md](RESULTS.md).
