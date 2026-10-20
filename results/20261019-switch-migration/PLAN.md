# CRS812 migration: one 200G link per node

Prepared October 19 HST / October 20 UTC, 2026. This supersedes the networking
portion of the [earlier standby plan](../20261017-runtime-plan/PLAN.md).
The October 17 runtime upgrade is already complete.

## Current state and physical handoff

**DeepSeek is intentionally stopped for recabling.** All four mesh supervisors
were stopped and disabled through the installed controller. At
`2026-10-20T05:28:12Z`, all four nodes had no running containers or GPU compute
processes, no mesh/relay process, and an inactive/disabled model mesh service.
Port 8015 was unavailable as expected. A subsequent read-only inspection again
found no running containers.

The user selected 400G → 2×200G breakout, one ConnectX physical port per node,
probably port 0. Two breakout cables supply four node links. Exact cable media,
switch leg assignments, management address/access, and RouterOS version remain
to be established. Keep each node's ordinary management Ethernet connected.
Do not restart the old `ds` / `recover-ds` controller during recabling: its
`up` action explicitly enables the ring mesh.

The selected image, checkpoint, plugins and configuration remain unchanged.
This work stopped workloads and mesh supervisors; it has **not** removed host
fabric configuration, installed a switched recipe, or configured the switch.
Private backups and detailed observations are under
`~/Agent/Diagnostics/deepseek-v41-flash-ring/switch-migration-20261019/`:
`ring-selection-backup.json`, `before-stop.json`, per-host network/teardown
snapshots, stop logs, `stopped-verification.json`, and pinned upstream sources.
Keep those private; Docker inspections can contain environment values.

## Recommended runtime

First qualify the switch with the existing immutable image and serving
configuration, changing topology and its required transport settings. Then
evaluate a smaller eugr-derived image and newer large-message collectives.
This separates network gains from compiler, transport and model-kernel changes.

The live Docker Hub metadata checked during this audit still identifies
`nightly-20261015` as eugr's latest B12x image. Its ARM64 digest is the
`03a95654…` base already recorded in [deployment.json](../deployment.json).
There is no newer eugr base to obtain merely by pulling `latest`.
[Registry metadata](https://hub.docker.com/v2/repositories/eugr/spark-vllm-b12x/tags?page_size=8).

Do not substitute eugr's stock DS41 recipe for our selected arguments. At
`0bdc9c94…`, that recipe uses the older checkpoint name, max sequences 2,
DSpark7 with standard rejection, MXFP8 target head, image limit 1 and port 8000.
It is useful packaging reference, but would change our concurrency and quality
choices. Retain our recipe on the eugr base.
[Pinned recipe](https://github.com/eugr/spark-vllm-docker/blob/0bdc9c94cd89843e1c8f7d7b33df2d5bc746c03d/recipes/4x-spark-cluster/deepseek-v4.1-flash.yaml).

Preserve:

- Official 1017 revision `1bae0e1088993b9b82de08f59de5be5a34e42170`, original
  published precision and BF16 target head, HF tokenizer and frontend fixes.
- DSpark5, selected block/probabilistic/adaptive verification, Engram projection
  TP and disk settings, adaptive-prefill and guarded query-indexer plugins.
- Max sequences 16, batched tokens 8192, 1M context, 20 GiB KV per rank,
  image limit 999, explicit sampling defaults and API port 8015.
- GPU ceiling 0–2350 MHz. About 118 GiB total system memory used immediately
  after loading on the head is a sizing goal, not an automatic runtime stop.

The local prepared transport's `_path_config.peer_hca_map()` explicitly supports
two selected HCAs with every remote peer using both. That makes the existing
image a plausible first switched candidate; this is source evidence, not
hardware qualification. Its imported overlay must remain correctly selected
and pass its existing verifier.

For the later clean image, preserve quality/plugin corrections and build a
new explicit composition receipt. Remove the ring overlay and patched-NCCL
dependency only after validating the base image's provider, CUDA/native ABI
and fallback collectives. Do not bypass the current image's sealed entrypoint
by unsetting its required transport profile.

## Network layout and switch configuration

Assuming physical port 0 is confirmed, the expected interfaces are:

| Function | Linux interface | RDMA device |
|---|---|---|
| Socket Direct rail A | `enp1s0f0np0` | `rocep1s0f0` |
| Socket Direct rail B | `enP2p1s0f0np0` | `roceP2p1s0f0` |

Both are functions of one physical 200G link, not two independent 200G cables.
Verify actual carrier and mapping with `ibdev2netdev`, `rdma link` and
`ethtool`; do not assume chassis labels establish Linux numbering.
NVIDIA documents one physical link per node, 400G breakout, two logical
interfaces and checking negotiated 200G.
[NVIDIA switched topology guide](https://github.com/NVIDIA/dgx-spark-playbooks/blob/main/nvidia/multi-sparks-through-switch/README.md).

Proposed addresses, subject to checking LAN/VPN/container route conflicts:

| Rank / node | Rail A | Rail B |
|---|---|---|
| 0 / spark-r0 | `10.20.0.10/24` | `10.20.1.10/24` |
| 1 / spark-r1 | `10.20.0.11/24` | `10.20.1.11/24` |
| 2 / gx10-r1 | `10.20.0.12/24` | `10.20.1.12/24` |
| 3 / gx10-r0 | `10.20.0.13/24` | `10.20.1.13/24` |

Use NetworkManager profiles, MTU 9000, no default route or DNS on these rails,
and separate subnets for unambiguous source/interface routing. Leave management
addressing and its default gateway intact. Deactivate old addressing on the
unused ConnectX physical port. Verify IPv4 RoCEv2 GIDs after configuration;
index 3 was the ring's value, not a value to assume forever.

On the CRS812, read/export current configuration first. Verify both 400G cages
are in 2×200G breakout mode and the four intended logical ports are bridged with
hardware offload. MikroTik's documented lane starts are `qsfp56-dd-N-1` and
`qsfp56-dd-N-5`. DAC examples use autonegotiation disabled and
`speed=200G-baseCR4`; optical media requires the corresponding optical mode.
Confirm the cable/module type and actual interface names before issuing commands.
[MikroTik breakout compatibility](https://help.mikrotik.com/docs/spaces/ROS/pages/220233794/MikroTik%2Bwired%2Binterface%2Bcompatibility).

Inspect RouterOS and the `switch-marvell` package before preparing QoS commands;
CRS8xx QoS syntax has changed across versions. Match DSCP/priority mapping on
the NIC, RoCEnante proxy and NCCL, then configure appropriate PFC/ECN treatment
for RoCE and CNP. The documentation's RoCE class 3 / DSCP 26 and CNP class 6 /
DSCP 48 are reference mappings, not evidence that our senders already use them.
Check counters under concurrent RDMA traffic. Avoid blanket pause on every class
or transplanting example rate limits written for slower ports.
[MikroTik QoS reference](https://help.mikrotik.com/docs/spaces/ROS/pages/189497483/Quality%2Bof%2BService).

The retained overlay's `_roce_proxy.c` hardcodes `traffic_class = 0`; setting
`NCCL_IB_TC` does not change that proxy. The base FlashInfer proxy supports
`B12X_ROCE_TRAFFIC_CLASS`, falling back to `NCCL_IB_TC`. For an unmodified-image
network baseline, account for the actual class-0 traffic when selecting switch
policy. Proper explicit marking is a reason to advance the modern transport
candidate before production promotion, rather than assume a class-3 policy
protects the old proxy.

## Retire the old ring configuration deliberately

Before applying the new profiles, archive root-owned network files and unit
enablement as well as the readable snapshots already saved. Use established
admin access: the fixed-action helper worked for shutdown, while arbitrary
`sudo -n` was not available on both Sparks during this audit.

1. Keep the model and all mesh supervisors stopped. Disable the old model
   autostart path and the old fabric/hairpin restoration units before changing
   addressing. These run `sparkring node restore` and `node hairpin apply`;
   leaving them enabled can resurrect ring configuration after a reboot.
2. Inventory exact connection UUIDs and their source files. Each host currently
   has four active `sparkring-sparkring-rN-{cw,ccw}-{primary,secondary}` profiles
   **and four autoconnecting `netplan-*` fallback profiles** carrying ring
   addresses/routes. Retire both sets and the generating source, where present.
   Preserve the management profile. Do not run `netplan apply`.
3. Remove only confirmed ring-owned routes/rules and forwarding objects.
   After mesh shutdown, the read-only `tc` inspection showed ordinary queue
   disciplines and no ingress/egress filters. Do not clear all host traffic
   control, firewall, bridges or sysctls merely because they exist.
4. Hairpin capacity settings may remain in the NIC after a unit stops. Inspect
   the installed ownership/configuration before reverting them. A device reload
   is a separate stopped-fabric operation; it is not necessary just to remove a
   supervisor. Preserve a record for physical rollback.
5. Replace the lifecycle mesh gate with checks for the switched profiles,
   per-peer RDMA reachability and expected HCA/GID mapping. Preserve image,
   checkpoint and plugin checks. Adapt the installed controller and local
   lifecycle script together; do not fake a healthy mesh.
6. After the switched deployment is qualified, retire obsolete ring observer,
   restore and mesh units/configuration. Keep checkpoints, caches and verified
   rollback archives. Package uninstallation comes last, after checking its
   uninstall hooks and any reused toolchain files.

Initial serving environment changes, to be generated from the saved selection:

| Setting | Switched candidate |
|---|---|
| `B12X_ROCE_HCA` | `rocep1s0f0,roceP2p1s0f0`, if port 0 confirmed |
| `NCCL_IB_HCA` | `=rocep1s0f0:1,roceP2p1s0f0:1` |
| `B12X_ROCE_PEER_HCA_MAP`, `B12X_ROCE_OPPOSITE_PATHS` | Remove ring mappings |
| `NCCL_SWITCHLESS_RING_ONLY` | Remove |
| `NCCL_ALGO` | Allow discovery instead of forced Ring |
| `NCCL_IB_SUBNET_AWARE_ROUTING` and other patched routing flags | Audit actual implementation; retain only demonstrated requirements |
| GID selection | Use verified IPv4 RoCEv2 entries |
| `NCCL_SOCKET_IFNAME`, `GLOO_SOCKET_IFNAME` | Keep management `enP7s7` initially |
| RoCEnante size limits | Keep 2 MiB AR / 16 MiB gather for first comparison |

Keep the initial four-channel policy and other unrelated settings for the
topology comparison, then test NCCL automatic channel selection separately.
Do not remove library-path, PCI-domain or compatibility flags blindly while
still running the existing patched library.

## Follow-up: larger all-reduces

The user supplied [PR #10](https://github.com/local-inference-lab/flashinfer/pull/10),
[PR #11](https://github.com/local-inference-lab/flashinfer/pull/11) and
[PR #12](https://github.com/local-inference-lab/flashinfer/pull/12) and requested
considering this as "RoCEnante 2". These are feature PRs, not a confirmed
package version numbered 2.0. #10 supplies pipelined two-shot all-reduce;
#11 supplies external pinned-region/native-runtime packaging interfaces;
#12 supplies variable-length gathers for device-selected contribution sizes.
The latter two are available in our base provider but are not automatically
used by our vLLM TP4 serving recipe. Keep variable-length allocation disabled
for the first candidate; implementing context-parallel prefill is separate work.

The current FlashInfer pin `91271757…` already contains the two-shot runtime,
but our prepared ring overlay shadows it. In addition, the current vLLM
`B12xRoceAllReduce` adapter passes only `max_size` and `max_gather_bytes`;
it does **not** pass `pipe_bytes`, which defaults to zero. Raising
`VLLM_ROCE_ALLREDUCE_MAX_SIZE` alone therefore does not enable two-shot.
[Pinned adapter](https://github.com/local-inference-lab/vllm/blob/8244d1c44348ae8a5bbfc9f1b607021652283ed4/vllm/distributed/device_communicators/b12x_roce_all_reduce.py).

Before enabling it, include the coherent October 16 buffer-lifetime correction
`f3bbd1ce79cb9a62afb88b367580b0583db167ee`: the proxy waits for outgoing writes
before releasing the send buffer, and the GPU waits for that release before
advancing. It changes Python/C proxy ABI 7→8 and the two-shot kernel together.
Do not mix these pieces across versions.
[Upstream correction](https://github.com/local-inference-lab/flashinfer/commit/f3bbd1ce79cb9a62afb88b367580b0583db167ee).

Implement explicit capacity/threshold parsing, all-rank configuration agreement,
constructor plumbing, preparation/graph warmup and accurate dispatch logging.
Start with the upstream 1 MiB TP4 threshold and modest pipe capacity, then size
from observed serving payloads. Account for pinned-memory growth against the
head's startup budget before expanding capacity. Preserve one-shot/gather and
NCCL fallback. Use a candidate-specific compilation cache.

**Source staging completed:** [the candidate](../../image/rocenante-switch/README.md)
now generates these adapter changes and the coherent ABI-8 fix with pinned
before/after hashes. Seven CPU contract tests passed. Image composition,
four-node GPU/graph correctness and serving benchmarks remain pending; no
candidate was installed or promoted.

A new KK container tag alone is not proof of a faster model runtime: the
canonical vLLM source checked here is still our `8244d1c4…` pin. Treat later
FlashInfer main/canonical branches as distinct candidates; their histories
diverge. Verify actual commits, platform and APIs instead of inferring inclusion
from release dates. SIRCL is optional future work, not required for this switch.

## Validation, promotion and rollback

Run network tests before loading the model:

1. Confirm all four links negotiate 200G, MTU works end-to-end, both rails reach
   every peer, GIDs match, and old ring routes do not return.
2. Exercise each rail alone and both together: all six node pairs, then
   simultaneous pairs and bidirectional traffic. Track throughput, latency,
   packet errors/retries and PFC/ECN counters. Two logical rails share one
   200G physical link; do not expect 400G aggregate per node.
3. Test NCCL fallback and RoCEnante separately, including numerical correctness,
   eager execution, CUDA graph replay and relevant small/large message sizes.
   Confirm logs/counters prove RDMA rather than socket fallback.
4. Start all four selected model ranks together. Verify identity, clocks,
   memory, tools/thinking, images/chat continuation, and uncached long-context
   retrieval. Keep the endpoint and generation settings unchanged.
5. Use the public LIL 0.7.6 procedure in OPERATIONS, without competing requests
   or hardware-monitor loops. Compare matched C1/C8/C16 and prefill against the
   October 17 results; repeat promising or anomalous cells before selection.

The selected ring's two focused 8K runs averaged **191.89 C8 / 267.98 C16**
aggregate output tokens/s. These are the relevant baseline, not historical
thinking-off figures near 150/220. A switch may help latency, reachability and
large-message efficiency; a specific throughput gain remains unmeasured.

Promote only after these checks and update deployment identity, README,
OPERATIONS, the maintenance skill and lifecycle instructions together. Verify
persistence through a coordinated networking/service restart before declaring
recovery complete.

An image/configuration fallback can run on the new switch after qualification.
Returning to the *physical ring* additionally requires restoring the saved
cabling, addressing and supervisor configuration; starting an old container
alone is not a rollback.

Planning estimate after cabling and switch access are ready: roughly 2–4 hours
for network conversion and baseline qualification if links behave normally;
the new image/two-shot work is a separate half-day-or-longer experiment.
No download or checkpoint replacement is required for the initial conversion.
