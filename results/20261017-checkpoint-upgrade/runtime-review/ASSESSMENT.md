# Runtime update assessment — 2026-10-17 UTC

The official 1017 checkpoint is now qualified and selected on the corrected
runtime. Runtime and collective upgrades are deferred until the switch arrives.
Then test a narrow image update for the relevant correctness and graph-memory fixes. A current FlashInfer/vLLM build is worth a separate
candidate, but the evidence does not yet establish higher DS41 TP4 throughput
on this switchless ring. The GPU runtime is unchanged. A reproduced Python tool-parser bug was fixed
in the selected 1017 image and passed serving qualification.

## Verified installed state

The preserved serving image has standalone B12x 1.3.0, FlashInfer 0.7.0,
CUTLASS DSL 4.7.0 and Torch 2.13.0+cu130. The selected source receipts pin
B12x `c8e461281a3872a0e5de2485ef1df3df6556f07c` and the corrected September
SparkRing/eugr build. Package version text is not a substitute for those source
receipts. The 1017 candidate adds the prompt encoder correction and the exact Python
parser fix from vLLM #921; GPU sources and libraries are unchanged.

Read-only source inspection confirms:

- The BF16 prefill projection and dynamic MoE producer-acquire sites lack the
  new async-proxy fences.
- DS41 still retains `metadata_buffers` as CUDA graph capture resources, the
  ownership pattern fixed by vLLM #918.
- The inspected DS41 implementation has no `VLLM_DS41_ATTENTION_COMPUTE`
  selection from #911. This establishes a missing change, not a measured
  quality defect on this fleet.

Evidence: `current-numerics-and-packages.txt`, `current-b12x-sources.json`.

## Parser fix selected during this assessment

The previous image dropped a parameter lacking `string=` in both full and partial
argument conversion: `{"a":"x","n":12}` became `{"a":"x"}`.
[KK #921](https://github.com/local-inference-lab/vllm/pull/921) fixes this using
the same upstream parser files. The rebuilt candidate passed all 128 upstream
DS4/DS41 parser tests on each rank, including streaming behavior. This does not
change the GPU benchmark stack. See `../parser-qualification.json` and
`parser-reproduction.txt`.

## Ranked follow-up candidates

1. **Relevant kernel race fixes.** FlashInfer [#25](https://github.com/local-inference-lab/flashinfer/pull/25)
   adds the missing fence in BF16 prefill projection; its GB10 reproducer
   includes hidden width 5120. [#24](https://github.com/local-inference-lab/flashinfer/pull/24)
   fixes four dynamic-MoE refill paths. Both corresponding source patterns
   exist in our old B12x. Also audit dense GEMM
   [#16](https://github.com/local-inference-lab/flashinfer/pull/16) and DSA
   barriers [#19](https://github.com/local-inference-lab/flashinfer/pull/19)
   against the selected plans. These are correctness candidates, not promised
   speed gains; upstream #24 measured roughly unchanged replay cost. Run the
   relevant race tests on GB10 with genuinely rebuilt kernels before a serving
   test. A source edit that reuses stale compiled kernels is not validation.

2. **DS41 graph metadata ownership, vLLM
   [#918](https://github.com/local-inference-lab/vllm/pull/918).** Narrow change
   with an identified matching old code pattern. It reduced per-graph retained
   memory on the upstream RTX PRO setup. Our smaller K5/16-sequence graph set
   means their 3.4 GiB saving cannot be assumed here. Measure startup allocation
   and graph replay, then full serving; do not change memory utilization in the
   same comparison.

3. **Reference-aligned arithmetic,
   [#911](https://github.com/local-inference-lab/vllm/pull/911).** BF16 sparse
   attention and FP32 output logits are numerically closer to the reference.
   The published end-to-end quality and speed comparisons were largely within
   noise on RTX PRO; GB10 needs its own evaluation. The stricter single-pass
   `reference` mode is a separate, slower option and is not the proposed default.

4. **RoCEnante chunked two-shot all-reduce,
   [425fb6](https://github.com/local-inference-lab/flashinfer/commit/425fb6b4095d).**
   The upstream four-Spark switch test cut a 4 MiB collective from 664 to
   325 microseconds. It primarily targets larger messages and is most promising
   for prefill. It does not establish a C8/C16 decode gain. Our switchless paths,
   2 MiB RoCEnante selection ceiling and larger prefill payloads require an
   adapter/capacity audit before testing. Revisit once the switch is installed
   as well; the reported test used one 200 GbE switch.

## What the FlashInfer migration changes

B12x was merged into FlashInfer's experimental subtree on October 6. New
development is in `flashinfer/experimental/b12x`; `import b12x` remains the
compatibility interface. This changes packaging and integration, not model
weights, quantization, or an automatic performance switch.

The [migration guide](https://github.com/local-inference-lab/b12x) requires
matching FlashInfer and vLLM revisions. FlashInfer no longer supplies the old
`b12x_loader` plugin entry point; the compatible vLLM adapter must register the
loader. Our explicit plugin list and root-owned toolchain receipts therefore
need adjustment in a full migration. Do not pip-upgrade the live container or
install both distributions over one another. Existing direct B12x calls do not
need `FLASHINFER_ALLOW_EXPERIMENTAL_AUTO_BACKENDS=1`.

## Image choices checked

- **KK canonical 20261016.2:** vLLM `8244d1c44348`, FlashInfer `6023d031be8e`.
  **KK beta 20261016.2:** vLLM `6d66eed35b0a`, FlashInfer `79819b112f8b`.
  Canonical currently includes additional FlashInfer changes beyond this beta,
  including the dynamic-MoE and BF16-projection fixes. Do not infer source
  freshness from the beta label. Registry inspection shows those exact tags
  are AMD64; use a verified ARM64 build/source composition for GB10. The release
  scope is native GPU/cache-contract testing, not a validated DS41 TP4 speedup.
  [Release listings](https://github.com/local-inference-lab/blackwell-llm-docker/releases).
- **eugr B12x latest:** ARM64 image pushed October 15, digest
  `sha256:03a956544e9f9b4b7ba91690469fbe7848bdbef29a7d2e0f5788368467bb3595`.
  Its maintained source build uses KK vLLM plus LIL FlashInfer main. The image
  config does not expose exact source revisions; pin and inspect them before
  adoption. Its published DS41 recipe uses K7, two sequences and MXFP8 LM head,
  so it is not an apples-to-apples replacement for our K5/16-sequence/BF16-head
  recipe. [Build guidance](https://github.com/eugr/spark-vllm-docker).
- **SparkRing 2026.10.4:** the prior image plus GLM DCP/TP6 and dashboard changes;
  DS41 installation was checked, but no serving speed was measured for this
  release. It does not by itself overturn our October 14 comparison.
  [Release](https://github.com/FujitsuPolycom/sparkring/releases/tag/2026.10.4).

Keep the complete KK compressor fix, selected plugins and activation guards,
2350 MHz cap, original precision, and fabric ownership in every candidate.
New A4 prefill, CSF, LMCache or head quantization must be separate experiments.
The large recent A16 MXFP8 prefill gain in FlashInfer #15 was measured on GLM
KDA projections; it is not evidence of the same gain for this DS41 recipe.

The full standby execution plan is in the operating repository at
`results/20261017-runtime-plan/PLAN.md`. No GPU/runtime/transport upgrade from
that plan has been applied.
