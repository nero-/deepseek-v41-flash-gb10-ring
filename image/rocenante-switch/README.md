# Switched RoCEnante two-shot candidate

**Staged source only; not built, installed or GPU-qualified.** The fleet remains
stopped for CRS812 recabling. Follow the
[migration plan](../../results/20261019-switch-migration/PLAN.md) for topology,
host cleanup and qualification.

This candidate keeps the October 15 vLLM/FlashInfer model kernels and stages
four changed files: the vLLM RoCEnante adapter plus the three-file upstream
two-shot buffer-lifetime fix. It does not change checkpoint precision, KV,
speculation, target head, local performance plugins or sampling.

`stage.py` downloads exact source revisions, verifies hardcoded SHA-256
preimages, and writes replacement sources, a unified patch and a manifest to
a **new** directory. It performs no SSH, Docker, installation or serving action:

```bash
python3 image/rocenante-switch/stage.py --output /absolute/new/staging-directory
python3 image/rocenante-switch/test_adapter.py /absolute/new/staging-directory
```

The staged files are relative to Python's site-packages directory. They are
inputs for a new image composition, not instructions to edit running containers.
Every input must match the manifest's `before` hash during image construction.

## Integration behavior

Two local experimental settings are added to this candidate's adapter:

| Setting | Default | First proposed TP4 trial |
|---|---|---|
| `DS41_ROCE_PIPE_BYTES` | `0` (disabled) | `64MiB` |
| `DS41_ROCE_PIPE_THRESHOLD` | `1MiB` at TP4; `2MiB` at TP2 | `1MiB` |

These are **local settings**, not upstream vLLM flags. All ranks vote on the
same one-shot, gather, pipe-capacity and pipe-threshold tuple before constructing
the transport. Invalid or inconsistent settings reject the backend collectively.
Enabling two-shot requires the fixed proxy ABI 8.

The preparation callback primes FP16, BF16 and FP32 two-shot calls as well as
the existing small all-reduces and gather before graph capture. Runtime logs
announce the first real one-shot and two-shot dispatch separately. Inputs
outside the runtime's eligibility/capacity retain NCCL fallback.

At TP4 a 64 MiB pipe uses approximately 192 MiB additional pinned region per
runtime, before other buffers and communicators. Measure actual total memory;
do not automatically subtract 1 GiB of KV or add a runtime memory stop.

The base provider already contains [PR #10](https://github.com/local-inference-lab/flashinfer/pull/10)
two-shot, [#11](https://github.com/local-inference-lab/flashinfer/pull/11) native
packaging interfaces, and [#12](https://github.com/local-inference-lab/flashinfer/pull/12)
variable-length gathering. Only the two-shot path is newly activated here.
Variable-length allocation remains zero and native packaging is not used.
The [ABI-8 correction](https://github.com/local-inference-lab/flashinfer/commit/f3bbd1ce79cb9a62afb88b367580b0583db167ee)
is taken as a complete three-file change. Its transport diff against our pinned
base contains only those three files even though the overall branches diverge.

## Remaining build and validation

The old SparkRing import overlay **must not shadow this provider**. Create a
new immutable image with an explicit transport selection, updated package
RECORDs and composition/toolchain receipts. Preserve the selected 1017 encoder,
parser and plugin corrections. Do not unset a required profile to evade the
current verifier. Inspect actual module origins in spawned compilation workers.

Use fresh proxy/CuTe caches. Verify ABI 8 in Python and the native proxy, then
run upstream two-shot, one-shot, gather, graph replay and fail-stop tests on
four nodes. Include repeated back-to-back large reductions to exercise the
send-buffer lifetime correction. Verify the numerical relationship to the
retained one-shot path and NCCL before measuring speed.

The newer proxy reads `B12X_ROCE_TRAFFIC_CLASS` and then `NCCL_IB_TC`, unlike
the old overlay's hardcoded class 0. Choose matching host/switch QoS settings
after inspecting the connected CRS812; source staging does not configure them.

Seven workstation CPU contract tests passed on the staged adapter: defaults,
invalid sizes, old-ABI refusal, per-rank setting agreement, constructor
plumbing, avoiding construction after a failed vote, and priming all three
two-shot dtypes. They use controlled GPU/transport stubs and **do not establish
GPU correctness, graph safety, network performance or a model speedup**.

Only after fabric and collective qualification should this become a serving
candidate for matched LIL C1/C8/C16 and prefill comparisons.
