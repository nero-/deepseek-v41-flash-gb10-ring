# Selected local vLLM plugins

Only the two plugins used by the live deployment are kept here. The local
entry-point metadata matches its root-owned installed bundle. The runtime also
selects the inherited `b12x_loader` and `sparkring_status` plugins.
[Deployed hashes](../../results/deployment.json).

## Adaptive prefill budget

`dsv41_adaptive_prefill` retains the normal mixed scheduler and its 8K allocation
ceiling. With at least four runnable decoders contending with prefill, it uses
a 4K quantum for that scheduling step, restoring the configured budget afterward,
including on exceptions. Unloaded prefill and decode-only steps retain the
configured budget. The plugin refuses combination with native compute sharing.

## Guarded query-row indexer sharding

`dsv41_indexer_tp` distributes eligible candidate-free long-prefill scoring
across the four TP ranks, gathering int32 top-k selections. The selected path
requires at least 128 query rows and 8,192 compressed positions. Decode,
candidate passes, projections and short contexts keep their original paths.

Each geometry must match the original local raw scores and selected score
multiset exactly on all ranks. Different legal keys tied at the cutoff are
allowed; a mismatch restores the original output and disables that geometry.
These finite guards are not a proof for every input.

With `DSV41_INDEXER_ARM_ON_REQUEST=1`, each fresh worker remains disabled through
complete startup and graph capture, then arms only after real requests arrive.
Synthetic warmup requests cannot activate it. The CPU regression check is:

```bash
python3 bench/indexer-startup-check.py
```

The plugins preserve the selected checkpoint bytes, target precision and full vocabulary.
Installing files alone does not enable plugins; the selected configuration's
`VLLM_PLUGINS` and root-owned manifest control activation. Do not edit installed
plugin files in place while serving. Historical unselected plugins are archived.
