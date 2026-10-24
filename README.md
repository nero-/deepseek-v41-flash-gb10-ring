# DeepSeek-V4.1-Flash on four switched GB10 nodes

DeepSeek-V4.1-Flash-1017, tensor-parallel across two DGX Sparks and two ASUS
GX10s on a MikroTik CRS812 switch, served by the **spark-ds41f-1022 TileLang
build**: Local Inference Lab's karmic-kraken-beta vLLM with spark-ds41f's
TileLang kernels, DeepSeek's TileKernels and sparknet one-shot RoCE
collectives.

API: **http://192.168.X.X:8015/v1** · model **DeepSeek-V4.1-Flash-TP4** · no API key.

## Performance

Public LIL 0.7.6 grid, temperature 1, model-default thinking, 20 s cells,
max 2048 tokens; aggregate output tokens/s
([report](results/20261024-tilelang/REPORT.md)):

| Context | C1 | C2 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|---:|
| 8K | 66.5 | 102.2 | 155.1 | 214.0 | 293.7 | 5,441 |
| 16K | 65.7 | 106.6 | 145.7 | 205.2 | 303.5 | 5,963 |
| 32K | 67.1 | 100.2 | 159.7 | 205.9 | 294.1 | 6,122 |
| 64K | 67.9 | 100.4 | 143.8 | 211.6 | 296.2 | 6,088 |
| 128K | 66.0 | 102.8 | 137.1 | 210.0 | 268.9 | 5,964 |

All 25 cells are above the previous B12X selection's grid (+0.6% to +16.2%),
and prefill is 33–42% faster. Coding probes: median 100.8 tokens/s.
Tool-calling quality (tool-eval-bench, leaderboard settings): **90/100**,
78 pass / 10 partial / 4 fail of 92 scenarios; the safety gate did not pass
(tenant isolation and one premature batched call). Uncached retrieval
passed at 122K and 962K prompt tokens.

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
| Recipe | [spark-ds41f](https://github.com/christopherowen/spark-ds41f) `9f1565f0`, release spark-ds41f-1022, `tp4-ring` rendered for the switch ([site changes](image/tilelang-ds41f/README.md)) |
| vLLM | LIL `integration/karmic-kraken-beta` `19f2c20e` + 186 patches (reports 0.29.1rc1.dev187) on vLLM nightly `af1c0149` |
| Kernels | TileLang 0.1.15 (`b95ee4ff` + SM12x block-scaled MMA patches), DeepSeek TileKernels 2.0.0, B12X for vision/loader |
| Collectives | sparknet 0.5.0 one-shot all-reduce/all-gather, switched clique on both port-1 rails; NCCL 2.30.7 with the AArch64 IB fence |
| Image | `sha256:2fc5565e9c15…` on all four ranks |
| Checkpoint | Official DeepSeek-V4.1-Flash-1017 `1bae0e1088993b9b82de08f59de5be5a34e42170`, native FP8/FP4/BF16 |
| Precision | FP32 logits from an exact packed BF16 head; reference-precision MoE, mHC and WO; batch-invariant rows |
| Speculation | DSpark, five greedy drafts, block rejection, rule-based budget, late admission, sink rejection |
| Serving | 1,048,576 context, 16 sequences, 20 GiB KV per rank (16.34M tokens), 999 images per request |
| Fabric | CRS812, one 200G port-1 cable per node, two Socket Direct rails, MTU 9000, GID 3 |
| GPU clocks | 0–2350 MHz ceiling, persistent; idle downclocking enabled |
| Selection | `4d2bc32e…` in root-owned `/etc/deepseek-ring/optimized-specs.json` |

Exact identities: [results/deployment.json](results/deployment.json).

**Rollback:** the previous five-draft B12X selection (`c87a397c…`, image
`9f26f0b3718c…`) is preserved exactly; `image/tilelang-ds41f/promote.py rollback`
restores it ([OPERATIONS](OPERATIONS.md#rollback-on-the-switch)).

## Repository contents

- [OPERATIONS.md](OPERATIONS.md): runbook — control, recovery, fabric, memory, benchmarks, rollback.
- [RESULTS.md](RESULTS.md): current measurements and the previous selection's.
- `cluster.sh`, `scripts/cluster.py`, `config/cluster.toml`: cluster TUI and CLI.
- `image/tilelang-ds41f/`: the selected recipe (render, selection, promote/rollback).
- `image/rocenante-switch`, `image/runtime-20261017`, `image/1017`, `image/kk926`,
  `image/vllm-local-plugins`: the B12X rollback image lineage and its plugins.
- `scripts/`: controller sources, fleet SSH helpers, switched-fabric gate.
- `bench/`: functional, retrieval, mixed-traffic, consistency and fabric checks.
- `host/`: clock-cap service, controller sudoers rule, SSH config block.
- `results/`: qualification evidence for the current and rollback selections.
- [Agent maintenance skill](../SKILL.md): fleet guidance shared by any agent.

This is an operating repository for this fleet; root-owned configuration,
checkpoints and caches live on the nodes. Superseded campaigns were removed on
2026-10-24 and remain at the Git tag `pre-tilelang-cleanup-20261024`.
