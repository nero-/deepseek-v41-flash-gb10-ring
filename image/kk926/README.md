# Compressor-state correction for the pinned SparkRing image

This is the complete [KK vLLM #926](https://github.com/local-inference-lab/vllm/pull/926)
fix at `7b935cb78a3f1f256b04006e82504a651685f72d`, also merged into beta by
[#943](https://github.com/local-inference-lab/vllm/pull/943). The earlier partial
beta port is insufficient: circular slot mapping **and** enabled ring writes
are required. The exact three-file upstream diff applied cleanly to our image.

The parent is the pinned SparkRing image in `manifest.json`, built on
`eugr/spark-vllm-b12x:nightly-20260924`. We do not replace the SparkRing stack
with the generic KK beta image. CUDA, NCCL, B12x, RoCEnante, checkpoints and
local performance plugins are unchanged.

`install.py` rejects unexpected parent source and receipt hashes. It archives
the original files and receipts, installs the correction, regenerates the vLLM
distribution RECORD, and updates the composition receipt and its toolchain
parent hash. It invokes the original external-base verifier; the build script
also runs the full toolchain verifier. No verification bypass is used.
The derived receipt deliberately says `serving_qualified: false`: runtime
qualification belongs to the separately recorded fleet experiment, not the
image construction step.

Fleet scripts are intentionally pinned to the September 29 experiment:

1. `scripts/kk926-build.py` captures the existing deployment, builds on every
   rank without network/package updates, and verifies each derived image.
2. `scripts/kk926-trial.py baseline-screen` records matched pre-fix throughput.
3. Download pure Python test dependencies into `/tmp/kk926-wheels` with
   `python3 -m pip download --only-binary=:all: --dest /tmp/kk926-wheels pytest==9.1.1 pluggy==1.6.0 iniconfig==2.3.0 packaging==26.3 pygments==2.21.0`.
4. `scripts/kk926-trial.py gpu-tests` stops the model, reproduces the old slot
   failure, and runs the corrected probe and 17 upstream tests on every GPU.
5. `scripts/kk926-trial.py start` launches isolated trial containers from the
   recorded deployment. GPU-test or startup failure restores the old service.
6. `scripts/kk926-qualify.py` saves function, distribution-consistency,
   throughput, long-prefill, mixed-load and million-token retrieval evidence.
7. Review results and record `promotion-decision.json` before running
   `scripts/kk926-promote.py`. Promotion retains the old stopped containers,
   image and root-owned configuration backup and rolls back on startup or
   functional failure. Do not rerun these historical scripts blindly against
   an already promoted fleet: their preconditions intentionally reject it.

LMCache #106 is not included: this deployment has no active LMCache connector.
Native prefix caching and the disk-backed Engram implementation are separate.

Upstream source and tests retain their Apache-2.0 notices. File hashes and
upstream revision are in `manifest.json`; the unchanged tests are in
`bench/upstream/kk926`.
