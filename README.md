# DeepSeek-V4.1-Flash on four switched GB10 nodes

> **Serving now, October 24 UTC: spark-ds41f TileLang build, kept by the user.**
> Image `2fc5565e9c15…` in containers `ds41f-tilelang-rN` serves on 8015 with
> the same model name. It beat the previous build in the focused screen (all six cells) and in
> 22 of 25 full-grid cells, with prefill 33–43% faster. The fleet is claimed by the start interlock,
> so **do not run `recover-ds`**; after a reboot run
> `python3 ../DS41-ds41f-tilelang/scripts/trial.py serve`. The selection below is the stopped,
> unchanged fallback (`trial.py restore`). Gaps: 4 images per request, 10.5 GiB KV.
> [Results and procedure](../DS41-ds41f-tilelang/README.md).

> **Current state, October 21 UTC:** five-draft vLLM serves on 8015 with 20 GiB
> KV. A coordinated four-node reboot cleared the observed allocation warnings
> on this startup. Three focused repeats passed: median 8K C1/C8/C16
> **66.8 / 203.1 / 285.5 tok/s**; 32K **64.7 / 202.8 / 289.2**. Exact fallback preserved.
> [Reboot protocol, individual runs and limitations](results/20261021-reboot-draft5/REPORT.md).

> **Stock-native source FLARE evaluation (October 21 UTC):** four FLARE settings
> were slower in all 24 focused decode cells against both fresh vLLM controls.
> No CSF was used and no candidate was promoted. Qualified vLLM is restored and
> healthy; the restoration control measured 66.0 t/s at 32K C1. See the
> [completed trial](../DS41-flare-source/README.md) and
> [developer report](../DS41-flare-source/output/pdf/FLARE-stock-checkpoint-feedback.md).

The broader decode optimization campaign remains paused at the user's request.
The requested five-draft change and Mia comparison are separate authorized work.
The persistent **2350 MHz GPU ceiling** remains on all four nodes.
See the [comparison audit](results/20261020-decode-recovery/REPORT.md)
and [clock-policy verification](results/20261020-clock-cap/REPORT.md).

Both rejected FLARE packages have been retired; the stock checkpoint and
qualified vLLM fallback remain intact. FLARE agents are stopped and disabled,
and their ownership markers are archived. The separate Mia interlock is also archived.
The completed stock-native FLARE trial removed
1148.46 GiB of allocated package/cache payload after recovery. Its source,
metadata, raw evidence and reproduction recipe remain in `../DS41-flare-source`.
The [earlier October 20 trial](results/20261020-flare-trial/REPORT.md) is separate
historical evidence and used a different package.

Corrected vLLM TP4 across two DGX Sparks and two ASUS GX10s on a CRS812 switch.
API: **http://192.168.X.X:8015/v1**. Model: **DeepSeek-V4.1-Flash-TP4**.

**CRS812 conversion, October 20 UTC:** switched networking and the new
controller are installed. RoCEnante pipelined two-shot and the selected serving
profile are qualified. The commands below operate the switched profile and leave
all retired ring services disabled. See the
[switch qualification report](results/20261019-switch-migration/REPORT.md).

Official **DeepSeek-V4.1-Flash-1017** remains on the qualified October 15
eugr/KK/FlashInfer math runtime. The switched transport layer preserves its
model corrections and local performance plugins.
[Runtime qualification, full benchmark and final KV screen](results/20261017-runtime-upgrade/REPORT.md).

Generation defaults are explicit: temperature 1, top_p 1, top_k disabled,
min_p 0 and repetition penalty 1. The 24-response language screen found no
Chinese ideographs at either top_p 1 or 0.95. This is finite evidence, not a
promise against rare language drift.

KV allocation is **20 GiB per GPU**, exposing **16.34M logical tokens**.
Head total used memory was **117.803 GiB immediately after the reboot recovery**,
leaving **3.884 GiB available**. The post-reboot startup and three focused repeats logged no allocation warnings. The 118 GiB goal is the initial
loaded budget; there is no automatic runtime stop guard.
The checkpoint's published precision is unchanged.
[Current transport and serving qualification](results/20261019-switch-migration/REPORT.md).

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

`recover-ds` stops the workload and disables the retired mesh, then validates
the switched fabric and starts the selected model. Allow roughly 4–20 minutes for loading and
warmup. It returns when the API is healthy. The script is `ring-mode.sh`.
For **RoCE GID differs**, follow the additional link repair in
[OPERATIONS.md](OPERATIONS.md#switched-link-or-gid-failure).

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
| Fabric | CRS812, one physical 200G port per node, two Socket Direct rails, MTU 9000, GID 3 |
| SparkRing package | `8b152d65c701f557f62ae6a9a1c3db90771c1df3`; retained container library, retired network services |
| Parent | eugr ARM64 `nightly-20261015`, digest `03a956544e9f9b4b7ba91690469fbe7848bdbef29a7d2e0f5788368467bb3595` |
| vLLM KK | `8244d1c44348ae8a5bbfc9f1b607021652283ed4` |
| FlashInfer / B12x provider | FlashInfer 0.7.1, `91271757f7746f3dfb58f7c2aeb44a663389de9e`; B12x compatibility namespace |
| GPU toolchain | Qualified CUDA 13.4.2 / patched NCCL 2.32.3 retained |
| Checkpoint | Official DeepSeek-V4.1-Flash-1017, revision `1bae0e1088993b9b82de08f59de5be5a34e42170` |
| Local image | Built October 20; `9f26f0b3718c…` on all four ranks |
| Local profile | `engram-adaptive4k-query-indexer-1017-runtime1015-kv20-images999-switch-draft5` (clean reboot and three focused retests passed) |
| Transport | RoCEnante one-shot/gather plus ABI-8 pipelined two-shot; patched NCCL fallback |
| KV budget | 20 GiB per GPU; 16,344,051 logical tokens |
| GPU clock policy | 0–2350 MHz ceiling, persistent across reboot; idle downclocking enabled |

[Deployment identity and plugin hashes](results/deployment.json),
[selected transport image recipe](image/rocenante-switch/README.md), and
[selected plugin sources](image/vllm-local-plugins/README.md).

Engram projection TP, native DSpark and adaptive verification come from this
recipe. The user-requested draft maximum is **five**, with the previous C1 cap
removed. Graph sizes cover 5*n and 6*n for n=1..16, through 96. This is a policy
change, not a measured performance promotion. The exact original four-draft
selection remains a stopped recovery artifact. The two local plugins reduce the
prefill scheduling quantum from 8K to 4K when at least one decoder contends, and
shard eligible long-prefill indexer queries across ranks with numerical guards.
The official 1017 checkpoint retains its published precision and full vocabulary.
HF tokenization is selected.

The RoCEnante pipe is 128 MiB with a 512 KiB two-shot threshold. Both switched
rails are active and share the node's single physical 200G connection.
This is RoCEnante with NCCL fallback; SIRCL is not enabled.

The historical four-draft full 25-cell LIL qualification, run with stock GPU boost, completed without
request errors or detected loops. At 8K, C1/C8/C16 measured **64.4 / 198.8 / 268.7 tokens/s**.
Uncached 961,724-token retrieval and mixed image/decode checks also passed.
Sustained 70 C1 and 300 C16 were not established.
[All contexts, repetitions and tradeoffs](RESULTS.md).

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

The [completed switch migration plan](results/20261019-switch-migration/PLAN.md)
records the shutdown, one-port 200G layout, exact ring cleanup, image options and
validation sequence. The [earlier runtime plan](results/20261017-runtime-plan/PLAN.md)
is historical research; its runtime upgrade was completed in the campaign above.
