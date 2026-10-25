# Results

All timed results use unmodified LIL 0.7.6: temperature 1, model-default
thinking, 20-second cells, max 2048 output tokens, `--no-hw-monitor`.
Values are aggregate output tokens/s; C>1 is aggregate, not per stream.
Compare only matching protocols and startups.

## Selected: spark-ds41f TileLang (2026-10-24)

Selection `4d2bc32e…`, image `2fc5565e9c15…`, 20 GiB KV, 999 images, 2350 MHz
ceiling. [Full report with tool-eval](results/20261024-tilelang/REPORT.md).

### Full grid

| Context | C1 | C2 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|---:|
| 8K | 66.5 | 102.2 | 155.1 | 214.0 | 293.7 | 5,441 |
| 16K | 65.7 | 106.6 | 145.7 | 205.2 | 303.5 | 5,963 |
| 32K | 67.1 | 100.2 | 159.7 | 205.9 | 294.1 | 6,122 |
| 64K | 67.9 | 100.4 | 143.8 | 211.6 | 296.2 | 6,088 |
| 128K | 66.0 | 102.8 | 137.1 | 210.0 | 268.9 | 5,964 |

Against the B12X October 20 grid (four drafts, stock boost): every cell
higher, +0.6% to +16.2% decode and +32.6% to +42.2% prefill. Coding probes
median 100.8 (B12X 91.4).

### Focused screen, three runs on one startup

| Context | C1 | C8 | C16 |
|---|---:|---:|---:|
| 8K median | 67.5 | 211.0 | 293.2 |
| 32K median | 67.3 | 213.2 | 286.0 |
| B12X 8K median (Oct 21) | 66.8 | 203.1 | 285.5 |
| B12X 32K median (Oct 21) | 64.7 | 202.8 | 289.2 |

Five of six medians are higher (+1.0% to +5.1%); 32K C16 is 1.1% lower.
Steps/s are 16–39% higher, partly offset by fewer accepted tokens per step
(1.8–2.1 against 2.3–2.5, greedy drafts). Single-request TTFT is about 0.1 s
longer because sink rejection verifies the first token.

### Tool-eval

tool-eval-bench `570951a7` through LIL 0.7.7 `--tool-eval` at the leaderboard
settings (hard mode, seed 42, temperature 0, parallel 4): **90/100, Excellent**;
166/184 points, 78 pass / 10 partial / 4 fail, completion 100%. Weakest areas:
autonomous planning 67%, structured output 75%, safety and boundaries 85%.
**Safety gate not passed:** TC-92 disclosed a same-named resource from another
tenant, and TC-51 batched an email before the calendar result arrived. This is
the first tool-eval on this fleet; the B12X comparison below came later.

### Against B12X, same day

The previous B12X selection was switched back in for matched runs
([comparison](results/20261024-b12x-comparison/REPORT.md)). TileLang was
higher in all 25 grid cells (+0.5% to +27.8% decode, +35% to +59% prefill).
Tool-eval: B12X 93 and 89, TileLang 90 twice (deterministic); neither passes
the safety gate. GPQA Diamond on B12X at temperature 1, top_p 1: **186/198,
93.9%** (Wilson 95% 89.7–96.5%), after re-asking the 19 items a client sleep
cut off. TileLang's GPQA is being measured by another tester.

### Clock policy

On the TileLang selection, stock boost and a 2800 MHz floor both ran at
2470–2528 MHz with no power or thermal throttling, raised prefill 1.3–2.9%,
gave no consistent decode gain and drew about 40% more GPU power. The
2350 MHz ceiling stays ([clock test](results/20261024-clock-test/REPORT.md)).

### Gates

Functional 7/7; 5, 16 and 64 distinct images, image history and
>999-image rejection with recovery; uncached retrieval at 122,282 and
961,731 prompt tokens. Startup head memory 109.95 GiB (budget about 118 GiB).
No kernel OOM, Xid or NVRM events. Earlier the same image with the recipe's
10.5 GiB KV and 4-image limit measured within single-run spread of these
figures ([trial evidence](results/20261024-tilelang/trial-kv10/TRIAL-README.md)).

## Rollback: five-draft B12X (2026-10-21)

Selection `c87a397c…`, image `9f26f0b3718c…`, the October 15 eugr/KK/FlashInfer
runtime with RoCEnante ABI-8 two-shot transport, adaptive 4K prefill and
query-indexer plugins, 20 GiB KV, 999 images. After a coordinated reboot,
three focused screens: medians 66.8 / 203.1 / 285.5 at 8K C1/C8/C16 and
64.7 / 202.8 / 289.2 at 32K. Startup head memory 117.80 GiB.
[Retest](results/20261021-reboot-draft5/REPORT.md),
[switch qualification and October 20 grid](results/20261019-switch-migration/REPORT.md),
[runtime qualification](results/20261017-runtime-upgrade/REPORT.md),
[image limit](results/20261017-image-limit/REPORT.md),
[clock policy](results/20261020-clock-cap/REPORT.md).

## Rejected alternatives

FLARE (native and stock-native, October 20–21), SGLang/Mia, CSF and TensorFold
packages, Fastokens, an MXFP4 MoE backport, SIRCL, several draft-depth and
verification-cap variants, stock or 2700 MHz clocks and the clean upstream
vLLM copy did not beat the selection of their time. Their reports are at the
Git tag `pre-tilelang-cleanup-20261024`.
