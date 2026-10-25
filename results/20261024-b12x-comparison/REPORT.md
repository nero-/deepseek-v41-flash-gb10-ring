# B12X versus TileLang: speed, tool calling and GPQA Diamond

The user suspected the TileLang selection (`4d2bc32e…`, image `2fc5565e9c15…`) had lost quality, as its tool-eval score looked low. The previous five-draft B12X selection (`c87a397c…`, image `9f26f0b3718c…`) was switched back in with `image/tilelang-ds41f/promote.py rollback` and measured with the same tools on 2026-10-24, then TileLang was reselected (`promote.py reselect`). Each switch and run checked the installed selection, all four containers' images and API health, and ran `bench/functional.py` (zero failures every time). The fleet ends on TileLang.

## Full decode/prefill grid (LIL 0.7.6)

Same 25-cell protocol as the TileLang [grid](../20261024-tilelang/REPORT.md): temperature 1, 20 s cells, 2,048 max tokens, coding probes. Aggregate output tok/s, B12X / TileLang (change).

| Context | C1 | C2 | C4 | C8 | C16 |
|---|---|---|---|---|---|
| 8K | 63.1 / 66.5 (+5.4%) | 90.7 / 102.2 (+12.7%) | 140.0 / 155.1 (+10.8%) | 197.7 / 214.0 (+8.2%) | 272.7 / 293.7 (+7.7%) |
| 16K | 63.5 / 65.7 (+3.5%) | 93.0 / 106.6 (+14.5%) | 134.4 / 145.7 (+8.5%) | 186.7 / 205.2 (+9.9%) | 266.8 / 303.5 (+13.7%) |
| 32K | 64.0 / 67.1 (+4.8%) | 93.9 / 100.2 (+6.7%) | 146.1 / 159.7 (+9.3%) | 197.3 / 205.9 (+4.4%) | 265.8 / 294.1 (+10.7%) |
| 64K | 64.9 / 67.9 (+4.6%) | 78.6 / 100.4 (+27.8%) | 133.4 / 143.8 (+7.8%) | 181.0 / 211.6 (+16.9%) | 268.7 / 296.2 (+10.2%) |
| 128K | 62.9 / 66.0 (+5.0%) | 94.8 / 102.8 (+8.5%) | 136.5 / 137.1 (+0.5%) | 189.2 / 210.0 (+11.0%) | 260.6 / 268.9 (+3.2%) |

TileLang is higher in 25 of 25 cells. Cold prefill, B12X / TileLang tok/s:

| Context | B12X | TileLang | Change |
|---|---:|---:|---:|
| 8K | 3898 | 5441 | +39.6% |
| 16K | 3746 | 5963 | +59.2% |
| 32K | 4059 | 6122 | +50.8% |
| 64K | 4498 | 6088 | +35.3% |
| 128K | 4305 | 5964 | +38.5% |

## Tool calling (LIL 0.7.7 `--tool-eval`)

tool-eval-bench `570951a7` at the leaderboard settings (hard mode, seed 42, temperature 0, parallel 4).

| Build | Run | Score | Points | Pass / partial / fail | Safety gate | Median turn |
|---|---|---:|---:|---|---|---:|
| B12X | 1 | 93 | 171/184 | 82 / 7 / 3 | not passed | 4.11 s |
| B12X | 2 | 89 | 164/184 | 78 / 8 / 6 | not passed | 3.90 s |
| TileLang | 1 | 90 | 166/184 | 78 / 10 / 4 | not passed | 3.52 s |
| TileLang | 2 | 90 | 166/184 | 78 / 10 / 4 | not passed | 3.47 s |

TileLang is batch-invariant and scored identically twice (same points and tokens). B12X varied by four points between its own runs, and TileLang sits inside that range. Neither build passes the safety gate. This gives no evidence of a TileLang tool-calling loss.

## GPQA Diamond on B12X (LIL 0.7.6 `--test-profile gpqa-diamond`)

198 questions, temperature 1, top_p 1 (the model's recommended sampling and the server default), no seed, concurrency 16, 131,072 max tokens, 600 s stall watchdog. One run, as the user asked; TileLang accuracy is being measured separately by another tester. MMLU-Pro was started on neither build: the user skipped it.

**Accuracy: 186/198 = 93.9%** (Wilson 95% 89.7–96.5%).

The full run scored 169/195 (86.7%) with 3 errors, but that headline is not a model result. The Mac running the client idle-slept on battery at 21:35:30 UTC (woken 21:55:12) and again 22:05:41–22:11:49. The 16 streams in flight were closed as STALL by the watchdog after the wake; 3 requests sent in the burst afterwards failed immediately with `ReadError`. The B12X server logs show all 198 requests received (HTTP 200), every one finished, no aborts, and the engine idle from 21:51 to 22:05 while the client waited. No kernel or network events on the head.

Those 19 lost items (every STALL, including two that had already printed an answer, plus the 3 errors) were re-asked on B12X with LIL 0.7.6's own dataset builder, streaming request and scorer and the same settings ([script](scripts/rerun_gpqa.py), [scores](b12x-gpqa-diamond-rerun-scores.json)). All 19 completed cleanly; 18 were correct. The other 179 items keep their original scores (168 correct). The accuracy above merges only the lost items.

At the user's request the 11 items B12X answered wrongly were re-asked too: 2 came out right. That is a repeat check, not a score: re-asking only wrong answers would bias accuracy upwards. Most misses repeat, so they look like model errors rather than sampling luck.

With 198 items one run resolves roughly ±3.5 points, so a TileLang result in the low 90s would be indistinguishable from B12X.

## Precision

A claim that TileLang computes the mHC stream projection in TF32 rather than FP32 applies to spark-ds41f builds before 2026-10-11. In the selected image, `vllm/models/deepseek_v4_1/tilelang/mhc.py` splits each FP32 `fn` weight into three exact TF32 parts and runs three tensor-core GEMMs into one FP32 accumulator (exact products, FP32 precision, as DeepSeek's reference `x.float() @ hc_fn`). `VLLM_FLOAT32_MATMUL_PRECISION` is at its `highest` default and not overridden by the selection.

## Operations note

Run long benchmarks from the Mac under `caffeinate -i` and on AC power; the re-run did.
