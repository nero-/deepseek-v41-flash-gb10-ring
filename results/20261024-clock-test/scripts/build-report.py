#!/usr/bin/env python3
"""Write REPORT.md from this directory's raw results; one screen per arm, no replicate chosen."""
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1]
EARLIER = [RESULTS.parent / f'20261024-tilelang/screen-run-{i}.json' for i in (1, 2, 3)]
ARMS = [('cap2350', '0–2350 MHz ceiling (selected)'), ('stock', 'driver stock boost (`-rgc`)'),
        ('floor2800', '2800–3003 MHz lock (`-lgc 2800,3003`)')]


def load(path):
    return json.loads(Path(path).read_text())


def busy(telemetry, phase):
    return [r for s in telemetry['samples'] if s['phase'] == phase for r in s['ranks'] if r['util_pct'] > 50]


screens = {a: load(RESULTS / f'{a}-screen.json') for a, _ in ARMS}
telemetry = {a: load(RESULTS / f'{a}-telemetry.json') for a, _ in ARMS}
execution = {a: load(RESULTS / f'{a}-screen-execution.json') for a, _ in ARMS}
earlier = [load(p)['summary_table'] for p in EARLIER]
restored, verify = load(RESULTS / 'restored.json'), load(RESULTS / 'restored-verify.json')
base = screens['cap2350']

out = []
w = out.append
w('# GPU clock policy on the TileLang selection')
w('')
w('After the fleet was moved to a cooler room (under 70 °C under load), the user asked whether to push clocks '
  'back to maximum, or higher. On 2026-10-24 the TileLang selection (`4d2bc32e…`) was measured under three '
  'policies applied to all four nodes ([script](scripts/clocks.py)): one LIL 0.7.6 screen each (temperature 1, '
  '20 s cells, 2,048 max tokens, C1/C8/C16 at 8K/32K/128K, cold prefill at 8K–128K, coding probes), driver '
  'throttle counters before and after the screen, then a separate untimed telemetry pass (16 concurrent '
  '1,500-token requests, then a nonce-prefixed 32K prefill) sampled every 2 s on every node. The GX10s were set '
  'with `sudo nvidia-smi`, the Sparks through a privileged `nsenter` container running the host `nvidia-smi`.')
w('')
w('## Policies')
w('')
w('| Policy | Active SM clock, decode / prefill (MHz) | Peak GPU W, decode / prefill | Peak °C | Power-cap / thermal throttle during screen |')
w('|---|---|---|---:|---|')
for arm, label in ARMS:
    d, p = busy(telemetry[arm], 'decode-c16'), busy(telemetry[arm], 'prefill-32k')
    x = execution[arm]
    cap = [a['SW Power Capping'] - b['SW Power Capping'] for a, b in zip(x['counters_after'], x['counters_before'])]
    thermal = [a['SW Thermal Slowdown'] - b['SW Thermal Slowdown'] + a['HW Thermal Slowdown'] - b['HW Thermal Slowdown']
               for a, b in zip(x['counters_after'], x['counters_before'])]
    w(f'| {label} | {min(r["sm_mhz"] for r in d)}–{max(r["sm_mhz"] for r in d)} / '
      f'{min(r["sm_mhz"] for r in p)}–{max(r["sm_mhz"] for r in p)} | '
      f'{max(r["power_w"] for r in d):.0f} / {max(r["power_w"] for r in p):.0f} | '
      f'{max(r["temp_c"] for r in d + p)} | {"none" if not any(cap) and not any(thermal) else f"{cap} µs / {thermal} µs"} |')
w('')
w('The 2800 MHz floor was accepted by the driver but not reached: the GPUs ran at the same 2470–2528 MHz as stock '
  'boost, with no power-cap or thermal throttling recorded. Stock boost tops out there on this load; the 3003 MHz '
  'maximum is not reachable, and no overclock control is exposed (power limits and supported clocks report N/A).')
w('')
w('## Throughput')
w('')
w('Aggregate output tok/s; change against the 2350 screen. The last column is the range of the three earlier '
  '2350 screens of the same selection ([report](../20261024-tilelang/REPORT.md)), for scale.')
w('')
w('| Cell | 2350 | Stock | 2800 floor | Earlier 2350 range |')
w('|---|---:|---:|---:|---|')
for ctx in base['summary_table']:
    for n in base['summary_table'][ctx]:
        ref = base['summary_table'][ctx][n]
        vals = [screens[a]['summary_table'][ctx][n] for a in ('stock', 'floor2800')]
        prior = [e[ctx][n] for e in earlier if ctx in e]
        w(f'| {int(ctx) // 1024}K C{n} | {ref:.1f} | ' + ' | '.join(f'{v:.1f} ({100 * (v / ref - 1):+.1f}%)' for v in vals)
          + f' | {f"{min(prior):.1f}–{max(prior):.1f}" if prior else "–"} |')
for ctx, row in base['prefill'].items():
    ref = row['tok_per_sec']
    vals = [screens[a]['prefill'][ctx]['tok_per_sec'] for a in ('stock', 'floor2800')]
    w(f'| {int(ctx) // 1024}K prefill | {ref:.0f} | ' + ' | '.join(f'{v:.0f} ({100 * (v / ref - 1):+.1f}%)' for v in vals)
      + ' | – |')
w('')
w('Stock boost raised cold prefill 1.4–2.2% and left decode between −5.4% and +1.7%, mostly within the earlier 2350 '
  'screens\' spread, for about 40% more GPU power. The 2800 floor was lower in most decode cells. As on '
  '2026-10-20 (B12X), higher clocks give no consistent decode gain, as expected if decode is bound by memory '
  'bandwidth rather than SM clock. The 2350 ceiling stays.')
w('')
w('## Restoration')
w('')
ok = restored['service_ok']
peak = max(r['sm_mhz'] for s in verify['samples'] for r in s['ranks'] if r['util_pct'] > 50)
steady = [r['sm_mhz'] for s in verify['samples'][3:] for r in s['ranks']]
w(f'`systemctl reload gb10-gpu-clock-cap.service` ran on all four nodes (service active, enabled, '
  f'`-lgc 0,2350`: {"verified" if ok else "NOT verified"}), and each journal logged '
  '`GPU clocks set to "(gpuClkMin 0, gpuClkMax 2350)"`. Samples taken in the first seconds still reported the '
  f'previous clocks (up to {peak} MHz); under a following C16 load the nodes settled within about 4 s at '
  f'{min(steady)}–{max(steady)} MHz ([receipt](restored.json), [verification](restored-verify.json)). Clock '
  'readings lag a change by a few seconds.')
w('')
(RESULTS / 'REPORT.md').write_text('\n'.join(out))
