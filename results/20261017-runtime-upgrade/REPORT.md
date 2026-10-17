# October 17 runtime upgrade qualification

**Selected and serving on all four nodes.** The official 1017 checkpoint now
runs on the qualified October 15 eugr/KK/FlashInfer runtime, with a separately
qualified 16.5 GiB KV budget per GPU. Head total used memory peaked at
**115.10 GiB**, below the user's 118 GiB ceiling. See [final fleet audit](final-audit.json)
and [deployment identity](../deployment.json).

## Composition

The candidate uses eugr's immutable ARM64 `nightly-20261015` base, vLLM KK
`8244d1c44348ae8a5bbfc9f1b607021652283ed4`, and FlashInfer 0.7.1 at
`91271757f7746f3dfb58f7c2aeb44a663389de9e`. B12x now comes from
`flashinfer.experimental.b12x` through its compatibility namespace. The retired
`b12x_loader` plugin is removed; vLLM's built-in loader is used. Source and
native identities are in [pins.json](pins.json) and the
[image recipe](../../image/runtime-20261017/README.md).

The layer retains the complete qualified CUDA 13.4.2 / patched NCCL 2.32.3
bundle and switchless RoCEnante one-shot/all-gather transport. Its provider
source guards and preparation-cache interface were adapted to the new
FlashInfer provider. No SIRCL, new two-shot transport, switch topology, clock
change, checkpoint conversion or target-head quantization is introduced.
The official 1017 tool-turn encoder correction is reapplied; upstream now
contains the KK compressor and Python parser corrections.

The existing adaptive 4K prefill and guarded query-indexer plugins remain
mounted with their original hashes. The model keeps DSpark5, Engram projection
TP, 16 active sequences, an 8192-token batch ceiling, 1M context, memory
utilization 0.83 for the initial comparison, and a 0–2350 MHz GPU clock policy.
The final explicit KV setting below supersedes that utilization fraction. Target head is full BF16;
draft and Markov NVFP4 settings remain enabled. Attention compute is explicitly
`auto` to preserve the prior policy during this runtime comparison; the new
upstream BF16 attention default is a separate numerical/performance tradeoff.

## Sampling

The verified checkpoint has no `generation_config.json`, and its HF config
contains no sampling defaults. The candidate explicitly sets temperature 1,
top_p 1, top_k -1, min_p 0 and repetition penalty 1. Presence/frequency
penalties resolve to 0. There is no generation-config output-token cap;
clients should still supply `max_tokens` appropriate to their task and the
remaining context. Client overrides such as top_p 0.95 remain effective.
[Actual candidate request-parser audit](sampling-audit-candidate.json).

The original server already used top_p 1 for omitted client fields; the old
full baseline's LIL payload omits top_p. Its comparison with candidate top_p 1
therefore does not change that sampling setting. The new `lil_top_p.py` adapter
adds only top_p to the existing harness requests and preserves thinking and
other fields. It is different from the historical `lil_matched.py`, which
forces thinking off. Sampling screens and the language check are recorded below.

## Completed low-level qualification

- CPU/source/manifest/loader contracts passed, including rejection of a
  corrupted manifest and the preparation cache's repeated-gather contract.
- 128 upstream parser tests passed.
- All four ranks passed 40 collective cases each: BF16/FP16/FP32 all-reduce
  through 2 MiB, BF16/int32 all-gather through 16 MiB per-rank shards, eager and
  repeated CUDA graphs, and a real oversize NCCL fallback. Each rank recorded
  5,563 operations, 171,350 completed writes and error sequence zero.
- BF16 prefill matched the FP32 oracle and passed 5,000 contention replays
  with zero mismatches under 38,000 noise kernels. Targeted DSA/BF16/vocabulary
  tests passed (11); dense-GEMM races passed (6); dynamic-MoE races passed (5).
- Embedded cubins were extracted from 15 fresh rank-2 cache objects and
  disassembled successfully. The dense-GEMM artifacts include the expected
  `FENCE.VIEW.ASYNC.S` instructions. Hashes bind objects, compiler/source/cache
  metadata, cubins and disassembly; this supplements the numerical race tests.

[Native qualification summary](native-qualification.json),
[representative native evidence](native-sass-r2.json),
[BF16 replay evidence](bf16-contention.json). Finite checks are not an
exhaustive correctness or broad model-quality equivalence proof.

Initial test-harness setup errors (coordinator missing `all_gather_object`,
noise-kernel compilation attempted after preparation freeze, and parser test
namespace layout) were corrected before the recorded passing runs. Their
failed logs remain in the private campaign. The framework/image was not
changed to conceal a test failure.

## Initial serving qualification

All seven functional checks, four tool round trips, twelve known-answer
questions and both 2048-token consistency probes passed. Late coarsened KL
was 0.00484 / 0.01349 with top-token agreement 98.49% / 96.04%. The fresh
125,237-token retrieval passed with zero cached tokens, 30.96 seconds to first
content. Query-indexer sharding activated with its exactness guard on; no
exactness-disable events occurred. Loaded clocks were 2320–2333 MHz.
[Serving status](serving-status.json), [consistency](consistency.json),
[cold retrieval](cold-128k.json), [loaded fleet audit](candidate-audit.json).

The new runtime exposes 14.96 GiB / 12,028,364 tokens of KV capacity versus
16.25 GiB / 13,019,717 tokens in the original runtime, at identical 0.83
memory utilization. The 1M per-request context limit is unchanged. This is a
net capacity tradeoff of the bundled runtime, not an isolated attribution to
one allocator change.

The fresh 1,008,437-token retrieval also passed with zero cached tokens and
the exact expected code, taking 319.69 seconds to first content. The earlier
same-checkpoint old-runtime check took 345.88 seconds; these are single probes,
and the new one followed monitor cleanup, so this is not an isolated runtime
speedup claim. [1M retrieval](cold-1m.json).

## Same-checkpoint baseline

The original qualified runtime completed the public LIL 0.7.6 25-cell grid
on official 1017 weights, temperature 1, default thinking, 20-second sustained
cells and 2048-token output ceiling. No errors or invalid cells were reported.
Aggregate output tokens/s:

| Context | C1 | C2 | C4 | C8 | C16 |
|---|---:|---:|---:|---:|---:|
| 8K | 59.09 | 89.97 | 121.70 | 192.18 | 269.63 |
| 16K | 60.59 | 94.04 | 127.16 | 189.73 | 261.05 |
| 32K | 58.40 | 86.37 | 122.48 | 193.09 | 255.83 |
| 64K | 59.65 | 85.38 | 118.28 | 186.86 | 252.67 |
| 128K | 57.31 | 85.52 | 123.35 | 182.70 | 244.91 |

Cold scout prefill: 4,049 / 4,311 / 4,317 / 4,337 / 4,174 prompt tokens/s
at 8K / 16K / 32K / 64K / 128K (one sample each).
[Raw full baseline](baseline-full.json), [source identity](baseline-source.json).

## Candidate full grid at top_p 1

All 25 cells completed with zero errors, underfilled cells or exact-loop failures.
These measurements keep the baseline 0.83 memory setting:

| Context | C1 | C2 | C4 | C8 | C16 |
|---|---:|---:|---:|---:|---:|
| 8K | 59.30 | 89.75 | 126.85 | 182.48 | 260.41 |
| 16K | 60.36 | 92.32 | 128.03 | 179.20 | 255.86 |
| 32K | 58.44 | 90.29 | 128.93 | 182.58 | 257.79 |
| 64K | 52.62 | 94.08 | 122.91 | 191.24 | 253.07 |
| 128K | 58.45 | 91.77 | 123.80 | 178.36 | 244.71 |

Cold scout prefill: 4,019 / 4,274 / 4,344 / 4,320 / 4,253 prompt tokens/s,
within 1.9% of the old runtime in this single-sample comparison. Five coding
probes completed; median 94.0 tokens/s versus baseline 94.8. No CJK ideographs
were found in those five outputs in either arm.

The full grid alone is mixed: C2/C4 often improve, C8 at 8–32K is about 5%
lower, C16 is mostly close, and 64K C1 has an 11.8% outlier. Speculative
acceptance also changes with the generated text. Repeat decisive cells before
attributing these differences to kernel speed or selecting the runtime.
[Raw candidate grid](candidate-full.json), [request provenance](candidate-full-source.json).

## Sampling and performance repeats

The new image completed two further nine-cell screens: C1/C8/C16 at
8K/64K/128K, top_p 0.95 then top_p 1. Both had zero errors or invalid cells.
The repeated top_p 1 values were:

| Context | C1 | C8 | C16 |
|---|---:|---:|---:|
| 8K | 61.44 | 187.41 | 262.46 |
| 64K | 59.15 | 178.09 | 253.13 |
| 128K | 58.96 | 185.62 | 251.22 |

The 64K C1 low result did not repeat. At 8K the mean of the candidate's two
runs was 3.8% below the old baseline at C8 and 3.0% below at C16; 128K C8/C16
were -0.4%/+1.2%. This supports broadly similar performance with a modest
short-context concurrency tradeoff, not an across-the-board speedup. The
16K/32K full-grid C8 losses were not separately repeated.

Neither top_p arm consistently wins across the nine cells. Changing sampling
also changes generated text and speculative acceptance; these finite screens
do not establish a sampling speed advantage. Preserve the official top_p 1
recommendation unless the separate language screen reveals a reason to change.
[Paired tables](benchmark-comparison.json), [top_p 0.95](candidate-p095-screen.json),
[top_p 1 repeat](candidate-p1-repeat.json).

## English language screen

Twenty-four paired responses (12 per sampling arm) completed: 27,648 generated
tokens at top_p 1 and 27,574 at 0.95. Neither arm produced any detected CJK
ideographs in reasoning or visible answers. The six subjects include technical
design, mathematics, debugging, tutorial writing, physics and fiction. Half
use ordinary English user prompts; half add an English-only system instruction.
Both thinking and non-thinking modes are included.

This is a bounded purposive screen, not proof that rare language drift cannot
occur. The 3072-token thinking and 1536-token non-thinking ceilings truncated
12/12 and 11/12 replies in the respective arms; longer reasoning remains
untested by this particular screen. All raw requests, responses and per-channel
counts are retained in [language-ab/summary.json](language-ab/summary.json).
Together with the mixed speed results, there is no observed reason here to
replace the official top_p 1 recommendation with 0.95.

## Historical monitor cleanup

After both timed sampling screens, 14 eleven-day-old detached GPU polling
loops on gx10-r0 were stopped. Each was verified by UID, parent, exact command,
PID start time and unconsumed output pipes. No model worker was stopped by this
cleanup. These loops were present throughout the old/new full grids and both
sampling screens. Later KV checks therefore also follow this background-process
cleanup; do not attribute their differences solely to KV allocation.
[Exact cleanup receipt](orphan-monitors-cleanup.json).

## Storage and rollback

At the user's request, all GLM checkpoints were retired across the fleet,
reclaiming 1,028 GiB total. GX10 free space after cleanup was 221/225 GiB.
No full GLM weight copy remains. Metadata and deletion receipts are in
`../GLM/results/checkpoint-retirement-20261017` relative to the repository root.
GLM startup/profile controls reject the retirement marker until a replacement
build is downloaded and qualified. DeepSeek weights and rollback images were
preserved. An older rejected SIRCL image was removed only from the two GX10s;
its copies remain on both Sparks.

Runtime rollback uses the SAME official 1017 checkpoint, so it needs no weight
transfer. Private trial/selection configs, full logs and rollback orchestration
are under `~/Agent/Diagnostics/deepseek-v41-flash-ring/runtime-20261017`.
The older checkpoint downgrade is a different operation and must not be used
as a runtime rollback.

## Final KV qualification and selection

The selected command adds `--kv-cache-memory-bytes 17716740096` on every
rank: **16.5 GiB per GPU**. This explicitly overrides the still-recorded 0.83
memory-utilization fraction; changing that fraction alone will not resize KV.
Measured logical capacity is **13,483,747 tokens**, 12.1% above the first
new-runtime trial and 3.6% above the old runtime's 13,019,717 tokens. This
increases room for concurrent long histories; it does not guarantee faster
decode or sixteen simultaneous full 1M contexts. Context remains 1,048,576
per request and the scheduler still permits 16 sequences.

The selected allocation passed a six-cell focused LIL screen, eight overlapping
decoders plus fresh 128K retrieval, a second fresh 1M retrieval, and final
fleet/clock/plugin checks. The adaptive prefill budget activated at 4096 under
contention and the indexer numerical guards stayed enabled. Final screen,
aggregate output tokens/s:

| Context | C1 | C8 | C16 |
|---|---:|---:|---:|
| 8K | 64.23 | 180.18 | 262.80 |
| 128K | 62.57 | 170.31 | 254.73 |


A final C8 repeat measured **189.59 / 175.31 tokens/s** at 8K / 128K,
versus **180.18 / 170.31** in the first KV screen. Their two-run means are
184.89 / 172.81, about **3.8% / 5.4% below** the old-runtime baseline. The
128K mean is also about 5.0% below the first new-runtime two-run mean.
The final repeat alone is within 5% of the old baseline at both contexts.
The larger-KV C8 runs verified more draft tokens per step than the initial
new-runtime screens; workload-dependent adaptive verification is a possible
contributor, not a proven cause. These data do not isolate the effect of KV
allocation from profiling, restart, cleanup and stochastic output. The lower
first cells remain part of the decision; long-context C8 is the clearest cost.
[Raw final C8 repeat](kv-c8-repeat.json).

[Focused screen](kv-final-screen.json), [mixed load](mixed-load.json),
[1M retrieval](kv-cold-1m.json), [capacity](kv-capacity.json).
The full 25-cell runtime comparison above used 0.83; this final focused check
uses the larger KV allocation and follows the monitor cleanup. It is not a
second full-grid benchmark or an isolated KV speedup experiment.

Head usage is measured as **MemTotal minus MemAvailable**, including model,
OS and other non-reclaimable usage, rather than container RSS or GPU allocation
alone. Total RAM is about 121.69 GiB. The observed campaign peak was
**115.10 GiB**, leaving 2.90 GiB below the requested ceiling and
about 6.59 GiB available at that peak. A finite 2-second
sampler covered startup and load. The temporary 117.5 GiB abort guard did not
trigger and was stopped after qualification. This is a tested allocation with
margin, not an OS-wide hard limit: unrelated host processes or different future
workloads can change total usage. Keep that margin when changing settings.
[Memory evidence](kv-memory-guard.json), [whole-campaign samples](host-memory-samples.jsonl).

The runtime is selected for its upstream correctness fixes, current provider
integration and restored KV capacity. The matched throughput comparison is
mixed, with concurrency losses including the final long-context C8 result; no universal performance
improvement is claimed. `top_p=1` remains selected. The target head remains
BF16, and official checkpoint precision is unchanged. The new large-message
collectives and switch/SIRCL work remain separate candidates.

The normal controller now owns `ds41-optimized-r0` through `r3` with the new
image on every rank. The previous runtime is retained as
`ds41-rollback-runtime-rN`; the first new-runtime 0.83 trial is also stopped and
retained. Private root config backups are on spark-r0 under
`/var/lib/deepseek-ring/experiments/runtime-20261017/`. The image's immutable
build-time `serving_qualified:false` predates its tests; this external report
and [promotion gate](promotion-gate.json) record the completed qualification.

The final audit helper initially compared Docker entrypoint and command
arrays separately. Docker had split the executable from its arguments; the
complete command was correct. The check was fixed to compare combined argv,
matching the installed controller, and the audit passed. Both attempts are
recorded in `kv-qualification-status.json`; no image or serving change was
needed for this harness correction.

The host sampler recorded 296 additional swap-out pages (1.16 MiB) across its 52-minute window; about 0.99 GiB of swap was already in use. This was a small amount of paging, not a zero-swap run. No OOM or container restart occurred.
