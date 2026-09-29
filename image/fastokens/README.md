# Fastokens on the corrected SparkRing runtime

This layer adds only `fastokens==0.3.2` to the existing KK926-corrected images.
The pinned aarch64 wheel and its SHA256 are in `manifest.json`. Installation
uses `pip --no-index --no-deps`; vLLM, CUDA, NCCL, B12x, RoCEnante and local
performance plugins remain unchanged. An installed-file inventory is saved at
`/opt/fastokens/installed.json`, and the original SparkRing toolchain verifier
is run independently on every image.

`scripts/fastokens-serving.py` records the current selection, builds the layer
on each node, measures the current backend, and switches through the normal
controller to the derived images with `VLLM_USE_FASTOKENS=1`. The prior
KK926-corrected containers are retained as `ds41-before-fastokens-r0` through
`r3`. The earlier pre-KK926 rollback containers are untouched.

The campaign's actions are `build`, `baseline`, `switch`, `candidate`, then
`select` after reviewing the evidence and recording `decision.json`. Use
`rollback` only when needed. `scripts/fastokens-c8-repeat.py` records the
additional C8 check without changing serving settings.
Startup failure restores the captured corrected HF deployment automatically.
Candidate benchmark failures preserve evidence for diagnosis; use `rollback`
to restore the previous deployment if the candidate is rejected. These are
fleet-specific campaign scripts, not a general installer or an idempotent
command to rerun after selection. Host launch receipts remain local.
