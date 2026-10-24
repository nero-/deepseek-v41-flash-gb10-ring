# spark-ds41f-1022 TileLang build on the switched SparkRing fleet

**Status, 2026-10-24 18:29 UTC: serving on 8015 and kept at the user's
request** ("if it's better we keep it"). Image
`sha256:2fc5565e9c15b005f3297a552131b8973a2f19fb811868a8358a3e99b33491d0`,
containers `ds41f-tilelang-r0..r3`. The fleet is claimed by
`/etc/deepseek-ring/FLARE_STAGING.json`, so the controller's `up` refuses.
The previous selection (`c87a397c…`, image `9f26f0b3718c…`, stopped
`ds41-optimized-rN`) is unchanged and returns with `trial.py restore`.

**After a reboot:** wait for SSH on all four nodes, then
`python3 scripts/trial.py serve` (not `ring-mode.sh recover-ds`). Expect about
2 minutes on warm caches.

A community member reported better speed from Local Inference Lab's
`karmic-kraken-beta` vLLM with spark-ds41f's TileLang kernels and sparknet
collectives. This directory builds that exact release and measured it on our
fleet with the October 21 protocol and the public full grid.

## Results

Same harness as production (pinned LIL 0.7.6, temperature 1, default thinking,
20 s cells, 2048 tokens, no hardware monitor). Aggregate output tok/s.

Focused screen, three runs on one startup, against the October 21 production
medians (three runs, one startup):

| Context | C | TileLang runs | Median | Oct 21 production | Change |
|---|---|---|---:|---:|---:|
| 8K | 1 | 68.6, 69.7, 67.6 | 68.6 | 66.8 | +2.7% |
| 8K | 8 | 222.4, 227.5, 220.8 | 222.4 | 203.1 | +9.5% |
| 8K | 16 | 296.7, 317.7, 289.4 | 296.7 | 285.5 | +3.9% |
| 32K | 1 | 68.7, 70.0, 66.7 | 68.7 | 64.7 | +6.3% |
| 32K | 8 | 206.1, 211.2, 203.2 | 206.1 | 202.8 | +1.6% |
| 32K | 16 | 298.2, 301.0, 294.1 | 298.3 | 289.2 | +3.1% |

Full 25-cell public grid against the October 20 qualification grid (four
drafts, stock boost; one run each):

| Context | C1 | C2 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|---:|
| 8K | 70.8 (+10%) | 106.7 (+14%) | 156.0 (+6%) | 226.4 (+14%) | 292.5 (+9%) | 5513 (+37%) |
| 16K | 69.8 (+7%) | 105.3 (+11%) | 157.4 (+12%) | 211.8 (+8%) | 295.3 (+13%) | 5994 (+43%) |
| 32K | 70.0 (+15%) | 97.8 (+1%) | 139.2 (+0%) | 209.5 (+9%) | 294.5 (+12%) | 6138 (+34%) |
| 64K | 69.1 (+11%) | 102.9 (+7%) | 152.5 (+14%) | 199.8 (+5%) | 284.1 (+11%) | 6105 (+33%) |
| 128K | 62.9 (-3%) | 98.3 (+6%) | 133.4 (-1%) | 189.0 (+1%) | 272.7 (+8%) | 5996 (+37%) |

- Decode gains come from step rate (C1 about 34 steps/s against about 28),
  partly offset by fewer accepted tokens per step (about 2.0 against 2.4 with
  greedy drafts). Prefill is 33–43% faster. Coding probes: median 101.9 against 91.4.
- Single-stream TTFT is about 0.1 s longer (0.45 s against 0.34 s at 8K C1):
  sink rejection holds the first token for one step.
- Functional checks 7/7 (text, code, tools, forced tools, image, thinking).
  Uncached retrieval passed at 122,279 and 961,731 prompt tokens (TTFT
  20.2 s and 218.6 s). `cold-needle.py` exits 1 only because this build omits
  `cached_tokens`; prompts start with a fresh nonce
  ([waiver](validation-waiver.json)).
- Startup 369 s cold, 117 s warm. Head used 100.3 GiB (21.4 GiB available);
  every rank stayed above 20.8 GiB available through the 1M prefill. No
  kernel OOM/Xid/NVRM events; the 1.5 GiB guard never tripped.

Limits: one trial startup; production was not re-measured the same day (the
user declined a control); the grid reference is a different, older startup.
Not tested: mixed traffic, soak, images beyond four, more than 8.6M KV tokens.

### Known differences that remain

- **Images per request: 4** (production 999). The fifth image in a
  conversation returns HTTP 400, as the old limit did before October 17.
- **KV: 10.5 GiB per rank, about 8.6M tokens** (production 20 GiB, 16.34M).
  About 21 GiB is still available on the head.
- Greedy drafts and sink rejection change sampling behaviour from production's
  probabilistic drafts; outputs are not bit-comparable.
- Not managed by the root controller; `trial.py serve`/`restore` are the
  lifecycle until a new root-owned selection is qualified.

## Attempt log

1. The built image passed its GPU, TileLang and sparknet smokes (611 s build).
2. The first start failed in 11 s: the pinned recipe sets
   `PYTHONPATH=/opt/spark3/...`, but the pinned Dockerfile (after spark-ds41f
   #486) installs to `/opt/spark-ds41f/...`, so stock vLLM rejected
   `--engram-config`. `render.py` now uses the image's own path
   ([attempt 1](attempt1/)). Worth reporting upstream.
3. A restore began at 18:03 UTC and was interrupted at the user's request.
   Production was stopped again with the controller; the premature archive was
   moved to `/etc/deepseek-ring/DS41F_TILELANG_20261024.interrupted-restore.json`.

## Source

- [christopherowen/spark-ds41f](https://github.com/christopherowen/spark-ds41f) at
  `9f1565f060ad84a6f06a745a9b7b4191393cc842`; its lock is the promoted
  `spark-ds41f-1022` baseline (image tag `vllm-ds41f-kkref:19f2c20ed4d6-1022-4`).
- `bin/spark build prepare` on the Mac produced
  `.work/build/vllm-19f2c20ed4d6-b12x-236ddff04a5f-99695427`, the same
  directory name as the community build. Every patched tree matches the
  release's `expected_labels`: vLLM `e68aa19c`, b12x `1a647a31`, NCCL
  `6af10aa7`, TileLang `222b895d`, TileKernels `cb2fa41c`, sparknet `f997a594`.
- vLLM is LIL `19f2c20e` plus a **186-patch** series
  (`experiments/2026-10-22-spark-ds41f-1022/vllm/series`), not only the
  0029–0044 TileLang patches. TileLang 0.1.15 carries **three** SM12x patches
  in the repository (the forwarded message says four).

## How it differs from production

| Area | Production | spark-ds41f-1022 |
|---|---|---|
| vLLM | LIL `8244d1c4` (Oct 15) on the eugr B12X base | LIL karmic-kraken-beta `19f2c20e` + 186 patches on vLLM nightly `af1c0149` |
| Kernels | B12X attention, linear, MoE, vocab | TileLang DS4.1 family + DeepSeek TileKernels 2.0.0; B12X only for vision/loader |
| Small collectives | RoCEnante ABI 8: one-shot <512 KiB, pipelined two-shot to 128 MiB | sparknet 0.5.0 one-shot ≤2 MiB for every TP collective; NCCL 2.30.7 (patched) above |
| Fabric | CRS812 switch, port 1, two rails | Switchless ring; switched clique is a documented but **unmeasured** sparknet path |
| Precision | BF16 target head, NVFP4 draft/Markov heads | FP32 logits from a packed exact BF16 head, reference-precision MoE/mHC/WO, batch-invariant |
| Speculation | DSpark 5, probabilistic drafts, native adaptive cost | DSpark 5, greedy drafts, rule-based budget (row cost 0.035), dead-row skip, sink rejection, late admission |
| Prefill | Adaptive 4K plugin, query-indexer TP plugin | Sequence-parallel prefill, one concurrent prefill |
| KV | 20 GiB/rank, 16.34M tokens | 10.5 GiB/rank, ~8.58M tokens |
| Images/request | 999 | 4 |
| Host kernel | 4 KiB `7.0.0-1019-nvidia` | Qualified on 64 KiB + memory-saver DKMS; a third site ran TP4 on 4 KiB |

Published figures are **not comparable** to ours: their TP4 release measured
16 streams 256.5 tok/s and one stream 74.1 tok/s with their own greedy suite,
while our LIL 0.7.6 (temperature 1, default thinking) medians are 285.5 (8K
C16) and 66.8 (8K C1). The third-site receipt shows a 36.7 ms idle step; ours
is about 36 ms per step at C1. Only a matched run on this fleet can decide it.

## Site changes (everything else is the recipe as rendered)

`scripts/render.py` loads the pinned `bin/spark`, resolves `tp4-ring`, and
applies only these, recorded in each launch manifest:

- sparknet's switched clique: `SPARKNET_ROCE_TOPOLOGY=direct`, both port-1
  rails, no peer map; sparknet's `switched` NCCL profile instead of the
  ring-only policy; `NCCL_CROSS_NIC=0`; no traffic class (CRS812 QoS unset);
- bootstrap on rail A (`10.10.10.1`), sockets on `enp1s0f1np1`;
- port 8015 and model `DeepSeek-V4.1-Flash-TP4`;
- our local 1017 checkpoint (read-only) and a fresh trial cache;
- the production SparkRing seccomp profile instead of `unconfined`.

spark-ds41f's own launcher rejects four-node switched fabrics, so it is not
used to start. Its four-rank Engram/reduce-scatter exchange always relays the
opposite rank through a neighbour; on a switch this works but costs prefill.

## Procedure

`scripts/trial.py PHASE`, in order. Each phase writes receipts under
`results/20261024-trial/` and refuses to repeat itself.

| Phase | Effect |
|---|---|
| `preflight` | Read-only identity, selection, staged-input and harness checks (**passed**) |
| `stop` | **Downtime begins.** Controller `down`; interlock `/etc/deepseek-ring/FLARE_STAGING.json` |
| `build` | Pull pinned base; spark-ds41f's builder on spark-r1 (memory-guarded) |
| `distribute` | `docker save | load` over rail A; identical layers on all ranks |
| `start` | FlashInfer prebuild, cache drop, ranks 1–3 then 0, 1.5 GiB fail-closed startup guard; functional, loaded clocks, 128K cold retrieval |
| `bench` | Three LIL 0.7.6 screens: 8K/32K, C1/C8/C16, 20 s, 2048 tokens, temperature 1, default thinking, coding probes |
| `restore` | Stop trial, archive marker as `DS41F_TILELANG_20261024.finished.json`, controller `up`, verify identities |
| `control` | Same-protocol screen of restored production |

Rollback at any point: `trial.py restore`. The selection file and canonical
`ds41-optimized-rN` containers are never modified. The controller refuses
`up` while the marker exists (its message names FLARE; this marker is the
shared interlock).

## Staging receipts

- Build checkout on spark-r1: `~/builds/ds41f-tilelang-20261024/spark-ds41f`
  (`build check` passed on the host).
- Seccomp copy on every rank: `~/ds41f-tilelang-20261024/seccomp.json`,
  SHA-256 `fd0fdc80…2513`, identical to production.
- Side effect: an SSH probe added fabric-address host keys to spark-r1's
  `~/.ssh/known_hosts`.
