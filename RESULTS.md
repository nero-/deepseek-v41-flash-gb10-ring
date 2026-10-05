# vLLM results — updated 2026-10-05 UTC

Four GB10 nodes: two DGX Sparks and two ASUS Ascent GX10s. Runtime and checkpoint pins are in [README.md](README.md). The initial migration record is [MIGRATION-20260927.md](MIGRATION-20260927.md); the follow-up campaign is [RESEARCH-20260928.md](RESEARCH-20260928.md).

The [October CSF upgrade](CSF-UPGRADE-20261004.md) was rejected: its
[full benchmark](FULL-BENCHMARK-CSF-20261004.md) had slower prefill and
high-concurrency decode than the same-day corrected baseline screen. The
previous corrected HF runtime remains selected. The candidate combined several
runtime updates, so these measurements do not isolate CSF storage as the cause.

Selected configuration: **Engram projection TP + adaptive 4K under contention + guarded query-row indexer sharding**, with native DSpark5, graph sizes and an 8K allocation ceiling.

The selected runtime also includes the **complete KK #926/#943 compressor-state
correction**. See [the September 29 report](KK926-CORRECTION-20260929.md) for
fresh baseline/corrected screens and all qualification evidence. Eight long
generation probes showed 89.6% lower late-answer coarsened decode/prefill KL.
Corrected prefill was about 4.35–4.42K prompt tok/s; repeated C16 decode reached
233–236 aggregate tok/s. The matched 128K/C1 screens were slower at 57.8–59.0
tok/s versus a 73.9 tok/s baseline sample. Million-token uncached retrieval
passed in 322.1 seconds. One initial long-context automatic-tool miss remains
recorded; the full repeat passed 7/7. Historical numbers below predate the fix.

The subsequent [Fastokens serving trial](FASTOKENS-SERVING-20260929.md)
reduced cached 1M TTFT from 2.57 to 1.11 seconds at C1 and 9.80 to 3.74 seconds
at C8. However, repeated C8 decode was 167–169 tok/s at 8K and 156.6–156.8
at 128K, versus HF's 171.8–179.0 and 164.8–168.5. All integration checks passed,
but the corrected HF backend was restored to prioritize decode/concurrency.
`VLLM_USE_FASTOKENS` is not enabled. This was a six-cell screen plus C8 repeats,
not a new full benchmark. The historical full benchmark's C1 was 64.3–66.2
tok/s; the isolated 73.9 result should not be treated as typical fleet speed.

## Full deployed-profile benchmark

The [full benchmark report](FULL-BENCHMARK-20260928.md) covers the deployed
profile with thinking off: 8K/32K/64K/128K × C1/C2/C4/C8/C16, 30-second
sustained cells, a separate complete-response burst grid, five coding prompts,
and fresh retrieval probes through 1,008,432 tokens. Original-run C1 sustained
decode was 64.3–66.2 tok/s and C16 was 235.1–240.7 aggregate tok/s. Standalone
8K–128K prefill was 4,517–4,624 prompt tok/s. Million-token first-content
latency was 308.79 seconds, with correct retrieval and zero cached prompt tokens.

The original full run was **not error-free**: exact repetition invalidated
128K/C2 sustained and 128K/C16 burst, leaving 19/20 valid cells in each grid.
The report preserves both failures and records focused repeats separately:
128K/C2 sustained passed at 118.9 tok/s, and the 128K/C16 burst passed at
221.3 tok/s with 16/16 completions. No fix was applied between these runs;
passing repeats do not establish that the intermittent repetition is resolved.
No cell was capacity-limited or marked with a warmup timeout. Overlapping
30-second baseline decode cells changed by −3.1% to +3.5%; this does not
establish a new decode gain.

## Follow-up selection

The query-row port distributes eligible long-prefill indexer work across the four
ranks and gathers integer selections. Exact raw scores and selected score values
must match the original local computation; legal tied indices may differ. It
activates only after complete worker warmup and real input. The checkpoint,
target precision and full vocabulary are preserved.

Fresh within-vLLM comparison, thinking off, temperature 1, top_p 1, top_k -1:

| Configuration | C1 | C3 | C5 | C8 | C16 | Prefill 8K | Prefill 64K |
|---|---:|---:|---:|---:|---:|---:|---:|
| Prior adaptive 4K, baseline return | 64.6 | 119.4 | 146.5 | 178.3 | 239.9 | 4460 | 4299 |
| **Query sharding, qualification** | **73.7** | **112.7** | **145.0** | **181.6** | **240.9** | **4486** | **4316** |

All throughput values are aggregate tokens/s; both runs had zero benchmark
errors. These short stochastic samples do not establish a new decode gain.
The ordinary decode path is unchanged, and C1's higher acceptance, rather than
higher engine step rate, explains its throughput rise. C3 was lower in this run.

| Uncached retrieval | Baseline TTFT | Query sharding TTFT | Reduction |
|---|---:|---:|---:|
| ~245.6K prompt tokens | 70.84 s | 61.12 s | 13.7% |
| ~1.008M prompt tokens | 529.54 s | 333.89 s | 36.9% |

All four retrievals returned the correct code with cached_tokens=0. The earlier
query-sharding run also passed the million-token test in 328.09 s. Cold here
means no prompt KV-cache reuse, not an empty operating-system file cache.

Qualification passed 24/24 numerical guards, seven ordinary and seven ~94K-token
functional probes, and two ~94K retrievals under eight ongoing decoders.
Ordinary mixed traffic retained similar p95 chunk gaps and fresh-request TTFT,
but worst gaps increased from 1.07–1.12 s to 1.19–1.27 s. That is a tradeoff,
not a claimed mixed-traffic improvement. The legacy smoke still fails its
byte-identical greedy-repeatability requirement, as the pinned baseline does.

All six research directions were tested. Context-axis sharding also improved
long prefill but was less balanced on short prefill. Context-aware verification
costs, timed prefill, Engram read-ahead, mHC row ownership, and top-20/top-128
Markov shortlists were not selected. See the [research record](RESEARCH-20260928.md)
for measurements, source hashes, failure details and finite-test limitations.

## Permanent deployment verification

The installed `engram-adaptive4k-query-indexer` profile repeated uncached
retrieval at **1,008,431 prompt tokens in 315.76 seconds** to first content,
**40.4% less TTFT** than the fresh 529.54-second baseline. The correct code was
returned with cached_tokens=0. Both standard and ~94K functional suites passed
7/7 again. Its fresh process passed 21 numerical geometries with zero rejected cases.

All four selected containers are running, the API is healthy, and root-owned
plugin hashes match the qualified source. All 48 regular checkpoint weight files
remain on each node. The mesh is active and enabled; no research container is
running. GX10 free space is 161.3/166.4 GiB. The delegated cleanup audit found no
remaining SGLang runtime to remove; Qwen and the stock vLLM fallback are preserved.
See the [deployment and health receipt](results/20260928-research/20260928T202948Z-selection)
and [cleanup audit](results/20260928-research/cleanup-audit.json).

## Initial migration measurements

The remaining sections describe the earlier migration and its then-selected
adaptive-4K profile, before query sharding. Engine-default screens below use
different request settings from the explicit non-thinking follow-up above.

## Controlled vLLM screens

LIL v0.6.2, 8K decode context, 20-second cells, engine-default thinking and sampling. Decode columns are **aggregate tokens/s**. Short stochastic screens are useful for selection, not confidence intervals.

| Configuration | C1 | C3 | C5 | C8 | C16 | Prefill 8K | Prefill 64K |
|---|---:|---:|---:|---:|---:|---:|---:|
| Official stock | 56.4 | 110.6 | 144.3 | 196.2 | 267.5 | 4433 | 3353 |
| Engram projection TP | 63.1 | 113.8 | 157.1 | 203.7 | 277.0 | 4467 | 4232 |
| Engram TP return | 64.7 | 118.5 | 152.4 | 193.2 | 276.9 | 4127 | 4101 |
| Engram + expanded graphs | 62.8 | 120.8 | 161.9 | 202.1 | 276.8 | 4274 | 4242 |
| Engram + adaptive 4K | 57.5 | 117.0 | 166.8 | 193.7 | 274.4 | 4449 | 4160 |
| **Prior adaptive 4K, permanent restart** | **63.1** | **122.6** | **148.5** | **202.7** | **280.4** | **4201** | **4117** |
| Engram + adaptive 4K + expanded graphs | 54.8 | 120.1 | 157.9 | 188.9 | 277.1 | 4458 | 4121 |
| Engram + top-20 proposals¹ | 62.4 | 119.7 | 160.2 | 193.8 | 278.6 | 4006 | 4053 |

¹ The benchmark JSON completed, but replacing its executing shell wrapper caused a trailing command error (exit 127). The campaign is recorded as failed, not a clean pass. Top-20 is not selected: no clear overall gain, qeval 71/75. Its independent GPU checks passed 19/19.

The prior profile's permanent-restart screen completed with zero errors and
reproduced C1/C16/64K-prefill gains: approximately +12%/+5%/+23% against the
stock tuning screen. Its 8K prefill was lower (4201 versus 4433), and C5 varied
substantially across runs (148.5 versus the earlier 166.8); do not claim a uniform
speedup at every load.

Engram TP reproduced gains in C1, C16 and 64K prefill relative to stock. The C8 difference varied enough that a small improvement is not established. Prefill still has room to improve; full residual sequence parallelism has not been ported.

## Explicit non-thinking baseline

The prior adaptive-4K profile also completed a separate run with **thinking off,
temperature 1.0, top_p 1.0, top_k -1**, with zero errors:

| C1 | C3 | C5 | C8 | C16 | Prefill 8K | Prefill 64K |
|---:|---:|---:|---:|---:|---:|---:|
| 60.2 | 116.0 | 131.0 | 168.9 | 225.5 | 4433 | 4071 |

The request contract and harness hashes are in
[the sidecar](results/20260928/final-selected-matched-tune.matched-request.json).
This differs from the engine-default screen in request settings; it is not an
isolated thinking-on/off A/B. **280 tok/s is not the non-thinking C16 result.**
No stock-vLLM or fresh SGLang screen with this complete explicit contract was
run, so this establishes a future comparison baseline, not a matched
cross-engine speedup. The within-vLLM improvement claims above use the same
engine-default settings on stock and selected configurations.

## Mixed traffic

Eight ongoing decoders plus two fresh ~29K-token prompts, three rounds per configuration. These are SSE content-chunk gaps, **not individual-token latency**: speculative decoding can return several tokens per chunk.

| Configuration | Maximum ongoing-stream gap | First fresh request TTFT | Second fresh request TTFT |
|---|---:|---:|---:|
| Engram, 16K budget | 3.87–4.10 s | 7.83–8.16 s | 14.06–14.37 s |
| Engram, 8K budget | 2.05–2.24 s | 8.15–8.79 s | 14.66–15.50 s |
| Native compute-share fairness, 4K | ~1.3 s | ~16 s | ~28 s |
| Local adaptive 4K under contention | 1.16–1.24 s | 8.95–9.02 s | 16.00–16.10 s |

The 16K default was rejected: little concurrency benefit and much larger stalls. The local adaptive budget retains ordinary scheduling and the 8K allocation ceiling, shrinking the step only when at least four runnable decoders contend with prefill. Its mixed and under-load retrieval checks completed without errors. Native compute-share fairness imposes too much fresh-request latency for the balanced objective.

## Quality and rejected experiments

Stock passed all seven functional probes and scored 71/75 on the retained task suite. Engram TP and adaptive 4K each scored 72/75; expanded graphs scored 73/75. Differences of one or two tasks do not establish quality improvements. Greedy byte-repeatability fails on the stock image as well as the optimized trials. The deterministic-kernel override failed preparation and was rejected.

The initial SGLang-inspired Q/KV projection and indexer-row attempts failed their original guards (0/43 and 0/12 enabled cases). Their fallbacks passed functional checks; those attempts received no speed credit. The later exact-score/value query-indexer guard and its selected results are reported above. Adaptive HC's Qwen communication pattern does not exist in this DeepSeek mHC implementation; copying its cutoff would not provide the same optimization.

## Million-token retrieval and limits

After the initial permanent restart, the adaptive-4K profile retrieved the correct code
from **1,008,411 prompt tokens in 526.4 seconds** (1,916 prompt tokens/s including
decode). Arithmetic, tools and thinking also passed. The overall smoke command
returned 1 because greedy repeatability still failed; it is not reported as an
unconditional smoke pass. See [the exact output](results/20260928/selected-near1m.txt).

This verifies one long retrieval request, not general 1M-context quality or
16 simultaneous million-token sessions. The historical SGLang probe reported
1,000,169 tokens in 247.6 seconds. That is a historical comparison with a slightly
different token count, not a fresh matched run, but the large latency gap matters:
**the initial adaptive-4K profile had not recovered that historical long-context speed.** The later query-sharding measurements above close much of the gap, but remain slower than this historical SGLang probe and do not establish a matched cross-engine comparison.
Full prefill sequence parallelism remains unported. No RDMA error/retry counters
changed between the selected before/after snapshots, and the API remained healthy.

## Historical comparison limit

[SGLang results](RESULTS-SGLANG-ARCHIVE.md) are retained as historical evidence. Its reported prefill was faster, while new vLLM default-mode concurrency throughput was higher. However, SGLang defaulted to thinking off and this vLLM profile defaults to thinking on. Historical decode numbers are **not a fully matched cross-engine comparison**, and no fresh SGLang test is planned. Explicitly fixed vLLM request settings are recorded by `bench/lil_matched.py` for future comparisons.


## Storage and mode switching

The retired SGLang runtime, old checkpoint paths, packed Engram shards, mesh,
cache and image tags were removed consistently on all four nodes. The new
checkpoint retained all 48 regular weight files. Cleanup reclaimed about
47.7 GiB per node; the GX10s had 161.7/166.9 GiB free immediately afterwards.
No global Docker prune or Qwen cleanup ran. See [retirement receipt](results/20260928/retirement.json).

The permanent DeepSeek deployment started after cleanup, then stopped through
the mode switch. Both Qwen pairs reached healthy APIs and returned `391` for
17×23 with thinking disabled using Qwen's own request option. Their existing
`hc-adaptive+cg4+m5500h` selection and 24 GiB KV allocation were preserved.
See [handoff receipt](results/20260928/qwen-handoff.json).

The initial selected deployment restarted successfully, and fixed passwordless up/status
controls passed after removal of the temporary broad sudo grants. A fresh request
after the million-token test returned 27×19 = 513 in 0.17 seconds. All four
selected containers and native mesh services were left running; see
[final health](results/20260928/final-health.json).
