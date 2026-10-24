# Engine-method applicability screen

October 20 UTC. Two bounded, read-only GPT-6.1 Sol investigations checked
current upstream work against the selected October 15 vLLM/FlashInfer source.
No engine transplant or new mathematical kernel was retained from this review.

## Potential investigation

SGLang's [DS4.1 optimization report](https://staging.lmsys.org/blog/2026-09-28-deepseek-v41-optimization)
motivates checking capacity-sized indexer bookkeeping. In our actual DS41
path, the public BF16 score buffer's unused tail is cleared to negative infinity
and `_pages` copies the planned index-page width. These are candidates for
measurement, not established bottlenecks.

Our indexer scoring and top-k already respect actual GPU sequence lengths.
There is no evidence that it scores the entire 1M context for every short
request. A useful next investigation would time the remaining bookkeeping at
real verification row counts and context lengths. Any change must preserve all
score consumers, scratch ownership, selected indices, ties and page validity
across short-to-long graph replays and recycled pages.

## Changes not justified for this build

- FlashInfer's [top-p=1 AIR shortcut](https://github.com/local-inference-lab/flashinfer/commit/4b36ac94cfa9949253972c652be3da778ae9e528)
  and [disabled top-k copy avoidance](https://github.com/local-inference-lab/flashinfer/commit/622cec10eb75da189f4dadddabc2d142a33cd211)
  are newer than our pin. However, our DSpark consumer directly calls Triton
  `gumbel_sample`; a live AIR consumer has not been established. Matching
  sampling defaults alone is insufficient reason to backport them.
- SGLang [WO-A fusion #39957](https://github.com/sgl-project/sglang/pull/39957)
  measures a different GPU/kernel contract. Its kernel targets SM100/103,
  whereas GB10 is SM121. Our target attention already uses B12x fused
  inverse-RoPE/WO projection. The current mHC path also already uses lagged
  `post_pre` fusion. Combined improvements in
  [#39370](https://github.com/sgl-project/sglang/pull/39370) do not establish an
  isolated gain in our build.
- TensorFold's [1.0 release notes](https://github.com/ashhart/TensorFold/blob/main/RELEASE-NOTES-1.0.0.md)
  do not qualify a native DeepSeek port. Reported GB10 native gains concern a
  different model. Our historical Zig TP4 prefill experiment used EXL3 and about
  23 GiB of additional stage weights per rank; short decode remained near
  parity. That allocation does not fit the selected deployment's headroom.
- Qwen-style gathered Markov top-k is not an available DS41 flag. The DS41
  class lacks the gathered operation, and its online NVFP4 representation
  differs from the retained-weight path. A port would need new correctness
  validation and a measured benefit; the current Markov head already fits
  GB10 L2.

These findings do not predict 70 C1 or 300 C16. They narrow the next experiments
without changing checkpoint precision or importing optimizations for unrelated
execution paths. Private-source research, if any, is kept outside this public
repository.

## SparkRing README comparison

Current upstream main was inspected at
[`9932204d25ab857ec4a5a7c437f4dc0f5bddee2e`](https://github.com/FujitsuPolycom/sparkring/tree/9932204d25ab857ec4a5a7c437f4dc0f5bddee2e).
The README's **71 / 137 / 194** means **C1 / C4 / C8 at 32K**. Its raw
values are 70.554 / 136.692 / 194.349; C16 in the same run is 277.940.
At 8K, that run records 67.327 / 200.419 / 275.639 at C1/C8/C16.
[Raw LIL result](https://github.com/FujitsuPolycom/sparkring/blob/9932204d25ab857ec4a5a7c437f4dc0f5bddee2e/performance/records/images/release-2026.10.2-speed-32k-20261012/deepseek-v41-flash-tp4-cycle4-ring-a/bench-result.json).

That October 12 run used the original checkpoint and locked 2418 MHz clocks.
It predates 1017 and our October 15 math runtime. Our comparisons through the
first draft4 trial used a 0–2350 MHz ceiling. The user subsequently authorized
testing removal of this limit. Clock frequency does not translate linearly
into throughput.
[Published conditions](https://github.com/FujitsuPolycom/sparkring/blob/9932204d25ab857ec4a5a7c437f4dc0f5bddee2e/performance/records/images/release-2026.10.2-speed-32k-20261012.md).

Upstream also publishes a newer 1017 result of 61.2 / 194.9 / 275.2 at
C1/C8/C16, median of two runs. Its acceptance harness uses **no added context**,
so this is supporting context, not a matched comparison to our 8K LIL cells.
[1017 report](https://github.com/FujitsuPolycom/sparkring/blob/9932204d25ab857ec4a5a7c437f4dc0f5bddee2e/performance/records/images/dev-20261013-dcp2prefill-status038-sircl-tp6-deepseek-v41-flash-tp4-1017-20261017.md).

The exact current profile has the same principal DSpark5, Engram, B12x,
scheduler and graph settings as our pre-draft4 selection. Our async scheduling
was already enabled. Upstream uses two physical ports per node; our switched
setup uses one physical port with two logical rails. Copying ring-only HCA
maps onto this switch would be incorrect.
[Profile](https://github.com/FujitsuPolycom/sparkring/blob/9932204d25ab857ec4a5a7c437f4dc0f5bddee2e/profiles/deepseek-v41-flash-tp4/config.json).

The subsequent transport comparison was more specific: our old-provider
**switched** baseline versus the new provider, including large FP32 logits
all-gathers. Existing microbenchmarks compared new-provider one-shot against
new-provider two-shot and NCCL all-reduces; they did not time the old provider
or logits all-gathers. Two-shot accelerates all-reduce, while all-gather remains
a one-shot path. The stopped-fleet provider comparison now passes all exact
numerical oracles, with large logits gathers within approximately 1% between
providers and lower two-shot latency at the tested 64/80/96-row reductions.
There was also a slower new-provider 48-row one-shot result. See
[the report](REPORT.md#old-provider-versus-new-provider-comparison).
These synthetic timings do not establish the source of the serving variation.

## DeepInfer: useful scheduling reference, not a fleet runtime replacement

Inspected October 20 at
[`8b16149741a4935e1dec8cea27853f273b374c5b`](https://github.com/deepseek-ai/DeepInfer/tree/8b16149741a4935e1dec8cea27853f273b374c5b).
Its default checkpoint is the same official 1017 model. Published support is
SM100 and Ascend 950, not GB10/SM121. The release provides offline inference;
the production KV-cache service, disaggregation and replica load balancing
are not included. Published prefill and decode measurements use four and
64 SM100 GPUs respectively, each within a scale-up domain. They are not
four-node GB10 TP4 predictions.
[Release scope](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/README.md).

Two advertised ideas already have counterparts in our pinned runtime:

- Confidence-scheduled verification already uses cumulative per-position
  confidence, a graph-cost-aware total budget, and current GPU confidence to
  distribute that budget across requests. A default maximum of five drafts
  is not a new capability.
  [DeepInfer GPU allocation](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/layers/tilelang_ops/cuda/schedule_mtp_varlen.py).
- Bounded decoder prefill is already implemented by our `ced.py`,
  `nvidia/model.py` and `nvidia/model_state.py`: gather retained suffix rows at
  the encoder/decoder boundary, execute the decoder on those rows, then
  restore the external row layout. DeepInfer's compact YoCo path implements
  the same broad optimization. Its default 140-token retained suffix includes
  its own backtracking allowance; that number is not a value to copy into our
  different cache and replay contract.
  [Compaction](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/models/v4_modules/yoco.py),
  [equivalence tests](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/examples/yoco/README.md).

**Concrete new candidate: update adaptive verification costs from runtime
measurements.** DeepInfer adjusts its startup forward-cost curve using robust
recent timing estimates and measures sampler overhead separately by request
count. Our inspected adaptive manager profiles initial curves and applies a
fixed cost scale. Context growth or transport/concurrency changes could make
those initial costs less representative; this is a hypothesis, not a measured
GB10 bottleneck.
[Cost model and runtime correction](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/csrc/engine/mtp_varlen.hpp).

The current image's `vllm/v1/worker/gpu/spec_decode/adaptive_verification.py`
was read from the stopped draft4 container and matches the inspected snapshot:
SHA-256 `e8301a3f5898ddfb710806975166d62735649533e04043c67ca5b452ec277955`.

A bounded port should update only scheduling costs, retaining the original
tables for fallback. Timing collection must be asynchronous and its overhead
measured. All TP ranks must choose the same budget. Preserve stale-confidence
budget selection versus fresh-confidence allocation, request remapping,
graph padding and the existing proposal/rejection algorithm. Validate these
contracts before matched C1/C8/C16 and short/long-context comparisons.
Begin by collecting bounded timing samples without changing any decisions;
compare predicted versus measured costs before implementing feedback.
Our startup profile closes target-forward timing before the target LM head,
logits communication and sampling, and separately times draft proposal.
The first cost audit should therefore measure those omitted target stages,
not assume the only discrepancy is context growth.
[Pinned runner timing boundaries](https://github.com/local-inference-lab/vllm/blob/8244d1c44348ae8a5bbfc9f1b607021652283ed4/vllm/v1/worker/gpu/model_runner.py).
Do not infer deterministic seeded output from variable-length speculation.
No DeepInfer code was installed in the serving fleet.

Its DeepEP-V2 EP/CP/Engram buffers and symmetric-memory compute integration
would require a much broader port than a RoCEnante flag. That work is not
justified by a demonstrated benefit on this one-port 200G topology.
[Communication integration](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/parallel_utils/userbuffer.py).

## Existing batch-sharded sampling: a separate conditional experiment

The pinned runtime also implements `--enable-batch-sharded-sampling`.
Our DS41 wrapper inherits `compute_logits_local`, so the model interface exists.
This path exchanges partial-vocabulary logits with all-to-all, samples only
each rank's assigned requests, then gathers the small outputs. It retains the
full vocabulary; this is distinct from lossy top-k proposal restriction.
[Implementation](https://github.com/local-inference-lab/vllm/blob/8244d1c44348ae8a5bbfc9f1b607021652283ed4/vllm/v1/worker/gpu/sample/batch_shard.py).

It is **not compatible with our enabled adaptive verification**. Its shard
plan uses CPU logits counts, while adaptive verification determines the
actual per-request split on the GPU. Upstream rejects that combination;
the guard must not be bypassed.
[Configuration validation](https://github.com/local-inference-lab/vllm/blob/8244d1c44348ae8a5bbfc9f1b607021652283ed4/vllm/config/vllm.py).

A future bounded test would first establish a fixed-verification control,
then enable sharded sampling with the same draft width and compare C1/C8/C16,
mixed request lengths, structured outputs, logprobs and images. The all-to-all
uses the Torch device group, so transport and empty-rank behavior also need
qualification. Reducing logits replication does not prove an end-to-end gain,
and could lose more from fixed verification or communication overhead.
This path has not been activated in the campaign.

The subsequent native Torch captures made this a lower-priority experiment:
the materialized MoE kernels dominate the observed C16 workload. No sharded
sampling throughput gain is claimed, and the fixed-verification/sharding pair
has not been run.

## Profile-guided compact MXFP4 candidate

The October 17 FlashInfer commit
[`a6b096f7b34dd0266af382a4ece59682676f6ece`](https://github.com/local-inference-lab/flashinfer/commit/a6b096f7b34dd0266af382a4ece59682676f6ece)
directly changes the `W4A8MaterializedPhase1Kernel` and `Phase2Kernel` observed
in our live CUDA traces. DS41's 2304-column MoE intermediate dimension becomes
576 columns at TP4, matching its compact-N64 case (`N % 128 == 64`).

It expands compact direct decode coverage through 16 tokens, folds ordered
route reduction into FC2, and adds grouped M64 execution with M32 arithmetic for
partly filled source tiles. Other changes cover activation quantization,
scale staging, padded K64 work, prepared storage, candidate selection and
cache contracts. The upstream numerical and graph tests are relevant; there
is no published GB10 end-to-end gain establishing our target performance.

This is not a two-file overlay. A dry-run of the complete 14-file commit against
our pinned October 15 source fails on five files, including both materialized
kernels and tuning. An import/API audit identified a coherent boundary: the complete changed MoE
implementation, four quantization support files and the preparation-cache schema
(29 files including one README). The resulting isolated candidate was built and
sealed, passed numerical and functional checks, then failed to improve two
matched serving screens. It was rejected in favor of the retained draft4 image.
Schema 23 requires
fresh tuning, including decisions for otherwise unchanged operators.
See [the candidate recipe](https://github.com/nero-/deepseek-v41-flash-gb10-ring/blob/pre-tilelang-cleanup-20261024/image/moe-20261020/README.md). Checkpoint storage precision and vocabulary remain
unchanged, but changed arithmetic scheduling still requires numerical,
graph-replay and serving qualification.

DeepInfer's runtime cost correction remains a separate possible investigation.
The profile does not by itself compare startup cost tables with live costs.
No online calibration or new scheduling decision has been implemented.

A native concurrency-specific proposal cap is a smaller complementary test:
`num_speculative_tokens_per_batch_size=[[1,1,3],[2,16,4]]` with the maximum
still four. It can reduce C1 target verification work while preserving higher
concurrency. It does **not** make the drafter itself variable-width: inherited
[DFlash proposal](https://github.com/local-inference-lab/vllm/blob/8244d1c44348ae8a5bbfc9f1b607021652283ed4/vllm/v1/worker/gpu/spec_decode/dflash/speculator.py#L507)
discards the requested per-batch width, and DSpark uses its fixed query/head/
Markov count. The
[runner applies the cap afterward](https://github.com/local-inference-lab/vllm/blob/8244d1c44348ae8a5bbfc9f1b607021652283ed4/vllm/v1/worker/gpu/model_runner.py#L2541).
The bounded trial subsequently passed seven functional checks and measured
67.06 / 192.21 / 270.95 tokens/s at 8K C1/C8/C16 on stock clocks. Its preceding
restored draft4 control measured 63.05 / 192.53 / 257.67, while an earlier
draft4 run reached 64.80 / 198.69 / 273.37. These stochastic screens suggest a
C1 benefit but do not isolate the C16 variation. See the full qualification
and final selection in [the campaign report](REPORT.md).
True variable-width drafting
would require coordinated input layouts, sampling and separate graph descriptors;
mutating step-count fields in a running captured graph is not safe.
