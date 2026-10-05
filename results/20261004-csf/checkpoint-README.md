---
base_model: deepseek-ai/DeepSeek-V4.1-Flash
base_model_relation: quantized
license: mit
pipeline_tag: image-text-to-text
tags:
  - mxfp4
  - fp8
  - multimodal
  - lossless-compression
  - csf
---

# DeepSeek-V4.1-Flash-lossless-CSF

A lossless MXFP4-CSF container of [`deepseek-ai/DeepSeek-V4.1-Flash`](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash) at revision `dba1be0a40aa45a94ad051997016db3960a90277`.

CSF stores the routed-expert block-scale planes in a compressed form. Nothing else changes: FP4 weight nibbles, every other tensor, the tensor names, dtypes, shapes and the source metadata are all byte-identical. Decoding is integer arithmetic on bytes, with no requantization or fitting. The original safetensors shards can be restored bit-exactly.

```
Routed experts (40 layers x 384) - MXFP4 (E2M1, UE8M0 scale per 32)
Engram tables, attention, shared experts - FP8 E4M3 with UE8M0 scales
Vision encoder, aligner, MTP (including its routed experts) - source format

Routed-expert block scales - lossless MXFP4-CSF (row-base-offset1-u24-exceptions/1)
```

## Sizes

- Weight files: 510.30 GB in the source, 495.63 GB here (14.67 GB saved).
- Compressed scales: 46,080 matrices (UE8M0 block scales of the 40 x 384 x 3 main-layer routed-expert projections): 16.99 GB -> 2.31 GB (13.6%).

## Provenance

- Source: `deepseek-ai/DeepSeek-V4.1-Flash` revision `dba1be0a40aa45a94ad051997016db3960a90277`, 48 index-referenced safetensors shards. During export, each source shard's SHA-256 was checked against its Hugging Face LFS hash.
- Built with trellis-quant `trellis_quant.lossless_scale_checkpoint` (commit `60feca330087`, family `deepseek_v41`).
- `verification.json`: every original shard was rebuilt from this container, and both the rebuilt and the stored files matched their SHA-256 (46,080 scale matrices, 48 shards, passed).
- Hub `main` (2cba9e42) adds `chat_template.jinja` and is otherwise byte-identical to dba1be0a. Every tensor and config file matches.
- `tensors/` is byte-identical (all 48 compressed-shard SHA-256 values) to `local-inference-lab/DeepSeek-V4.1-Flash-MXFP4-CSF` revision 872da235. This build adds the source LICENSE to `metadata/` and records the source revision.

## Layout

`lil-mxfp4-csf-checkpoint/1`, codec `row-base-offset1-u24-exceptions/1`:

- `tensors/` - the source shard names; each routed-expert scale `<name>` is stored as `<name>.mxfp4_csf_fixed` (uint8) plus `<name>.mxfp4_csf_exceptions` (uint32)
- `metadata/` - byte copies of the source's config, tokenizer, index, README and LICENSE
- `manifest.json`, `build-contract.json`, `receipts/` (per-shard source headers and hashes), `verification.json`, `LICENSE`

There is no top-level `model.safetensors.index.json`, so a plain safetensors loader will not open this directory by mistake.

## Serving

Use vLLM with the MXFP4-CSF reader: `--quantization mxfp4_csf --load-format mxfp4_csf`. Point vLLM at a serving directory that holds the files of `metadata/`, with `config.json`'s `quantization_config` replaced by:

```json
{
  "...": "every key of metadata/config.json quantization_config",
  "quant_method": "mxfp4_csf",
  "format_version": 1,
  "checkpoint_root": "/path/to/this/checkpoint"
}
```

The weights are read from `checkpoint_root`; the serving directory holds only metadata.

## Verify or restore

```bash
PYTHONPATH=/path/to/trellis-quant python3 -m trellis_quant.lossless_scale_checkpoint verify \
  --checkpoint /path/to/this/checkpoint --workers 16
PYTHONPATH=/path/to/trellis-quant python3 -m trellis_quant.lossless_scale_checkpoint restore \
  --checkpoint /path/to/this/checkpoint --destination /path/to/fresh/dir --workers 16
```

`verify` rebuilds every original shard and compares SHA-256 values. `restore` writes the original shards and metadata files into a fresh directory, checking every hash before a file is published. The result is an ordinary copy of the source checkpoint.

## License

Same license as the source; `LICENSE` is copied unchanged from `deepseek-ai/DeepSeek-V4.1-Flash`.
