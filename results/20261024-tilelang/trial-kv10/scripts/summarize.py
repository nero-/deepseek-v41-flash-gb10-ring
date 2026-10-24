#!/usr/bin/env python3
"""Tabulate every trial, same-day control and October 21 run; choose no replicate."""
import csv
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO, RESULTS, save  # noqa: E402

OCT21 = REPO / 'results/20261021-reboot-draft5'
FIELDS = ['aggregate_tps', 'server_steps_per_s', 'server_accept_len_effective', 'ttft_p50',
          'server_spec_drafts', 'server_spec_draft_tokens', 'server_spec_accepted_tokens', 'num_errors']


def runs(directory, prefix):
    found = []
    for i in range(1, 10):
        path = directory / f'{prefix}-{i}.json'
        if path.exists():
            found.append(json.loads(path.read_text()))
    return found


def index(run):
    return {(r['context_tokens'], r['concurrency']): r for r in run['results']}


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


arms = {'tilelang': runs(RESULTS, 'tilelang-run'), 'control': runs(RESULTS, 'control-run'),
        'oct21': runs(OCT21, 'five-draft-run')}
if not arms['tilelang']:
    raise SystemExit('no trial runs recorded')
cells = sorted(index(arms['tilelang'][0]))
summary, flat = [], []
for cell in cells:
    row = {'context_tokens': cell[0], 'concurrency': cell[1]}
    for arm, recorded in arms.items():
        rows = [index(r).get(cell) for r in recorded]
        row[arm] = {'runs': [r['aggregate_tps'] for r in rows if r],
                    'median': median(r['aggregate_tps'] for r in rows if r),
                    'median_steps_per_s': median(r.get('server_steps_per_s') for r in rows if r),
                    'median_tokens_per_step': median(r.get('server_accept_len_effective') for r in rows if r),
                    'median_ttft_p50': median(r.get('ttft_p50') for r in rows if r)}
        for i, r in enumerate(rows, 1):
            if r:
                flat.append({'arm': arm, 'run': i, 'context_tokens': cell[0], 'concurrency': cell[1],
                             **{k: r.get(k) for k in FIELDS}})
    for reference in ('control', 'oct21'):
        if row[reference]['median']:
            row[f'change_vs_{reference}_pct'] = 100 * (row['tilelang']['median'] / row[reference]['median'] - 1)
    summary.append(row)

with (RESULTS / 'decode-measurements.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(flat[0]))
    writer.writeheader()
    writer.writerows(flat)
coding = {arm: [r['coding_peak']['summary']['median_generation_tok_s'] for r in recorded]
          for arm, recorded in arms.items()}
prefill = {arm: [{k: v.get('client_tok_per_sec') for k, v in r['prefill'].items()} for r in recorded]
           for arm, recorded in arms.items()}
save('summary.json', {'cells': summary, 'coding_run_medians': coding, 'prefill_client_tok_per_sec': prefill,
                      'run_counts': {arm: len(v) for arm, v in arms.items()}})

print('| Context | C | TileLang runs | TileLang median | Control median | vs control | Oct 21 median | vs Oct 21 |')
print('| --- | --- | --- | --- | --- | --- | --- | --- |')
for s in summary:
    t, c, o = s['tilelang'], s['control'], s['oct21']
    fmt = lambda v: f'{v:.2f}' if v else '-'
    pct = lambda k: f"{s[k]:+.1f}%" if k in s else '-'
    print(f"| {s['context_tokens'] // 1024}K | {s['concurrency']} | {', '.join(f'{v:.1f}' for v in t['runs'])} | "
          f"{fmt(t['median'])} | {fmt(c['median'])} | {pct('change_vs_control_pct')} | {fmt(o['median'])} | "
          f"{pct('change_vs_oct21_pct')} |")
print()
print('| Context | C | TileLang steps/s | Control steps/s | TileLang tok/step | Control tok/step | TileLang TTFT p50 | Control TTFT p50 |')
print('| --- | --- | --- | --- | --- | --- | --- | --- |')
for s in summary:
    t, c = s['tilelang'], s['control']
    fmt = lambda v, n=2: f'{v:.{n}f}' if v else '-'
    print(f"| {s['context_tokens'] // 1024}K | {s['concurrency']} | {fmt(t['median_steps_per_s'])} | "
          f"{fmt(c['median_steps_per_s'])} | {fmt(t['median_tokens_per_step'], 3)} | "
          f"{fmt(c['median_tokens_per_step'], 3)} | {fmt(t['median_ttft_p50'], 3)} | {fmt(c['median_ttft_p50'], 3)} |")
print()
print('coding run medians:', {k: [round(x, 1) for x in v] for k, v in coding.items()})
for arm, rows in prefill.items():
    print('prefill', arm, [{k: round(v) for k, v in r.items() if v} for r in rows])
