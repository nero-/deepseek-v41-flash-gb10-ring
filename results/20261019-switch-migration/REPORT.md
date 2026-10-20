# CRS812 and RoCEnante pipelined two-shot

Qualification completed October 20 UTC. The selected profile uses switched
RoCEnante ABI 8, DSpark4 with the native C1 verification cap of three, adaptive
4K prefill from one contending decoder and driver stock GPU boost.
The 25-cell LIL grid, functional checks, uncached near-1M retrieval, mixed
image/decode and lifecycle checks passed. Sustained 70 C1 and 300 C16 were
not established. See `qualification.json` for collective/source evidence and
`final-qualification.json` for the final serving result.

## What changed

The user installed the switch and host network configuration. Each node has
one physical 200G port-1 connection, with two Socket Direct rails sharing that
bandwidth. Both rails use MTU 9000 and IPv4 RoCEv2 GID 3. The GX10 order remains
rank 2 = gx10-r1 and rank 3 = gx10-r0. Exact addresses and recovery commands are
in [OPERATIONS](../../OPERATIONS.md#switched-fabric).

The controller now checks addresses, links, direct routes, GIDs and jumbo
reachability without starting the old mesh. Fabric, hairpin, agent, mesh and
model services from the physical ring remain disabled. `stock-up` rejects
switched configurations before stopping the serving workload. The installed
SparkRing package remains because its container-spec library and seccomp
profile are still dependencies.

The new image is `sha256:9f26f0b3718ccca889cfd93cb72e2165b6d4c11dd9dc93fe65f585883537f2db`.
It retains the qualified October 15 eugr/vLLM/FlashInfer math runtime and
October 17 corrections. Its changes are limited to transport selection,
the vLLM adapter and the complete three-file upstream ABI-8 buffer-lifetime fix.
The old SparkRing provider shadowed FlashInfer's RoCEnante module; the new,
verified import hook selects the FlashInfer provider in every spawned worker.

The official 1017 checkpoint, published precision, full vocabulary, BF16 target
head, NVFP4 draft/Markov, native DSpark/adaptive verification, disk Engram, local
prefill/indexer plugins, HF tokenizer and generation defaults are retained.
KV remains 20 GiB/rank, max sequences 16, batch ceiling 8192, context 1M and
image limit 999. Initial comparisons used the persistent 0–2350 MHz ceiling.
The user subsequently authorized changing or removing it; stock-clock trials
are recorded below. Driver stock boost was subsequently made persistent.

## Integration findings

- [FlashInfer PR #10](https://github.com/local-inference-lab/flashinfer/pull/10)
  provides pipelined two-shot; it is already present in our base provider but
  requires an explicitly allocated pipe and adapter integration.
- The compatibility `AllReduce.from_exchange_group(..., **_ignored)` silently
  discards `pipe_bytes` and `pipe_threshold`. The first candidate failed the
  collective routing check and was never used to serve the model. The corrected
  adapter calls `AllReduce(...)` directly, with the same Gloo exchange group.
- [PR #11](https://github.com/local-inference-lab/flashinfer/pull/11) provides
  native packaging and [PR #12](https://github.com/local-inference-lab/flashinfer/pull/12)
  variable-length gathering. Those facilities are not activated by this recipe;
  the latter's allocation remains zero.
- [The ABI-8 correction](https://github.com/local-inference-lab/flashinfer/commit/f3bbd1ce79cb9a62afb88b367580b0583db167ee)
  waits for NIC send completion before reusing two-shot buffers. Python,
  proxy C and CuTe changes are kept together.
- A 64 MiB pipe would miss the model's 8192 × 5120 BF16 all-reduce. The selected
  trial allocates **128 MiB**, and serving logs confirm an actual **80 MiB**
  reduction takes two-shot. Small one-shot and logits all-gather dispatches
  are also confirmed.
- `DS41_ROCE_PIPE_BYTES` and `DS41_ROCE_PIPE_THRESHOLD` are local adapter knobs,
  not upstream vLLM environment variables. All ranks must agree. Pipeline
  block and chunk sizes are constructor arguments; inventing similarly named
  environment variables would not tune them.

Patched NCCL 2.32.3 remains the fallback for unsupported/oversized operations.
This is not SIRCL and does not remove NCCL wholesale. The four-channel NCCL
policy is retained, but physical-ring maps, forced Ring algorithm and switchless
mode are removed. Host/switch QoS, PFC and ECN have not been inspected or changed;
passing fabric tests does not establish that these policies are enabled.

## Qualification and comparison protocol

The stopped-fleet baseline passed 40 collective cases/rank. The corrected
two-shot image passed 58 local cases/rank: FP16/BF16/FP32 all-reduces through
128 MiB, all-gathers through 16 MiB shards, graph replay and 130 MiB NCCL fallback.
Each rank posted 9,184 operations and completed 2,236,812 writes with no proxy
error; traffic was evenly distributed across both HCAs.

The upstream test module pinned to the ABI-8 fix passed **23 tests/rank**,
covering numerical comparison, one-shot bitwise agreement, mixed graphs,
proxy catch-up, external regions and fail-stop behavior. Its successful
teardown logs include process-group cleanup warnings; these are not serving
failures. Seven workstation adapter contract tests also passed.

Native/proxy/JIT caches are separate from the switched baseline. Only validated
schema-22 math tuning decision JSON was reused per rank, preserving its namespace
and identities; no executable artifacts were copied. Serving reused 1,878
weight decisions and 281 state decisions, with no new measurements.

Serving comparisons use the unchanged public LIL **0.7.6** source, SHA-256
`c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553`,
on gx10-r0, API port 8015, temperature 1, other model/server defaults,
20-second cells, 2048 maximum output tokens and `--no-hw-monitor`.
This is a **focused 8K C1/C8/C16 comparison**, with 64K/128K prefill scouts,
not a new full 25-cell grid. Coding uses five runs on each initial arm.
C8/C16 numbers are aggregate output throughput.

| Switched serving arm | 8K C1 | 8K C8 | 8K C16 | 64K prefill | 128K prefill |
|---|---:|---:|---:|---:|---:|
| Original provider + switched networking | 62.74 | 197.60 | 281.66 | 4340 | 4247 |
| Two-shot, 1 MiB crossover | 61.48 | 195.60 | 263.95 | 4543 | 4466 |
| Same two-shot arm, repeat | 61.96 | 193.49 | 269.90 | 4413 | 4449 |
| Two-shot, 2 MiB crossover | 65.49 | 195.90 | 270.31 | 4480 | 4404 |
| Two-shot, 512 KiB + automatic OMP | 61.12 | 199.16 | 267.62 | 4514 | 4484 |
| Same settings, fixed 4096 batch budget | 61.83 | 183.78 | 272.56 | 3887 | 4113 |
| Draft4, 8192 ceiling, adaptive 4K from one decoder | 64.43 | 198.73 | 273.91 | 4529 | 4481 |
| Same draft4, performance CPU cores only | 63.77 | 198.14 | 266.98 | 4514 | 4425 |
| Same draft4, stock GPU clocks, original CPU affinity | 64.80 | 198.69 | 273.37 | 4635 | 4556 |
| Draft3, stock clocks, same batch/transport settings | 68.70 | 201.19 | 265.78 | 4591 | 4542 |
| Draft4, temporary 0–2700 MHz ceiling | 62.25 | 196.61 | 272.68 | 4051 | 4390 |

Units are tokens/s. The first two-shot arm improves long prefill but its C16
screen is slower. C1/C8 remain close. The 2 MiB crossover did not recover C16. A lower 512 KiB crossover plus
automatic CPU thread management also failed to establish a C16 gain in its
first screen. These are measured results, not a successful crossover diagnosis.
Adaptive speculation and stochastic outputs also change work per step;
normalizing by accepted length alone does not fully remove that difference.

The temporary 2700 MHz ceiling did not improve the draft4 screen and was
removed on all four nodes. During a separate instrumented cold 125,239-token
retrieval, observed active clocks were about 2398–2502 MHz, temperatures peaked
at 79°C, and no swap counters advanced. Retrieval passed with zero cached tokens
and 28.91 s TTFT. These telemetry samples were collected separately from LIL;
they do not establish the clocks during each timed decode cell. Driver stock
boost was restored. The persistent service still carried the old 2350 MHz limit
at that point; the final selection below makes stock boost persistent.

A temporary native Torch profiling configuration captured eight worker execution
intervals at each of C1 and C16 on all four ranks, with approximately 8K record
prompts and adaptive draft4. Individual CUDA graph kernel events are present,
not just graph launches. Automatic stop and explicit cleanup completed. The
profiling configuration was then removed and the retained draft4 containers
selected again. Raw traces are in the private campaign archive;
[the compact summary](native-profile-summary.json) records all ranks.

The C16 rank-zero trace spans 1163.72 ms of GPU activity. Its materialized
W4A8 MoE phase1/phase2 kernels account for 406.72/208.66 ms of summed kernel
duration, with 320 calls each. All MoE kernels sum to about 633.89 ms;
RoCEnante kernels sum to 141.12 ms. C1 shows the same main MoE kernels and
substantial overlapping L2 prefetch. Kernel sums can overlap across streams;
these are diagnostic durations, not additive critical-path attribution or
unprofiled throughput. This evidence prioritizes the exact MoE path over a
speculative sampling optimization.

Both initial arms passed all seven functional checks (including tools, vision
and reasoning), and fresh uncached retrieval at 125,239 actual prompt tokens.
The cold retrieval's TTFT was 29.52 s on the baseline and 28.92 s on two-shot.
Finite checks do not establish universal output equivalence.

The forced `OMP_NUM_THREADS=16` setting disabled vLLM's built-in transition
from parallel weight loading to one Torch thread for serving. Removing that
override produced confirmed 20-to-1 transitions in all four workers and engine
processes. Both changes in the 512 KiB arm were measured together; no separate
CPU-thread speedup is claimed. Its head loaded at 117.33 GiB total used.

The initial DSpark5 graph ladder ended at 96 tokens. A 96 × 5120 BF16
reduction is 960 KiB, below the initial 1 MiB crossover. The 512 KiB trial routes
that size through two-shot, but isolated collective savings did not translate
into a demonstrated aggregate C16 gain in this screen.

The user subsequently set an optimization goal of approximately **70 C1 / 300
C16** and authorized a **4096-token batch-budget comparison**. Those targets
were not established by these initial screens. The subsequent trials and final
qualification follow below; the ideal targets remained unmet.

The fixed 4096-token trial did not establish a sustained decode gain and slowed
standalone long prefill. Its head loaded at 116.50 GiB used. Functional checks
and fresh 125,239-token retrieval passed, with 30.80 s cold TTFT.

A separate matched mixed-traffic comparison used one ongoing decoder and two
fresh roughly 29K prompts, repeated twice. With the 8192 ceiling and the
previous minimum of four decoders for adaptive reduction, p95 content-chunk
gaps during prefill were 1.827/1.831 s. Fixed 4096 reduced them to 1.004/1.003 s,
about 45%, while the incoming prompts' TTFT increased from approximately
7.7/13.5 s to 8.2/14.5 s. No errors occurred. These are SSE chunk gaps, not
individual token latency. See `mixed-batch-comparison.json`.

The draft4 trial restored the 8192 allocation ceiling, enabled the existing
4096 adaptive quantum from one contending decoder, and reduced DSpark width
from five to four with a matching graph ladder. Its head loaded at 117.63 GiB
total used. It passed the seven functional checks and fresh 125,239-token
retrieval with 28.82 s TTFT. These combined changes are not an isolated
measurement of draft width.

Pinning existing serving threads to the ten 3.9 GHz performance CPU cores
did not improve throughput. Every thread's original affinity was restored.
Removing the GPU ceiling did not establish a decode gain in the first matched
draft4 comparison; 64K/128K prefill improved modestly. A separate instrumented
cold prompt showed approximately 2411 MHz on most nodes and occasional
2470 MHz on rank 2, with no fresh swap activity. Resetting clocks does not
mean continuously running at the advertised 3003 MHz maximum.

Draft4 at 32K measured C1/C4/C8/C16 of 63.38/129.20/201.73/270.92 with the
2350 ceiling, and 61.04/134.84/200.90/271.58 at stock clocks. These stochastic
screens do not establish a clock-induced change in acceptance.

With draft4 at stock clocks, the adaptive-one-decoder mixed-traffic check
measured p95 chunk gaps of 0.972/0.974 s and fresh-prompt TTFT of
7.95/14.03 s and 8.22/14.31 s. It retains standalone 8K prefill while limiting
the mixed-traffic quantum. Clock and draft settings also differ from the
earlier fixed-budget comparison. Three streamed requests, each containing
five distinct 1024px images and fresh text padding, passed while a background
request decoded. Actual prompt lengths were 7,340/7,396/7,452 tokens with no
prefix reuse. This checks mixed image processing, not the full 999-image limit.

The draft3 screen improved C1 but reduced C16; it did not provide a balanced
gain. Its five-run coding median was 91.41 tokens/s, versus 94.71 for draft4
with the earlier 2350 ceiling. That coding comparison is not clock-matched.
Draft3 started at 117.37 GiB head memory, passed the functional checks and
fresh 125,236-token retrieval (28.23 s TTFT). Draft4 was restored for the
next bounded clock-ceiling comparison. No 70 C1 / 300 C16 result is established.
Public-source engine research is recorded in [ENGINE-RESEARCH.md](ENGINE-RESEARCH.md).

## Direct transport measurements

The pinned upstream `benchmark_roce_twoshot.py` was run with the model stopped,
four ranks, both rails and the serving toolchain. BF16 results use the maximum
over ranks of each rank's median replay of 20-op graphs, ten replays. One-shot
and two-shot outputs agreed bitwise at their common tested sizes.

| Message | One-shot | Two-shot | Patched NCCL |
|---|---:|---:|---:|
| 256 KiB | 100.9 µs | 116.9 µs | 150.7 µs |
| 512 KiB | 142.9 µs | 102.3 µs | 162.8 µs |
| 1 MiB | 206.2 µs | 136.1 µs | 207.9 µs |
| 1.875 MiB | 340.2 µs | 174.9 µs | 275.9 µs |
| 2 MiB | 350.2 µs | 192.5 µs | 300.2 µs |
| 4 MiB | — | 330.6 µs | 368.8 µs |
| 16 MiB | — | 1113.6 µs | 1188.3 µs |
| 80 MiB | — | 5275.7 µs | 5547.0 µs |

At 80 MiB, two-shot achieves 23.9 GB/s of collective bus bandwidth, about 96%
of the theoretical 25 GB/s physical link. This limits the remaining gain from
transport tuning alone; model throughput includes considerable other work.

Reducing chunks from 128 KiB to 64 KiB or increasing blocks from four to eight
did not establish a broad improvement. Their 80 MiB results were 5225.1 and
5263.6 µs, respectively; smaller-message results varied in both directions.
The upstream defaults remain the serving candidate's settings. Direct transport
tests do not alone establish the best crossover inside a loaded model.

### Old-provider versus new-provider comparison

Both providers were subsequently measured on the stopped fleet with the same
requested 2418 MHz lock, fabric, toolchain, CPU policy and exact numerical
fixtures. The images share the math runtime but have different transport
compositions. Each case uses 20 replays of a ten-operation graph; reported
values are the maximum over ranks of the per-rank median. The p95 in raw
results describes graph-average latency, not individual-operation tails.
Input values vary by rank, row and column, and change between replays.
Every eager/replay output passed its exact oracle on every rank.

| Operation and shape | Old one-shot | New configured path |
|---|---:|---:|
| BF16 all-reduce, 48 × 5120 | 127.2 µs | 151.1 µs, one-shot |
| BF16 all-reduce, 64 × 5120 | 126.9 µs | 102.6 µs, two-shot |
| BF16 all-reduce, 80 × 5120 | 186.9 µs | 134.3 µs, two-shot |
| BF16 all-reduce, 96 × 5120 | 207.8 µs | 180.0 µs, two-shot |
| FP32 all-gather, 48 × 32320 per rank | 1144.1 µs | 1133.3 µs |
| FP32 all-gather, 80 × 32320 per rank | 1893.5 µs | 1882.3 µs |
| FP32 all-gather, 96 × 32320 per rank | 2268.5 µs | 2278.9 µs |

Large all-gathers were within approximately 1%; this does not support a new
large-gather regression. Small one-shot timings varied in both directions,
and the 48-row case was slower in this screen. Two-shot saved time at the
tested larger decode reductions. Synthetic repeated collectives omit model
compute and cannot by themselves explain or predict serving throughput.
Stock clocks were restored before starting the next serving trial.
See `provider-comparison.json` for raw results and identities.

## Recovery and evidence

Private campaign:
`~/Agent/Diagnostics/deepseek-v41-flash-ring/switch-migration-20261019`.
It contains complete selections, logs, raw tests, image/build receipts,
microbenchmarks, tuning-decision reuse hashes and rollback tooling.

The practical fallback is `baseline-specs.json` with **switched** addresses
and the previous immutable image, plus retained stopped containers
`ds41-before-switch-baseline-rN`. No checkpoint transfer is required.
`restore_baseline.py` accepts the recorded one- or two-MiB trial specifications
only with the fleet stopped. See OPERATIONS. Historical ring containers and
older rollback helpers must not be started directly on the switch.

## Compact MXFP4 MoE prequalification

The profile-guided candidate was built separately as
`sha256:452a5d89b8de34d3a166fc344bc9aef2058f1c6d2f67af8ce355ba2a77d28cd6`.
It backports the coherent MoE implementation and quantization/cache dependencies
from FlashInfer `a6b096f7b34dd0266af382a4ece59682676f6ece`. The checkpoint,
vLLM, other operator sources and ABI-8 transport are retained. Online CSF is off.
This is a serving-trial candidate, not a selected upgrade yet.

On a stopped fleet, 31 pinned upstream compact-N64 tests passed on rank zero.
They cover live row counts, poisoned scratch, graph replay, padding, activation
clamping and ordered BF16 route reduction. The fixture was copied unchanged
outside its original `b12x`-named test directory to avoid pytest shadowing the
installed package. Two earlier fixture import failures executed no kernels.

The live checkpoint configuration corrected an initial E=256 planning
assumption: target geometry is **E384/K5120/N576/topk6**, draft is
**E128/K5120/N576/topk3**, with W31 source order and SiLU clamp 10.
Matched old/new tests passed 24 target and 24 draft cases per image, followed by
12 tuned target cases per image: **120 actual-shape cases** total. Random,
balanced and concentrated routes, output error against a float reference,
fixed-address graph updates and allocation-free replay were checked. Target
worst-row cosine remained above 0.99963; draft above 0.99962. These synthetic
checks do not establish full-model quality or bitwise-equivalent answers.

Native tuning used a fresh namespace, graph-captured benchmark calls, explicit
activation production and the library's L2 eviction. Default untuned decode
paths were mostly unchanged in speed. The tuned candidate selected M64 for an
8192-row prefill batch; its MoE graph time fell from 20.40 to 17.22 ms with
random routing and 17.56 to 11.74 ms with balanced routing. Tuned decode results
were mixed, including some regressions. Post-tuning kernel timings reuse a
fixed synthetic input and are **not model-throughput forecasts**.
See [the qualification summary](moe-kernel-qualification.json).

The prefill evidence warrants a fresh-cache serving trial with unchanged
serving flags. Startup memory, actual selected tactics, functional behavior,
cold retrieval and matched LIL remain required before promotion.

The subsequent serving trial **was rejected**. It loaded successfully with
identical schema-23 selection records on all four ranks. The 2,045 records
included 78 MoE decisions: 14 micro, 62 dynamic-M16 and two dynamic-M64.
Online CSF remained off. Head startup memory was 118.20 GiB used, leaving
3.49 GiB available, slightly above the initial-load target.

Seven functional checks and twelve exact-answer checks passed. Two fixed
2,048-token teacher-forced comparisons against the October 17 qualification of
the retained math runtime had coarsened top-20 KL of 0.00492/0.01171 and top-1
agreement of 98.63%/96.09%. Both replay requests had zero cached tokens.
These are finite distribution checks, not a broad equivalence proof.

| Stock-clock draft4 image | 8K C1 | 8K C8 | 8K C16 | 64K prefill | 128K prefill |
|---|---:|---:|---:|---:|---:|
| Retained two-shot image | 64.80 | 198.69 | 273.37 | 4635 | 4556 |
| MoE composition, first screen | 59.56 | 190.29 | 254.14 | 4473 | 4460 |
| MoE composition, confirmation | 59.44 | 198.08 | 263.61 | 4596 | 3996 |
| Retained image, after restoration | 63.05 | 192.53 | 257.67 | 4567 | 4383 |

Both candidate screens completed without request errors or detected loops.
A separate instrumented cold 128K retrieval passed with zero prefix reuse.
Active clocks were approximately 2398–2515 MHz, peak observed temperature
67°C, no swap-out occurred, and only one swap-in page was observed on rank zero.
There was no evidence of the earlier stuck-clock fault.

The retained image's subsequent screen recovered C1, but C16 remained below
its earlier result and between the candidate's two screens. This variation
weakens isolated attribution of the C16 difference. The candidate still did
not demonstrate an overall serving benefit.

The candidate changes both MoE source and tuning selections for unchanged
operators. These measurements reject that composition; they do not isolate
the upstream commit's effect or establish that it is slower on other systems.
The large-M synthetic gain also has limited coverage: our existing bounded
decoder prefill retains at most 128 rows per eligible single request, while
the encoder and explicit keep-full cases still process full input.
[Pinned decoder plan](https://github.com/local-inference-lab/vllm/blob/8244d1c44348ae8a5bbfc9f1b607021652283ed4/vllm/models/deepseek_v4_1/ced.py#L141).

A global `B12X_DYNAMIC_MAX_ACTIVE_CLUSTERS` override was considered and
not tested. It is not a uniform compact-micro/dynamic control, is absent from
the preparation control snapshot, and the source's 24-cluster heuristic is for
a different MoE geometry. The selected per-shape cluster counts are not by
themselves evidence of a fault. The retained switched draft4 image was chosen
for restoration rather than broadening this unsuccessful image trial.
See [serving evidence](moe-serving-qualification.json).

## Native single-request verification cap

The final bounded tuning candidate keeps DSpark's maximum draft width at four
and sets `num_speculative_tokens_per_batch_size=[[1,1,3],[2,16,4]]`.
This caps proposals passed to target verification at C1; the drafter still
computes four proposals. C2–16 retains the existing maximum. Adaptive
verification, probabilistic drafting and block rejection remain enabled.

Seven functional checks passed. Head startup usage was 117.31 GiB, with
4.38 GiB available. Its first matched stock-clock LIL screen measured
**67.06 / 192.21 / 270.95 tokens/s** at 8K C1/C8/C16, with zero request errors
or detected loops; 64K/128K prefill was **4571 / 4560 tokens/s**.
The immediately preceding restored draft4 control was 63.05 / 192.53 / 257.67.
The earlier draft4 stock run reached 64.80 / 198.69 / 273.37, so the C16 rebound
is not attributed to this C1-only cap. The full grid and final correctness
qualification below subsequently passed, and this profile was selected.
[Raw screen](c1cap3-screen-lil.json).

Driver stock boost is now persistent on all four nodes. The historically named
`gb10-gpu-clock-cap.service` calls `nvidia-smi --reset-gpu-clocks`; it no longer
imposes the old 0–2350 MHz ceiling. The exact old unit is backed up separately
on every host. Focused stock/2350/2700 trials did not demonstrate a consistent
decode gain from raising the ceiling.
[Installed policy receipt](persistent-clock-policy.json).

## Final full benchmark

The C1-cap candidate completed public LIL 0.7.6's full 25-cell grid and five
coding probes on stock clocks. Temperature 1, top_p 1, model-default thinking,
20-second cells, max 2048 tokens, no hardware monitor. Zero request errors,
underfilled cells, capacity-limit flags or detected loops were recorded.

| Context | C1 | C2 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|---:|
| 8K | 64.4 | 93.4 | 147.2 | 198.8 | 268.7 | 4023 |
| 16K | 65.3 | 95.0 | 140.4 | 195.4 | 261.2 | 4192 |
| 32K | 60.9 | 96.7 | 139.0 | 192.6 | 263.6 | 4582 |
| 64K | 62.3 | 96.5 | 133.7 | 189.9 | 256.5 | 4591 |
| 128K | 64.8 | 92.6 | 134.8 | 188.1 | 252.7 | 4362 |

All rates are tokens/s; C8/C16 are aggregate. Coding median was 91.44 tokens/s,
maximum 95.02, with no detected CJK runs. The five fresh prefill scouts are
single observations, not confidence intervals.
[Raw full grid](final-full-lil.json), [source conditions](final-full-source.json),
[exact invocation](final-full-argv.json).

The focused C1-cap screen reached 67.06/192.21/270.95 at 8K C1/C8/C16; the
full-grid repeat was 64.36/198.83/268.74. The earlier uncapped draft4 stock
screen reached 64.80/198.69/273.37 and its restoration screen was
63.05/192.53/257.67. These finite runs support a modest C1 candidate but not a
statistically established general improvement. The cap does not change the
C2–16 maximum; C16 variation is not credited to it. Sustained 70 C1 and 300 C16
remain unmet. No performance claim is based on the faster coding workload.

## Final selection and operational checks

The selected profile is
`engram-adaptive4k-query-indexer-1017-runtime1015-kv20-images999-switch-c1cap3`,
on immutable image `9f26f0b3718c…`. It retains official 1017 weights and the
October 15 math runtime. Promotion changed external qualification metadata
only; running commands, environment, mounts and container start times did not
change. Build-time receipts inside the immutable image remain historical.
The complete selected configuration hash is recorded in
[deployment.json](../deployment.json).

Seven functional checks passed, including automatic/forced tools, vision and
thinking output. A new nonce-prefixed **961,724-token** retrieval returned the
expected code with **zero cached tokens**. Its instrumented TTFT was 285.17 s;
this is a correctness/thermal observation, not a matched LIL timing.
Three streamed requests each containing five distinct 1024-pixel images passed
while another request decoded. Each image request reported zero prefix reuse.

Head startup memory was **117.31 GiB used / 4.38 GiB available**. Five-second
sampling during the long request observed **118.53 GiB used / 3.16 GiB available**
at the head. There is no 118 GiB runtime stop guard. Swap-counter increments
were 111 pages in / 60 out on rank zero, 47 in / zero out on rank one, and zero
on both GX10s. This is not a claim of zero swapping.

Peak GPU temperatures were **85 / 82 / 85 / 88°C** by rank. Active SM clocks
stayed between **2398 and 2528 MHz** across the fleet. Hardware/software thermal
slowdown counters remained zero in the post-request driver snapshots. These
are bounded observations, not a guarantee for every room temperature or load.
Only packet/data/write counters increased on both RDMA rails; all sampled
error counters had zero deltas.

The fixed-action controller's `up` was idempotent, `status` passed, and
`stock-up` rejected the obsolete physical-ring configuration without changing
any container ID or start time. All eight GIDs and all jumbo routes passed;
legacy ring services remained disabled. The stopped switched fallback's image,
commands, selected environment and mounts match its retained specification.
No benchmark, GPU collector or profiler process remained in the final inventory.

[Complete qualification receipt](final-qualification.json),
[long-context response](final-cold1m.json),
[memory/thermal summary](final-memory-thermal.json),
[mixed image checks](final-mixed-images.json).

The exact temporary `90-nero-cluster-maintenance` grants were removed from both
Sparks after qualification. Sudoers validation passed, and the existing fixed
passwordless `deepseek-ring-control up` still returned the healthy deployment.
GX10 privileges were unchanged. [Cleanup receipt](temporary-admin-retired.json).
