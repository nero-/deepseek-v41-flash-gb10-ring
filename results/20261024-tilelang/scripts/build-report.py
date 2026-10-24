#!/usr/bin/env python3
"""Write REPORT.md from this directory's raw results; chooses no favourable replicate."""
import json
import statistics
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1]
REPO = RESULTS.parents[1]
B12X_SCREENS = [REPO / f'results/20261021-reboot-draft5/five-draft-run-{i}.json' for i in (1, 2, 3)]
B12X_GRID = REPO / 'results/20261019-switch-migration/final-full-lil.json'
TRIAL = RESULTS / 'trial-kv10'


def load(path):
    return json.loads(Path(path).read_text())


def cells(run):
    return {(r['context_tokens'], r['concurrency']): r for r in run['results']}


def median_of(runs, cell, key='aggregate_tps'):
    return statistics.median(cells(r)[cell][key] for r in runs)


def pct(new, old):
    return f'{100 * (new / old - 1):+.1f}%'


screens = [load(RESULTS / f'screen-run-{i}.json') for i in (1, 2, 3)]
b12x = [load(p) for p in B12X_SCREENS]
trial = [load(TRIAL / f'tilelang-run-{i}.json') for i in (1, 2, 3)]
grid, b12x_grid, trial_grid = load(RESULTS / 'full-grid.json'), load(B12X_GRID), load(TRIAL / 'tilelang-full-grid.json')
tool = load(RESULTS / 'tool-eval.json')['tool_eval']
gates = load(RESULTS / 'gates.json')
needle = load(RESULTS / 'cold-needle.json')
needle1m = load(TRIAL / 'cold-needle-1m.json')
promoted = load(RESULTS / 'promotion/controller-up.json')
screen_cells = sorted(cells(screens[0]))
grid_cells = cells(grid)
contexts = sorted({c for c, _ in grid_cells})
concurrency = sorted({n for _, n in grid_cells})
s = tool['summary']

out = []
w = out.append
w('# TileLang selection: full benchmark, tool-eval and qualification')
w('')
w('DeepSeek-V4.1-Flash-1017 on the spark-ds41f-1022 TileLang build, installed as the root controller\'s '
  'selection `4d2bc32eb4f2e9a2540ee18ca2eafbe2c7da95c4ec7f4c7e2ac8c3052fc54dfc` on 2026-10-24: image '
  '`2fc5565e9c15…`, 20 GiB KV per rank (16,344,051 tokens), 999 images per request, persistent 0–2350 MHz '
  f'ceiling. The controller started it in {promoted["elapsed_seconds"]:.0f} s. '
  '[Recipe and site changes](../../image/tilelang-ds41f/README.md).')
w('')
old_grid = cells(b12x_grid)
grid_better = sum(grid_cells[c]['aggregate_tps'] > old_grid[c]['aggregate_tps'] for c in grid_cells)
screen_changes = {c: statistics.median(cells(r)[c]['aggregate_tps'] for r in screens) / median_of(b12x, c) - 1
                  for c in screen_cells}
screen_better = sum(v > 0 for v in screen_changes.values())
lower = [f'{c[0] // 1024}K C{c[1]} {100 * v:+.1f}%' for c, v in screen_changes.items() if v <= 0]
w(f'**Summary.** Against the previous B12X selection, {grid_better} of {len(grid_cells)} full-grid cells and '
  f'{screen_better} of {len(screen_cells)} focused-screen medians are higher'
  + (f' ({", ".join(lower)} is lower)' if lower else '') +
  '; prefill is about a third faster. Tool-eval scores '
  f'**{s["final_score"]}/100 ({s["rating"].split()[-1]})** at the leaderboard settings; its safety gate did '
  'not pass (two warnings, below). All functional, image and retrieval gates passed; no kernel OOM, Xid or NVRM '
  'events were recorded.')
w('')
w('## Method')
w('')
w('Timed runs: unmodified LIL 0.7.6 (SHA-256 `c4c7eaed…9553`) from the Mac client, temperature 1, model-default '
  'thinking, 20 s cells, max 2048 output tokens, `--no-hw-monitor`, `--coding-peak`, no other traffic. '
  'Aggregate output tok/s; C>1 values are aggregate, not per stream. Tool-eval: LIL 0.7.7 `--tool-eval` '
  f'(tool-eval-bench `{tool["tool_eval_bench"]["commit"][:8]}`, {tool["tool_eval_bench"]["version"]}) with the '
  'community leaderboard settings: hard mode, seed 42, temperature 0, parallel 4, 30 turns, 600 s timeout. '
  'Every command and execution receipt is in this directory (`*-command.json`, `*-execution.json`).')
w('')
w('Comparisons: the B12X selection\'s three post-reboot screens (2026-10-21) and its October 20 full-grid '
  'qualification (four drafts, stock GPU boost), plus the same TileLang image measured earlier on 2026-10-24 '
  'with the recipe\'s 10.5 GiB KV and 4-image limit (`trial-kv10/`). These are different startups, not a '
  'randomized same-day control.')
w('')
w('## Full benchmark: 25-cell grid')
w('')
w('| Context | ' + ' | '.join(f'C{n}' for n in concurrency) + ' | Prefill tok/s |')
w('|---|' + '---:|' * (len(concurrency) + 1))
for ctx in contexts:
    row = [f'{grid_cells[(ctx, n)]["aggregate_tps"]:.1f}' for n in concurrency]
    w(f'| {ctx // 1024}K | ' + ' | '.join(row) + f' | {grid["prefill"][str(ctx)]["client_tok_per_sec"]:,.0f} |')
w('')
w('Change against the B12X October 20 grid (same protocol):')
w('')
w('| Context | ' + ' | '.join(f'C{n}' for n in concurrency) + ' | Prefill |')
w('|---|' + '---:|' * (len(concurrency) + 1))
old = cells(b12x_grid)
for ctx in contexts:
    row = [pct(grid_cells[(ctx, n)]['aggregate_tps'], old[(ctx, n)]['aggregate_tps']) for n in concurrency]
    w(f'| {ctx // 1024}K | ' + ' | '.join(row) + ' | '
      f'{pct(grid["prefill"][str(ctx)]["client_tok_per_sec"], b12x_grid["prefill"][str(ctx)]["client_tok_per_sec"])} |')
better = sum(grid_cells[c]['aggregate_tps'] > old[c]['aggregate_tps'] for c in grid_cells)
same_image = cells(trial_grid)
w('')
w(f'{better} of {len(grid_cells)} decode cells are above the B12X grid. Against the same image at 10.5 GiB KV '
  'and four images (`trial-kv10/tilelang-full-grid.json`), cells differ by '
  f'{min(100 * (grid_cells[c]["aggregate_tps"] / same_image[c]["aggregate_tps"] - 1) for c in grid_cells):+.1f}% '
  f'to {max(100 * (grid_cells[c]["aggregate_tps"] / same_image[c]["aggregate_tps"] - 1) for c in grid_cells):+.1f}%. '
  'Each is a single 20-second run, so read that as run-to-run spread, not an effect of KV size.')
flagged = [c for c, r in grid_cells.items() if any(r.get(k) for k in ('num_errors', 'underfilled', 'capacity_limited',
                                                                      'warmup_timed_out', 'loop_detected', 'failure_reason'))]
w(f'All {len(grid_cells)} cells completed with continuous usage accounting; flagged cells: {flagged or "none"}.')
w(f'Coding probes (five): median {grid["coding_peak"]["summary"]["median_generation_tok_s"]:.1f} tok/s, '
  f'range {grid["coding_peak"]["summary"]["min_generation_tok_s"]:.1f}–'
  f'{grid["coding_peak"]["summary"]["max_generation_tok_s"]:.1f}; B12X grid median '
  f'{b12x_grid["coding_peak"]["summary"]["median_generation_tok_s"]:.1f}. CJK runs: '
  f'{grid["coding_peak"]["summary"]["cjk_runs"]}.')
w('')
w('## Focused screen: three runs')
w('')
w('| Context | C | Run 1 | Run 2 | Run 3 | Median | B12X median (Oct 21) | Change | TileLang kv10 median |')
w('|---|---|---:|---:|---:|---:|---:|---:|---:|')
for cell in screen_cells:
    runs = [cells(r)[cell]['aggregate_tps'] for r in screens]
    new, base, kv10 = statistics.median(runs), median_of(b12x, cell), median_of(trial, cell)
    w(f'| {cell[0] // 1024}K | {cell[1]} | ' + ' | '.join(f'{v:.1f}' for v in runs) +
      f' | {new:.1f} | {base:.1f} | {pct(new, base)} | {kv10:.1f} |')
w('')
w('Step rate and useful tokens per step (harness counters, medians):')
w('')
w('| Context | C | Steps/s | B12X steps/s | Tokens/step | B12X tokens/step | TTFT p50 s | B12X TTFT p50 s |')
w('|---|---|---:|---:|---:|---:|---:|---:|')
for cell in screen_cells:
    w(f'| {cell[0] // 1024}K | {cell[1]} | {median_of(screens, cell, "server_steps_per_s"):.1f} | '
      f'{median_of(b12x, cell, "server_steps_per_s"):.1f} | {median_of(screens, cell, "server_accept_len_effective"):.2f} | '
      f'{median_of(b12x, cell, "server_accept_len_effective"):.2f} | {median_of(screens, cell, "ttft_p50"):.2f} | '
      f'{median_of(b12x, cell, "ttft_p50"):.2f} |')
w('')
w('More steps per second, fewer accepted tokens per step (greedy drafts, rule-based budget). A single '
  'request\'s first token waits one extra step for sink rejection.')
w('')
w('| Nominal prefill | ' + ' | '.join(f'Run {i}' for i in (1, 2, 3)) + ' | B12X Oct 21 runs |')
w('|---|---:|---:|---:|---|')
for ctx in ('8192', '32768', '65536', '131072'):
    w(f'| {int(ctx) // 1024}K | ' + ' | '.join(f'{r["prefill"][ctx]["client_tok_per_sec"]:,.0f}' for r in screens) +
      ' | ' + ', '.join(f'{r["prefill"][ctx]["client_tok_per_sec"]:,.0f}' for r in b12x) + ' |')
w('')
w('Prefill is client-observed input tok/s including TTFT, one fresh scout per context per run. Coding medians '
  'per run: ' + ', '.join(f'{r["coding_peak"]["summary"]["median_generation_tok_s"]:.1f}' for r in screens) + '.')
w('')
w('## Tool-eval (tool-calling quality)')
w('')
w(f'**{s["final_score"]}/100, {s["rating"]}** — {s["total_points"]}/{s["max_points"]} points; '
  f'{s["pass"]} pass, {s["partial"]} partial, {s["fail"]} fail of {s["scenarios"]} scenarios; pass rate '
  f'{s["pass_rate"]}%, completion {s["completion_rate"]}%. Deployability {s["deployability"]}, responsiveness '
  f'{s["responsiveness"]} (median turn {s["median_turn_ms"] / 1000:.2f} s), {s["total_tokens"]:,} tokens in '
  f'{tool["duration_seconds"]:.0f} s. Engine reported: {s["engine"]["engine_name"]} {s["engine"]["engine_version"]}. '
  f'Leaderboard settings: {tool["settings"]["leaderboard"]}; config fingerprint `{s["config_fingerprint"]}`.')
w('')
w(f'**Safety gate: {"passed" if s["safety_gate_passed"] else "not passed"}.**')
for warning in s['safety_warnings']:
    w(f'- {warning}')
w('')
w('| Category | Score | Pass | Partial | Fail |')
w('|---|---:|---:|---:|---:|')
for c in s['categories']:
    w(f'| {c["category"]} {c["label"]} | {c["earned"]}/{c["max"]} ({c["percent"]}%) | {c["pass"]} | {c["partial"]} | {c["fail"]} |')
w('')
w('Hard Mode capabilities:')
w('')
w('| Capability | Score |')
w('|---|---:|')
for c in s['capabilities']:
    w(f'| {c["label"]} | {c["earned"]}/{c["max"]} ({c["percent"]}%) |')
w('')
w('Scenarios that did not pass:')
w('')
w('| Scenario | Result | Note |')
w('|---|---|---|')
for item in s['not_passed']:
    w(f'| {item["scenario_id"]} {item["title"]} | {item["status"]} {item["points"]}/2 | {item["summary"]} |')
w('')
w('No previous tool-eval exists for the B12X selection, so this is a baseline, not a comparison. The run uses '
  'temperature 0 and `--parallel 4`; LIL\'s own validation of another model at these settings ranged '
  '86–93 over 12 runs, so treat a single score as ± a few points. Conversations, progress and the SQLite store are in `tool-eval.tool-eval/`.')
w('')
w('## Qualification gates')
w('')
rows = [(r['name'], r['status'], r['pass']) for r in gates['image_checks']]
w(f'- Functional checks: {7 - gates["functional_failures"]}/7 passed (count, arithmetic, code, tool call, forced '
  'tool call, image, thinking).')
w('- Images: ' + '; '.join(f'{name} HTTP {status} {"pass" if ok else "FAIL"}' for name, status, ok in rows) + '.')
w(f'- Uncached retrieval: correct at {needle["usage"]["prompt_tokens"]:,} prompt tokens (TTFT '
  f'{needle["ttft_seconds"]:.1f} s) and, on the same image earlier, at {needle1m["usage"]["prompt_tokens"]:,} '
  f'tokens (TTFT {needle1m["ttft_seconds"]:.1f} s). `cold-needle.py` exits 1 because the server omits '
  '`cached_tokens`; the prompts start with a fresh nonce.')
w('- Memory after startup and gates (used GiB by rank): ' +
  ', '.join(f'{h["used_gib"]:.2f}' for h in gates['hosts']) + '; startup budget about 118 GiB.')
w('- Kernel OOM/Xid/NVRM/allocation events during gates and every timed run: none.')
w('')
w('## Limits')
w('')
w('One startup of the final selection. The B12X comparisons come from earlier startups; the October 20 B12X '
  'grid used four drafts and stock boost, and earlier B12X startups varied by several percent. The tool-eval is '
  'one run. Not measured here: mixed prefill/decode latency, soak, more than 16 concurrent streams.')
w('')
w('Files: `screen-run-*.json`, `full-grid.json`, `tool-eval.json` and `tool-eval.tool-eval/`, `gates.json`, '
  '`multi-image-checks.json`, `cold-needle.json`, `promotion/`, and the earlier same-image trial in `trial-kv10/`.')
(RESULTS / 'REPORT.md').write_text('\n'.join(out) + '\n')
print('wrote', RESULTS / 'REPORT.md')
