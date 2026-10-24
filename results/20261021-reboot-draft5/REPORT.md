# Five-draft vLLM after a coordinated fleet reboot

The unchanged five-draft configuration exceeded the earlier five-draft screen in 6 of six median decode cells. Median changes ranged from +10.7% to +23.7%. The reboot was followed by a clean observed startup and all three successful screens. These results show that the earlier low run should not be used alone to attribute poor throughput to five drafts. They do not isolate the cause of the difference between startups.

## Method

One graceful reboot of all four nodes, followed by one unchanged vLLM startup and three consecutive focused screens. Each screen used pinned, unmodified LIL 0.7.6, 8K/32K contexts, C1/C8/C16, 20-second cells, max 2048 tokens, temperature 1 and default thinking. Hardware telemetry was excluded from timed windows. Five coding probes per run are reported separately.

The exact selection `c87a397ccc4614c6f3fee59e566bb7599e7165c80e858bb12c84d78ef5e27775` was retained: five drafts, 20 GiB KV per rank, stock 1017 checkpoint, same immutable image/plugins/transport, port 8015 and persistent 0-2350 MHz ceiling. No CSF or driver/kernel/configuration change was made. Original qualified four-draft containers remain stopped and preserved.

## Useful decode throughput

All values are output tokens/s; concurrent values are aggregate. Each run is shown; the median is not a selected best result.

| Context | C | Run 1 | Run 2 | Run 3 | Median | Range | Previous 5 | Change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8K | 1 | 63.60 | 66.84 | 68.01 | 66.84 | 63.60-68.01 | 59.29 | +12.7% |
| 8K | 8 | 203.13 | 200.70 | 207.10 | 203.13 | 200.70-207.10 | 164.16 | +23.7% |
| 8K | 16 | 280.38 | 285.53 | 293.38 | 285.53 | 280.38-293.38 | 258.04 | +10.7% |
| 32K | 1 | 68.27 | 63.61 | 64.70 | 64.70 | 63.61-68.27 | 56.38 | +14.8% |
| 32K | 8 | 203.56 | 202.81 | 199.32 | 202.81 | 199.32-203.56 | 179.90 | +12.7% |
| 32K | 16 | 289.22 | 289.35 | 266.92 | 289.22 | 266.92-289.35 | 253.02 | +14.3% |

### Historical four-draft comparison

| Context | C | Prior 4-draft control | Post-reboot 5-draft median | Change |
| --- | --- | --- | --- | --- |
| 8K | 1 | 61.22 | 66.84 | +9.2% |
| 8K | 8 | 202.36 | 203.13 | +0.4% |
| 8K | 16 | 268.60 | 285.53 | +6.3% |
| 32K | 1 | 65.01 | 64.70 | -0.5% |
| 32K | 8 | 189.73 | 202.81 | +6.9% |
| 32K | 16 | 264.60 | 289.22 | +9.3% |

### Step-rate evidence

The table below reports the harness counter-derived step rate and useful tokens per step. These counters explain the observed rate decomposition; they do not isolate a kernel or driver cause.

| Context | C | Prior 5 steps/s | New median steps/s | Prior tokens/step | New median tokens/step |
| --- | --- | --- | --- | --- | --- |
| 8K | 1 | 25.80 | 27.67 | 2.298 | 2.415 |
| 8K | 8 | 69.33 | 87.03 | 2.368 | 2.334 |
| 8K | 16 | 103.00 | 118.81 | 2.505 | 2.405 |
| 32K | 1 | 24.82 | 27.78 | 2.272 | 2.329 |
| 32K | 8 | 74.79 | 86.60 | 2.406 | 2.342 |
| 32K | 16 | 102.75 | 115.34 | 2.462 | 2.474 |

## Coding and prefill

Coding median output rates for the five probes in each run: 96.58, 104.93, 99.02 tokens/s. These are separate workloads from sustained decode.

| Nominal prefill | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- |
| 8K | 4,259 | 4,331 | 4,323 |
| 32K | 4,505 | 4,513 | 4,481 |
| 64K | 4,526 | 4,511 | 4,506 |
| 128K | 4,478 | 4,473 | 4,462 |

Prefill values are client-observed input tokens/s including TTFT, one scout per context per run; actual prompt counts are preserved in the raw JSON.

## Reliability and final state

Startup/validation kernel event counts by rank: [0, 0, 0, 0]. SSH probe failures: [0, 0, 0, 0]. The post-ready gate and each timed-run kernel check passed. All 18 decode cells passed request-error, underfill, capacity, warmup and loop checks; all used continuous completion-usage accounting.

Sampled startup-plus-validation peak used GiB by rank: 118.355, 117.056, 117.072, 117.167. Immediate startup head used memory: 117.803 GiB. Final API health was HTTP 200. Loaded-clock probes before and after timing passed. Exact serving and fallback container IDs were verified.

## Interpretation limits

Three repeats on one startup estimate within-startup variability. They do not measure variability across three reboots. The historical five-draft result is one earlier startup and is not a concurrent randomized control. Any changed result after reboot can reflect boot/startup state, adaptive cost calibration, cache history and stochastic requests; this experiment cannot isolate those causes. The nearby four-draft control remains a useful historical comparator, but no new four-draft arm was run. These focused results do not qualify the full context/concurrency grid or broad model quality.

Raw JSON, logs, boot IDs, kernel checks, commands, memory samples and exact identities are retained in this directory. See `summary.json` and `decode-measurements.csv` for unrounded values and step/acceptance counters.
