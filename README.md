# DeepSeek-V4.1-Flash on four switched GB10 nodes

DeepSeek-V4.1-Flash-1017, tensor-parallel across two DGX Sparks and two ASUS
GX10s on a MikroTik CRS812 switch, served by the **five-draft B12X build**:
the October 15 eugr/KK/FlashInfer runtime with RoCEnante two-shot transport.
It was re-selected as the production default on 2026-10-24 for answer quality.
The faster spark-ds41f TileLang build is kept, stopped, as the alternative.

API: **http://192.168.X.X:8015/v1** · model **DeepSeek-V4.1-Flash-TP4** · no API key.

## Performance and quality

Public LIL 0.7.6 grid, temperature 1, model-default thinking, 20 s cells,
max 2048 tokens; aggregate output tokens/s, measured 2026-10-24
([comparison](results/20261024-b12x-comparison/REPORT.md)):

| Context | C1 | C2 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|---:|
| 8K | 63.1 | 90.7 | 140.0 | 197.7 | 272.7 | 3,898 |
| 16K | 63.5 | 93.0 | 134.4 | 186.7 | 266.8 | 3,746 |
| 32K | 64.0 | 93.9 | 146.1 | 197.3 | 265.8 | 4,059 |
| 64K | 64.9 | 78.6 | 133.4 | 181.0 | 268.7 | 4,498 |
| 128K | 62.9 | 94.8 | 136.5 | 189.2 | 260.6 | 4,305 |

GPQA Diamond at temperature 1, top_p 1: **186/198 = 93.9%** (Wilson 95%
89.7–96.5%). Tool-calling quality (tool-eval-bench, leaderboard settings):
93 and 89 in two runs; the safety gate did not pass. TileLang was faster in
every grid cell (+0.5% to +27.8% decode, +35% to +59% prefill) and scored 90
on tool-eval twice, but another tester reported about 91.5% on GPQA Diamond
for it, so the user chose B12X.

## Start, stop and recover

```bash
cd ~/Agent/Builds/deepseek-v41-flash-spark
./cluster.sh               # TUI: nodes, health, actions, live output
./cluster.sh status
./cluster.sh up            # start (asks first)
./cluster.sh down          # stop (asks first)
./cluster.sh recover       # after a reboot: wait for SSH on all four nodes first
```

The TUI and its actions are defined in [`config/cluster.toml`](config/cluster.toml)
and are not DeepSeek-specific: add nodes, workloads and commands there.
`scripts/ring-mode.sh ds|recover-ds|stop|status` still works. Startup takes
about 2 minutes with warm caches. Details: [OPERATIONS.md](OPERATIONS.md).

```bash
curl --fail --max-time 5 http://192.168.X.X:8015/health
```

## Current build

| Component | Selected |
|---|---|
| Recipe | [RoCEnante switch image](image/rocenante-switch/README.md) on the October 15 runtime ([lineage](image/runtime-20261017)) |
| vLLM | local-inference-lab/vllm `8244d1c4` (0.1.dev21830), torch 2.13.0+cu130 |
| Kernels | B12X from local-inference-lab/flashinfer `91271757`, FlashInfer 0.7.1, CUTLASS DSL 4.7.0 |
| Collectives | RoCEnante ABI 8: one-shot below 512 KiB, pipelined two-shot to 128 MiB, patched NCCL fallback |
| Plugins | adaptive 4K prefill, guarded query-indexer TP sharding (`/usr/local/lib/deepseek-ring/plugins`) |
| Image | `sha256:9f26f0b3718c…` on all four ranks |
| Checkpoint | Official DeepSeek-V4.1-Flash-1017 `1bae0e1088993b9b82de08f59de5be5a34e42170`, native precision |
| Speculation | DSpark, five probabilistic drafts, block rejection, adaptive verification |
| Serving | 1,048,576 context, 16 sequences, 20 GiB KV per rank (16.34M tokens), 999 images per request |
| Fabric | CRS812, one 200G port-1 cable per node, two Socket Direct rails, MTU 9000, GID 3 |
| GPU clocks | 0–2350 MHz ceiling, persistent; idle downclocking enabled |
| Selection | `c87a397c…` in root-owned `/etc/deepseek-ring/optimized-specs.json` |

Exact identities: [results/deployment.json](results/deployment.json). Startup
head memory 117.8 GiB (budget about 118 GiB).

**Alternative:** the spark-ds41f TileLang selection (`4d2bc32e…`, image
`2fc5565e9c15…`) is kept exactly as stopped `ds41-tilelang-rN` containers;
`image/tilelang-ds41f/promote.py reselect` switches to it
([OPERATIONS](OPERATIONS.md#switching-between-b12x-and-tilelang)).

## Repository contents

- [OPERATIONS.md](OPERATIONS.md): runbook — control, recovery, fabric, memory, benchmarks, switching builds.
- [RESULTS.md](RESULTS.md): current measurements and the previous selection's.
- `cluster.sh`, `scripts/cluster.py`, `config/cluster.toml`: cluster TUI and CLI.
- `image/rocenante-switch`, `image/runtime-20261017`, `image/1017`, `image/kk926`,
  `image/vllm-local-plugins`: the selected B12X image lineage and its plugins.
- `image/tilelang-ds41f/`: the TileLang alternative (render, selection, promote/rollback/reselect).
- `scripts/`: controller sources, fleet SSH helpers, switched-fabric gate.
- `bench/`: functional, retrieval, mixed-traffic, consistency and fabric checks.
- `host/`: clock-cap service, controller sudoers rule, SSH config block.
- `results/`: qualification evidence for the selected and alternative builds.
- [Agent maintenance skill](../SKILL.md): fleet guidance shared by any agent.

This is an operating repository for this fleet; root-owned configuration,
checkpoints and caches live on the nodes. Superseded campaigns were removed on
2026-10-24 and remain at the Git tag `pre-tilelang-cleanup-20261024`.
