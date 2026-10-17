# Current-image decode trials and KV sizing — October 17

The October 15 eugr/KK/FlashInfer image and official 1017 weights remain selected.
The decode trials did not establish a repeatable overall improvement, so the
existing DSpark5 probabilistic/block/adaptive-verification settings, graph
ladder and L2 prefetch remain. No old-image rollback was performed.

KV increased from 16.5 to **20 GiB per rank**, exposing
**16,344,051 logical tokens**. Head total system memory immediately after
loading was **117.40 GiB**, with **4.28 GiB available**.
The user's 118 GiB goal is a startup budget, not a runtime ceiling.
No automatic stop guard remains. KV is mostly allocated at startup; other
working allocations can grow during use. Qualification peak after readiness
was **118.66 GiB**. Capacity increased; this is not proof
that a larger KV allocation speeds decode.

## Protocol and selection

Pinned public LIL 0.7.6 (SHA256
`c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553`),
20-second sustained cells, max 2048 generated tokens, temperature 1, top_p 1,
default thinking, no hardware monitor. The top_p adapter injects only top_p;
it does not use the historical thinking-off wrapper. All ranks retained the
0–2350 MHz clock policy. Baseline and decode trials used 16.5 GiB KV; the final
profile uses 20 GiB. The initial baseline was already warm; later arms
restarted the engine. `control-screen` is a fresh restart with original
current-image settings. Request content, stochastic acceptance and warmup
still vary: these are focused screens, not confidence intervals or a new full
25-cell benchmark. The prior full runtime grids remain in the
[initial runtime report](../20261017-runtime-upgrade/REPORT.md).

8K aggregate output tokens/s, including every completed arm:

| Arm | C1 | C8 | C16 |
|---|---:|---:|---:|
| baseline-1 | 62.05 | 192.66 | 263.38 |
| cost140-screen | 62.74 | 184.76 | 254.50 |
| cost070-screen | 58.88 | 187.13 | 264.14 |
| l2off-screen | 56.37 | 174.57 | 271.63 |
| graphsteps-screen | 55.83 | 190.21 | 264.69 |
| l2max40-screen | 65.27 | 184.08 | 265.19 |
| graphs48p-screen | 58.74 | 193.80 | 260.83 |
| graphs48p-followup | 54.84 | 194.60 | 259.30 |
| control-screen | 63.62 | 192.95 | 257.55 |
| greedy-screen | 58.27 | 166.14 | 240.47 |
| final-screen | 58.29 | 192.21 | 270.00 |
| final-followup | 61.66 | 191.57 | 265.95 |

Changes screened:

- `cost140` / `cost070`: adaptive verification cost scale 1.4 / 0.7.
- `l2off`: disable DS41 L2 prefetch; the isolated C16 increase came with C1/C8 losses.
- `graphsteps`: add missing multiples of four to the capture ladder through 96.
- `l2max40`: retain that ladder but suppress shared L2 prefetch above 40 tokens.
- `graphs48p`: add dense C4/C8 ragged-token CUDA graph shapes through a guarded
  vLLM plugin. It armed on all four ranks; rank zero reported 70 full captures,
  versus 55 for graphsteps and 42 for the default. The extra coverage did not
  deliver a repeatable overall gain, including the 128K follow-up.
- `greedy`: native greedy draft proposals with standard rejection; target
  sampling settings retained. C8 fell from 192.95 to 166.14 tokens/s. Summed
  per-request speculative rounds were similar (81.14 versus 80.00 per second),
  while emitted tokens per round fell from 2.388 to 2.081. This points to lower
  accepted output per round, rather than a useful reduction in drafting cost.
  These counters are not global GPU batch iterations per second.

The attempted direct package-file overlay (`graphs48`) was rejected at startup
by the installed package-inventory verifier. The verifier was not bypassed.
The separately declared plugin allowed the experiment without altering sealed
package files. Both the failed overlay and unselected plugin were removed;
all stopped tuning containers were removed by recorded identities. Images,
weights, caches, selected plugins and the same-image recovery containers were
preserved.

Async scheduling was already enabled. Qwen-specific draft top-k controls and
the local-draft-argmax hook are not implemented for this native DS41 path.
Dynamic draft scheduling truncates returned proposals after the fixed-width
parallel draft computation; it does not provide the hoped-for compute saving.
The NVFP4 layer-max input-scale switch had no demonstrated consumer in the
selected original FP4/FP8 checkpoint route. Engram overlap was not enabled
because of the previously recorded cold-prefill synchronization issue. No
unsupported or unmeasured flag was left in the selected recipe.

## Selected profile qualification

Mean of two final focused screens, aggregate output tokens/s. The second
followed the long-context and mixed-load checks to investigate the first
screen's lower C1 rate; both raw runs are retained. This mean is descriptive,
not a confidence interval:

| Context | C1 | C8 | C16 |
|---|---:|---:|---:|
| 8K | 59.98 | 191.89 | 267.98 |
| 128K | 59.01 | 185.94 | 251.03 |

C1 was 58.29 / 56.62 tokens/s at 8K / 128K in the first run and recovered to
61.66 / 61.41 in the repeat. At 8K, C8 was 192.21 then 191.57; C16 was 270.00
then 265.95. The 200 C8 / 300 C16 target was not established. Selection is for
larger cache capacity with the existing decode settings, not a demonstrated
engine speedup.

Scout prefill, prompt tokens/s (one sample per context per run):

| Run | 8K | 64K | 128K |
|---|---:|---:|---:|
| Fresh 16.5 GiB control | 4,002 | 4,266 | 4,357 |
| Final 20 GiB, first | 3,950 | 4,240 | 4,179 |
| Final 20 GiB, repeat | 4,121 | 4,356 | 4,235 |

The final 128K scouts were 2.8–4.1% below the fresh control. These short
measurements do not isolate a KV allocation effect; no prefill speedup is claimed.

All seven functional checks passed, including automatic/forced tools, vision
and reasoning. Fresh long-context retrieval passed with
**961,728 actual prompt tokens** and zero cached
tokens. Eight 2048-token decoders completed while a fresh 128K retrieval ran;
retrieval and adaptive-prefill/indexer activation checks passed. All four
selected container identities, plugin hashes, service states and clocks under
load passed the final audit. Rank-zero startup logs independently confirmed
live RoCEnante all-reduce and all-gather in the four-rank group; patched NCCL
remains the fallback. These finite tests do not establish broad model
quality equivalence.

[Memory evidence](final-memory-summary.json), [startup measurements](startup-memory.json),
[all measured cells](comparison.json), [serving checks](functional.txt),
[final audit](final-audit.json), and [exact cleanup receipt](cleanup-receipt.json).
The passive memory sampler was stopped explicitly after qualification.

## Recovery

Selected profile: `engram-adaptive4k-query-indexer-1017-runtime1015-kv20`.
Image: `sha256:a182696cb59fad1352ca17aae13c248e276d5cb7b7811f0fc8ead1cde4516221` on all ranks.
Configuration SHA256:
`e7136bf21f3885421e3d0ede9b9f43214f9be43bd8bfc62a1c2a049698b30c47`.
Normal `ring-mode.sh ds` / `recover-ds` uses this selection on port 8015.

The previous **current-image** 16.5 GiB profile is preserved in stopped
`ds41-before-tuning-rN` containers. Head config backup:
`/var/lib/deepseek-ring/experiments/decode-tuning-20261017/original-selection.json`.
The private workstation campaign is
`~/Agent/Diagnostics/deepseek-v41-flash-ring/decode-tuning-20261017`;
`tuning_cutover.py rollback --specs final-specs.json` restores that configuration
without changing image or checkpoint. This is separate from the older runtime
rollback. Consult OPERATIONS before any rollback; verify live state first.
