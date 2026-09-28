# Transferring the Qwen performance changes

This investigation concerns the actual Qwen optimizations, including adaptive
HC and top-20 draft proposals. It does not treat benchmark methodology as a
substitute for porting useful execution changes. The SGLang runtime is retired; this review records vLLM execution experiments.

| Qwen change | DeepSeek applicability | Current action |
|---|---|---|
| Owned-row HC prefill | The principle transfers: retain residual rows on their owning rank and exchange only attention/MoE boundaries. Native DeepSeek currently replicates residual rows and Engram rejects sequence-parallel inputs. Its lagged mHC and CED boundaries also need explicit ownership. | Follow-up native mHC row ownership was implemented with reconstruction at Engram, CED and final consumers. Its correctness checks passed, but prefill remained approximately baseline, so it is not selected. Separate query-row indexer sharding is selected after passing long-context, mixed-load and exact-score/value checks; see the research record. |
| Adaptive HC decode | Qwen uses channel-sharded HC through four rows and replicated HC above that, avoiding two channel gathers at larger batches. DeepSeek uses fused lagged mHC, with different coefficients and prepared kernels, and does not have those HC channel gathers to remove. | No direct port of the four-row cutoff. Review the native per-shape mHC plans; a distributed mHC rewrite needs evidence that saved compute exceeds extra communication. |
| Top-20 draft proposals | Applicable at DSpark's final base-plus-Markov logits. Its sampler caches logits for rejection sampling, allowing the same filtered proposal to be used for both. | `dsv41_draft_topk` masks the final draft logits before sampling/cache. 19/19 GPU distribution and CUDA-graph/cache checks passed; the full-model screen showed no clear throughput gain and scored 71/75. It is not selected. Full target vocabulary and target sampling remain intact. |
| Exact graph sizes (`cg4`) | Applicable, but DeepSeek DSpark5 with adaptive verification has different live shapes from Qwen MTP3. | `engram-graphs` adds sizes 1–32 to the existing 5/6-multiple captures. Independent and combined screens did not establish a balanced gain; expanded graph sizes are not selected. |
| MTP depth 3 versus 5 | DeepSeek already uses DSpark5, a parallel draft backbone plus sequential Markov sampling. Qwen's sequential MTP result does not predict its optimum. | The cost-scale 1.25 trial did not establish a balanced gain; keep native defaults rather than copying Qwen's chosen depth. |
| QAD5500 hybrid weights | Checkpoint changes and tensor geometry are model-specific. | Keep the pinned DeepSeek checkpoint; no Qwen tensors or QAD assumptions transfer. |
| GDN/recurrent-state and target-head experiments | Qwen's recurrent GDN state is not DeepSeek's sparse-attention implementation. The Qwen campaign rejected several kernel/precision changes. | No GDN flags, target-head quantization or rejected MoE override copied. |

The native `dspark_draft_topk` setting is a different optimization: it evaluates
the Markov head only on selected **base** logits and explicitly supports Qwen3
DSpark architectures. The first local DeepSeek experiment instead filtered **final**
logits, matching the earlier Qwen proposal-filter strategy. That version still computes
the full draft head and Markov logits, so any benefit must come from acceptance
or verification behavior after accounting for the filtering overhead.

The follow-up `dsv41_markov_shortlist` adapts the gathered Markov kernel to
DeepSeek's online NVFP4 head, retaining its exact quantized rows before scale
swizzling. Both top-20 and top-128 reduced acceptance and decode throughput; neither
is selected. It does not change the target vocabulary or target weights. See
[the follow-up research record](RESEARCH-20260928.md) for results and qualification.

Top-20 is not a universal Qwen win. The retained Qwen report measured an optional
non-thinking coding improvement but lower matched reasoning throughput for the
combined top-20/MTP5 profile. DeepSeek adoption therefore remains conditional on
its own measured throughput and quality.

Source references:

- `../qwen38-flash-next-spark/tp2/optimization/HC-SEPARATION.md`
- `../qwen38-flash-next-spark/tp2/optimization/candidate/hc_prefill.py`
- `../qwen38-flash-next-spark/tp2/optimization/candidate/hyperconnection.py`
- `../qwen38-flash-next-spark/tp2/optimization/candidate/speculator.py`
- Pinned vLLM `models/deepseek_v4_1/b12x_layers.py`, `nvidia/model.py`,
  `v1/worker/gpu/spec_decode/dspark/speculator.py`, and `config/speculative.py`.
- Pinned B12x `norm/mhc/_tuning.py` and `_preparation.py`.
