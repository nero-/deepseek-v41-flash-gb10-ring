# vLLM results — 2026-09-28 UTC

Four GB10 nodes: two DGX Sparks and two ASUS Ascent GX10s. Runtime and checkpoint pins are in [README.md](README.md). The full trial record is [MIGRATION-20260927.md](MIGRATION-20260927.md); measurements are in [results/20260928](results/20260928).

Selected configuration: **Engram projection TP + adaptive 4K under contention**, with the recipe's stock graph sizes, DSpark5 and 8K allocation ceiling. Expanded graphs did not establish a balanced gain in the combined screen and are not selected.

## Controlled vLLM screens

LIL v0.6.2, 8K decode context, 20-second cells, engine-default thinking and sampling. Decode columns are **aggregate tokens/s**. Short stochastic screens are useful for selection, not confidence intervals.

| Configuration | C1 | C3 | C5 | C8 | C16 | Prefill 8K | Prefill 64K |
|---|---:|---:|---:|---:|---:|---:|---:|
| Official stock | 56.4 | 110.6 | 144.3 | 196.2 | 267.5 | 4433 | 3353 |
| Engram projection TP | 63.1 | 113.8 | 157.1 | 203.7 | 277.0 | 4467 | 4232 |
| Engram TP return | 64.7 | 118.5 | 152.4 | 193.2 | 276.9 | 4127 | 4101 |
| Engram + expanded graphs | 62.8 | 120.8 | 161.9 | 202.1 | 276.8 | 4274 | 4242 |
| Engram + adaptive 4K | 57.5 | 117.0 | 166.8 | 193.7 | 274.4 | 4449 | 4160 |
| **Selected adaptive 4K, permanent restart** | **63.1** | **122.6** | **148.5** | **202.7** | **280.4** | **4201** | **4117** |
| Engram + adaptive 4K + expanded graphs | 54.8 | 120.1 | 157.9 | 188.9 | 277.1 | 4458 | 4121 |
| Engram + top-20 proposals¹ | 62.4 | 119.7 | 160.2 | 193.8 | 278.6 | 4006 | 4053 |

¹ The benchmark JSON completed, but replacing its executing shell wrapper caused a trailing command error (exit 127). The campaign is recorded as failed, not a clean pass. Top-20 is not selected: no clear overall gain, qeval 71/75. Its independent GPU checks passed 19/19.

The selected profile's permanent-restart screen completed with zero errors and
reproduced C1/C16/64K-prefill gains: approximately +12%/+5%/+23% against the
stock tuning screen. Its 8K prefill was lower (4201 versus 4433), and C5 varied
substantially across runs (148.5 versus the earlier 166.8); do not claim a uniform
speedup at every load.

Engram TP reproduced gains in C1, C16 and 64K prefill relative to stock. The C8 difference varied enough that a small improvement is not established. Prefill still has room to improve; full residual sequence parallelism has not been ported.

## Explicit non-thinking baseline

The final selected profile also completed a separate run with **thinking off,
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

The SGLang-inspired Q/KV projection and indexer-row ports failed their exactness guards (0/43 and 0/12 enabled cases). Their fallbacks passed functional checks; neither port is selected or credited with a speed gain. Adaptive HC's Qwen communication pattern does not exist in this DeepSeek mHC implementation; copying its cutoff would not provide the same optimization.

## Million-token retrieval and limits

After the permanent restart, the selected profile retrieved the correct code
from **1,008,411 prompt tokens in 526.4 seconds** (1,916 prompt tokens/s including
decode). Arithmetic, tools and thinking also passed. The overall smoke command
returned 1 because greedy repeatability still failed; it is not reported as an
unconditional smoke pass. See [the exact output](results/20260928/selected-near1m.txt).

This verifies one long retrieval request, not general 1M-context quality or
16 simultaneous million-token sessions. The historical SGLang probe reported
1,000,169 tokens in 247.6 seconds. That is a historical comparison with a slightly
different token count, not a fresh matched run, but the large latency gap matters:
**the selected vLLM profile has not recovered SGLang's very-long-context prefill speed.**
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

The selected deployment restarted successfully, and fixed passwordless up/status
controls passed after removal of the temporary broad sudo grants. A fresh request
after the million-token test returned 27×19 = 513 in 0.17 seconds. All four
selected containers and native mesh services were left running; see
[final health](results/20260928/final-health.json).
