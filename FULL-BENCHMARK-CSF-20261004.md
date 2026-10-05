# CSF full benchmark — October 2026

Four GB10 nodes at a persistent 2350 MHz upper GPU cap. The measured candidate is the custom CSF vLLM/B12x rebase described in [the upgrade report](CSF-UPGRADE-20261004.md). It was rejected for performance; the previous corrected runtime remains the selected default. The context limit is 1,048,576 tokens; max active sequences is 16; adaptive prefill retains an 8K allocation ceiling and lowers steps to 4K under decode contention. HF tokenization and disk-backed Engram remain enabled.

LIL v0.6.2, explicit thinking off, temperature 1, top_p 1, top_k −1. Four context lengths × five concurrency levels, 30-second sustained windows after warmup. The separate burst grid uses one complete response per stream (up to 2,048 output tokens) plus a warmup request; it includes admission, prefix-cache behavior, first-token time and response completion. The prompt cap and request contract match the previous full benchmark. This is a finite performance sample, not a general task-quality evaluation.

## Sustained decode

20/20 valid cells. All throughput values below are aggregate output tokens/s.

| Context | C1 | C2 | C4 | C8 | C16 |
|---|---:|---:|---:|---:|---:|
| 8K | 76.9 | 81.5 | 128.0 | 153.8 | 219.2 |
| 32K | 58.0 | 81.1 | 123.3 | 158.3 | 211.4 |
| 64K | 59.6 | 85.7 | 123.2 | 150.8 | 205.4 |
| 128K | 58.9 | 78.9 | 106.4 | 131.5 | 188.6 |

## Complete-response burst

19/20 valid cells. All throughput values below are aggregate output tokens/s.

| Context | C1 | C2 | C4 | C8 | C16 |
|---|---:|---:|---:|---:|---:|
| 8K | 58.0 | 85.7 | 115.0 | 144.8 | 213.8 |
| 32K | 78.2 | 85.3 | 127.8 | 158.2 | 224.9 |
| 64K | 52.7 | 91.6 | 123.4 | 163.1 | 220.8 |
| 128K | 53.7 | 92.6 | 122.0 | INVALID | 207.9 |

Failures: [[131072, 8, "output repetition during warmup"]]

## Cold prefill

Prompt throughput is actual prompt tokens divided by client first-content latency. These samples have no prompt KV reuse; cold does not mean an empty OS file cache.

| Target | Actual prompt tokens | First content | Prompt tok/s | Samples |
|---|---:|---:|---:|---:|
| 8K | 8,194 | 2.49 s | 3,308 | 4 |
| 32K | 32,351 | 9.03 s | 3,582 | 2 |
| 64K | 64,575 | 17.96 s | 3,595 | 1 |
| 128K | 129,016 | 37.65 s | 3,427 | 1 |

Larger fresh retrieval requests are separate from LIL’s capped prefill grid:

| Actual prompt tokens | First content | Correct needle | Cached tokens |
|---:|---:|---|---:|
| 245,588 | 68.31 s | True | 0 |
| 503,898 | 150.84 s | True | 0 |
| 1,008,429 | 351.85 s | True | 0 |

## Coding throughput

5/5 sequential Sieve-of-Eratosthenes prompts completed, up to 2000 output tokens. Mean generation rate was **94.3 tok/s**, median 93.9, range 87.9–101.9. This is a throughput prompt; generated programs were not scored for correctness.

## Evidence and limits

[Raw results](results/csf-full-20261005T011459Z/lil.json), [request contract/source hashes](results/csf-full-20261005T011459Z/lil.matched-request.json), [exact arguments](results/csf-full-20261005T011459Z/lil-argv.json), [runner](results/csf-full-20261005T011459Z/runner.py), [cell CSV](results/csf-full-20261005T011459Z/cells.csv), [exit statuses](results/csf-full-20261005T011459Z/statuses.json) and [final health](results/csf-full-20261005T011459Z/final-health.json).

Speculative acceptance varies with generated text. Raw tokens/s combines target-engine step rate and accepted tokens per step; the CSV and JSON retain both. Short stochastic throughput differences do not establish a universal speedup. The earlier September 28 full run predates the fidelity correction and the 2350 MHz cap, so its grid is historical context rather than a matched speed comparison. Use the same-day corrected baseline screen in the upgrade report for that comparison.
