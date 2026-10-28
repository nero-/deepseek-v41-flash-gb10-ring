# DeepSeek-V4.1-Flash on four switched GB10 nodes

DeepSeek-V4.1-Flash-1017, tensor-parallel across two DGX Sparks and two ASUS
GX10s on a MikroTik CRS812 switch, served by **FLARE** (Local Inference Lab's
native engine) from the signed TP4 package
`local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE@gb10`. FLARE became the
production default on 2026-10-27, replacing the five-draft B12X vLLM build.

API: **http://192.168.X.X:8015/v1** · model **DeepSeek-V4.1-Flash-TP4** · no API key.

## Performance

Public LIL 0.7.6 grid, temperature 1, model-default thinking, 20 s cells,
max 2048 tokens; aggregate output tokens/s, measured 2026-10-27
([report](results/20261027-flare/REPORT.md)):

| Context | C1 | C2 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|---:|
| 8K | 58.9 | 99.9 | 141.1 | 179.4 | 253.8 | 3,873 |
| 16K | 60.1 | 95.7 | 143.2 | 168.9 | 253.4 | 4,102 |
| 32K | 63.6 | 98.3 | 146.5 | 176.1 | 246.7 | 4,444 |
| 64K | 63.4 | 98.6 | 140.2 | 200.4 | 245.8 | 4,479 |
| 128K | 61.0 | 95.9 | 136.7 | 198.4 | 261.0 | 4,411 |

Against the B12X grid of 2026-10-24: C1 −3.6% on average, C2 +8.9%, C4
+2.6%, C8 −2.8%, C16 −5.5%, prefill +4.1%; coding peak median 100.3 against
104.1. Functional checks 7/7, uncached retrieval at 122K and 923K tokens,
1000 images in one request. GPQA Diamond and tool-eval have not been run on
FLARE yet (B12X: 93.9% and 93/89).

**Known issue:** in default (thinking) mode, a few positions in the first 128
tokens get context-free logits, so short replies can contain a spliced stray
token or, once, the model's `<ds_safety>` annotation. `enable_thinking: false`
avoids it ([details](results/20261027-flare/REPORT.md#known-issue-stray-tokens),
[upstream #118](https://github.com/NVIDIA/local-inference/issues/118)).

## Start, stop and recover

```bash
cd ~/Agent/Builds/deepseek-v41-flash-spark
./cluster.sh               # TUI: nodes, health, actions, live output
./cluster.sh status
./cluster.sh up            # start the FLARE group (asks first)
./cluster.sh down          # stop it (asks first)
./cluster.sh recover       # after a reboot: wait for SSH on all four nodes first
```

The actions run `flare orbit` on spark-r0 (controller and rank 0); the agents
on all four nodes start at boot, the group does not. Startup takes under 30
seconds once each node holds its package. The TUI is defined in
[`config/cluster.toml`](config/cluster.toml). Details:
[OPERATIONS.md](OPERATIONS.md) and the [FLARE guide](flare/README.md).

```bash
curl --fail --max-time 5 http://192.168.X.X:8015/health
```

## Current build

| Component | Selected |
|---|---|
| Engine | `flare-inference 0.1.0~git20261027170349.7c22369f-1` from `ppa.local-inference-lab.ai`, same binary on all four nodes |
| Package | `DeepSeek-V4.1-Flash-1017-FLARE@gb10` commit `607c1abf`, deployment `0a377833…`, TP4, native expert scales, signed |
| Orbit | controller spark-r0, cluster `ds41`, persistent group `ds41-flare` ([launch](flare/launch.sh)) |
| Speculation | MTP, up to five drafts, adaptive verification |
| Serving | 1,048,576 context, 32 requests, 4,096-token prefill chunks, Engram tables on disk with RAM scales and 1 GiB row cache |
| KV | 16.6 GiB per GPU, **19,306,112 tokens** (`--memory-limit=-2G`) |
| Memory | spark-r0 110.9 GiB used after loading (budget about 118 GiB) |
| Fabric | CRS812, one 200G port-1 cable per node, two Socket Direct rails, MTU 9000, GID 3; RoCE on both rails |
| GPU clocks | 0–2350 MHz ceiling, persistent; idle downclocking enabled |

Exact identities: [results/deployment.json](results/deployment.json).

Clients: thinking is on by default; turn it off with
`"chat_template_kwargs": {"enable_thinking": false}` (vLLM's `thinking`
option is rejected). Temperature and top_p are fixed at 1 by the package.

**Retired:** the B12X and TileLang vLLM builds. Their containers and images
remain on every node, but the GX10 copies of the 1017 checkpoint were removed
to make room for FLARE, so neither can start without copying it back from a
Spark. Their records stay in [RESULTS.md](RESULTS.md) and `results/`.

## Repository contents

- [flare/](flare/README.md): FLARE install, download, launch and upgrade guide for this fleet.
- [OPERATIONS.md](OPERATIONS.md): runbook — control, recovery, fabric, memory, benchmarks.
- [RESULTS.md](RESULTS.md): current measurements and earlier selections.
- `cluster.sh`, `scripts/cluster.py`, `config/cluster.toml`: cluster TUI and CLI.
- `scripts/`: fabric check and repair, fleet SSH helpers, root controller sources.
- `bench/`: functional, retrieval, mixed-traffic, consistency and fabric checks.
- `host/`: clock-cap service, controller sudoers rule, SSH config block.
- `image/`: the retired B12X and TileLang vLLM image lineages.
- `results/`: qualification evidence.
- [Agent maintenance skill](../SKILL.md): fleet guidance shared by any agent.

This is an operating repository for this fleet; packages, caches and
root-owned configuration live on the nodes. Superseded campaigns removed on
2026-10-24 remain at the Git tag `pre-tilelang-cleanup-20261024`.
