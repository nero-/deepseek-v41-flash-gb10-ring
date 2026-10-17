# DeepSeek-V4.1-Flash on the four-node GB10 ring

Corrected SparkRing vLLM TP4 across two DGX Sparks and two ASUS GX10s.
API: **http://192.168.50.219:8015/v1**. Model: **DeepSeek-V4.1-Flash-TP4**.

**Selected as of 2026-10-17 UTC:** official **DeepSeek-V4.1-Flash-1017** on
all four nodes, with the existing corrected GPU runtime and two small prompt/tool
parser fixes. GLM remains stopped. [Upgrade results and focused LIL screen](results/20261017-checkpoint-upgrade/REPORT.md).

The September GPU stack and selected performance plugins remain in use. Newer
vLLM/FlashInfer correctness, memory and collective changes are assessed in the
[runtime review](results/20261017-checkpoint-upgrade/runtime-review/ASSESSMENT.md);
they are separate follow-up candidates.

## Start, stop and recover

From the Mac:

```bash
cd ~/Agent/Builds/deepseek-v41-flash-ring
./scripts/ring-mode.sh ds                 # start the selected DeepSeek profile
./scripts/ring-mode.sh recover-ds         # coordinated restart after a node reboot/failure
./scripts/ring-mode.sh stop
./scripts/ring-mode.sh status
```

`recover-ds` stops the workload and every mesh supervisor, then starts the
mesh and selected model together. Allow roughly 7–16 minutes for loading and
warmup. It returns when the API is healthy. The script is `ring-mode.sh`.
For **RoCE GID differs**, follow the additional link repair in
[OPERATIONS.md](OPERATIONS.md#roce-gid-differs-after-a-peer-reboot).

Qwen serving on this ring was retired to make room for GLM. Its old stop
entry points remain compatible with DeepSeek recovery; `ring-mode.sh qwen`
reports retirement without stopping DeepSeek. See the
[GLM handoff and storage receipt](../GLM/HANDOFF.md#capacity-and-protected-rollback).

```bash
curl --fail --max-time 5 http://192.168.50.219:8015/health
```

## Current build

| Component | Selected version |
|---|---|
| SparkRing installer | `8b152d65c701f557f62ae6a9a1c3db90771c1df3`, profile `deepseek-v41-flash-tp4` |
| Parent | SparkRing/eugr nightly 2026-09-24; image `sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf` |
| vLLM source | `03c4af34fbe6d2ff863bd03a6ed255c4de96785b` plus complete KK #926/#943 correction at `7b935cb78a3f1f256b04006e82504a651685f72d` |
| B12x source | `c8e461281a3872a0e5de2485ef1df3df6556f07c` |
| Checkpoint | Official DeepSeek-V4.1-Flash-1017, revision `1bae0e1088993b9b82de08f59de5be5a34e42170` |
| Frontend layer | Built 2026-10-17: official tool-turn boundary + KK #921 Python DSML parser |
| Local profile | `engram-adaptive4k-query-indexer-1017` |
| GPU upper clock limit | 2350 MHz on every node, persistent across reboot |

[Deployment identity and plugin hashes](results/deployment.json),
[immutable per-rank images](results/20261017-checkpoint-upgrade/candidate-images.json),
[frontend image recipe](image/1017/README.md),
[compressor correction](image/kk926/README.md), and
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
- `image/`: the selected compressor and frontend corrections, plus two selected plugins.
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

The [switch and runtime upgrade plan](results/20261017-runtime-plan/PLAN.md) is
prepared for the switch arrival. It is research and a staged execution plan;
those runtime and topology changes have not been applied.
