# Standby plan: DS41-1017 runtime and switched TP4 upgrades

> **October 19 HST / October 20 UTC:** the CRS812 has arrived and the fleet is
> stopped for recabling. Use the [updated switch plan](../20261019-switch-migration/PLAN.md).
> It incorporates the actual selected runtime, one-port breakout topology and
> current transport audit; this document remains historical research.

> **Scope update, October 17:** the user advanced the full eugr/KK/FlashInfer
> runtime comparison ahead of the switch. Its live selection and qualification
> are recorded in [the runtime campaign](../20261017-runtime-upgrade/REPORT.md)
> and [deployment.json](../deployment.json). This document preserves the earlier
> research plan; do not apply its small backports blindly to the newer provider.
> The switch topology and new large-message/two-shot collective experiment remain
> separate, pending work. Rebase those steps on the actual selected runtime.

Prepared 2026-10-17 UTC for the user's CRS812 arrival in about two days.
**Research and planning only. No cluster changes, image pulls, GPU tests, or
network changes were made by this work.** Resume this plan when the switch is
present and the user is ready for that maintenance window. It is not an
automatic timer or a background installation.

Finish the official 1017 checkpoint qualification and return serving to the
user first. The recommended next work is a small correctness/memory image
update, then a separate large-message collective experiment on the switched
fabric. A wholesale move to current FlashInfer/vLLM is a fallback or later
comparison, not a prerequisite for the small fixes.

The source evidence supports trying these changes. It does **not** establish a
DS41 TP4 speedup, or promise 200 C8 / 300 C16 on this fleet. Large-message
collectives matter on the current switchless ring too: reducing bytes sent and
overlapping transfers can help whenever those collectives occupy critical-path
time. The switch makes peer reachability simpler and removes the need for the
ring's opposite-peer forwarding. It does not by itself raise a software
all-reduce size limit or enable a new kernel.

## Start here when resuming

Read `../../README.md`, `../../OPERATIONS.md`, `../../results/deployment.json`,
`../../../SKILL.md`, and `../20261017-checkpoint-upgrade/` first. Those files were
being reconciled while this plan was written. Resolve the **actually promoted**
1017 image IDs and configuration hash from the completed campaign; do not treat
an earlier candidate image as selected merely because it appears in a log.

The previous runtime assessment is retained at
[evidence/ASSESSMENT.md](evidence/ASSESSMENT.md). Exact upstream commits and
release component pins are in [PINS.json](PINS.json). The locally observed old
source patterns, hashes, and line numbers are in
[evidence/selected-source-audit.json](evidence/selected-source-audit.json).
These are read-only evidence, not already-applied patches.

Fleet rank order: `spark-r0` / `192.168.50.219`, `spark-r1` /
`192.168.50.129`, `gx10-r1` / `192.168.50.192`, `gx10-r0` /
`192.168.50.23`; SSH user `nero`. API remains
`http://192.168.50.219:8015/v1`, alias `DeepSeek-V4.1-Flash-TP4`.

Preserve these invariants in every arm:

- Official `deepseek-ai/DeepSeek-V4.1-Flash-1017` revision
  `1bae0e1088993b9b82de08f59de5be5a34e42170`, original precision and full target
  vocabulary. No CSF, EXL3, A4 prefill, MXFP8 target head, or new checkpoint.
- TP4, native DSpark5 with selected adaptive/block/probabilistic settings,
  Engram projection TP, BF16 target-head weights, existing NVFP4 draft/Markov
  heads, HF tokenizer, max sequences 16, batched tokens 8192, 1M context and
  memory utilization 0.83 unless the final manifest proves a later selection.
- Complete KK #926/#943 compressor-state correction, official 1017 encoder
  tool-result boundary fix, and Python tool-parser #921. Rust frontend stays
  off. Preserve tools, vision and thinking behavior.
- `dsv41_adaptive_prefill` and `dsv41_indexer_tp`, including startup/request
  activation and numerical/fallback guards. The plugin hashes are authoritative
  in the selected manifest. Retain explicit plugin registration.
- Persistent GPU ceiling **0–2350 MHz**, no competing GLM/Qwen workload, and
  port 8015. No host kernel/driver/firmware upgrade in the same experiment.
- Preserve management LAN and NetworkManager ownership. Never replay netplan
  instructions from a generic playbook onto these GX10s.

The new checkpoint remains on all four nodes. Old checkpoint rollback copies
are on the two Sparks; the old GX10 weight shards were removed for space.
Image rollback for this campaign uses **1017 on both sides** and therefore
does not need an old-checkpoint transfer.

## Recommended candidates and dependencies

| Order | Candidate | Expected value | Change size and evidence |
|---|---|---|---|
| 1 | B12x synchronization fixes | Remove known race patterns; speed usually neutral | Five old Python/CuTe source files, eight insertion sites; exact old sites confirmed |
| 2 | vLLM #918 metadata ownership | Less retained CUDA-graph memory and startup margin | One serving Python file plus regression test; old ownership pattern confirmed |
| 3 | RoCEnante chunked two-shot | Faster large all-reduces, most plausibly prefill | C proxy/protocol, CUDA kernel, Python runtime/preparation and vLLM dispatch integration; separate transport build |
| 4 | Matched ARM64 KK/FlashInfer image | Maintained packaging and newer kernels/adapters | Broad rebuild; use only after explicit source/ABI/feature audit |
| Later | vLLM #911 arithmetic | Closer reference arithmetic | Separate quality/performance experiment; do not silently inherit changed defaults |

### 1. Synchronization backports onto the selected image

Keep standalone B12x for this candidate. Map upstream
`flashinfer/experimental/b12x/…` paths to the selected `b12x/…` paths; do not
replace whole modern files with hundreds of unrelated changes.

| Upstream change | Selected file and adaptation | Verification |
|---|---|---|
| [FlashInfer #25](https://github.com/local-inference-lab/flashinfer/pull/25), `bbda89255b955b0d23ff008f41f7d169702e741b` | `gemm/bf16_gemv/_prefill.py`: async-proxy fence after its one producer acquire, before TMA refill | BF16 projection replay under SM contention; selected DS41 projection shapes |
| [FlashInfer #24](https://github.com/local-inference-lab/flashinfer/pull/24), `0d7906847edffcf168f7277a9eaabbad418f902a` | `moe/_shared/kernels/dynamic.py`: all four acquire sites, including both up paths | Dynamic MoE contended replay and default atomic-output numerical tests |
| [FlashInfer #16](https://github.com/local-inference-lab/flashinfer/pull/16), `eff47835e107f558cc469284bc9f38aef5c8ac1c` | `_lib/dense_gemm.py`: insert the complete fence guarded by `load_path == "tma"` | Quantized and A16 plans, selected projection shapes, rebuilt SASS |
| [FlashInfer #19](https://github.com/local-inference-lab/flashinfer/pull/19), `3603bb317bb1f44f00e5c6aa26738d0aca6f0bcc` | `attention/dsa_indexer/fused_indexer.py` and `persistent_topk.py`: CTA synchronization before thread zero publishes grid-barrier arrival | Delayed-warp barrier test and DSA numerical tests, with local query sharding both bypassed and eligible |

**Important backport detail:** our dense GEMM has no fence at this mainloop
site. #16's published diff changes a guard around an existing fence. Applying
only that textual diff would fail or miss the fix. Add the entire intended
TMA-path fence after checking the old producer/consumer control flow.

The old source already imports `cutlass.cute`; no new FlashInfer packaging is
intrinsic to these synchronization operations. Build feasibility is high, but
compilation and SM121 execution remain untested. Verify that every thread
required by the added DSA CTA barrier reaches it; do not insert a barrier in a
divergent caller path. The local indexer plugin wraps the DSA API, so both the
underlying barrier and sharded request path must pass.

Build immutable per-rank descendants with guarded before-hashes, an explicit
patch manifest, updated package RECORD/toolchain receipts, and the parent
verifier. Keep original images and caches. Do not edit running containers.
Build the five-file correctness set as one candidate after checking each diff;
retain patch-level labels so a regression can be bisected without changing
other settings.

**Fresh compilation is mandatory.** Use a candidate-specific B12x, CuTe,
Triton, Inductor, vLLM and RoCEnante cache namespace. Inspect compilation
workers' imported source paths and hashes, not only the parent process. Retain
tuning-plan identity where compatible; distinguish a changed tactic from a
changed fence. Require representative native artifact/disassembly evidence
that the fence/barrier is present. Upstream #16 specifically caught a false
patched result caused by stale worker kernels.

The upstream race suite is stored under
`evidence/flashinfer/tests/experimental/b12x/race/`. It uses modern preparation
APIs; check compatibility before running it against standalone 1.3.0. Port the
small test harness or selected scenarios when necessary, without importing the
entire new runtime to make a test pass. Start with uninstrumented
SM-contention replay and 2,000 iterations per relevant case; use at least 5,000
for the known BF16/dynamic reproducer shapes. Require noise kernels actually
ran. Use upstream deterministic modes for bitwise tests and the appropriate
oracle/tolerance for normal atomic-scatter output. Test the old image as a
negative control in disposable test processes; no serving request uses a
deliberately broken variant. Optional warp-delay fuzzing is a second pass only
if its compiler instrumentation is ported correctly.

Run the delayed-publish DSA regression plus ordinary DSA, MoE and projection
unit tests. Record pre-existing failures explicitly; an unrelated upstream
failure is neither a blanket waiver nor evidence of a new regression. A
passing quiet replay alone is insufficient for these races. An upstream
reproducer does not prove this fleet has exhibited user-visible corruption.

### 2. Metadata ownership, separately measurable

[vLLM #918](https://github.com/local-inference-lab/vllm/pull/918) at
`1d95593e751e28632a730076fb584b5e4473a4c6` changes
`vllm/models/deepseek_v4_1/attention.py`: retain the borrowed workspace arena,
not fresh per-forward decode metadata. Our source has the affected pattern.
The patch does not require a new B12x API or new memory-utilization setting.

Backport the ownership change and its fresh-forward-context/poisoned-metadata
replay test together. Preserve any selected local attention changes; do not
overwrite the whole model file. Run the graph replay regression across relevant
shapes, including DSpark verification and prefill/decode transitions. Require
released metadata references and correct replay after poisoning; check repeated
capture/teardown as well.

Measure allocated/reserved graph-pool bytes, per-shape growth, KV capacity and
host available memory before and after startup, at identical profile settings.
Use exact graph-accounting diagnostics in a separate diagnostic run if
available; do not silently change the selected memory profiler. Log each actual
capture shape. The upstream 3.4 GiB saving was on RTX PRO with K7/32 sequences;
our K5/16 profile needs measurement. Unified GB10 memory also makes host
headroom relevant. Extra free memory is not automatically more KV or more t/s.

Use arms `A` (selected) → `B` (kernel fixes) → `C` (B + metadata). If both
pass and there is no regression, C becomes the candidate base for transport
work. A combined final image is fine; preserve the isolated evidence.

### 3. Chunked two-shot is a transport integration

Pin [commit 425fb6](https://github.com/local-inference-lab/flashinfer/commit/425fb6b4095d0259228e12432b2635ae833b4a43).
It reduces per-rank payload from `3 × message` to `1.5 × message` at TP4 and
overlaps staging, transfer and reduction. Its four-Spark switched 4 MiB result
was 664 → 325 µs. That is a collective microbenchmark, not a model throughput
claim. Its rank-ordered FP32 accumulation is intended to match one-shot bits.

The source change spans 11 files, including `_roce_proxy.c`, `_proxy.py`,
`_preparation.py`, existing kernels, a new `_twoshot_cute.py`, runtime routing
and tests. The new `pipe_bytes` defaults to **0**, so installing those files
alone does not enable it. The old vLLM adapter must pass capacity/threshold
parameters, prepare launchers before graph capture, and dispatch eligible sizes
to that runtime. Audit the actual selected overlay/module origins; SparkRing
vendors a prepared transport and can shadow the ordinary B12x module.

Minimum integration strategy after the switch:

1. Preserve small-message one-shot and all-gather behavior. Add the coherent
   two-shot protocol/kernel/runtime changes to an isolated candidate transport
   bundle, built as one unit. Do not mix the new C proxy with the old Python
   layout or copy just the CUDA file.
2. Compare the selected vendored bundle against the exact upstream parent
   `d4f22893cca5e96c46ff06b3258e189cf0c559c3`, including preparation contracts,
   route selection, stream lifetime, epoch/poison handling and health counters.
   Backport the protocol into the old bundle only if those interfaces can be
   reconciled locally. Otherwise use a matched newer transport namespace with
   an explicit thin adapter; do not replace unrelated B12x math kernels.
3. The upstream `_routes.py` pairs switched interfaces by rail/subnet. It does
   **not** recreate the four-node ring's opposite-peer forwarding. It can reject
   our old opposite-rank topology despite supporting directly connected
   neighbors. Keep ring-specific routing out of the switched experiment and
   retain the old ring bundle for physical rollback.
4. Keep one-shot allocation at the current 2 MiB. Start two-shot capacity at
   64 MiB for microbenchmarks, then extend to 128 MiB only if measured serving
   payloads require it and memory is acceptable. At TP4 the cited 64 MiB pipe
   allocates about 192 MiB pinned memory per runtime; separately account for
   existing buffers and multiple communicators.
5. Start at upstream TP4 threshold 1 MiB, four blocks and 128 KiB shard chunks.
   Tune only after correctness. Record selected route, runtime capacity and
   counter deltas proving actual two-shot execution. Keep fallback NCCL for
   unsupported/over-capacity operations.

Current limits are **2 MiB all-reduce** and **16 MiB all-gather**; they are
distinct settings. Increasing `VLLM_ROCE_ALLREDUCE_MAX_SIZE` alone would route
more work to old one-shot and potentially allocate large buffers. It is not the
two-shot upgrade. The general FlashInfer all-reduce selector is also not a
substitute for this RoCE runtime.

Illustrative BF16 `[rows,5120]` all-reduce payloads are 0.47 MiB at 48 rows,
0.94 MiB at 96, 1.72 MiB at 176, 10 MiB at 1024, 40 MiB at 4096 and 80 MiB at
8192. Those are shape arithmetic, **not an observed call census**. DSpark's
target verification/draft graph shapes can exceed `(K+1) × concurrency`, so do
not conclude that decode never crosses 1 MiB. Log actual operation kind,
dtype, bytes, shape, frequency and selected backend during separate C1/C8/C16
and prefill profiling runs. Remove instrumentation for final timings.

This census will also show whether the local indexer plugin's all-gathers, or
Engram/attention reductions, dominate. A two-shot all-reduce improvement need
not speed up an all-gather-bound path. Do not increase the 16 MiB gather cap or
add variable-length gather in the same arm.

### 4. Full FlashInfer/KK migration, only if justified

B12x development moved under FlashInfer; `import b12x` remains a compatibility
interface. A compatible vLLM loader adapter is required because the old
`b12x_loader` plugin is no longer supplied by the FlashInfer package. This is a
packaging/source change, not automatic acceleration.
[Migration guidance](https://github.com/local-inference-lab/b12x).

The checked canonical `20261016.2` composition pins vLLM `8244d1c44348…` and
FlashInfer `6023d031be8e…`; beta pins `6d66eed35b0a…` and `79819b112f8b…`.
Canonical has additional relevant FI fixes beyond that beta. Full commits are
in PINS.json. Those **exact** published images are AMD64, so do not pull them
onto GB10 as the serving candidate. The October 15 eugr ARM64 image digest
`sha256:03a956544e9f9b4b7ba91690469fbe7848bdbef29a7d2e0f5788368467bb3595`
is a possible base, but its image config did not identify exact source SHAs.
Inspect its embedded receipts or build from pinned source. Its example K7,
max-sequences 2 and MXFP8 target-head profile is not our serving profile.
[KK releases](https://github.com/local-inference-lab/blackwell-llm-docker/releases)
and [eugr build source](https://github.com/eugr/spark-vllm-docker).

Before any broad build, produce a lock of ARM64 base digest, vLLM/FI commits,
Torch/CUDA/CUTLASS/compiler versions, SparkRing transport/adapter source and
local patches. Verify SM121 compilation, native ABI and loader registration in
a disposable container. Install only one provider of the B12x namespace;
never overlay standalone B12x and FlashInfer's compatibility package. Preserve
local plugins while adapting the retired loader entry. Run original-format
loader checks and ensure no launcher guesses CSF for this official checkpoint.

Audit changed defaults explicitly, especially #911's attention arithmetic and
logits dtype. Initially preserve the selected behavior where supported for an
isolated runtime comparison. Then assess #911 separately if desired. Its
`reference` mode has a published speed cost and is not the default candidate.
Keep the full compressor correction and both 1017 frontend fixes, even if they
must be reapplied. Do not resurrect SIRCL merely because a new base includes it.

Research refresh at execution: FI main observed here was
`7e203806a82b588b9113f5a0866a028564847741`; its latest change concerns KDA
verification, not a demonstrated DS41 gain. SparkRing main was
`68a995125bef92e3eb70e37d960ca121f55797fe`. Check newer releases by exact source
diff, not date/`latest`/`beta` labels. Small-source metadata refresh is enough
until a candidate is selected.

## Switch arrival and topology conversion

Confirm the label/SKU, cables, available high-speed ports and RouterOS/package
versions. The likely CRS812-8DS-2DQ-2DDQ-RM has two 200G QSFP56 and two 400G
QSFP56-DD ports, plus eight 50G SFP56. Four equivalent 200G host links must be
verified; do not assume the eight 50G ports meet that goal, that a 400G port
automatically negotiates the desired mode, or that any splitter/DAC is suitable.
[MikroTik product specification](https://mikrotik.com/product/crs812_ddq).

Prefer the simple initial topology: one verified 200G physical cable per node
to the switch, using the two Socket Direct functions associated with that
physical port. Enumerate actual HCA/netdev/PCI/function mapping on both Spark
and GX10. Logical rails do not multiply a cable's line rate. NVIDIA's switched
playbook is a cabling/reference check, not a host configuration installer for
this fleet. [NVIDIA switched playbook](https://github.com/NVIDIA/dgx-spark-playbooks/blob/main/nvidia/multi-sparks-through-switch/README.md).

Before unplugging:

1. Save all four selected image/config/plugin/cache identities; full 1017
   checkpoint verification receipts; NetworkManager profile contents and UUIDs;
   addresses/routes/rules/neighbors, HCA/GID/MTU mappings; mesh service state and
   fabric documents; patched NCCL/transport paths; switch export and cable map.
   Save private configuration outside public results. Record exact rollback
   commands from the installed controller. No broad Docker prune.
2. Capture the new-checkpoint **full public LIL baseline** on the old runtime
   and original ring before conversion, if a completed one does not exist.
   Today's 1017 qualification intentionally has focused 8K C1/C8/C16 gates;
   October 14's full grid uses old weights and is not an isolated runtime A/B.
3. Stop DeepSeek and all mesh supervisors together using the existing fixed
   lifecycle helper. Verify no GPU containers and no surviving relays before
   changing links. Keep management connectivity available throughout.

Create a separate switched fabric document and NetworkManager profiles under
the same owner. Use two non-conflicting plane subnets across all four ranks,
with unique addresses and explicit source/interface selection. Derive them
from current routes; do not assume a free subnet from this document. Preserve
MTU 9000 and initially preserve IPv4 RoCEv2 GID 3; validate actual GID type,
mapped address and netdev on every selected function. If address/profile
creation changes indexing, resolve that deliberately rather than borrowing an
old GID number. Keep ring profiles disabled and saved for rollback.

The installed controller's **ring-specific mesh gate is not a switched gate**.
Stage a private switched trial controller/config that retains image, manifest,
all-rank, workload, clock and memory guards but replaces ring reachability
expectations with verified switched ones. Do not bypass a failing mesh gate or
mark a stopped mesh service healthy. Current upstream's explicit switched
profile is for GLM; it is a useful lifecycle pattern, not a DS41 profile to run.

Reconcile transport settings to that document: selected switch-connected HCA
functions only, matching per-peer rails, remove ring-only HCA maps/opposite
paths and `NCCL_SWITCHLESS_RING_ONLY=1` from the **switched candidate**. Audit
subnet-routing/preserve-domain NCCL patches and forced Ring/channel/protocol
settings; retain math/runtime settings while changing only what topology
requires. Record every changed env var. Do not enable SIRCL. A later NCCL
auto-algorithm trial is separate from establishing the first switched baseline.

Configure switch hardware forwarding and jumbo-frame support for the chosen
ports. Inspect actual RoCE traffic class/DSCP first; align NIC and switch ECN,
PFC and lossless-class settings, including CNP handling. RouterOS 7.23 changed
the QoS interface, and CRS8xx uses `switch-marvell`; use the installed-version
manual and verify support rather than pasting an old example with 10G queue
rates. Keep lossless policy scoped to the fabric class/ports. Preserve
management access and rollback export.
[Current MikroTik QoS manual](https://manual.mikrotik.com/docs/bridging-and-switching/quality-of-service/).

Validate stopped-fleet networking before loading the model:

- Link speed, lane/FEC mode, MTU path, physical mapping, and hardware offload.
- All six node pairs on each plane, in both directions; then concurrent pair
  traffic to expose shared-link or switch congestion. Adapt existing RDMA
  diagnostics to switched endpoints; `ring/rdma_links.sh` hardcodes old links.
- Small-message latency plus 1/4/16/64 MiB RDMA bandwidth, single and dual rail.
  Expect realistic protocol/PCIe overhead, not 200 Gb/s payload on each logical
  function. Compare symmetry; investigate a persistent pair/rail outlier.
- Before/after NIC and switch counters: CRC/FEC uncorrectables, drops, retries,
  completion errors, pause/ECN/CNP activity and congestion. No new uncorrected
  errors or sustained pause storm. Do not confuse historic counters with deltas.
- Gloo/bootstrap over intended management interface; RDMA payload over fabric,
  with no socket fallback hidden by a successful API response.

Load the selected image with only verified switched topology changes. Qualify
it and save a switched-old-runtime baseline before introducing kernel or
two-shot changes. This separates the switch benefit from software benefit.

## Experiment matrix and acceptance

| Arm | Topology | Runtime | Purpose |
|---|---|---|---|
| R0 | Existing ring | Selected 1017 | Before-switch baseline |
| S0 | Switch | Selected 1017; required topology adapter only | Isolate topology |
| S1 | Switch | S0 + synchronization fixes | Correctness and cost |
| S2 | Switch | S1 + #918 | Memory and serving |
| S3 | Switch | S2 + two-shot, conservative capacity/threshold | Collective and model gain |
| S4, optional | Switch | Fully matched ARM64 FI/vLLM with same profile | Maintained-stack comparison |

Use a single new campaign directory with per-arm sources, images, environment,
source/kernel receipts, live module origins, native cache namespace, full logs,
telemetry, raw tests and benchmark JSON. Keep candidate configs separate from
`/etc/deepseek-ring/optimized-specs.json`. Use the established strict
trial/cutover pattern, adapted to switched checks. Followers require
`--headless`. Start/stop all ranks as a unit; no rolling transport upgrade.

For each new code candidate:

1. Pass targeted CPU/source/manifest checks, then stopped-fleet GPU regressions.
   For two-shot, run upstream size-routing, eager/graph numerical agreement,
   mixed one-/two-shot doorbell, stream-lifetime and failure/poison tests. A
   timeout injection belongs only in disposable test processes; teardown all
   ranks afterwards. Validate the real fallback path and all-gather separately.
2. Run the collective payload matrix: 10 KiB, 64/256/512 KiB, 960 KiB, 1 MiB,
   1.72/2/4/10/16/32/40/64/80 MiB, plus measured serving shapes and threshold
   boundary sizes. Compare old one-shot where supported, new one-shot, forced
   two-shot, automatic routing, and NCCL. Use BF16 primarily; test supported
   FP16/FP32 paths for API correctness. Run eager and 20-operation CUDA graphs,
   at least ten measured replays, max-over-ranks latency and numerical checks.
   Non-aligned and over-capacity inputs must take a validated fallback or fail
   clearly, never silently corrupt. The exact upstream benchmark is archived
   under `evidence/two-shot-exact/benchmarks/…`.
3. Start DS41, inspect real route counters and loaded GPU clocks, confirm no
   graph-capture fallbacks, guard-disable logs, OOM, swapping or worker restarts.
   Run `bench/functional.py`, tools including omitted-string parameters,
   vision/thinking, finite exact-answer checks and late-output consistency.
   Use the completed 1017 campaign's same-checkpoint quality screen, not old
   model answers as a correctness oracle. Require uncached 128K retrieval;
   require uncached 1M retrieval for the final candidate.
4. Screen C1/C8/C16 at 8K and 128K, and long-prefill plus active decoders. Track
   aggregate and per-stream decode, TTFT, inter-token latency, request errors,
   draft acceptance, prefill throughput and graph/KV/host memory. Adaptive 4K
   prefill and indexer sharding must still activate only when eligible.
5. Run the full public LIL 25-cell grid for S0 and the best qualified software
   candidate. Preserve the installed unmodified LIL 0.7.6 harness
   `bbfec004beac908692030b10b14846db4a3c6457`, script SHA256
   `c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553`.
   Use gx10-r0 client, port 8015, contexts 8/16/32/64/128K, concurrency
   1/2/4/8/16, 20-second cells, max output 2048, temperature 1, coding probes,
   no hardware-monitor overhead or self-update. Keep model/default request
   settings equal; do not insert the old thinking-off wrapper into one arm.
6. Repeat decisive C8/C16 and prefill cells at least three times per arm with
   warm caches and reversed/alternating arm order when differences are small.
   Compare medians and spread, not the best cell. Full-grid repeats are needed
   only when ambiguity or a regression warrants them. A fresh request nonce and
   cached-token checks distinguish prefill from prefix-cache hits.

Suggested promotion rules, set before measuring:

- Correctness, health and rollback readiness are mandatory. Any new numerical
  failure, race, hang, stale-result publication, unknown transport fallback,
  fidelity-fix loss or persistent hardware/network error stops promotion.
- Synchronization fixes can be valuable with neutral speed; #918 can be
  valuable with neutral speed and verified memory savings. A repeatable >5%
  regression in C1/C8/C16 or prefill triggers diagnosis and bisection. Deltas
  inside ordinary run-to-run spread are reported as inconclusive.
- For the performance-only two-shot addition, require a repeatable model-level
  benefit, not just faster large-message tests. A modest prefill loss (roughly
  up to 5%) can be an acceptable user-aligned trade if useful decode/concurrency
  improves clearly, but document that trade explicitly. Keep small-message C1
  and tail latency from regressing materially.
- Measure power and temperature for regressions, but keep the 2350 ceiling.
  Do not chase 300 C16 by silently raising clocks, changing draft depth,
  reducing context, or altering the sampling workload.

Promote the selected immutable per-rank images, switched controller/fabric
document and root config only after the gates pass. Verify installed identities
and actual serving one more time. Preserve private rollback specs and stopped
containers/images. Update README, OPERATIONS, RESULTS, deployment manifest and
the shared SKILL together, including switched recovery and physical ring
rollback. Stop temporary test servers/proxies and leave only the selected
workload active.

## Rollback and stopping points

Maintain two independently usable rollback descriptions:

1. **Software rollback on the switch:** stop all trial workers, restore S0 or
   the last qualified switched images/config/cache namespaces, then start all
   four. No checkpoint deletion/transfer and no cable changes. Target warm
   restart time is the established roughly 7–16 minutes, not a guarantee.
2. **Physical ring rollback:** stop all workloads and switched transport;
   restore the saved NetworkManager/fabric/controller profiles; recable the
   recorded clockwise f0 → next f1 ring; validate all 16 original GID entries,
   MTU and opposite paths; restore the original mesh as a coordinated unit;
   start selected 1017. This requires the user's physical cabling action.

If topology validation fails, stop before runtime experimentation. If a new
candidate fails twice for the same unresolved reason, preserve logs, restore
the last qualified service, and investigate offline instead of repeated blind
restarts. Do not use checkpoint downgrade as the first image rollback.

GX10 storage is the limiting resource. Inventory exact free space and image
layer/cache growth before building. Prefer small descendant layers; do not
download another model. Build/archive large artifacts on a Spark when possible
and transfer over the validated fabric. If the full-image fallback would remove
the selected image or its only rollback, postpone it until targeted cleanup is
reviewed against mounted/protected objects. Never broad-prune Docker or caches.

## Realistic timing

These are engineering estimates, not benchmark-derived deadlines. Preparation
can leave serving available; GPU stress tests, topology work and final LIL runs
need exclusive fleet time. Each new native source set may need substantial cold
JIT time even when image construction is quick.

| Work | Expected elapsed effort/window |
|---|---|
| Inventory, source refresh, locked small patch builds and rollback staging | 2–4 hours, mostly before downtime |
| Full 1017 ring baseline and evidence capture | 45–90 minutes of exclusive benchmark time |
| Physical cabling, switched profiles/controller gate, RDMA validation and S0 startup | 2–4 hours if ports/cables work; longer if negotiation/QoS needs repair |
| Small kernel + metadata candidates, native tests, startup and focused serving A/B | 3–6 hours including cold compilation |
| Two-shot adapter/proxy integration and standalone qualification | 4–8 hours; budget another half-day if preparation/routing contracts diverge |
| Best-candidate full grid, decisive repeats, 1M retrieval, promotion and docs | 1–3 hours |
| Full matched ARM64 image fallback | Additional 1–2 days for source build, compatibility fixes and qualification |

With preparation and no compatibility surprises, expect **one to two working
days** to establish the switched baseline and qualify the useful small fixes
plus two-shot. Do not promise all of it in an hour. Keep the model usable at
each qualified stopping point; the switch and small fixes can be delivered
before the more involved collective port. A fallback full-stack rebuild should
not hold the working model offline for days.

## Evidence and remaining uncertainty

This directory contains exact upstream PR metadata/diffs, selected old-source
site checks, release/platform receipts, the exact two-shot files, relevant test
and route sources, and pinned SparkRing switched-reference files. Downloaded
small source files are indexed and hashed in `evidence/source-files.json`;
all retained evidence is hashed in `evidence/SHA256SUMS.json`.

Still pending: actual delivered switch/SKU/cables/RouterOS; all four live HCA
mappings and switched reachability; final 1017 selected identities and full
baseline; current selected transport overlay source origin; real collective
payload census; compile/test compatibility of each backport; GB10 memory and
serving gains. Resolve those facts at the phase that needs them. No missing
measurement in this plan is a claim that an upgrade already works.
