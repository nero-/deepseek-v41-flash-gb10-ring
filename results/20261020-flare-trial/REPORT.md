# FLARE qualification — October 20, 2026 UTC

Decision: do not promote this release. The publisher recipe ran successfully, but all 25 decode cells were slower than the qualified vLLM deployment. The throughput scheduler also lost at matched 32K C1/C8/C16. The qualified vLLM deployment has been restored and verified healthy.

## Matched full benchmark

Public unmodified LIL 0.7.6, SHA256 `c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553`; same external Mac/client environment, 20-second sustained cells, 2048-token output budget, temperature 1, top_p 1 server defaults, temporary 2418 MHz GPU lock. Stock clocks restored after each run. All 25 FLARE cells completed without errors, loops, or warmup timeouts. Both runs use `openai_continuous_usage` for headline decode, not SSE chunk counts. FLARE engine-specific diagnostics are unavailable to this harness; native metrics were recorded separately and confirmed C16 activity.

Each cell below is **FLARE / vLLM**, aggregate tokens/s.

| Context | C1 | C2 | C4 | C8 | C16 |
|---|---:|---:|---:|---:|---:|
| 8K | 47.8 / 62.2 | 75.1 / 93.0 | 108.4 / 142.0 | 160.0 / 190.5 | 228.3 / 269.1 |
| 16K | 50.1 / 60.3 | 82.5 / 96.9 | 110.6 / 144.2 | 161.2 / 197.0 | 226.0 / 268.7 |
| 32K | 49.8 / 62.8 | 76.7 / 92.2 | 109.7 / 139.9 | 164.2 / 193.7 | 225.9 / 266.2 |
| 64K | 53.0 / 63.6 | 73.9 / 93.8 | 114.9 / 137.7 | 160.7 / 192.1 | 228.1 / 263.2 |
| 128K | 52.1 / 58.8 | 74.3 / 91.0 | 111.2 / 136.5 | 157.2 / 187.9 | 223.1 / 241.8 |

Prefill is the same harness’s integrated scout input-tokens/TTFT measurement, not an isolated GPU kernel measurement.

| Context | FLARE tok/s | vLLM tok/s |
|---|---:|---:|
| 8K | 4341 | 4238 |
| 16K | 3465 | 4136 |
| 32K | 3809 | 4470 |
| 64K | 4101 | 4476 |
| 128K | 4072 | 4377 |

Coding peak: FLARE median **82.46 t/s** versus vLLM **91.16 t/s**. Five successful runs each; FLARE’s five coding outputs contained no CJK ideographs.

## Follow-up settings

Three drafts could not start: `packed verification requires adaptive execution at the captured draft depth`. The signed export requires its captured five-draft depth. Do not use the local FLARE `research/rejected-mtp3-argv.json` as a working launch command. No signed payload was modified.

Throughput scheduler, otherwise unchanged, 32K only:

| Concurrency | Throughput scheduler | Publisher balanced | vLLM |
|---|---:|---:|---:|
| C1 | 54.51 | 49.80 | 62.75 |
| C8 | 160.46 | 164.24 | 193.71 |
| C16 | 237.34 | 225.95 | 266.23 |

## Functional and operational findings

- Text arithmetic, thinking, automatic tools, tool-result continuation, streaming continuous usage, and six English response probes passed. Four repeated creative prompts at temperature 1 produced four distinct responses. This is a functional screen, not a broad quality evaluation.
- Temperature 0 is rejected. Replace old `chat_template_kwargs.thinking` with `thinking_mode: "chat"` or `"thinking"`. Named forced tool choice is not implemented.
- Actual image budget is 4096 image tokens, up to 1024 per image. One and eight small images passed; 64 needed 10,816 tokens and were rejected. The user accepts this smaller budget only if FLARE is faster. The earlier four-image interpretation of exported feature slots was incorrect.
- Initial system memory use was about 108.06 GiB on spark-r0; 22.7 GiB KV per rank, 27,077,888 logical tokens. Full 1M-context retrieval was not qualified because the candidate failed the performance selection.
- Native direct RoCE connected both switched rails on all four ranks. No ring emulation or old ring networking was enabled.
- Fix user-agent limits to `LimitNOFILE=65536`; default 1024 failed on the full source package. Use regular hard-linked package files instead of the HF blob symlink view.
- All 1485 source files were fully hash-verified, signatures validated, and exact publisher key accepted. Orbit verified each peer transfer. Normal startup omits redundant full `--verify-weights` reads.

## Evidence

Complete raw outputs, metrics traces, startup failures, memory snapshots and validation requests:
`~/Agent/Diagnostics/DS41-flare/20261020/`.

Engine and package pins are in the local `~/Agent/Builds/DS41-flare/deployment.json`. The qualified fallback is the October 20 switched ABI-8 image `9f26f0b3718cc...`, with `selected-specs.json` SHA256 `d86c7e0725efae1ced95a4891da59753853992aaad4fda926814531145e43ca2`. The interrupted `old4cap3b` image is not the selected fallback.

## Checkpoint restoration

Both GX10s received 48 original 1017 shards (510,296,708,312 bytes each) over fabric A, using one Spark source per GX10. Every transferred shard matched the recorded SHA256. The receiver initially could not write its final summary into the user-owned receipt directory; its 48 successful per-file hash/rename records were recovered, final file sizes and absence of partials checked, and the final receipts saved as the owning user. No weight retransfers or hash failures occurred. Temporary transfer containers and listeners were removed.

Retained qualified containers matched the selected image, argv, environment, labels, and mounts on all four nodes. The exact qualified spec was restored. The native-worker shutdown and the FLARE start interlock were verified before vLLM startup.

## Final serving state

The restored vLLM 32K C1 check measured **62.16 t/s**, with no errors, versus the preceding qualified 62.75 t/s result. Arithmetic returned 391. All four selected containers run immutable image `9f26f0b3718cc...`; the API is healthy. Head startup system memory was **117.60 GiB**, below the 118 GiB goal. GPU clock resets succeeded on all four nodes; persistent policy remains stock boost. FLARE has no active workers, and its wrapper refuses startup while vLLM owns the fleet. The prior optimization campaign remains paused.
