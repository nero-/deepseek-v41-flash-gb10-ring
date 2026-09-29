# Fastokens serving experiment — 2026-09-29 UTC

This experiment compares the deployed KK926-corrected SparkRing model using
its existing HF tokenizer against the same corrected model with
`fastokens==0.3.2` and `VLLM_USE_FASTOKENS=1`. The wheel is pinned, its native
ARM64 compatibility and bounded token/template parity were already tested in
the [CPU assessment](FASTOKENS-ASSESSMENT-20260929.md), and the derived images
pass the original SparkRing toolchain verification. The scheduler, context
limit, DSpark5, adaptive-prefill and query-indexer settings are unchanged.

## Baseline interpretation

The historical [full benchmark](FULL-BENCHMARK-20260928.md) had C1 decode in
the **64.3–66.2 tok/s** range. The later 73.9 tok/s single 128K/C1 baseline
sample was unusually high and should not be treated as this fleet's typical
speed. That sample had effective speculative acceptance of 3.136 tokens/step;
the first corrected sample had 2.441, while reported step rates were similar.
This explains much of that sample's output-rate difference. The measurements
do not establish JIT as the cause of the outlier.

This experiment therefore takes a fresh baseline on the **corrected** runtime.
It measures the tokenizer change rather than reusing the old 74 tok/s number
as a performance target.

## Method

`bench/tokenizer-serving.py` sends deterministic record corpora with an access
code in the middle and requests that code. Every response must retrieve it
correctly. Three nominal sizes cover ~8K, ~128K and ~1M tokens. The HF run uses
a fresh nonce. After the service restart clears its native KV cache, the
Fastokens run reuses the **exact same prompt text**, including that nonce.
Prompt SHA256 hashes must match across phases, and each initial request must
report zero cached tokens.
After a repeated-prompt warmup, five sequential requests measure cached C1
TTFT; a wave of eight identical requests measures cached C8 TTFT. Cached
requests must reuse at least 95% of prompt tokens. Raw per-request times,
answers and cache usage are retained. The HF and Fastokens phases use the
same corpus, prefixes and settings; the phase label is separate metadata.

TTFT is client time to the first content-bearing SSE event. Temperature is
zero, thinking is off, and output is limited to 16 tokens. Cached TTFT includes
frontend processing, cache restoration, scheduling and initial GPU work, not
tokenization alone. All timings run over localhost on the API node.

After these large-prompt warmups, both phases run the pinned matched LIL v0.6.2
screen: 8K/128K × C1/C8/C16, 30-second sustained windows, 2,048 output tokens,
EOS ignored, temperature 1, top_p 1, top_k -1 and thinking off. Repetition
detection and normal warmups remain enabled. This is a six-cell regression
screen, not the historical full 20-cell sustained plus 20-cell burst suite.
Generated continuations and speculative acceptance may differ between runs.

The candidate also runs the seven short functional checks, seven fresh
long-prefill checks (tools, vision and thinking included), and fresh long
retrieval while eight decoders run. The actual running flag and successful
Fastokens patch must be verified, so a silently ineffective toggle is not
accepted as a successful experiment.

An initial harness attempt completed the 8K case, then stopped because a local
list shadowed the `concurrent` module. No model request failed. That incomplete
attempt is retained as `hf-api-harness-first.*`; it is excluded from the
comparison. The fixed harness uses an independent module alias and fresh
nonce per run. Both compared backends use that corrected harness.

## Corrected HF baseline

All 45 retrieval responses passed (15 per context, including warmups).
The initial requests were uncached and the repeated requests met the cache
reuse threshold. [Raw API results](results/20260929-fastokens/hf-api.json).

| Nominal context | Cold TTFT | Cached C1 median | Cached C8 median |
|---|---:|---:|---:|
| 8K | 1.916 s | 0.286 s | 1.078 s |
| 128K | 33.226 s | 0.565 s | 1.966 s |
| 1M | 342.168 s | 2.566 s | 9.800 s |

The timer begins after client JSON serialization. The C8 wave uses eight
client threads, so arrivals need not occur at exactly the same instant.

All six warmed HF decode cells passed without repetition or capacity limits.
[Raw decode screen](results/20260929-fastokens/hf-screen.json):

| Context | C1 tok/s | C8 aggregate tok/s | C16 aggregate tok/s |
|---|---:|---:|---:|
| 8K | 56.76 | 179.00 | 226.75 |
| 128K | 61.74 | 168.52 | 220.09 |

## Fastokens API results

All 45 retrieval responses passed, with matching prompt hashes and token counts
against HF. Each cold request reported zero cached tokens. All repeats met
the cache threshold. [Raw candidate results](results/20260929-fastokens/fastokens-api.json).

| Nominal context | Cold TTFT | Cached C1 median | Cached C8 median |
|---|---:|---:|---:|
| 8K | 1.885 s | 0.295 s | 0.789 s |
| 128K | 30.148 s | 0.393 s | 1.703 s |
| 1M | 334.721 s | 1.110 s | 3.739 s |

Cached 128K TTFT improved 30.4% at C1 and 13.4% at C8. Cached 1M improved
56.7% at C1 and 61.8% at C8. At 8K, C1 was 8.9 ms slower (3.1%), while C8
improved 26.8%. These are five-request and eight-request medians from one
paired campaign, not confidence intervals or production percentiles.

Cold 1M TTFT improved 2.2% in this pair. Cold prefill remains predominantly GPU
work: the measured cold differences must not all be attributed to CPU
tokenization. Cached long prompts expose frontend cost more clearly.

## Warmed decode comparison

| Context | Concurrency | HF tok/s | Fastokens tok/s | Change |
|---|---:|---:|---:|---:|
| 8K | 1 | 56.76 | 60.95 | +7.37% |
| 128K | 1 | 61.74 | 62.10 | +0.59% |
| 8K | 8 | 179.00 | 168.53 | -5.85% |
| 8K | 16 | 226.75 | 232.53 | +2.55% |
| 128K | 8 | 168.52 | 156.81 | -6.95% |
| 128K | 16 | 220.09 | 219.49 | -0.27% |

All six candidate cells completed without errors, repetition, capacity limits
or warmup timeouts. Multi-client rates are aggregate throughput. The C8 drops
require follow-up; this first pair does not support a blanket no-slowdown claim.
[Candidate screen](results/20260929-fastokens/fastokens-screen.json).

Standalone cold-prefill client rates were 4,374 → 4,248 tok/s at 8K and
4,193 → 4,200 tok/s at 128K. Those timings show essentially retained long
GPU-prefill performance, with no established prefill-kernel speedup.

## C8 follow-up

A second Fastokens run reproduced the C8 decrease: 167.27 tok/s at 8K and
156.57 tok/s at 128K, versus 168.53 and 156.81 in its first run. Both cells
passed without errors, repetition, capacity limits or warmup timeouts.
[Repeat evidence](results/20260929-fastokens/fastokens-c8-repeat.json).
The repeat uses the same pinned harness and sampling, with standalone prefill
skipped; normal decode warmups remain enabled.

Because this decrease repeated, the saved KK926-corrected HF deployment was
restored for a second HF C8 check. The first Fastokens activation and rollback
state are preserved as `first-activation.json` and `first-switch-state.json`.
This follow-up tests whether the original HF result was unusually favorable.

The restored HF repeat reached **171.78 tok/s at 8K/C8 and 164.83 tok/s at
128K/C8**. Both cells passed without errors, repetition, capacity limits or
warmup timeouts. Compared with those HF repeats, the Fastokens repeats were
2.6% and 5.0% lower. [HF repeat](results/20260929-fastokens/hf-c8-repeat.json).

| Context | HF first | Fastokens first | Fastokens repeat | Restored HF repeat |
|---|---:|---:|---:|---:|
| 8K/C8 aggregate tok/s | 179.00 | 168.53 | 167.27 | 171.78 |
| 128K/C8 aggregate tok/s | 168.52 | 156.81 | 156.57 | 164.83 |

This is sequential HF → Fastokens → HF evidence, not a randomized trial or
proof of a universal regression. LIL uses fresh generated prompts, and sampled
continuations and speculative acceptance differ. The first API comparison used
identical prompts; the decode screen does not guarantee identical output tokens.
Still, both HF measurements exceeded both Fastokens measurements at each C8
context. The data do not justify describing Fastokens as a free speedup.

## Decision and final state

**Retain the KK926-corrected HF tokenizer as the default.** The workload priority
is decode/concurrency; the cached-long-prompt latency gain does not eliminate
the observed C8 tradeoff. Fastokens remains an available candidate, not an
enabled serving feature. [Decision](results/20260929-fastokens/decision.json).

The original corrected HF selection was restored exactly. Its compressor source
hashes were verified on all four running ranks, the seven short functional
checks passed again after restoration, and controller health was checked.
[Final deployment receipt](results/20260929-fastokens/deployment.json).
The endpoint remains `http://192.168.50.219:8015/v1`, model
`DeepSeek-V4.1-Flash-TP4`. The KK quality correction and all local performance
plugins remain active.

Candidate qualification passed 7/7 short and 7/7 fresh long-prefill functional
checks, all 45 API retrieval responses, and two fresh ~94K retrievals under
eight active decoders. No candidate functional failure was observed. Evidence:
[short](results/20260929-fastokens/fastokens-functional.txt),
[long](results/20260929-fastokens/fastokens-long-functional.json),
[mixed](results/20260929-fastokens/fastokens-mixed.json).

The unused pinned candidate images are retained for future work. An encoder-only
integration that preserves HF streaming detokenization is a possible follow-up;
it has **not** been implemented or shown to remove the C8 tradeoff. This campaign
ran no new full 40-cell benchmark and establishes no universal quality claim.
