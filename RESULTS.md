# Selected build results

The current configuration is corrected vLLM/SparkRing TP4, official 1017 weights,
HF tokenization, Engram projection TP, adaptive 4K prefill under contention,
guarded query-row indexer sharding and a 2350 MHz upper GPU clock limit.
[Exact deployment identity](results/deployment.json).

## October 17 decode tuning and selected KV budget

The current image remains selected with **20 GiB KV per rank**
(**16,344,051 logical tokens**). Startup head usage was **117.40 GiB**,
leaving **4.28 GiB available**; qualification peaked at
**118.66 GiB**. The 118 GiB goal applies just after loading,
with no automatic runtime stop guard.

Adaptive cost scales, L2 prefetch changes, extra graph coverage and greedy
draft proposals did not establish an overall decode gain. The original
current-image decode settings remain. Mean of two final public LIL 0.7.6
focused screens (both raw runs are retained in the report):

| Context | C1 | C8 | C16 |
|---|---:|---:|---:|
| 8K | 59.98 | 191.89 | 267.98 |
| 128K | 59.01 | 185.94 | 251.03 |

Aggregate output tokens/s; temperature 1, top_p 1, default thinking,
20-second cells, max 2048 tokens, 2350 MHz ceiling. These are focused screens,
not a new full grid or an isolated KV speedup. Functional, uncached 1M,
mixed prefill/decode and fleet checks passed.
[All arms, comparisons, limits and qualification](results/20261017-decode-tuning/REPORT.md).

## October 17 initial runtime and KV upgrade

The initial October 15 eugr/KK/FlashInfer qualification selected explicit top_p 1
and 16.5 GiB KV per GPU; the later KV sizing is recorded above. All native,
parser, serving/tool and fresh long-context checks passed. The head peaked at
**115.10 GiB total used**, below 118 GiB;
logical KV capacity is **13,483,747 tokens**. No Chinese ideographs appeared in
24 paired language responses across top_p 1 and 0.95.

Both old and new runtimes completed the same public LIL 0.7.6 25-cell grid at
0.83 memory utilization. Prefill was within 1.9%; decode was mixed. Candidate
C2/C4 often improved, while short-context C8/C16 lost a few percent. Repeats
cleared the 64K C1 outlier; there is no across-the-board speedup claim.

The final allocation's focused screen, following removal of old monitor loops:

| Context | C1 | C8 | C16 |
|---|---:|---:|---:|
| 8K | 64.23 | 180.18 | 262.80 |
| 128K | 62.57 | 170.31 | 254.73 |


The C8 repeat was 189.59 / 175.31 at 8K / 128K. Including the first screen,
the two-run means were 3.8% / 5.4% below the old baseline; long-context C8
is the clearest tradeoff.

These final rows are not a full-grid rerun or an isolated KV speedup measurement.
[Full grids, repeats, quality checks, memory evidence and rollback](results/20261017-runtime-upgrade/REPORT.md).

## October 17 official 1017 checkpoint

The official 1017 checkpoint is selected after four-node hash verification,
serving/tool/vision checks, bounded decode/prefill consistency checks, fresh
128K and 1M retrieval, and a focused public LIL 0.7.6 8K C1/C8/C16 screen.
The frontend adds the official tool-turn boundary correction and KK #921's
Python DSML parser fix. GPU sources, DSpark5, target precision, plugins and
transport are unchanged.

Public LIL 8K C1/C8/C16: **59.68 / 191.09 / 265.63 tokens/s**.
These are aggregate decode rates with the public request settings, not the
historical thinking-off wrapper. The later runtime campaign above supplies the full grid; these checkpoint-upgrade
rows preserve the earlier focused evidence. No request errors were
recorded. Single-cell
stochastic measurements do not establish a statistical speedup; finite
correctness checks do not establish broad model-quality superiority.
[Focused results, matched historical comparison, pins and qualification](results/20261017-checkpoint-upgrade/REPORT.md).

## October 14 clean upstream comparison

The original corrected build was retained after testing SparkRing's clean
2026.10.3 DS41 profile on its benchmarked `d52737a109e0` image, without our local
performance plugins. Both builds completed the published LIL 0.7.6 25-cell grid
and five coding probes at our 2350 MHz ceiling, with zero request errors.

With the **unwrapped upstream request settings**, original 8K C8/C16 measured
**197.67 / 271.32 tokens/s**, versus **186.86 / 264.79** for the clean copy.
Original 128K measured **194.18 / 263.89**, versus **175.99 / 252.91**.
The copy improved C4 and coding, but lost 5–9% at C8 and about 8% in 128K prefill.
It passed functional, fixed-sequence quality and uncached retrieval checks;
there was no performance reason to replace the working default.

Our historical `lil_matched.py` forces thinking off, top_p=1 and top_k=-1.
The public invocation leaves those at server/model defaults. Its higher numbers
on our original build are a **request-setting difference, not an engine gain**.
Do not compare these rows directly with the historical thinking-off rows below.

[Both full grids, qualification, exact pins and comparison limits](results/20261014-upstream-baseline/REPORT.md).

## October 14 HF inference audit and restoration

GLM was stopped at the user's request and the original DS41 profile restored.
The October 12 HF changes need no direct port: our native indexer already binds
its source cache rather than using the affected shared pointer, and the fused
B12x output projection already quantizes activations before WO-A. The image,
checkpoint, plugins and root-owned selection were unchanged in that audit.

The focused LIL screen measured 8K C1/C8/C16 **60.54 / 163.99 / 227.99** and
128K **69.16 / 153.52 / 217.63** tokens/s aggregate. C8 repeats were **169.95**
and **153.28**. C8 remains approximately 5–8% below October 11; this is a
historical comparison, not a patched/unpatched A/B or evidence of a speed gain.
Cold prefill was **4,255 / 4,129** tokens/s. Seven functional checks and fresh
125,241-token retrieval passed. Eight 2048-token consistency probes completed;
late coarsened KL was 0.01837 with 96.875% top-token agreement. These finite
checks do not establish broad quality equivalence. All four selected images,
configuration, mesh and clock services passed final verification.
[Audit, protocols, limitations and raw evidence](results/20261014-hf-runtime-audit/REPORT.md).

## Sustained decode and cold prefill

The October 11 clean-start control remained selected after the SIRCL trial.
It used the same installed LIL v0.6.2 harness and matched sampling settings as
the candidates: thinking off, temperature 1, top_p 1, top_k -1, 2,048-token
output ceiling and 30-second sustained cells.

| Context | C1 | C8 | C16 |
|---|---:|---:|---:|
| 8K | 62.90 | 179.31 | 234.12 |
| 128K | 61.86 | 165.67 | 220.88 |

Values are aggregate output tokens/s. Cold prefill measured 4,285 and 4,179
prompt tokens/s respectively. These are focused, stochastic screens, not a
new full grid or confidence intervals; the 128K prefill cell has one sample.
[October 11 comparison and qualification evidence](results/20261011-sircl/comparison.json).

The October 4 baseline screen used this exact runtime, thinking off,
temperature 1, top_p 1, top_k -1, and 30-second sustained cells. These are
short stochastic measurements, not confidence intervals or a new full grid.

| Context | C1 | C8 | C16 |
|---|---:|---:|---:|
| 8K | 60.98 | 178.40 | 242.96 |
| 128K | 59.36 | 166.88 | 229.62 |

Decode values are aggregate output tokens/s. Cold prefill was about 4,434
prompt tokens/s at 8K and 4,421 at approximately 129K actual prompt tokens.
[Raw screen](results/20261004-original/baseline-screen.json),
[request settings](results/20261004-original/baseline-screen.matched-request.json).

The September 30 2350 MHz screen measured 64.62 / 187.92 / 250.78 at 8K
and 61.39 / 171.88 / 232.69 at 128K for C1/C8/C16. This illustrates normal
run-to-run variation. Prefill was 4,503 and 4,449 prompt tokens/s.
[Raw screen](results/20260930-maintenance/2350-screen.json).

## Exact sparkDash protocol comparison

The October 5 run used sparkDash 1.8.8 at
`ced96c8553dec4fe2fdaf2b58e345e46db2cf651`, unmodified collectors,
256 output tokens, temperature 0 and thinking off. C1 is the median of five
measured runs after two discarded warmups; higher concurrency is one run each.

| Prompt | C1 | C2 | C4 | C8 | C16 |
|---|---:|---:|---:|---:|---:|
| Prose | 73.79 | 116.77 | 164.68 | 240.25 | 344.61 |
| Code | 119.71 | 174.76 | 233.42 | 308.14 | 417.36 |
| Structured | 145.41 | 189.01 | 312.54 | 496.80 | 776.71 |
| JSON | 117.06 | 185.16 | 271.46 | 405.33 | 612.90 |

These short-prompt decode rates are workload-dependent and should not be
compared directly with LIL's long-context sustained rates. Prose C8/C16 was
close to Mia's published 237.6/342.7 on this protocol. The repeated-token
prefill sweeps measured roughly 4.2–4.7K prompt tokens/s; they are not a
real-text prefill benchmark. The external reference is not a same-hardware A/B.
[Protocol and results](results/mia-sparkdash-20261005T073040Z/summary.json),
[raw measurements](results/mia-sparkdash-20261005T073040Z/measurements.json),
[comparison](results/mia-sparkdash-20261005T073040Z/decode-comparison.csv).

## Fidelity, retrieval and limits

The complete KK #926/#943 compressor correction reduced late-answer coarsened
decode/prefill KL by 89.6% across eight 2,048-token probes. This finite
consistency metric is not a universal quality score. The correction addresses
long-answer drift; it is retained even where single-user decode was slower.
[Before](results/20260929-kk926/baseline-consistency.txt),
[after](results/20260929-kk926/corrected-consistency.txt).

Uncached retrieval returned the correct code from 1,008,432 prompt tokens in
322.1 seconds to first content.
[Raw retrieval](results/20260929-kk926/cold-1m.json).
Seven ordinary and seven fresh long-context functional probes passed in the
qualification repeat; an initial long-context automatic-tool miss remains
recorded. Greedy byte-repeatability was already unreliable on the stock
runtime. Neither finite functional checks nor passing repeats prove universal
quality or eliminate intermittent output repetition.

## Why this build remains selected

- **October 11 SIRCL image:** tested the published 2026.10.2 pre-release image
  at `4fffc4dc3074…`, SIRCL 0.3.2/native ABI 9, with the original checkpoint and
  selected local plugins. All four ranks recorded SIRCL traffic with NCCL
  disabled. Each candidate passed seven serving checks, twelve known-answer
  checks, uncached 128K retrieval and finite long-answer consistency checks.
  BF16-target-head SIRCL measured 59.20 / 164.48 / 224.91 at 8K and
  58.99 / 162.36 / 227.59 at 128K. The fresh original control above was better
  overall, although SIRCL's 128K C16 sample was higher. MXFP8/A16 target-head
  quantization and larger 2 MiB all-reduce / 16 MiB gather buffers produced no
  consistent decode improvement. The MXFP8 8K C1 peak reflected higher draft
  acceptance while verification-step rate fell. Neither variant was selected.
  The new image also changes vLLM/B12x, so these results do not isolate SIRCL
  as the cause. The trial workers and owned relay objects were stopped and
  the original mesh restored fleet-wide. Checkpoints, selected images, plugins,
  root-owned selection and the `0,2350` clock policy are unchanged.
  [Exact identities, all cells, precision settings and limits](results/20261011-sircl/comparison.json).
- **CSF/beta bundle:** rejected for slower prefill and C8/C16 decode. The final
  candidate's concurrency rates were 9.8–21.2% below the same-day corrected
  baseline. Several components changed together; this does not isolate the
  lossless checkpoint format as the cause. Original checkpoints were restored
  and all 48 shard hashes per rank verified.
- **Fastokens:** improved cached 1M first-token latency, but repeated C8 decode
  was lower than both HF controls. HF remains selected.
- **TensorFold transfers:** exact Markov caching and paced prefetch failed the
  promotion gates. The native TP4 adapter remains incomplete and unqualified;
  no EXL3 checkpoint was downloaded or accepted. Its unfinished source is in
  the external pre-cleanup snapshot.
- **Other proposals:** draft top-20, projection splits, context-axis variants,
  read-ahead and ownership experiments were not selected. Their source and
  detailed reports are archived rather than included in the active image tree.
- **2350 MHz cap:** selected for lower power and temperature with acceptable
  measured throughput. GPU telemetry showed roughly 46–49 W total savings
  versus the first stock-clock run; this is not whole-system wall power.
  [Clock comparison](results/20260930-maintenance/2350-comparison.json).

Earlier full-grid results predate the compressor fix. No complete new LIL grid
was run after the October rollback; the current evidence above retains that
limitation. Historical reports and discarded candidate results are recoverable
from Git at `364eb87` and the external snapshot recorded in `.local/cleanup.json`.
