# FLARE cutover — October 27, 2026 UTC

FLARE replaced the five-draft B12X vLLM build as the production engine at the
user's direction ("this is our new default"; test only FLARE, do not switch
back to vLLM). B12X was stopped at 20:42 UTC; FLARE served from 21:08 UTC.
No B12X run was made after the cutover; B12X figures below are the
2026-10-24 grid with the same harness and arguments.

## Build

| Item | Value |
|---|---|
| Engine | `flare-inference 0.1.0~git20261027170349.7c22369f-1`, `/usr/bin/flare` SHA-256 `4cb29623fa38d22e…`, same agent binary on all four nodes |
| Package | `local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE@gb10`, commit `607c1abfc2fc2e14bf9dcc9cdc8d4a6128a081a9`, primary `model.safetensors` (43,046,937 bytes) |
| Deployment | `0a377833bb1c431ab417837a50bb18a8`, TP4, native expert scales, payload v2, signatures verified (publisher key `937c0143…a8c1`) |
| Local version | `gb10-tp4-202610271726` in `~/flare-models` on spark-r0 (489.39 GiB); peers `gb10-tp4-202610272052`, 264 GiB each |
| Group | persistent `ds41-flare`, cluster `ds41`, launch argv in [`flare/launch.sh`](../../flare/launch.sh) |
| Serving | 1,048,576 context, 32 requests, 4,096-token prefill chunks, MTP up to five drafts with adaptive verification, Engram on disk with RAM scales and 1 GiB row cache |
| KV | `--memory-limit=-2G`: 16.6 GiB per GPU, **19,306,112 tokens** (user asked for about 16M) |
| Memory | spark-r0 110.86 GiB used after loading (budget about 118); other ranks 111.1–111.3 GiB; swap 0.33 GiB |
| Clocks | 2327–2333 MHz on all four under load (2350 MHz ceiling unchanged) |
| Transport | RoCE, two rails per peer (`roceP2p1s0f1`, `rocep1s0f1`), rendezvous `10.10.10.1:29800` |

## Full grid

Unmodified LIL 0.7.6 (`c4c7eaed…9553`) from the Mac, the exact B12X argv
(`--temperature 1 --duration 20 --max-tokens 2048 --coding-peak`, contexts
8k–128k, C1–C16, `--no-hw-monitor`), model-default thinking, idle fleet, Mac on
AC under `caffeinate -i`. Started 21:21 UTC, all 25 cells and 5/5 coding runs
completed, no errors. Aggregate output tok/s, change against B12X 2026-10-24:

| Context | C1 | C2 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|---:|
| 8K | 58.9 (−6.7%) | 99.9 (+10.1%) | 141.1 (+0.8%) | 179.4 (−9.3%) | 253.8 (−6.9%) | 3,873 (−0.6%) |
| 16K | 60.1 (−5.4%) | 95.7 (+2.9%) | 143.2 (+6.5%) | 168.9 (−9.5%) | 253.4 (−5.0%) | 4,102 (+9.5%) |
| 32K | 63.6 (−0.6%) | 98.3 (+4.7%) | 146.5 (+0.3%) | 176.1 (−10.7%) | 246.7 (−7.2%) | 4,444 (+9.5%) |
| 64K | 63.4 (−2.3%) | 98.6 (+25.4%) | 140.2 (+5.1%) | 200.4 (+10.7%) | 245.8 (−8.5%) | 4,479 (−0.4%) |
| 128K | 61.0 (−3.0%) | 95.9 (+1.2%) | 136.7 (+0.1%) | 198.4 (+4.9%) | 261.0 (+0.2%) | 4,411 (+2.5%) |

Column means: C1 −3.6%, C2 +8.9%, C4 +2.6%, C8 −2.8%, C16 −5.5%, prefill
+4.1%. Coding peak median **100.3** tok/s (mean 102.1, 95.9–116.5) against
B12X 104.1 (mean 102.8); no CJK in either. These are single runs on different
days; differences of a few percent are within run-to-run spread. On
2026-10-20 the previous FLARE release was 6–24% slower than vLLM in every cell.

Raw: [`flare-full-grid-1.json`](flare-full-grid-1.json),
[log](flare-full-grid-1.log), [command](flare-full-grid-1-command.json).
An informal C1 probe before the grid (1,500 tokens, short prompt) measured
71.3 tok/s with 0.33 s TTFT.

## Quick grid, second run

Same client and arguments without `--coding-peak`, C1/4/8/16 at 8K/64K/128K, run about an
hour after the full grid ([raw](flare-quick-grid-2.json), [log](flare-quick-grid-2.log),
[command](flare-quick-grid-2-command.json)). No errors and no loops. Aggregate output
tok/s, with the change against the first grid:

| Context | C1 | C4 | C8 | C16 | Prefill |
|---|---:|---:|---:|---:|---:|
| 8K | 64.2 (+9%) | 123.6 (−12%) | 193.5 (+8%) | 278.2 (+10%) | 2,828 (−27%) |
| 64K | 60.1 (−5%) | 120.1 (−14%) | 201.7 (+1%) | 277.1 (+13%) | 3,665 (−18%) |
| 128K | 65.7 (+8%) | 135.1 (−1%) | 187.6 (−5%) | 266.0 (+2%) | 3,781 (−14%) |

Cell-to-cell spread between the two runs is ±5–14% for decode, so differences of that size
in single 20 s cells are noise. Prefill is one request per context, and this run it was 14–27%
lower. Each run uses fresh padding text, so first-touch Engram disk reads (upstream #78) may
explain the difference; that is untested.

## Quick grid after rebooting all four nodes

The second run looked weak, so on 2026-10-28 FLARE was stopped, all four nodes were
rebooted (6 days 15 hours uptime before), and the group was started again. The cached start
took at most 26 s from `orbit run` to `/health` 200. The fabric check passed on all eight
rails, the 0–2350 MHz clock lock was logged at boot on every node, and memory after loading
was 111.2–111.6 GiB. Same arguments as the second run
([raw](flare-quick-grid-3-postreboot.json), [log](flare-quick-grid-3-postreboot.log),
[command](flare-quick-grid-3-postreboot-command.json)); 12 cells, no errors, no loops.

| Context | Run | C1 | C4 | C8 | C16 | Prefill |
|---|---|---:|---:|---:|---:|---:|
| 8K | 1 full grid | 58.9 | 141.1 | 179.4 | 253.8 | 3,873 |
| | 2 before reboot | 64.2 | 123.6 | 193.5 | 278.2 | 2,828 |
| | 3 after reboot | 68.0 | 145.3 | 189.2 | 275.6 | 4,000 |
| 64K | 1 | 63.4 | 140.2 | 200.4 | 245.8 | 4,479 |
| | 2 | 60.1 | 120.1 | 201.7 | 277.1 | 3,665 |
| | 3 | 66.0 | 143.0 | 182.1 | 259.6 | 4,499 |
| 128K | 1 | 61.0 | 136.7 | 198.4 | 261.0 | 4,411 |
| | 2 | 65.7 | 135.1 | 187.6 | 266.0 | 3,781 |
| | 3 | 66.5 | 152.4 | 188.6 | 260.0 | 4,589 |

After the reboot, prefill and C4 are back to at least the first run's level, and C1 is the
best of the three runs (66–68). The second run's prefill (−14 to −27%) and C4 (−12 to −14%)
deficits are gone. C8 and C16 move by under 10% between runs in both directions.

Two things differed before the reboot, but neither is shown to be the cause:
- spark-r0 had 0.33 GiB in swap when recorded after the cutover load (0 after the reboot;
  not measured just before it).
- The server held 13,342 cached KV pages from about 1,000 probe requests (2,636 after the
  third run).

Whether the slowdown returns with uptime and cache churn is untested.

## Functional gates

- `bench/functional.py` (updated for FLARE: `enable_thinking`, package
  sampling): **7/7** — count, arithmetic, code, automatic tool call, forced
  tool call, image colours, thinking with reasoning text
  ([log](functional.log)). An earlier run of the forced tool call returned
  HTTP 500 `required tool choice was not satisfied: the model did not produce
  a completed tool call`; the server stayed healthy.
- Uncached retrieval (`bench/cold-needle.py`): pass at **122,280** prompt
  tokens (TTFT 32.7 s) and **923,228** (TTFT 315.9 s). FLARE reports
  `cached_tokens: 1` (the BOS token), so the script's strict `cold_confirmed`
  check exits 1; the nonce prefix makes both cold
  ([128K](cold-needle-128000.json), [960K](cold-needle-960000.json)).
- Images ([probe](check_images.py), [results](check_images.json)): 1, 8,
  16, 64, 256 and **1000** distinct 64 px images in one request, one and four
  1024 px images; all answered correctly, health 200 afterwards.
- Request options: vLLM's `chat_template_kwargs.thinking` → HTTP 400;
  `enable_thinking: false`, `thinking_mode: "chat"` and `reasoning_effort`
  work. Temperature and top_p are fixed at 1 by the package; default seed 0.

## Known issue: stray tokens

Short open-ended replies sometimes contain a spliced foreign fragment, e.g.
`"Hi! 👋 What's on your五 mind today?"`, `"How can\n can I help"`, and once the
model's internal safety annotation:
`"Hi! 👋 How can<ds_safety>[用户未成年]否 … [判定]用户消息仅为打招呼…</ds_sHome>can I"`.
With varied seeds, 2 of 60 short replies (four prompts × five seeds × three
thinking modes) were affected; `enable_thinking: false` had 0/20. Because the
default seed is fixed, an affected prompt repeats its corruption on every
identical request ("Say hi." was corrupted or cut short in 12 of 12 tries
with default settings or `thinking_mode: "chat"`, streamed and not). Structured output (counting 1–30, 24/24 exact),
arithmetic, code, tools and retrieval were unaffected. GPQA Diamond and
tool-eval have not been run on FLARE.

**Cause (traced the same day, [NVIDIA/spark-local-inference#118](https://github.com/NVIDIA/spark-local-inference/issues/118)):**
the logprobs at the corrupted token are a fixed, context-free document-start
distribution (`'\n'` −2.25, `'#'` −2.37, `'<'` −2.74) where the model is
otherwise certain (after "What's on your", `' mind'` scores 0.00 one token
later). This reproduces deterministically at the prefill's last position
through raw `/v1/completions`, so speculation, the prefix cache and the chat
frontend are ruled out. It needs the `Reasoning Effort` header that the official
encoder adds in thinking mode, and it only occurs at prompt lengths below 128,
which is both the sliding window and the KV page size. The `<ds_safety>` leak
is the same defect: `'<'` is sampled from the blank distribution, and the model
continues into its trained annotation format. The frontend is not at fault.
Workarounds: `enable_thinking: false`, or a system prompt long enough that
replies start past token 128.

## Deployment events

- `flare-inference` builds on 2026-10-27: `8f32be2a` (Oct 20, installed) →
  `b697d3b8` → `f9edc315` → `ec0a3126` → `7c22369f` (selected). The Oct 20 build
  could not parse the package header (`unknown field align.000000`).
- First download (b697d3b8 into `~/.cache/flare/packages`, 17:20 UTC, 490 GiB)
  was deleted two minutes later by the `ec0a3126` rank-0 agent during the first
  `orbit push` ("removed superseded …/blobs, …/models, …"). Re-downloaded into
  `~/flare-models` (17:26–19:22 UTC) and hardlink-snapshotted to
  `~/flare-models.keep`.
- Agents were reinstalled on `0.0.0.0:29900`; the first push failed with only
  rail A bound. The user approved the wider listener.
- Each rank needs 264 GiB (both Engram tables); the GX10s had 194/198 GB free.
  With the user's approval, B12X was stopped and the GX10 copies of the 1017
  checkpoint (476 GB each) were deleted after recording manifests
  (`~/Agent/Diagnostics/deepseek-v41-flash-ring/20261027-flare-cutover/`).
  The Sparks keep both their checkpoints.
- `orbit push` then staged and verified 264 GiB per peer (20:43–20:50), but
  `orbit run` did not use those copies and transferred and verified the data
  again into `~/.cache/flare/models` (GX10 free space fell to 142–145 GB). The
  unused push copies (490 GiB on spark-r0, 264 GiB per peer) were removed once
  serving; GX10s now have 406/409 GB free.
