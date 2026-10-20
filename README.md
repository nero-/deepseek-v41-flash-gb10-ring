# DeepSeek-V4.1-Flash on the four-node GB10 ring

Corrected SparkRing vLLM TP4 across two DGX Sparks and two ASUS GX10s.
API: **http://192.168.X.X:8015/v1**. Model: **DeepSeek-V4.1-Flash-TP4**.

**Maintenance, October 19 HST / October 20 UTC:** DeepSeek and all mesh
supervisors are stopped for CRS812 recabling. The switch conversion is not
deployed yet. Do not use the ring start/recovery commands below during this
handoff; they enable the old mesh. See the
[current switch migration plan](results/20261019-switch-migration/PLAN.md).

**Selected as of 2026-10-17 UTC:** official **DeepSeek-V4.1-Flash-1017** on
the qualified October 15 eugr/KK/FlashInfer runtime. The existing RoCEnante ring
transport and local performance plugins are preserved.
[Runtime qualification, full benchmark and final KV screen](results/20261017-runtime-upgrade/REPORT.md).

Generation defaults are explicit: temperature 1, top_p 1, top_k disabled,
min_p 0 and repetition penalty 1. The 24-response language screen found no
Chinese ideographs at either top_p 1 or 0.95. This is finite evidence, not a
promise against rare language drift.

KV allocation is **20 GiB per GPU**, exposing **16.34M logical tokens**.
Head total used memory was **117.40 GiB immediately after loading**,
leaving **4.28 GiB available**. The 118 GiB goal is the initial
loaded budget; there is no automatic runtime stop guard. The decode tuning
trials did not establish an overall gain, so the existing decode settings remain.
The checkpoint's published precision is unchanged.
[Decode trials, larger KV and final qualification](results/20261017-decode-tuning/REPORT.md).

Image input accepts **up to 999 images across the full request**, including
chat history. The old four-image restriction has been removed. Distinct-image
requests through 64 images and streamed chat continuation passed; very large
requests still depend on context length and available memory.
[Image-limit change and checks](results/20261017-image-limit/REPORT.md).

## Start, stop and recover

From the PC:

```bash
cd ~/Agent/Builds/deepseek-v41-flash-ring
./scripts/ring-mode.sh ds                 # start the selected DeepSeek profile
./scripts/ring-mode.sh recover-ds         # coordinated restart after a node reboot/failure
./scripts/ring-mode.sh stop
./scripts/ring-mode.sh status
```

`recover-ds` stops the workload and every mesh supervisor, then starts the
mesh and selected model together. Allow roughly 4–20 minutes for loading and
warmup. It returns when the API is healthy. The script is `ring-mode.sh`.
For **RoCE GID differs**, follow the additional link repair in
[OPERATIONS.md](OPERATIONS.md#roce-gid-differs-after-a-peer-reboot).

Qwen serving on this ring was retired to make room for GLM. Its old stop
entry points remain compatible with DeepSeek recovery; `ring-mode.sh qwen`
reports retirement without stopping DeepSeek. See the
[GLM handoff and storage receipt](../GLM/HANDOFF.md#capacity-and-protected-rollback).

```bash
curl --fail --max-time 5 http://192.168.X.X:8015/health
```

## Current build

| Component | Selected version |
|---|---|
| SparkRing installer | `8b152d65c701f557f62ae6a9a1c3db90771c1df3`; existing switchless ring |
| Parent | eugr ARM64 `nightly-20261015`, digest `03a956544e9f9b4b7ba91690469fbe7848bdbef29a7d2e0f5788368467bb3595` |
| vLLM KK | `8244d1c44348ae8a5bbfc9f1b607021652283ed4` |
| FlashInfer / B12x provider | FlashInfer 0.7.1, `91271757f7746f3dfb58f7c2aeb44a663389de9e`; B12x compatibility namespace |
| GPU toolchain | Qualified CUDA 13.4.2 / patched NCCL 2.32.3 retained |
| Checkpoint | Official DeepSeek-V4.1-Flash-1017, revision `1bae0e1088993b9b82de08f59de5be5a34e42170` |
| Local image | Built October 17; identical immutable image on all four ranks |
| Local profile | `engram-adaptive4k-query-indexer-1017-runtime1015-kv20-images999` |
| KV budget | 20 GiB per GPU; 16,344,051 logical tokens |
| GPU upper clock limit | 2350 MHz, minimum 0, persistent across reboot |

[Deployment identity and plugin hashes](results/deployment.json),
[selected image recipe](image/runtime-20261017/README.md), and
[selected plugin sources](image/vllm-local-plugins/README.md).

Engram projection TP, native DSpark5 and adaptive verification come from this
recipe. The two local plugins reduce the prefill scheduling quantum from 8K to
4K when at least four decoders contend, and shard eligible long-prefill indexer
queries across the four ranks with numerical guards. The official 1017 checkpoint
retains its published precision and full vocabulary. HF tokenization is selected.

## Repository contents

- [Agent maintenance skill](../SKILL.md): fleet-specific guidance shared by any agent.
- [OPERATIONS.md](OPERATIONS.md): endpoints, thinking, recovery, host maintenance and checks.
- [RESULTS.md](RESULTS.md): current measurements and concise selection decisions.
- `scripts/`: fleet lifecycle and full benchmark runner.
- `image/`: the selected runtime and transport layer, retained rollback patches and local plugins.
- `bench/`, `ring/`, `host/`: validation, fabric diagnostics and clock-cap service.
- `results/`: selected-build evidence and original-checkpoint recovery proofs.

This is an operating repository for this existing fleet. The installed
SparkRing package, root-owned configuration, checkpoints and tuning caches live
on the nodes; this checkout is not a universal bootstrap. A new installation
starts from the [pinned upstream installer](https://github.com/FujitsuPolycom/sparkring/tree/8b152d65c701f557f62ae6a9a1c3db90771c1df3).

Completed experiments and superseded reports were removed from the active
checkout. Tracked history is recoverable from Git at `364eb87`; a complete
pre-cleanup working snapshot also preserves uncommitted research outside the
repository. Its local location is recorded in `.local/cleanup.json`.

The [current switch migration plan](results/20261019-switch-migration/PLAN.md)
records the shutdown, one-port 200G layout, exact ring cleanup, image options and
validation sequence. The [earlier runtime plan](results/20261017-runtime-plan/PLAN.md)
is historical research; its runtime upgrade was completed in the campaign above.
