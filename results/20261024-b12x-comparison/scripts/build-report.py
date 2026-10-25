#!/usr/bin/env python3
"""Write REPORT.md from this directory's raw results (and the TileLang selection's grid)."""
import json
import math
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1]
TILELANG = RESULTS.parent / '20261024-tilelang'


def load(path):
    return json.loads(Path(path).read_text())


def cells(run):
    return {(r['context_tokens'], r['concurrency']): r['aggregate_tps'] for r in run['results']}


def wilson(k, n, z=1.96):
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


b12x_grid, tl_grid = load(RESULTS / 'b12x-full-grid-1.json'), load(TILELANG / 'full-grid.json')
tools = [('B12X', 1, load(RESULTS / 'b12x-tool-eval-1.json')), ('B12X', 2, load(RESULTS / 'b12x-tool-eval-2.json')),
         ('TileLang', 1, load(TILELANG / 'tool-eval.json')), ('TileLang', 2, load(RESULTS / 'tilelang-tool-eval-2.json'))]
gpqa = load(RESULTS / 'b12x-gpqa-diamond-t1-1.json')
rerun = load(RESULTS / 'b12x-gpqa-diamond-rerun-scores.json')
r = rerun['summary']
acc = gpqa['accuracy']

out = []
w = out.append
w('# B12X versus TileLang: speed, tool calling and GPQA Diamond')
w('')
w('The user suspected the TileLang selection (`4d2bc32e…`, image `2fc5565e9c15…`) had lost quality, as its '
  'tool-eval score looked low. The previous five-draft B12X selection (`c87a397c…`, image `9f26f0b3718c…`) was '
  'switched back in with `image/tilelang-ds41f/promote.py rollback` and measured with the same tools on '
  '2026-10-24, then TileLang was reselected (`promote.py reselect`). Each switch and run checked the installed '
  'selection, all four containers\' images and API health, and ran `bench/functional.py` (zero failures every '
  'time). The comparison ended on TileLang; the user then re-selected B12X as the production default '
  '(see the end of this report).')
w('')
w('## Full decode/prefill grid (LIL 0.7.6)')
w('')
w('Same 25-cell protocol as the TileLang [grid](../20261024-tilelang/REPORT.md): temperature 1, 20 s cells, '
  '2,048 max tokens, coding probes. Aggregate output tok/s, B12X / TileLang (change).')
w('')
b, t = cells(b12x_grid), cells(tl_grid)
contexts = sorted({c for c, _ in b})
conc = sorted({n for _, n in b})
w('| Context | ' + ' | '.join(f'C{n}' for n in conc) + ' |')
w('|---' * (len(conc) + 1) + '|')
for ctx in contexts:
    w(f'| {ctx // 1024}K | ' + ' | '.join(
        f'{b[(ctx, n)]:.1f} / {t[(ctx, n)]:.1f} ({100 * (t[(ctx, n)] / b[(ctx, n)] - 1):+.1f}%)' for n in conc) + ' |')
w('')
better = sum(t[c] > b[c] for c in b)
w(f'TileLang is higher in {better} of {len(b)} cells. Cold prefill, B12X / TileLang tok/s:')
w('')
w('| Context | B12X | TileLang | Change |')
w('|---|---:|---:|---:|')
for ctx, row in b12x_grid['prefill'].items():
    new = tl_grid['prefill'][ctx]['tok_per_sec']
    w(f'| {int(ctx) // 1024}K | {row["tok_per_sec"]:.0f} | {new:.0f} | {100 * (new / row["tok_per_sec"] - 1):+.1f}% |')
w('')
w('## Tool calling (LIL 0.7.7 `--tool-eval`)')
w('')
w('tool-eval-bench `570951a7` at the leaderboard settings (hard mode, seed 42, temperature 0, parallel 4).')
w('')
w('| Build | Run | Score | Points | Pass / partial / fail | Safety gate | Median turn |')
w('|---|---|---:|---:|---|---|---:|')
for name, i, run in tools:
    s = run['tool_eval']['summary']
    w(f'| {name} | {i} | {s["final_score"]} | {s["total_points"]}/{s["max_points"]} | '
      f'{s["pass"]} / {s["partial"]} / {s["fail"]} | {"passed" if s["safety_gate_passed"] else "not passed"} | '
      f'{s["median_turn_ms"] / 1000:.2f} s |')
w('')
w('TileLang is batch-invariant and scored identically twice (same points and tokens). B12X varied by four '
  'points between its own runs, and TileLang sits inside that range. Neither build passes the safety gate. '
  'This gives no evidence of a TileLang tool-calling loss.')
w('')
w('## GPQA Diamond on B12X (LIL 0.7.6 `--test-profile gpqa-diamond`)')
w('')
w('198 questions, temperature 1, top_p 1 (the model\'s recommended sampling and the server default), no seed, '
  'concurrency 16, 131,072 max tokens, 600 s stall watchdog. One run, as the user asked; TileLang accuracy is '
  'being measured separately by another tester. MMLU-Pro was started on neither build: the user skipped it.')
w('')
lo, hi = wilson(r['combined_correct'], r['items'])
w(f'**Accuracy: {r["combined_correct"]}/{r["items"]} = {100 * r["combined_accuracy"]:.1f}%** '
  f'(Wilson 95% {100 * lo:.1f}–{100 * hi:.1f}%).')
w('')
w(f'The full run scored {acc["correct"]}/{acc["scored"]} ({100 * acc["accuracy"]:.1f}%) with {acc["errors"]} '
  'errors, but that headline is not a model result. The Mac running the client idle-slept on battery at '
  '21:35:30 UTC (woken 21:55:12) and again 22:05:41–22:11:49. The 16 streams in flight were closed as STALL by '
  'the watchdog after the wake; 3 requests sent in the burst afterwards failed immediately with `ReadError`. '
  'The B12X server logs show all 198 requests received (HTTP 200), every one finished, no aborts, and the engine '
  'idle from 21:51 to 22:05 while the client waited. No kernel or network events on the head.')
w('')
w(f'Those {r["lost_rerun"]} lost items (every STALL, including two that had already printed an answer, plus the '
  f'3 errors) were re-asked on B12X with LIL 0.7.6\'s own dataset builder, streaming request and scorer and the '
  f'same settings ([script](scripts/rerun_gpqa.py), [scores](b12x-gpqa-diamond-rerun-scores.json)). All '
  f'{r["lost_rerun"]} completed cleanly; {r["lost_rerun_correct"]} were correct. The other '
  f'{r["unaffected_items"]} items keep their original scores ({r["unaffected_correct"]} correct). The '
  f'accuracy above merges only the lost items.')
w('')
w(f'At the user\'s request the {r["wrong_rerun"]} items B12X answered wrongly were re-asked too: '
  f'{r["wrong_rerun_now_correct"]} came out right. That is a repeat check, not a score: re-asking only wrong '
  'answers would bias accuracy upwards. Most misses repeat, so they look like model errors rather than '
  'sampling luck.')
w('')
w('With 198 items one run resolves roughly ±3.5 points, so a TileLang result in the low 90s would be '
  'indistinguishable from B12X.')
w('')
w('## Production decision')
w('')
w('Another tester measured 90.91% GPQA Diamond for TileLang and saw it loop and get stuck on some '
  'questions (not measured on this fleet). GPQA Diamond rankings are separated by fractions of a percent, so the user re-selected B12X as the production default, '
  'accepting TileLang\'s speed loss. `promote.py rollback` ran at 02:35 UTC on 2026-10-25; functional 0 '
  'failures, head memory 117.83 GiB ([receipts](../20261024-b12x-production)). TileLang stays stopped as '
  '`ds41-tilelang-rN` and returns with `promote.py reselect`.')
w('')
w('## Precision')
w('')
w('A claim that TileLang computes the mHC stream projection in TF32 rather than FP32 applies to spark-ds41f '
  'builds before 2026-10-11. In the TileLang image, `vllm/models/deepseek_v4_1/tilelang/mhc.py` splits each FP32 '
  '`fn` weight into three exact TF32 parts and runs three tensor-core GEMMs into one FP32 accumulator (exact '
  'products, FP32 precision, as DeepSeek\'s reference `x.float() @ hc_fn`). `VLLM_FLOAT32_MATMUL_PRECISION` is '
  'at its `highest` default and not overridden by the selection.')
w('')
w('## Operations note')
w('')
w('Run long benchmarks from the Mac under `caffeinate -i` and on AC power; the re-run did.')
w('')
(RESULTS / 'REPORT.md').write_text('\n'.join(out))
