# TensorFold assessment for DeepSeek-V4.1-Flash

Date: 2026-10-04. Read-only research; no fleet downloads, installations, patches or inference tests were performed for this assessment.

**Recommendation: retain corrected vLLM TP4 as the default. A later TensorFold TP2 pilot may be worthwhile for short independent requests, particularly as two replicas across our four nodes. Defer a TensorFold TP4 port.** Published results do not establish a general improvement in our prefill, quality, concurrency or serving behavior.

## What exists and what is compatible

Upstream [ashhart/TensorFold](https://github.com/ashhart/TensorFold) was at **0.6.5**, commit `609ca419abecebdc5a059498a613680bd3aa847f`, when inspected. Its supported CUDA model list does not include DS4.1. Results for its Qwen, GLM, Nemotron and Apple Silicon engines should not be transferred to DS4.1.

The relevant implementation is [bertholomus/TensorFold](https://github.com/bertholomus/TensorFold/tree/deepseek-v41-tp2), branch `deepseek-v41-tp2`, **v0.3**, commit `bbaa6cd3e4a15d80f3c2c649bbab5a7d11fb3391`, built on upstream 0.6.3. It was measured on two DGX Spark/GB10 nodes, establishing practical ARM64/SM121 support for that configuration. Its [family module](https://github.com/bertholomus/TensorFold/blob/bbaa6cd3e4a15d80f3c2c649bbab5a7d11fb3391/src/tensorfold/families/deepseek_v41/__init__.py) explicitly accepts only **TP1/TP2 and EXL3**. Neither our original MXFP4 checkpoint nor the rejected lossless-CSF checkpoint loads directly.

The [published recipe](https://huggingface.co/bertholomus/DeepSeek-V4.1-Flash-TensorFold-TP2-2xGB10) was inspected at HF revision `285786b530c3dd75eb7c51ba96fdf7d7bed02a68`. Its v0.3 results are:

| Two GB10s, greedy decoding and DSpark | Published result |
|---|---:|
| Single stream, 512 generated tokens, code | 72.7 tok/s |
| Same, prose | 45.6 tok/s |
| Same, structured text | 87.9 tok/s |
| Four streams sustained, 90 seconds | 107.5 aggregate tok/s |
| Four streams, per-stream median | 32.4 tok/s |
| Prefill at 8K–128K | approximately 1,739–1,984 tok/s |

These are author measurements, not reproduced here. Different prompts, greedy sampling, quantization and unspecified clock equivalence prevent a matched comparison with our 2350 MHz deployment. The recipe reports unchanged replies across v0.2/v0.3 and drafted-versus-serial checks; it does not establish equivalence to our checkpoint.

## Fair four-node option: two TP2 replicas

Our fresh corrected vLLM TP4 screen measured approximately **4.4K prefill tok/s**, **178.4 aggregate decode tok/s at C8**, and **243.0 at C16**. The [local baseline receipt](results/20261004-csf/baseline-screen.json) controls the clock and selected profile; it is not a TensorFold A/B.

Two independent TensorFold pairs are more plausible than an immediate TP4 port:

| Four-node comparison | Interpretation |
|---|---|
| Two replicas × published 107.5 tok/s | **~215 aggregate tok/s at total C8**, an unverified projection, about 21% above our C8 screen |
| Two simultaneous independent prefills | **~3.5–4.0K aggregate tok/s**, projected; no advantage over our ~4.4K single TP4 result |
| One fresh 128K request | **~65–74 seconds**, projected from fork prefill rates, versus our measured ~29 seconds |
| Total C16 or long concurrent prompts | No published comparable evidence; cannot extrapolate the C4 result unchanged |

The Spark pair and GX10 pair could each serve a replica. Real benefit depends on request mix, quantization quality, memory pressure, pair performance, and balancing. Conversation affinity is needed to preserve prompt reuse; idle capacity in one replica cannot directly enlarge the other's cache or accelerate a request there.

## KV and concurrency: small cache, shared total window

The [design](https://github.com/bertholomus/TensorFold/blob/bbaa6cd3e4a15d80f3c2c649bbab5a7d11fb3391/tools/dsv41/DESIGN.md) uses DS4.1's native packed FP4 compressed latents and indexer keys, approximately **890 bytes per token per rank**: **~0.87 GiB at 1,048,576 tokens**, excluding rings, token storage, graphs and workspace. The small cache is replicated across ranks. This DS4.1 path does not inherently inflate KV; fixed full-window-per-stream accounting in some Qwen TensorFold recipes is a different implementation.

Its [scheduler source](https://github.com/bertholomus/TensorFold/blob/bbaa6cd3e4a15d80f3c2c649bbab5a7d11fb3391/src/tensorfold/families/deepseek_v41/cuda/multi.py) shows **one total context pool shared by concurrent streams**. The default 262K pool cannot hold four independent 128K prompts. Admissions reserve prompt, requested reply and scratch space; retained prompts also consume pool space until evicted. This is distinct from allowing every stream the configured context length.

Default rounds hold **16 verification rows**. At eight live streams, speculative depth is capped at one; at sixteen it becomes zero. Larger settings require separate qualification. Parallel mode explicitly rejects constrained structured output and logprobs. Plain structured-looking text in a speed benchmark is not JSON-schema-constrained generation.

## Checkpoint quality and storage cost

The [Mia-AiLab EXL3 2.9bpw checkpoint](https://huggingface.co/Mia-AiLab/DeepSeek-V4.1-Flash-EXL3-2.9bpw), revision `64ba41b6c916a587db06eae2e19b7845f7be6e6b`, changes weights lossily: mixed 2/3-bit routed experts, higher precision for sensitive projections, and 4-bit DSpark weights. Original Engram tables remain FP8 in original shards 47/48; some Engram projection weights are quantized. It is not a lossless alternative to our original checkpoint.

“Exact” means speculative output matches serial output within the same TensorFold engine, quantization and settings. It does not establish identical output to vLLM, original weights or another rank count. Small MMLU/GSM8K subsets in the release recipe cannot quantify quality loss against our corrected deployment. Long-answer fidelity, coding and tool reliability need matched evaluation.

[HF file metadata](https://huggingface.co/api/models/Mia-AiLab/DeepSeek-V4.1-Flash-EXL3-2.9bpw?blobs=true) totals **210,600,939,078 bytes / 196.14 GiB across 39 safetensor shards**. A complete local EXL3 tree plus the reported approximately 99 GiB per-rank weight cache adds **~295 GiB per node**, reusing our original Engram files. That exceeds the GX10s' approximate free space with the restored original deployment retained. Disk staging or a deliberately qualified rank-local loading arrangement would be necessary.

## Prefill, memory and API caveats

The [engineering report](https://github.com/bertholomus/TensorFold/blob/bbaa6cd3e4a15d80f3c2c649bbab5a7d11fb3391/tools/dsv41/REPORT.md) distinguishes its fast **bounded decoder replay** prefill from exact all-layer prefill. It reports approximately 99 GiB resident weights per rank with only 5–8 GiB headroom; an earlier 1M-context setting reduced prefill by about 10%. An exact non-replay 128K prefill previously triggered host OOM. Subsequent changes were made, but that case was not rerun in the report.

The fork demonstrates tools, thinking and images, including six image checks. Those demonstrations are not qualification of our full API and tool-policy contract. Its first numerical comparison also fell below its initial teacher-forced agreement target; serial/drafted equality alone is insufficient evidence of model fidelity. The reported 1M needle success was an earlier single-stream trial, not a repeated release-build concurrency qualification.

## What could transfer into our current stack

Our existing vLLM implementation already fuses shifted **mHC post → next pre → RMSNorm**. The [baseline vLLM source at `1794dcf18454900263e0c66711af8ea4a1283ac1`](https://github.com/local-inference-lab/vllm/blob/1794dcf18454900263e0c66711af8ea4a1283ac1/vllm/models/deepseek_v41/nvidia/model.py#L699) calls `mhc_shifted_post_pre` and documents that each layer's post runs inside the next fused pre. The live source snapshot inspected locally contains the same structure. TensorFold's headline mHC fusion is therefore already conceptually present, though its kernel implementation differs.

The fork's [v0.3 kernels](https://github.com/bertholomus/TensorFold/blob/bbaa6cd3e4a15d80f3c2c649bbab5a7d11fb3391/src/tensorfold/families/deepseek_v41/cuda/kernels.py) suggest profiling small-row router/indexer projections, cache-write/compressor epilogues and launch dependencies. These are potential experiments, not demonstrated gains for our stack. EXL3 rotation/grouped expert kernels are not drop-ins for B12x MXFP4. TensorFold already has DSpark, but our adaptive verifier, guarded query-row sharding, Engram projection TP and SparkRing transport would require integration or equivalent qualification.

A TP4 port is substantial work: DS4.1's 2304-wide expert intermediate becomes **576 per rank**, cutting EXL3's 128-element block structure. The [EXL3 linear kernel](https://github.com/bertholomus/TensorFold/blob/bbaa6cd3e4a15d80f3c2c649bbab5a7d11fb3391/src/tensorfold/cuda/exl3/linear.py#L84) requires dimensions divisible by 128. Padding or a different shard/layout strategy, kernel changes, rank-order arithmetic, transport and correctness testing would be needed. Removing the TP2 guard alone is inadequate.

## Suggested future work, in order

1. Profile the restored vLLM at representative solo and concurrent verify rows. Test one genuinely absent fusion using original weights, with numerical and CUDA-graph checks before serving benchmarks.
2. If pursuing TensorFold, start with the published TP2 fork on the Spark pair. Match prompts, sampling, 2350 MHz cap, fresh/cache-hit accounting and generated lengths; test quality, long-answer behavior, tools, memory and failures before speed selection.
3. If the pilot is acceptable, compare **two TP2 replicas against one TP4** under realistic short/long traffic, including C8/C16, queueing, prompt reuse and long concurrent admissions. Count all four nodes in throughput and power comparisons.
4. Defer the TP4 port until measured results justify the extra integration and maintenance cost.

No execution is proposed as part of this research artifact. The current decision remains restoring and retaining the prior corrected vLLM deployment; TensorFold is a separate future experiment.
