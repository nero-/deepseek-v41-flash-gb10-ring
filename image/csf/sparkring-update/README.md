# Rejected candidate: SparkRing reliability layer

This layer applies the DeepSeek-relevant updates from SparkRing
`721db585e2050bef93518c6cced1dae57ff43af4` over the sealed CSF image.
It retains the original CSF source pins and native toolchain.

```bash
python3 image/csf/sparkring-update/prepare-context.py /path/to/new/update-context
docker tag YOUR_RECORDED_CSF_IMAGE_ID ds41:csf-base
docker build -t ds41:csf-sparkring-721db585 /path/to/new/update-context
docker run --rm ds41:csf-sparkring-721db585 verify
```

Use each node's parent identity from
`results/20261004-csf/images-before-sparkring-update.json`. The final images are
recorded in `results/20261004-csf/images.json`. The preparation command checks
out the exact public commit; `--source` accepts an existing clean checkout only
if it matches that commit. Source hashes accompany the generated context.

The six changed RoCEnante files add host-supervised peer waits and proxy ABI 5.
The old ABI-4 profiles remain available inside the image; the final profile is
`tp2-rocenante-adaptive-prepared-csf-peerwait`. Its manifest keeps the CSF B12x
preimages and records every replacement. All four ranks must use the same
profile and ABI. A live but delayed peer is waited for; stopped, unreachable or
inconsistent peers, or the configured timeout, stop the collective. This is a
reliability change, not a claim of higher collective throughput.

The named/required tool-call wrapper is copied unchanged from upstream. Both
its module and the serving-file substitution match upstream's exact SHA-256
pins. Enable it with `SPARKRING_TOOL_CHOICE_CONTRACT=1`. A token limit that
prevents a complete required call returns HTTP 400, or an equivalent SSE error;
other contract violations return 500. Complete calls and ordinary chat keep
existing behavior. Runtime-status advances to 0.3.3.

The candidate [lifecycle template](../lifecycle/optimized_vllm.py) checks NVIDIA
CDI refresh before starting model containers. It was prepared for promotion,
but was not installed: this candidate was rejected for performance. The refresh unit is enabled across reboots. Its installed GPU
selector and actual NVML access are checked on each host; final serving is
validated across a systemd daemon reload. This uses the existing NVIDIA toolkit
and preserves the persistent 2350 MHz clock cap.

The generated derived manifest and inventory record the additional layer;
the first CSF image's inventory is retained as parent provenance. Upstream
installer progress UI and unrelated model-profile changes are outside this
DeepSeek runtime overlay. Fixed, verified GID-3/HCA mappings remain in use.
