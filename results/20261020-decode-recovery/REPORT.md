# Decode recovery and comparison audit — October 20

The optimization campaign resumed after FLARE was rejected. The qualified
October 20 switched image remains the recovery baseline. Trials are not
promotions; check the installed selection and campaign receipts for live state.

## Comparison corrections

The public README's 71 / 137 / 194 numbers are **32K C1 / C4 / C8**, using
the original checkpoint. They are not C1 / C8 / C16 measurements of 1017.
The newer official-1017 report gives median-of-two **61.2 / 194.9 / 275.2**
at C1 / C8 / C16 with **no added decode context**. Its prefill scouts still
cover 8K/64K/128K. It uses a different fleet and SIRCL image, so reproducing
the client protocol does not make it a same-hardware comparison.

Sources: [original-model record](https://github.com/FujitsuPolycom/sparkring/blob/9932204d25ab857ec4a5a7c437f4dc0f5bddee2e/performance/records/images/release-2026.10.2-speed-32k-20261012.md),
[1017 record](https://github.com/FujitsuPolycom/sparkring/blob/9932204d25ab857ec4a5a7c437f4dc0f5bddee2e/performance/records/images/dev-20261013-dcp2prefill-status038-sircl-tp6-deepseek-v41-flash-tp4-1017-20261017.md).

All new comparisons use the unmodified public LIL 0.7.6 script,
SHA256 `c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553`,
from the external Mac client, with hardware monitoring disabled. Timed runs
and startup calibration use a temporary 2418 MHz GPU lock; every wrapper
restores stock boost afterward. Defaults remain temperature1/top_p1,
model-default thinking, full vocabulary and unchanged target precision.

The full grid is 8K/16K/32K/64K/128K × C1/2/4/8/16, 20 seconds per cell,
max2048, estimate token targeting, default 3 s initial warmup at the largest
context, followed by five coding requests. The separate public-1017 protocol
uses context0, C1/8/16, exact targeting and 5 s initial warmup. Do not pool the
protocols or substitute thinking-off requests to improve a headline.

## Original provider versus selected two-shot provider

Both completed the full grid with the same checkpoint, draft4/C1cap3,
graph sizes, KV, local plugins and CPU policy. C8 averaged **192.25 t/s**
with the selected provider versus **180.02** with the original provider;
C16 averaged **261.79 versus 254.29**. C1 averaged about 0.8% higher with
the original provider. Coding median was **91.16 versus 89.41**.
The original provider was not selected.

No request errors, loops, underfilled cells or capacity flags occurred in the
completed original-provider grid. An earlier interrupted run is excluded.
FLARE agents were disabled for the completed timed grid, but that provider's
startup calibration preceded their disablement; this limits causal attribution.
The selected provider's baseline predates the FLARE installation.

## SIRCL investigation

Direct-peer SIRCL passed isolated four-rank eager and mutable CUDA graph
correctness checks on the switch. It was not installed into the serving image.
Revised synthetic timing placed CUDA events inside each graph, avoiding
host launch gaps in the measured interval.

Small reductions and logits gathers were effectively equal to the current
provider. SIRCL's main middle-size advantage was largely reproduced by
starting the current two-shot kernel earlier: a 48×5120 BF16 reduction took
about 87.6 µs through current one-shot versus 69.4 µs through current two-shot,
and 61.2 µs through SIRCL. At 80/96 rows the current pipe was faster.
These are synthetic collective latencies, not model throughput.

A full SIRCL serving integration is deferred. The existing threshold is the
smaller independent experiment. No buffer-lifetime protection was removed,
and no host networking was changed.

## Draft-only temperature 0.8

An opt-in proposal-only overlay passed all-rank CPU/native GPU qualification,
including the proposal-logit cache contract, standard/block rejection,
mutable graph replay and greedy handling. Both serving arms passed 7/7
functional checks and 10/10 sampling/API checks. These are finite correctness
screens, not universal quality proof.

Both arms used the same overlay and CPU diagnostics. Aggregate t/s:

| Context | C1 tau1 / .8 | C8 tau1 / .8 | C16 tau1 / .8 |
|---|---:|---:|---:|
| 0 | 52.97 / 57.75 | 190.71 / 193.78 | 250.34 / 257.26 |
| 8K | 61.37 / 64.39 | 194.82 / 193.00 | 255.55 / 257.70 |
| 32K | 59.46 / 60.82 | 199.90 / 206.08 | 257.32 / 265.41 |

Tau0.8 did not consistently improve accepted output per request step. Startup
target-cost tables also varied substantially between arms despite unchanged
target code, changing admitted draft budgets. Coding mean fell **4.2%**
(88.96 to 85.24 t/s); median fell **3.5%**. No request errors or detected
loops occurred. The overlay is not promoted, and its trials were unwound to
the exact qualified native image.

Startup cost tables were exported on all ranks. The planned shutdown
dispatch-histogram export did not run, so no actual graph-dispatch histogram
is claimed. The calibration gap remains a diagnostic lead, not a demonstrated
scheduler fix.

## Earlier two-shot routing

The native image with a 256 KiB threshold passed functional checks and both
bounded LIL screens. Context-zero C1/C8/C16 reached
**61.77 / 192.54 / 264.52**; 8K reached **62.32 / 196.74 / 263.98**;
32K reached **64.56 / 198.68 / 262.72**. Coding median was **87.04 t/s**.
No decode errors or detected loops occurred.

The context screen's prefill scouts measured 3046/3826/4120/4222 input t/s
at 8K/32K/64K/128K, below the earlier qualified full-grid baseline. The
initial warmup context differs between those two grids, so this is not a
clean causal prefill regression measurement. There was no sufficient
overall advantage to select the new threshold. The synthetic middle-message
gain did not establish a worthwhile model speedup; 512 KiB is retained.

## Native five drafts

The same native image at 512 KiB, using five drafts and its corresponding
graph ladder through 96 tokens, passed functional checks and started at
117.15 GiB head total used memory. Context-zero C1/C8/C16 measured
**57.9 / 188.3 / 266.2**; 8K **60.9 / 192.5 / 255.0**; 32K
**57.4 / 186.2 / 254.3**. The two protocols remain separate single-run screens.
No request errors or loops occurred.

Coding median rose to **93.97 t/s**, but concurrency throughput was
insufficient to select the candidate. More accepted output per target step
was offset by lower step frequency. Width4/C1cap3 remains the qualified
default; upstream's five-draft setting is not automatically faster here.

## High-concurrency verification cap

The native cap table `[[1,1,3],[2,8,4],[9,16,2]]` kept four-draft computation
and allowed at most two proposals into verification at C9–16. Startup head
memory was 117.43 GiB; seven functional checks and all 16 concurrent
mixed-temperature text/JSON sequence checks passed.

Context-zero C1/C8/C16 measured **62.8 / 182.5 / 256.2**; 8K
**64.3 / 184.5 / 255.5**; 32K **61.1 / 192.7 / 262.6**.
No errors or detected loops occurred. Coding median was **86.19 t/s**.
Although C16 request-step frequency rose, output per step fell. The candidate
did not establish a worthwhile overall advantage and is not promoted.

The table leaves the C1–C8 cap values unchanged, but can change draft graph
preparation and startup cost calibration. These results therefore do not
prove that C1–C8 throughput must remain constant. A fresh native control
under the same short protocols follows the trial; full-grid results and
focused screens must retain their different warmup/context labels.

## Fresh qualified control

The exact qualified native image and configuration were restored after the
trials. Startup head total system memory used was 117.214 GiB, seven functional
checks passed, and both short protocols completed without decode errors,
loops, underfilled concurrency or capacity flags. Stock clocks were restored
after each run.

| Context | C1 | C8 | C16 |
|---|---:|---:|---:|
| 0 | 63.84 | 191.81 | 247.78 |
| 8K | 60.53 | 196.92 | 246.46 |
| 32K | 62.61 | 191.89 | 250.85 |

Coding median was 87.87 t/s. The context screen's prefill scouts were
3682 / 4329 / 4303 / 4178 input t/s at 8K / 32K / 64K / 128K.
The same image and configuration therefore did not reproduce the earlier
full-grid C16 rate in this focused run. The warmup/grid differs, so this is
not by itself a measured reboot regression.

This control also changes the interpretation of the preceding trial screens.
The 256 KiB threshold was 7.1% faster at 8K C16 and 4.7% faster at 32K C16,
with essentially equal 8K C8, but its 8K/32K prefill scouts were lower.
Five drafts improved coding and context-zero C16, with mixed context
throughput. The C9–16 cap2 improved C16 but lost 8K C8. These candidates
remain unselected; the data do not establish that the default is faster in
every workload.

The qualified control admitted approximately 3.96 / 3.97 draft tokens per
request at 8K / 32K C16, versus 2.40 / 2.41 in the earlier full grid with
the same configured maximum of four. That is an observed policy difference,
not proof of its cause. Startup calibration and warmup history require
controlled repetition before attributing the gap to a specific setting.
Native uncapped4 was the next isolated control, recorded below.

## Uncapped native draft4

Removing the native cap table while retaining width4 and the same graph ladder
passed all seven functional checks and loaded at 117.214 GiB on the head.
Context-zero C1/C8/C16 measured **61.30 / 183.61 / 256.15**; 8K measured
**60.55 / 185.21 / 256.04**; 32K measured **49.99 / 178.68 / 255.32**.
All decode error and loop flags were clear. The low 32K C1 cell is one sample,
not an established repeatable regression.

Coding median improved to **92.97 t/s**, but C8 lost 6.0% / 6.9% against the
fresh qualified 8K / 32K control. C16 improved 3.9% / 1.8%. Prefill scouts
were lower, at 3288 / 3673 / 3786 / 3709 input t/s across
8K / 32K / 64K / 128K. The trial was not selected.

A separate loaded-clock probe found all four GPUs at 2398–2411 MHz under
92–95% GPU utilization; there was no recurrence of the earlier 611 MHz fault
in that probe. It was outside the timed tests and is not another benchmark.
The exact qualified parent was restored, stopped, before preparing the native
C9–16 cap3 trial. That trial kept C1cap3 and C2–8cap4.

## Three-proposal high-concurrency cap

The native cap table `[[1,1,3],[2,8,4],[9,16,3]]` passed seven functional
checks and all 16 concurrent text/JSON checks. Startup head total system
used memory was 117.21 GiB.

| Context | C1 | C8 | C16 |
|---|---:|---:|---:|
| 0 | 56.97 | 182.79 | 254.11 |
| 8K | 59.53 | 194.77 | 255.19 |
| 32K | 58.73 | 178.24 | 259.71 |

There were no decode errors or detected loops. Coding median was 86.18 t/s.
Prefill scouts were 3739 / 4131 / 4071 / 3720 input t/s across
8K / 32K / 64K / 128K. C16 admitted about 2.21 / 2.20 drafts per request
at 8K / 32K, below the maximum of three. It slightly improved C16 over the
fresh control but did not improve serving overall, and was not selected.
The exact qualified configuration and saved containers were restored
for a second matched control across startups.

## Second qualified control and final state

The same configuration SHA256
`d86c7e0725efae1ced95a4891da59753853992aaad4fda926814531145e43ca2`
was restored on native image `9f26f0b3718cc...`. Head startup system memory
used was **117.222 GiB**. Seven functional checks passed. Both controls below
used the same short-protocol sequence, clock policy and native settings,
but different startups and stochastic generations.

| Context | C1 first / repeat | C8 first / repeat | C16 first / repeat |
|---|---:|---:|---:|
| 0 | 63.84 / 60.86 | 191.81 / 186.81 | 247.78 / 257.66 |
| 8K | 60.53 / 62.19 | 196.92 / 179.26 | 246.46 / 263.37 |
| 32K | 62.61 / 63.04 | 191.89 / 191.08 | 250.85 / 261.73 |

The repeat coding median was **85.79 t/s**. Its context-screen prefill scouts
were 3811 / 4269 / 3688 / 3866 input t/s at 8K / 32K / 64K / 128K.
All decode cells had zero errors and no loop, underfill, capacity or warmup
timeout flags. All-rank serving logs showed no JIT warnings or errors during
the repeat's timed protocols.

At 8K / 32K C16 the repeat admitted about **2.68 / 2.72** drafts per request,
versus **3.96 / 3.97** in the first short control. At C8 it admitted more
drafts than the first control. This establishes that the observed policy and
throughput changed across these runs; it does not isolate calibration from
request variation or prove a particular cost-model fix. The earlier fast
full-grid baseline also had startup calibration at 2418 MHz, confirmed by
its separate startup receipts. An undocumented startup-clock change does
not explain the difference.

No candidate from this resumed campaign is promoted. All trial selections
have been unwound. After the final control, the exact qualified fleet was
healthy and idle, the head used **117.904 GiB**, FLARE agents were stopped
and disabled, and stock-clock resets had succeeded on all four ranks.
No temporary GPU lock or experiment remains selected.

The performance goal remains unresolved. A bounded diagnostic of real
forward/draft costs and actual graph descriptors is the next evidence gate
before a scheduler patch. It must stay separate from final LIL scoring.
No live-cost correction, proxy-affinity change or DS41 top-k port is installed.

## Evidence and recovery

Private campaign:
`~/Agent/Diagnostics/deepseek-v41-flash-ring/decode-recovery-20261020/`.
It retains complete LIL JSON, argv, source/configuration hashes, container
identities, startup memory, clock-reset receipts, failed/interrupted samples
and exact reversible selection records. [Exported measurements](measurements.json)
include raw-result hashes, configuration hashes, protocol labels and all
completed samples. Public image build receipts remain immutable.
