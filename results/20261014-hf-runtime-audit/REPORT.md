# October 12 upstream inference changes: preserved DS41 audit

2026-10-14. The user authorized stopping GLM, auditing the recent Hugging Face
reference changes, and testing the preserved DeepSeek deployment. GLM was
stopped successfully on all four ranks through its saved controller. Its
qualified Weightless alpha-2 selection, checkpoint and images were preserved.

## Source decision

**No runtime patch is indicated by these two changes.** The selected B12x
implementation already avoids the cache-selection defect and already quantizes
the attention output before WO-A. Adding another quantization operation or
copying the reference model wholesale would not implement a missing operation.

The comparison is our checkpoint revision `dba1be0a40aa45a94ad051997016db3960a90277`
against upstream `5254448103b6254fc646dacbca1cbbf20e9216c1`. The actual diff is
saved in `upstream.diff`, with both source revisions under `upstream/`.

### Indexer cache selection

Upstream moved `shared_attn.index_k = self.k_cache` outside the condition that
requires a newly completed compression group. Previously an incomplete group
could leave the decoder's cache in that shared slot for the encoder to read.
The bounded source reproduction exercises that exact old/new publication block
with `latent=None` and confirms the stale/fixed selections.

Our native `DeepseekV4Indexer` stores a source-bound `k_cache` object. KV sources
construct their own index cache; reindex consumers bind to their declared source.
The scoring binding reads `self.indexer.k_cache.kv_cache` directly and metadata
is selected with that object's prefix. It does not use `shared_attn.index_k`.
Therefore the specific shared-slot defect is absent from this implementation.
This is separate from the KK #926/#943 compressor ring-state correction already
retained in our image; neither fix should be substituted for the other.

### Activation quantization before WO-A

Upstream added `act_quant(...)` between inverse RoPE and the WO-A einsum in
both ordinary and decoder paths. That reference operation quantizes and
dequantizes activations in place before the BF16 projection.

Our attention `_o_proj` calls the prepared native `wo_projection.run_inv_rope`.
Its installed implementation calls `quantize_a_inv_rope` and then feeds the
resulting FP8 values/scales into `ordinary_a.run`. Both dispatch variants for
the following WO-B projection share that quantized WO-A input. The native CuTe
quantizer has 32-value groups, power-of-two UE8M0 scaling and E4M3 payloads.
The projection keeps the checkpoint's block32 FP8 weights rather than using
the reference script's dequantized BF16 weights.

This establishes that the missing-quantization operation is already present;
it does **not** establish bitwise equality between fused B12x and unfused
TileLang arithmetic (including intermediate rounding and tiny-value handling).
No new numerical-equivalence claim or general quality score is made.

### Evidence and scope

- `fleet-source-hashes.json`: matching attention/WO implementation hashes across
  all four actual selected containers.
- `source-manifest.json`: SHA-256 manifest of copied runtime and upstream source.
- `audit_source.py` / `source-audit.json`: passing old/new cache-publication
  reproduction, native cache-binding inspection, and execution of the installed
  WO orchestration with recording stand-ins for both WO-B dispatch paths.
- Local indexer startup guard regression passed separately.
- These source checks are not standalone GPU numerical tests.

Serving validation is recorded by `validate_serving.py` in
`validation-status.json`, the functional log, matched LIL output, fresh retrieval,
long-answer consistency output and final serving receipt. See `summary.json`
for completed results once generated. No image/checkpoint/plugin changes are
part of this audit, and there is no patched-vs-unpatched speed claim.

Sources: [HF cache fix](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/discussions/12),
[HF October 12 source](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/5254448103b6254fc646dacbca1cbbf20e9216c1/inference/model.py),
[selected deployment](../deployment.json).

## Completed serving results

All seven functional checks passed (counting, arithmetic, code, automatic/forced
tools, image input and thinking). Fresh retrieval passed with 125,241 actual
prompt tokens, zero prefix-cache reuse and 32.36 s to first content.

Unchanged LIL v0.6.2, thinking off, temperature 1/top_p 1/top_k -1, 30-second
sustained cells and a 2048-token output ceiling:

| Context label | C1 | C8 first / repeat | C16 | Cold prefill |
| --- | ---: | ---: | ---: | ---: |
| 8K | 60.54 | 163.99 / 169.95 | 227.99 | 4,255 |
| 128K | 69.16 | 153.52 / 153.28 | 217.63 | 4,129 |

All rates are tokens/s; C8/C16 decode rates are aggregate. The cold prefill
requests contained 8,193 and 129,015 actual tokens. All eight timed cells had
zero errors. C8 is still approximately 5–8% below the October 11 restored
control (179.31 / 165.67). Both draft acceptance and verification rate were
lower; this does not establish a cause. No runtime change occurred, and no
performance gain or universally unchanged speed is claimed. Other cells are
within or above the historical range; the 128K C1 sample had higher acceptance.

Eight 2048-token decode/prefill probes completed, four with thinking off and
four on. Final-512-token coarsened KL was 0.01837 and top-token agreement
96.875%, compared with retained September 29 values 0.0154 / 97.49%. Different
generated continuations and finite top-20 distributions limit that comparison;
there is no obvious late-answer drift resurgence in this screen. Raw responses
are retained in consistency-raw.tar and the original remote results directory.

All four GPUs sampled at 2327–2333 MHz under load, with clock and mesh services
active. Final source/image/configuration verification is in final-audit.json.
DS41 remains available at http://192.168.50.219:8015/v1. GLM remains stopped.
The checkpoint, selected image IDs, plugins and root-owned selection are unchanged.
