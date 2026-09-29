# Full deployed-profile benchmark — 2026-09-28 UTC

These measurements predate the KK #926/#943 compressor-state correction.
The selected runtime now uses corrected images; see
[the September 29 correction report](KK926-CORRECTION-20260929.md) for its
measured fidelity gain and throughput tradeoffs. The original benchmark
results are retained below as historical evidence.

Four GB10 nodes (two DGX Sparks, two GX10s), selected vLLM profile `engram-adaptive4k-query-indexer`. Serving configuration remained fixed throughout.

Original run: **19/20 sustained cells valid; 19/20 burst cells valid**. Both rejected cells passed one focused repeat without changing the serving configuration or disabling the repetition detector. Rejected cells remain visible below; a diagnostic repeat does not erase the original failure.

## Scope and request contract

- LIL v0.6.2, pinned harness `ccd9ad8ced7e387794391bfb0ac6d99b1f66ba6f`; the optional self-update was declined.
- Full repository preset: nominal 8K/32K/64K/128K contexts × C1/C2/C4/C8/C16; 30-second sustained windows after warmup, maximum 2,048 output tokens and EOS ignored.
- Additional burst grid: one measured wave of C complete responses per cell, one warmup request, 2,048 output tokens. This is one wave per cell, not the harness default of five waves.
- Thinking off, temperature 1, top_p 1, top_k -1 through the recorded request adapter. These overrides also apply to coding-peak requests; the raw coding metadata may retain its unset CLI temperature.
- Decode and burst use warmed benchmark prefixes. Fresh-input latency is measured separately. Context labels are targets from the harness calibration; actual prompt counts are retained in the JSON.
- Three separate nonce-prefixed long retrieval probes use temperature 0, thinking off and maximum 32 output tokens. Zero cached prompt tokens is verified for these probes.
- No changes to model weights, serving parameters, plugins or the runtime during the run. Hardware power/thermal monitoring was not collected.

## Sustained decode

Aggregate output tokens/s. These rates are across all concurrent requests, not per user.

| Nominal context | C1 | C2 | C4 | C8 | C16 |
| --- | --- | --- | --- | --- | --- |
| 8K | 64.3 | 93.6 | 141.4 | 180.5 | 236.6 |
| 32K | 64.7 | 99.2 | 132.9 | 176.2 | 235.1 |
| 64K | 65.5 | 110.7 | 137.8 | 171.5 | 236.2 |
| 128K | 66.2 | LOOP | 131.0 | 171.3 | 240.7 |

## Complete-response bursts

Aggregate output tokens/s including the measured batch’s admission, cache/prefill behavior and completion.

| Nominal context | C1 | C2 | C4 | C8 | C16 |
| --- | --- | --- | --- | --- | --- |
| 8K | 62.9 | 93.7 | 128.8 | 173.8 | 236.0 |
| 32K | 59.6 | 96.4 | 126.2 | 164.8 | 237.8 |
| 64K | 61.1 | 100.0 | 128.1 | 170.5 | 232.2 |
| 128K | 63.9 | 105.8 | 124.3 | 159.7 | LOOP |

Median per-request completion latency in seconds for 2,048 output tokens:

| Nominal context | C1 | C2 | C4 | C8 | C16 |
| --- | --- | --- | --- | --- | --- |
| 8K | 32.5 | 38.6 | 61.2 | 90.4 | 132.0 |
| 32K | 34.2 | 41.9 | 62.7 | 94.3 | 133.6 |
| 64K | 33.3 | 38.7 | 56.8 | 93.7 | 137.5 |
| 128K | 32.0 | 32.4 | 62.1 | 99.6 | LOOP |

Mean time to first token in seconds, with warmed benchmark prefixes:

| Nominal context | C1 | C2 | C4 | C8 | C16 |
| --- | --- | --- | --- | --- | --- |
| 8K | 0.3 | 0.5 | 0.6 | 0.9 | 1.5 |
| 32K | 0.4 | 0.5 | 0.8 | 1.0 | 1.6 |
| 64K | 0.5 | 0.6 | 0.9 | 1.4 | 2.2 |
| 128K | 0.6 | 0.8 | 1.2 | 1.9 | LOOP |

## Standalone prefill

LIL reports median client TTFT and prompt-token/TTFT rates; sample counts vary by context. Its pinned version caps this phase at 128K. Prometheus prefill validation was not populated, so these are client measurements.

| Nominal context | Actual prompt tokens | Samples | TTFT (s) | Prompt tok/s |
| --- | --- | --- | --- | --- |
| 8K | 8,166 | 5 | 1.807 | 4,520 |
| 32K | 32,231 | 2 | 6.970 | 4,624 |
| 64K | 64,330 | 1 | 14.005 | 4,593 |
| 128K | 128,497 | 1 | 28.445 | 4,517 |

Long probes are a separate retrieval workload, not additional LIL cells. Cold means no prompt KV-cache reuse, not an empty OS file cache.

| Actual prompt tokens | First content (s) | Prompt tokens / TTFT | Cached tokens | Retrieval |
| --- | --- | --- | --- | --- |
| 245,586 | 59.06 | 4,158 | 0 | Pass |
| 503,896 | 130.88 | 3,850 | 0 | Pass |
| 1,008,432 | 308.79 | 3,266 | 0 | Pass |

## Coding prompt

Five sequential Sieve-of-Eratosthenes coding requests, up to 2,000 output tokens. All five completed. This is a throughput prompt, not a coding-correctness score. Mean generation rate **101.1 tok/s**, median **100.7**, range **98.7–104.7**.

| Run | Output tokens | TTFT (s) | Generation tok/s | Finish |
| --- | --- | --- | --- | --- |
| 1 | 1005 | 0.097 | 100.7 | stop |
| 2 | 775 | 0.113 | 101.4 | stop |
| 3 | 932 | 0.118 | 104.7 | stop |
| 4 | 669 | 0.116 | 100.0 | stop |
| 5 | 802 | 0.116 | 98.7 | stop |

## Validity and repeat

- `results`: 128K/C2, aggregate source `invalid_exact_repetition`, loop flag `True`, harness error count 2.
- `burst_results`: 128K/C16, aggregate source `invalid_exact_repetition`, loop flag `True`, harness error count 15.

Both failures included a confirmed exact loop during measurement. The sustained
case repeated a 130-character span; the burst case repeated a 58-character span.
The harness invalidated each whole cell and aborted its streams; the error
counts above are not counts of independent HTTP/server failures. The 19 valid
original burst cells completed 108 measured requests. No original cell was
marked capacity-limited, underfilled, or with a warmup timeout.

One focused repeat per rejected cell, using the same thinking/sampling,
2,048-token limit and enabled loop detector:

| Repeat | Aggregate tok/s | Measured completion count | Flags |
| --- | --- | --- | --- |
| 128K/C2 sustained, 30 s | 118.9 | Duration measurement | None |
| 128K/C16 burst, 16 requests | 221.3 | 16/16 | None |

The burst repeat's mean TTFT was 3.196 seconds and median completion latency
was 140.75 seconds, with warmed prefixes. Each repeat was a fresh harness run
with a new prompt nonce; the burst repeat used native request-count mode with
one warmup request. Raw results and exact arguments are linked below.

The original grid therefore remains **38/40 valid**, followed by **2/2 valid
diagnostic repeats**. No fix was applied between them. These observations do
not identify the cause or prove that repetition has been resolved. LIL ignores
EOS to force long outputs; the failures are evidence under that condition,
not a controlled test of ordinary early-stopping requests or proof of a
query-sharding regression.

## Comparison and limits

Against the preceding 30-second baseline matrix, overlapping C1/C8 decode cells changed by −3.1% to +3.5%. This supports broadly maintained decode performance; a new decode speedup is not established. Sampling and speculative acceptance vary, and these single passes provide no confidence intervals. The full grid is not a concurrent-million-token or beyond-C16 capacity test.

The same cold-retrieval probe family previously measured 70.84 seconds at
~246K tokens and 529.54 seconds at ~1.008M on the prior adaptive-4K profile.
This run measured 59.06 and 308.79 seconds respectively: 16.6% and 41.7%
lower first-content latency. These are individual measurements with slightly
different nonce token counts. The million-token result remains slower than
the historical SGLang probe's 247.6 seconds; that is not a fresh matched
cross-engine comparison, and no SGLang runtime was started.

All four selected containers remained running from their original 20:30 UTC
start, the API was healthy, and the serving configuration was unchanged after
the main run. Current-process logs contained 30 enabled indexer guard decisions
and zero rejected decisions. These numerical checks do not eliminate the
observed output-repetition issue.

After both repeats, the API and all four selected containers were healthy,
their original start times were unchanged, and the serving configuration still
matched the pre-repeat configuration.

## Evidence

Text transcripts have trailing terminal padding removed; CSV uses LF line endings. JSON measurements and executed source snapshots are unchanged.

- [Raw LIL results](results/selected-full-20260928T222742Z/lil.json), [text output](results/selected-full-20260928T222742Z/lil.txt), [cell CSV](results/selected-full-20260928T222742Z/cells.csv).
- [Request overrides and source hashes](results/selected-full-20260928T222742Z/lil.matched-request.json), [exact arguments](results/selected-full-20260928T222742Z/lil-argv.json), [executed runner snapshot](results/selected-full-20260928T222742Z/runner.py).
- [Configuration receipt](results/selected-full-20260928T222742Z/configuration.json), [process exit statuses](results/selected-full-20260928T222742Z/statuses.json), [health receipt](results/selected-full-20260928T222742Z/final-health.json).
- [~246K cold retrieval](results/selected-full-20260928T222742Z/cold-256000.json), [~504K cold retrieval](results/selected-full-20260928T222742Z/cold-524288.json), [~1M cold retrieval](results/selected-full-20260928T222742Z/cold-1048576.json).
- [Earlier baseline matrix](results/20260928-research/20260928T193307Z-baseline-return/matrix.json).
- [Sustained repeat](results/selected-full-20260928T222742Z/recheck.json), [arguments](results/selected-full-20260928T222742Z/recheck-argv.json), [request contract](results/selected-full-20260928T222742Z/recheck.matched-request.json).
- [Burst repeat](results/selected-full-20260928T222742Z/recheck-burst.json), [arguments](results/selected-full-20260928T222742Z/recheck-burst-argv.json), [request contract](results/selected-full-20260928T222742Z/recheck-burst.matched-request.json), [final health](results/selected-full-20260928T222742Z/post-recheck-burst-health.json).
