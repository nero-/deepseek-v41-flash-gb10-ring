# Selected October 15 eugr / KK / FlashInfer runtime

This runtime was qualified and selected on October 17 for the existing
four-node ring. All four ranks use immutable image
`sha256:a182696cb59fad1352ca17aae13c248e276d5cb7b7811f0fc8ead1cde4516221`.
Read [qualification and performance](../../results/20261017-runtime-upgrade/REPORT.md)
and [deployment.json](../../results/deployment.json) for the actual selection.
The sealed composition's `serving_qualified:false` is its immutable build-time
state; the external qualification report records the subsequent passing tests.

The base is the immutable ARM64 eugr B12x nightly-20261015 image, with vLLM
`8244d1c44348ae8a5bbfc9f1b607021652283ed4` and FlashInfer
`91271757f7746f3dfb58f7c2aeb44a663389de9e`. FlashInfer supplies the B12x namespace;
there must be no separate installed B12x distribution or `b12x_loader` plugin.

The layer carries the official 1017 tool-turn encoder fix and retains the
qualified CUDA 13.4.2 / patched NCCL 2.32.3 toolchain. It retains the complete
switchless RoCEnante kernel/proxy/path-mapping bundle. The transport's provider
source guards now bind FlashInfer's B12x implementation; its preparation
function uses the new provider's explicit program cache. These changes passed CPU contracts, four-rank GPU/collective checks and model
qualification before selection.

The current local adaptive-prefill and guarded indexer plugins are mounted from
the existing root-owned bundle. Their real activation and numerical guards were verified. Use fresh native/JIT caches for this runtime. Keep the selected
1017 checkpoint, all rollback images and current configuration intact.

Build on spark-r0 after tagging the retained previous runtime image
`sha256:8e9d1bff575e6618ae354f557140aa43e9242d85762c83899fd7dfb898959f8f`
as `dsv41-runtime-toolchain-parent:20261017`. Do not substitute whichever image
happens to be selected later. The Dockerfile copies only the
qualified toolchain from that image, not the old framework packages. Its new
source/native receipts are sealed and checked independently. Build and trial
orchestration and private configurations are recorded under the workstation's
`Agent/Diagnostics/deepseek-v41-flash-ring/runtime-20261017` campaign.

Selected serving settings include official 1017 weights, explicit temperature 1
and top_p 1, target BF16 head, retained NVFP4 draft/Markov settings, attention
compute `auto` to preserve the previous policy, 1M context, 16 sequences and an
8192-token batch ceiling with adaptive 4096 contention steps. KV is explicitly
20 GiB per rank (`21474836480` bytes); it supersedes memory utilization 0.83.
The later [decode and KV campaign](https://github.com/nero-/deepseek-v41-flash-gb10-ring/blob/pre-tilelang-cleanup-20261024/results/20261017-decode-tuning/REPORT.md) retained the original
decode settings after screening alternatives and sized KV against the
118 GiB initial-loaded head target. There is no automatic runtime stop guard.
No SIRCL or new large-message transport is enabled by this image.

The subsequent [image-limit change](../../results/20261017-image-limit/REPORT.md)
sets `--limit-mm-per-prompt '{"image":999}'` on all four ranks. This removes
the old four-image request limit without rebuilding the image or changing KV,
image preprocessing, encoder batch budgets, or decode settings. The cap covers
images in all chat turns included in each request.
