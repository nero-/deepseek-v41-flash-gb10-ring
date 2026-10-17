# Official 1017 checkpoint upgrade — 2026-10-17 UTC

The official `deepseek-ai/DeepSeek-V4.1-Flash-1017` checkpoint is selected on all four nodes.
Pinned revision: `1bae0e1088993b9b82de08f59de5be5a34e42170`.
API: `http://192.168.50.219:8015/v1`; alias: `DeepSeek-V4.1-Flash-TP4`.

## What changed

- All 48 weight shards changed; all 96,085 tensor layouts, config and tokenizer artifacts match the old architecture.
- All 55 installed files were hash-verified on all four nodes. Downloads were staged once, then copied over the fabric.
- Added the official tool-result turn-boundary encoder correction and exact Python parser files from KK #921. The old parser silently dropped a parameter when its DSML `string=` attribute was absent.
- Retained the complete KK #926/#943 compressor correction, GPU stack, RoCEnante/patched NCCL, DSpark5, selected plugins, target precision, full vocabulary and 0–2350 MHz clock policy.
- Model-dependent vLLM/Inductor caches use a new checkpoint prefix. Native kernel caches remain compatible.

## Focused public LIL 0.7.6 screen

The public LIL 0.7.6 protocol from the October 14 original-build baseline, narrowed to 8K C1/C8/C16 for availability qualification: 20-second sustained measurements, temperature 1, output ceiling 2048. Server/model defaults apply to the other request settings. These are not the historical thinking-off wrapper results. The user prioritized normal serving; a new full grid and runtime comparisons are deferred to the switch campaign.

| Context | C1 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|
| 8K | 59.68 | 191.09 | 265.63 | 4,074 |

Decode is aggregate output tokens/s; prefill is client-observed prompt tokens/s. No request errors, failed cells, detected loops or underfilled cells were recorded.

| Context / concurrency | Previous | 1017 | Change |
|---|---:|---:|---:|
| 8K C1 | 62.55 | 59.68 | -4.6% |
| 8K C8 | 197.67 | 191.09 | -3.3% |
| 8K C16 | 271.32 | 265.63 | -2.1% |

This is a historical matched-protocol comparison with one stochastic cell per geometry, not a confidence interval or an isolated runtime A/B. New model weights can change output content and speculative acceptance.

## Qualification and recovery

Each image passed 128 upstream parser CPU tests and source/toolchain verification. Twelve prompt-encoding cases matched the 1017 reference. Serving passed seven functional checks, four typed-tool round trips covering streaming and thinking modes, twelve exact-answer checks, and two 2048-token decode/prefill consistency probes. Fresh 128K and 1M retrieval results are retained in `qualification/`. These finite checks do not establish broad model-quality superiority.

The fresh long request contained 1,008,428 actual prompt tokens, with zero cached tokens and the expected code returned.

The selected config and all four live image IDs, plugins, mesh services, clock policy and clocks under load were checked after promotion. See `final-audit.json`.

Original images and verified old weight copies remain on both Sparks. The old GX10 shards were deleted for capacity; rollback requires fabric restoration before restarting the old profile. See the rollback instructions in `OPERATIONS.md`. Temporary artifact servers were stopped.

## Runtime follow-up

B12x now develops inside FlashInfer. A full migration needs matching vLLM adapters and a verified ARM64 image; upgrading the live Python package alone is not appropriate. The current checkpoint upgrade preserves the GPU stack. Ranked candidates and source links are in [the runtime assessment](runtime-review/ASSESSMENT.md).

Full local campaign, logs, rebuild launchers and rollback scripts: `/Users/jg/Agent/Diagnostics/deepseek-v41-flash-ring/upgrade-1017-20261017`.
