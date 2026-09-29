# DeepSeek compressor-state correction — 2026-09-29 UTC

**Deployed through the normal controller at 18:33 UTC.** All four permanent
containers use their recorded corrected image IDs; the three patched source
hashes were checked in every running container. The final short functional
suite passed 7/7 and controller status passed. Endpoint:
`http://192.168.50.219:8015/v1`, model `DeepSeek-V4.1-Flash-TP4`.
The previous image, stopped containers and configuration backup are preserved;
see [operations](OPERATIONS.md) for explicit rollback.
[Deployment receipt](results/20260929-kk926/deployment.json).

This campaign ports the complete [KK vLLM #926 correction](https://github.com/local-inference-lab/vllm/pull/926),
including enabled compressor ring writes, to the existing SparkRing runtime.
The corresponding complete beta merge is [#943](https://github.com/local-inference-lab/vllm/pull/943).
It is a model-fidelity correction, not a new scheduler or quantization recipe.

The original worker disabled slot mapping for `CircularBufferSpec`. The
compressor consequently received padding slots and skipped state writes across
decode steps. The correction enables circular slot mapping, wraps positions
within the ring, and preserves padding/missing-block behavior. An isolated GPU
probe reproduced the original disabled writes and passed on all corrected GPUs.
The unchanged 17 upstream tests also passed independently on all four nodes.

## Runtime provenance and scope

SparkRing's parent is `eugr/spark-vllm-b12x:nightly-20260924`. Its integrated
vLLM revision is `03c4af34fbe6d2ff863bd03a6ed255c4de96785b`; this derived image
adds the three-file upstream diff at `7b935cb78a3f1f256b04006e82504a651685f72d`.
The complete beta merge is `38283c44a7e574661c5d6a374416a7720b47cf1b`.
We retained SparkRing's CUDA 13.4.2, NCCL 2.32.3, B12x/RoCEnante, checkpoint,
DSpark5, Engram projection TP, adaptive 4K contention steps, guarded query-row
indexer and 8K scheduler allocation ceiling. No native library was rebuilt.

The [source manifest](image/kk926/manifest.json) pins old and new hashes.
[Build details](image/kk926/README.md) explain receipt regeneration and unchanged
verification enforcement. Per-rank image IDs are recorded in
[images.json](results/20260929-kk926/images.json). Builds have identical corrected
runtime source; Docker metadata produces different image IDs.

[LMCache #106](https://github.com/local-inference-lab/LMCache/pull/106) was not
ported: this deployment does not use an LMCache connector. Native prefix
caching and the disk-backed Engram implementation are separate systems.

## Consistency measurement

Eight fixed prompts generate 2,048 tokens each: four with thinking off and
four with thinking on. Greedy generation ignores EOS to keep the length fixed.
Each generated token sequence is then replayed as one fresh prefill, using
exact token IDs. All replays must report zero cached prompt tokens and fit
within one 8K prefill step. Decode and prefill next-token distributions are
compared at corresponding positions.

The API exposes top-20 probabilities. We intersect the two reported token
sets, put all remaining probability in one other-mass bucket, and compute
KL(prefill || decode). This **coarsened KL is a lower bound**, not full-vocabulary
KL or the exact upstream metric. Top-1 agreement and retained probability mass
are also recorded. Each build generates its own continuation from the same
prompts; this is not a shared-continuation A/B experiment or a comparison with
an external full-precision DeepSeek reference. It tests this runtime's
decode-versus-prefill consistency, not general intelligence or universal output
correctness. Fresh replay also disables prefix-cache reuse by requirement.

Raw token IDs, log probabilities and responses are preserved in per-prompt
gzip files beside [baseline-consistency.json](results/20260929-kk926/baseline-consistency.json).

All eight probes completed on both builds (16,384 generated positions each).
Late-answer coarsened divergence fell **89.6%**, and top-1 agreement rose from
91.94% to 97.49%. The original rising-with-length pattern is absent in the
corrected averages. Both thinking modes improved: late KL fell from 0.1519 to
0.0167 with thinking off and 0.1433 to 0.0140 with thinking on.

| Generated positions (zero-based, end exclusive) | Original KL | Corrected KL | Original top-1 agreement | Corrected top-1 agreement |
|---|---:|---:|---:|---:|
| 0–256 | 0.0355 | 0.0213 | 96.00% | 96.14% |
| 256–512 | 0.0801 | 0.0180 | 92.72% | 97.12% |
| 512–1024 | 0.1151 | 0.0175 | 91.67% | 96.90% |
| 1024–1536 | 0.1415 | 0.0198 | 91.58% | 97.09% |
| 1536–2048 | 0.1476 | 0.0154 | 91.94% | 97.49% |

Corrected evidence: [summary](results/20260929-kk926/corrected-consistency.json).
This is a substantial measured fidelity improvement, not an 89.6% improvement
in general answer quality. Residual decode/prefill differences remain.

## Performance method

Fresh baseline and corrected screens use pinned LIL v0.6.2 revision
`ccd9ad8ced7e387794391bfb0ac6d99b1f66ba6f`, the same matched request adapter,
thinking off, temperature 1, top_p 1, top_k -1, 2,048 maximum output tokens,
EOS ignored and repetition detection enabled. Both cover 8K and 128K nominal
contexts at concurrency 1, 8 and 16, with 20-second sustained cells and separate
cold-prefill samples. These are six-cell regression screens, **not another full
20-cell sustained plus 20-cell burst benchmark**. Different sampled answers and
speculative acceptance introduce variability; engine-step rates are retained
to help interpret token throughput. A single screen does not establish a small
speedup or regression statistically.

First matched screen (aggregate output tokens/sec):

| Context | Concurrency | Original | Corrected | Change |
|---|---:|---:|---:|---:|
| 8K | 1 | 61.4 | 58.6 | −4.5% |
| 128K | 1 | 73.9 | 59.0 | −20.1% |
| 8K | 8 | 171.1 | 155.4 | −9.1% |
| 8K | 16 | 236.7 | 230.3 | −2.7% |
| 128K | 8 | 161.6 | 152.2 | −5.8% |
| 128K | 16 | 228.8 | 219.8 | −3.9% |

All six cells on each image were valid, without detected repetition, capacity
limits or failure reasons. Cold-prefill throughput was 4,360 → 4,418 tok/s at
8K (+1.3%) and 4,321 → 4,401 tok/s at 128K (+1.9%). The prefill figures use
client prompt tokens / TTFT; the 128K label is nominal (about 128.5K actual
tokens in these samples).

This screen does **not** support a decode speedup or unchanged throughput.
The largest token-rate change, 128K/C1, accompanies effective speculative
acceptance falling from 3.136 to 2.441 tokens/step, while reported engine-step
rate rises from 23.56 to 24.19. At 8K/C8 the reported step rate falls from
76.56 to 68.82 with similar acceptance. Thus acceptance changes explain some,
but not all, of the observed differences. The corrected target also produces
different continuations; attribution to a single kernel cost would be unjustified.
These server step counters are aggregate draft-bearing request steps, as
reported by LIL, not GPU utilization or a direct kernel microbenchmark.

Evidence: [original screen](results/20260929-kk926/baseline-screen.json),
[corrected screen](results/20260929-kk926/corrected-screen.json), and their
matched-request sidecars and command receipts.

The [second corrected screen](results/20260929-kk926/corrected-screen-repeat.json)
also passed all six cells. Results below keep the repeat separate rather than
selecting the best sample:

| Context | Concurrency | Corrected repeat tok/s | Change vs original screen |
|---|---:|---:|---:|
| 8K | 1 | 61.3 | −0.2% |
| 128K | 1 | 57.8 | −21.7% |
| 8K | 8 | 161.1 | −5.8% |
| 8K | 16 | 233.3 | −1.4% |
| 128K | 8 | 158.0 | −2.2% |
| 128K | 16 | 236.1 | +3.2% |

Repeat prefill was 4,385 tok/s at 8K and 4,354 tok/s at 128K. High-concurrency
throughput is broadly retained across these samples. Long-context C1 remains
slower; it should not be dismissed as noise or described as performance-neutral.
The original screen's 73.9 tok/s at 128K/C1 was also above the prior full
benchmark's roughly 64–66 tok/s C1 range. The 89.6% consistency improvement
is the reason to select the correction, with this speed limitation recorded.

The earlier [full benchmark](FULL-BENCHMARK-20260928.md) used the pre-correction
image. It remains historical evidence and must not be presented as a corrected
runtime result. Focused 128K/C2 and C16 sustained/burst repeats target the cases
that previously triggered repetition diagnostics. Passing repeats do not prove
all possible repetition is resolved.

The [focused corrected run](results/20260929-kk926/corrected-128k-repeat.json)
passed both 30-second sustained cells (128K/C2: 92.3 tok/s; C16: 232.8 tok/s)
and both complete-response burst cells (C2: 90.6 tok/s; C16: 217.4 tok/s).
No repetition was detected. Bursts used one warmup request, then one measured
request per concurrency slot, with the same 2,048-token EOS-ignored contract.
This is evidence for those four cells, not proof that all long-output loops
have disappeared.

Functional checks cover counting, arithmetic, code, automatic and forced tool
calls, vision and thinking. Long-functional repeats insert at least 65,536
uncached prompt tokens per request. Mixed-load retrieval injects two fresh
long prompts while eight decoders run. The million-token retrieval probe
requires a correct needle and zero cached prompt tokens. These checks provide
bounded integration coverage rather than a broad model-quality benchmark.

The initial long-functional run passed 6/7 checks: automatic weather-tool
selection returned no parsed tool call after a ~94K-token fresh prompt.
The forced tool call and the five other checks passed. This initial failure is
preserved in [the first-run transcript](results/20260929-kk926/long-functional-first.txt)
and [usage receipt](results/20260929-kk926/long-functional-first.json); it must
not be erased by a passing repeat. The first harness recorded usage but not
the complete response for this failure, so its exact content is unavailable.
The harness now also records full responses and nonce prefixes for diagnosis;
the prompts, checks and generation settings are unchanged.

The [complete repeat](results/20260929-kk926/long-functional.json) passed 7/7,
including an automatic `get_weather` call for Paris. Every request again used
at least 65,536 uncached tokens. This establishes that the automatic-tool path
works with the correction, but leaves an intermittent long-context tool-choice
limitation. Neither these two runs nor the short suite establishes that the
correction caused or resolved that limitation.

The [mixed-load integrity probe](results/20260929-kk926/mixed-integrity.json)
retrieved both codes correctly with eight active decoders and no request
errors. Fresh long-prompt first-content times were 26.37 and 50.87 seconds.
Decoder client SSE chunk-gap p95 was 0.124 seconds before the arrivals,
1.230 seconds during them, and 0.149 seconds afterward. A chunk may contain
multiple speculative tokens: these are not token ITL figures, and this
integrity workload is not a matched pre/post mixed-traffic speed comparison.

The [million-token probe](results/20260929-kk926/cold-1m.json) returned the
correct code after **322.11 seconds** to first content (322.13 seconds total),
with 1,008,430 prompt tokens and **zero cached tokens**. Earlier pre-correction
query-indexer runs ranged from 308.79 to 333.9 seconds. This historical range
provides context; it is not a fresh paired million-token timing experiment.

All 27 recorded query-indexer guards enabled with exact scores and selected
score values; none disabled. Startup completed before real requests armed
those guards. [Guard receipt](results/20260929-kk926/guards-final.json).

The separately requested [Fastokens assessment](FASTOKENS-ASSESSMENT-20260929.md)
found 14–16× faster CPU prompt encoding with matching tested token IDs. It
was disabled during this campaign; no result above includes that tokenizer
change. See the subsequent [Fastokens serving trial](FASTOKENS-SERVING-20260929.md)
for its end-to-end measurements.
