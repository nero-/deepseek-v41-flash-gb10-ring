# Compact MXFP4 MoE candidate

**Rejected for serving performance after two matched screens.** Numerical and
functional checks passed, but the composed image with fresh tuning was slower
at C1 and showed no consistent long-prefill gain. C16 overlapped the restored
control's variation, so its slowdown is not isolated. The retained switched
image remains the preferred deployment.
[Trial results and scope](../../results/20261019-switch-migration/REPORT.md#compact-mxfp4-moe-prequalification).
Candidate image: `sha256:452a5d89b8de34d3a166fc344bc9aef2058f1c6d2f67af8ce355ba2a77d28cd6`,
built October 20 at 10:54:30 UTC on rank zero.

The October 20 native Torch profiles identified materialized W4A8 MoE kernels
as the main C16 cost. The candidate takes a coherent MoE implementation from
[FlashInfer `a6b096f7b34dd0266af382a4ece59682676f6ece`](https://github.com/local-inference-lab/flashinfer/commit/a6b096f7b34dd0266af382a4ece59682676f6ece),
published October 17. It targets the compact N64 geometry used by DS41 TP4:
2304 intermediate columns / 4 = 576.

Base image:
`sha256:9f26f0b3718ccca889cfd93cb72e2165b6d4c11dd9dc93fe65f585883537f2db`.
vLLM, checkpoint, attention, dense GEMM, mHC and the qualified ABI-8 RoCEnante
provider remain unchanged. This is a mixed-source backport, not a claim that
the entire FlashInfer distribution is at the candidate commit.

## Source boundary

`stage.py` compares the actual installed B12x source with the pinned upstream
snapshot. It stages the complete changed MoE implementation and required
quantization/cache dependencies: 29 changed or added files, including one README.
The installer checks every preimage and replacement hash, updates the package
RECORD and composition receipt, and creates a new toolchain seal.

Online CSF remains **off**. Its new API requires explicit scale-compression
constraints and scratch ownership; this candidate does not supply them.
Existing activation precision selection and checkpoint storage are retained.
The compact decode path and ordered FC2 route reduction change arithmetic
scheduling and need numerical tests; they are not assumed bitwise equivalent.

Preparation cache schema changes from 22 to 23. Use a fresh, isolated cache
namespace. Do not relabel or copy old tuning selections into the new schema.
Even unchanged attention/GEMM code may retune, so record the resulting decisions
and startup memory rather than attributing every change solely to MoE.

## Qualification before selection

1. Verify the new composition and all preserved transport/model files.
2. On a stopped fleet, run the pinned upstream compact-N64 numerical, live
   routing, padding, poisoned-scratch, graph-replay and ordered-reduction tests.
   Use the live 1017 geometry: target E=384, K=5120, N=576, top-k=6;
   draft E=128, top-k=3. Both use SiLU with clamp 10 and the W31 source
   layout. The earlier E=256 planning assumption came from the generic DS4
   benchmark helper and does not describe this checkpoint. Exercise actual
   decode/prefill row counts. Compare timings separately from correctness checks.
3. Keep vLLM/serving settings and clock policy matched. Measure startup memory
   against the approximately 118 GiB head budget, functional serving, cold
   retrieval and focused C1/C8/C16 LIL. Inspect which MoE tactics were selected.
4. Only promote after useful, repeated gains and long-context/mixed-load
   qualification. Otherwise restore the retained switched draft4 deployment.

The isolated large-M kernel improvement did not carry through to serving.
Do not promote this candidate from its kernel timings alone.
