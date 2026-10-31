# Results

All timed results use unmodified LIL 0.7.6: temperature 1, model-default
thinking, 20-second cells, max 2048 output tokens, `--no-hw-monitor`.
Values are aggregate output tokens/s; C>1 is aggregate, not per stream.
Compare only matching protocols and startups.

## Selected: FLARE, package update (2026-10-30)

`flare-inference a161b17f`, package `@gb10` commit `ab4f07af` (deployment
`7cf40bec…`, 8,192-token prefill chunks), verification alpha 0.5, 17.9 GiB
KV per GPU (20,942,336 tokens). Quick grid against the old package after its
reboot, single runs ([report](results/20261030-flare-ab4f07af/REPORT.md)):

| Context | C1 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|
| 8K | 68.4 (68.0) | 143.6 (145.3) | 202.0 (189.2) | 272.3 (275.6) | 4,000 (4,000) |
| 64K | 66.9 (66.0) | 158.8 (143.0) | 197.4 (182.1) | 267.2 (259.6) | 4,871 (4,499) |
| 128K | 64.3 (66.5) | 143.8 (152.4) | 201.4 (188.6) | 255.9 (260.0) | 4,832 (4,589) |

Old package in parentheses. C8 gains 7–8% from alpha 0.5 (with alpha 1.0
it was 177–191), and prefill gains 5–8% at 64K–128K. C1, C4 and C16 are
within single-cell noise. Functional 7/7. The stray-token issue
([NVIDIA/spark-local-inference#118](https://github.com/NVIDIA/spark-local-inference/issues/118))
still reproduces.

## FLARE cutover (2026-10-27)

`flare-inference 7c22369f`, package `DeepSeek-V4.1-Flash-1017-FLARE@gb10`
(`607c1abf`, deployment `0a377833…`), MTP up to five drafts, 16.6 GiB KV per
GPU (19,306,112 tokens), 2350 MHz ceiling. Made the default by the user;
B12X was not re-run after the cutover. Startup head memory 110.86 GiB
([report](results/20261027-flare/REPORT.md)).

| Context | C1 | C2 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|---:|
| 8K | 58.9 | 99.9 | 141.1 | 179.4 | 253.8 | 3,873 |
| 16K | 60.1 | 95.7 | 143.2 | 168.9 | 253.4 | 4,102 |
| 32K | 63.6 | 98.3 | 146.5 | 176.1 | 246.7 | 4,444 |
| 64K | 63.4 | 98.6 | 140.2 | 200.4 | 245.8 | 4,479 |
| 128K | 61.0 | 95.9 | 136.7 | 198.4 | 261.0 | 4,411 |

Against B12X on 2026-10-24 (same harness and arguments, single runs): C1
−0.6% to −6.7%, C2 +1.2% to +25.4%, C4 +0.1% to +6.5%, C8 −10.7% to +10.7%
(lower to 32K, higher at 64K–128K), C16 −8.5% to +0.2%, prefill −0.6% to
+9.5%. Coding peak median 100.3 (B12X 104.1). The October 20 FLARE release had
been 6–24% slower than vLLM in every cell.

Functional 7/7; uncached retrieval at 122,280 and 923,228 prompt tokens; 1000
distinct images in one request. Known issue: occasional spliced stray tokens
in short chat replies, once the internal `<ds_safety>` annotation (about 2 in
60 with varied seeds). GPQA Diamond and tool-eval not yet run on FLARE.

## Retired: five-draft B12X (production 2026-10-24 to 2026-10-27)

Selection `c87a397c…`, image `9f26f0b3718c…`, 20 GiB KV, 999 images, 2350 MHz
ceiling. The user made it the production default again after the same-day
comparison below, choosing GPQA Diamond accuracy over TileLang's speed:
**186/198, 93.9%** here against 90.91% measured for TileLang by another
tester, who also saw it loop and get stuck on some questions (not measured on
this fleet; with 198 items one run resolves roughly
±3.5 points). Switched back with `promote.py rollback` at 02:35 UTC on
October 25; functional 0 failures, head memory 117.83 GiB
([receipts](results/20261024-b12x-production)).

Same-day grid (aggregate output tok/s; [comparison](results/20261024-b12x-comparison/REPORT.md)):

| Context | C1 | C2 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|---:|
| 8K | 63.1 | 90.7 | 140.0 | 197.7 | 272.7 | 3,898 |
| 16K | 63.5 | 93.0 | 134.4 | 186.7 | 266.8 | 3,746 |
| 32K | 64.0 | 93.9 | 146.1 | 197.3 | 265.8 | 4,059 |
| 64K | 64.9 | 78.6 | 133.4 | 181.0 | 268.7 | 4,498 |
| 128K | 62.9 | 94.8 | 136.5 | 189.2 | 260.6 | 4,305 |

Tool-eval 93 and 89 (safety gate not passed).

The build is the October 15 eugr/KK/FlashInfer runtime with RoCEnante ABI-8
two-shot transport and adaptive 4K prefill and query-indexer plugins, first
selected on 2026-10-21. After a coordinated reboot that day,
three focused screens: medians 66.8 / 203.1 / 285.5 at 8K C1/C8/C16 and
64.7 / 202.8 / 289.2 at 32K. Startup head memory 117.80 GiB.
[Retest](results/20261021-reboot-draft5/REPORT.md),
[switch qualification and October 20 grid](results/20261019-switch-migration/REPORT.md),
[runtime qualification](results/20261017-runtime-upgrade/REPORT.md),
[image limit](results/20261017-image-limit/REPORT.md),
[clock policy](results/20261020-clock-cap/REPORT.md).

## Retired: spark-ds41f TileLang (selected 2026-10-24, stood down the same day)

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
cut off. Another tester measured 90.91% for TileLang, with looping on some
questions; the user then re-selected B12X.

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

## Rejected alternatives

The October 20–21 FLARE releases (native and stock-native), SGLang/Mia, CSF and TensorFold
packages, Fastokens, an MXFP4 MoE backport, SIRCL, several draft-depth and
verification-cap variants, stock or 2700 MHz clocks and the clean upstream
vLLM copy did not beat the selection of their time. Their reports are at the
Git tag `pre-tilelang-cleanup-20261024`.
