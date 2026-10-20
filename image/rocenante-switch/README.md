# Switched RoCEnante two-shot layer

**Qualified and selected on all four nodes.** The switch
network is installed. Follow the [qualification report](../../results/20261019-switch-migration/REPORT.md)
and [current operations](../../OPERATIONS.md#switched-fabric).

This layer keeps the October 15 vLLM/FlashInfer model kernels and stages
four changed files: the vLLM RoCEnante adapter plus the three-file upstream
two-shot buffer-lifetime fix. It does not change checkpoint precision, KV,
speculation code, target head, local performance plugins or sampling.
The serving profile's draft width and scheduling settings are tuned separately;
read the current deployment manifest and campaign report for the selected values.

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

| Setting | Adapter default | Selected TP4 setting |
|---|---|---|
| `DS41_ROCE_PIPE_BYTES` | `0` (disabled) | `128MiB` |
| `DS41_ROCE_PIPE_THRESHOLD` | `1MiB` at TP4; `2MiB` at TP2 | `512KiB` |

These are **local settings**, not upstream vLLM flags. All ranks vote on the
same one-shot, gather, pipe-capacity and pipe-threshold tuple before constructing
the transport. It calls `AllReduce(...)` directly with the Gloo exchange group;
the provider's compatibility `from_exchange_group(...)` silently discards pipe
settings and must not be used here. Invalid or inconsistent settings reject the backend collectively.
Enabling two-shot requires the fixed proxy ABI 8.

The preparation callback primes FP16, BF16 and FP32 two-shot calls as well as
the existing small all-reduces and gather before graph capture. Runtime logs
announce the first real one-shot and two-shot dispatch separately. Inputs
outside the runtime's eligibility/capacity retain NCCL fallback.

At TP4 a 128 MiB pipe uses approximately 384 MiB additional pinned region per
runtime, before other buffers and communicators. The initial 64 MiB proposal
would miss an 8192 × 5120 BF16 hidden-state reduction (80 MiB). Measure actual
total memory; do not automatically subtract 1 GiB of KV or add a runtime stop.

The base provider already contains [PR #10](https://github.com/local-inference-lab/flashinfer/pull/10)
two-shot, [#11](https://github.com/local-inference-lab/flashinfer/pull/11) native
packaging interfaces, and [#12](https://github.com/local-inference-lab/flashinfer/pull/12)
variable-length gathering. Only the two-shot path is newly activated here.
Variable-length allocation remains zero and native packaging is not used.
The [ABI-8 correction](https://github.com/local-inference-lab/flashinfer/commit/f3bbd1ce79cb9a62afb88b367580b0583db167ee)
is taken as a complete three-file change. Its transport diff against our pinned
base contains only those three files even though the overall branches diverge.

## Image composition

`Dockerfile` builds on the exact qualified October 17 local image. Create a
fresh context, stage sources into its `staged/` directory, and copy
`Dockerfile`, `install.py`, `ds41_switch_guard.py` and `entrypoint.py` into it.
Pass `--build-arg SELECTED_IMAGE=<verified-local-parent-tag>`; the parent ID is
`sha256:a182696cb59fad1352ca17aae13c248e276d5cb7b7811f0fc8ead1cde4516221`.
The built candidate ID is
`sha256:9f26f0b3718ccca889cfd93cb72e2165b6d4c11dd9dc93fe65f585883537f2db`.

The installer verifies the parent, preserves its receipts, checks all four
source preimages, updates package RECORDs, and creates a distinct composition
and toolchain seal. Framework/native math libraries are unchanged. It removes
the old SparkRing import hook; the old provider files remain inert history.
The new source-verified import hook selects the base FlashInfer provider in
spawned workers under `DS41_ROCE_TRANSPORT=flashinfer-abi8-switched`. It rejects
old peer/opposite-path maps and switchless settings. The entrypoint requires
that hook for serving and retains full toolchain verification.

Build receipts record `serving_qualified=false` because they are created before
GPU tests. Serving qualification is recorded externally against the immutable
image ID; do not edit a built image's receipt to claim a successful deployment.

## Qualification

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

The completed campaign passed 58 collective cases per rank, 23 pinned upstream
GPU tests per rank and seven CPU adapter contract tests. Serving qualification
includes the full 25-cell LIL grid, functional checks, uncached 961,724-token
retrieval and mixed image/decode requests. Rebuilding this recipe on another
fleet still requires its own fabric, collective and serving qualification.

`tests/switched_collectives.py` runs eager/graph checks over three floating
point types, all-reduce sizes through 128 MiB (including 80 MiB), two gather
types through 16 MiB per-rank shards, and oversized NCCL fallback. Set
`TEST_PIPE_BYTES=134217728` for the candidate; zero selects the baseline path.
It requires one process per node, a stopped fleet, matching rank/bootstrap/RDMA
environment, the verified image's toolchain environment, and `/receipts` for
outputs. The upstream two-shot GPU test module is separately pinned to the
ABI-8 fix commit, including random numerical, mixed-graph and fail-stop tests.

## Selected fabric environment

The model's math and precision remain those of the parent recipe. Serving
profile changes are recorded in the campaign. Switched transport uses:

```text
DS41_ROCE_TRANSPORT=flashinfer-abi8-switched
DS41_ROCE_PIPE_BYTES=128MiB
DS41_ROCE_PIPE_THRESHOLD=512KiB
B12X_ROCE_HCA=rocep1s0f1,roceP2p1s0f1
B12X_ROCE_GID_INDEX=3
NCCL_IB_HCA==rocep1s0f1:1,roceP2p1s0f1:1
NCCL_IB_GID_INDEX=3
NCCL_CROSS_NIC=0
NCCL_SOCKET_IFNAME=enp1s0f1np1
GLOO_SOCKET_IFNAME=enp1s0f1np1
VLLM_ROCE_ALLREDUCE_MAX_SIZE=2097152
VLLM_ROCE_ALLGATHER_MAX_SIZE=16777216
```

The doubled `=` in the NCCL_IB_HCA line is intentional: the value begins with
`=` to request exact HCA matches. Bootstrap uses `--master-addr 10.10.10.1`;
`VLLM_HOST_IP` is each rank's rail-A address from OPERATIONS. Retain the
qualified four-channel patched-NCCL fallback, but remove forced `NCCL_ALGO`,
`NCCL_SWITCHLESS_RING_ONLY`, `B12X_ROCE_PEER_HCA_MAP`,
`B12X_ROCE_OPPOSITE_PATHS`, and old `SPARKRING_TRANSPORT_*` profile settings.

The candidate has its own native/JIT cache paths and RoCE proxy cache. To keep
the comparison's math choices stable, copy only each rank's validated schema-22
`b12x_compile_cache_dir/preparation/*.json` selection records from its baseline
cache into the new cache **with all workers stopped**. Preserve namespace,
identity and program-hash validation; do not rewrite identities or force stale
records to load. Executable artifacts and transport caches are not copied.
The initial trial reused 1,878 decisions during model preparation. Later
batch/draft-shape trials retuned affected shapes normally; their cache reuse
and compilation counts differ.
