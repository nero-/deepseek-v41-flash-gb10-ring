# Local DeepSeek optimization experiments

Each plugin is explicitly selected through `VLLM_PLUGINS`; installing this
directory does not enable every experiment. The selected deployment installs
`dsv41_adaptive_prefill` and `dsv41_indexer_tp`, with restricted entry-point
metadata and a root-owned SHA-256 manifest. The other plugins remain unselected experiments.

The follow-up prototypes `dsv41_context_cost`, `dsv41_timed_prefill`,
`dsv41_context_indexer`, `dsv41_engram_readahead`, `dsv41_owned_mhc`, and
`dsv41_markov_shortlist` are staged only by `scripts/research-trial.py`, which
creates isolated entry-point metadata and snapshots the actual source used.
They are not added to the selected plugin manifest. See
[the research record](../../RESEARCH-20260928.md) for qualification and outcomes.

## Top-20 draft proposals (`dsv41_draft_topk`)

Ports the Qwen proposal-filter strategy to native DSpark's final-logit sampling
boundary. Filters the full base-plus-Markov logits before both sampling and
verification caching; target logits and vocabulary remain unchanged. This is
not the Qwen-only native `dspark_draft_topk` Markov projection optimization and
does not save full-head computation. The GPU tests in `bench/draft_topk_tests`
reuse the Qwen rejection-distribution oracle with five draft steps, plus
129,280-column cache and CUDA-graph checks. Its serving screen showed no clear gain and scored 71/75; top-20 is not selected.
See [the transfer review](../../QWEN-TRANSFER.md) for adaptive HC and other changes.

## Long-prefill indexer TP (`dsv41_indexer_tp`)

**Original selection guard rejected:** 0 of 12 real-input cases passed exact
selection checks. Fallback functional checks passed 7/7 and the 122,260-token
needle passed. The throughput screen was interrupted once rejection was clear;
no optimization speedup is claimed for that attempt. Follow-up score/value
checks distinguish tied selected keys from arithmetic errors. The explicit
`DSV41_QUERY_VALUE_GUARD=1` mode requires exact raw scores and exact selected
score multisets, with valid distinct indices, against each rank's own original
computation. It permits different keys tied at the cutoff, not a score tolerance.
See the research record for the serving results. `DSV41_INDEXER_ARM_ON_REQUEST=1`
adds restart-safe activation through the pinned runner's real-request branch;
the selected mode requires the complete worker warmup to finish before
observing a real request. It passed 24/24 numerical geometry guards, seven short
and seven ~94K functional probes, uncached million-token retrieval, and mixed-load
retrieval. The legacy smoke repeatability check still fails as on the baseline.

Transfers the query-row partition idea from the historical SGLang
`spark_prefill_dense.py` adapter. On candidate-free native MXFP4 indexer passes
with at least 128 rows in the selected profile (256 in the earlier trials) and 8,192
compressed positions, each rank scores one
quarter of the rows. Only the resulting int32 top-k selections are gathered.
Q/K projection and quantization, candidate source/consumer passes, short
contexts, decode and residual sequence parallelism remain unchanged.

The existing prepared DSA plan supports a smaller live row count, so this
experiment reuses its kernels and scratch allocation. For each layer/row-count/
context-width bucket, the first eligible real request also runs the original
full scorer. The original mode requires identical selected indices; the explicit value-guard
mode requires each rank's local scores and selected score multiset to equal its
own full-compute reference. An all-rank MIN must pass before retaining a case.
A mismatch restores the original output and disables that case. Finite input
checks are not an exhaustive proof; alternative legal tie selections can change
the model output.

`installer_variant.py engram-indexer-tp` removes the activation sentinel before
startup and creates it on all ranks only after API readiness. An all-rank
activation handshake prevents staggered file creation from enabling only some
ranks. This keeps empty startup inputs from satisfying the real-input guard.
That older file-armed experiment must restart through its controller. The new
request-armed mode does not depend on a persistent sentinel: every fresh worker
stays disabled through startup and graph capture, then arms after its runner
receives real requests after the entire worker warmup method returns.
Synthetic sampler warmups also call the runner's request method, so that method
alone is insufficient as a startup boundary. All ranks still synchronize activation.

## Adaptive token quantum (`dsv41_adaptive_prefill`)

The selected local plugin retains the ordinary mixed scheduler and its 8K
allocation capacity. When at least four runnable decoders compete with local
prefill, it temporarily limits that scheduling step to 4K tokens. It restores
the configured budget after constructing the step, including on exceptions.
It refuses combination with native compute sharing, so a token-budget change
is measured independently of time-share policy. Decode-only and unloaded
prefill steps retain the configured budget. Its three mixed rounds approximately halved worst stream stalls, with a modest
increase in fresh-request first-token times; see RESULTS.md.

## Decode projection (`dsv41_decode_split`)

**Rejected in its current form:** the GPU trial reached readiness and fallback
passed functional 7/7, but none of 43 projections passed its exactness guard.
The split remains disabled; no serving speedup is attributed to this plugin.

`dsv41_decode_split` transfers the bounded strategy from the historical SGLang
adapter's `replicated_split.py` to the pinned native vLLM/B12x implementation.
It is an experiment, not part of the selected serving configuration.

The selected layer is `fused_wqa_wkv`. For up to 96 activation rows, each of
four ranks computes a contiguous group of 128-column tiles and all-gathers
them in their original order. The 1,792-column projection uses 512/512/384/384
columns, padding each local weight to 512 columns and removing padding after
the gather. Equal padded geometries keep native B12x's distributed preparation
boundaries aligned across ranks. The zero-weight padding is excluded from
exactness comparisons and the final output. Larger
batches use the original full projection.
Both weight representations use the checkpoint's block32 FP8 bytes and scales;
there is no new target quantization. Full weights remain available for prefill
and fallback, so this is not a weight-memory-saving optimization.

Each layer checks the sliced output against the corresponding full output on
the first small eager input plus seeded random inputs of 1, 6 and 16 rows. A
distributed MIN requires all ranks to agree bit for bit. A mismatch disables
the split for that layer. These finite checks are a qualification guard, not a
proof for every possible activation. Graph capture refuses an undecided path.

The local method declares B12x preparation requests for both projection sizes
and accounts for their workspaces. Its custom op keeps dynamic row dispatch
inside the eager/CUDA-graph execution boundary. Plugin discovery uses the
standard `vllm.general_plugins` entry point, preserving `b12x_loader` and
`sparkring_status`. It is mounted separately; upstream sources and frozen
installer receipts are unchanged.

Pinned runtime image: `sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf`.
Relevant upstream implementation: `vllm/models/deepseek_v4_1/attention.py` and
`b12x_layers.py`. SGLang reference: `/opt/dsv41/adapter/replicated_split.py` in
the retired `dsv41-4x-spark:canary-roce-ring` image.

Run using `bench/installer_variant.py engram-qkv-split` on the head after
staging this directory at the documented bind source on all four nodes.
Inspect the per-layer `bit-exact=ON/OFF` messages before interpreting results.
Serving, correctness and matched performance tests are required before use.
