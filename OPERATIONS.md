# Operating the switched TP4 cluster

**FLARE evaluation, October 20 UTC:** the native trial lost the matched full
benchmark and was not selected. All 48 original 1017 shards on each GX10 were
restored over fabric and SHA256-verified. The qualified spec and containers are
restored; the 32K C1 recovery check measured 62.2 t/s and the API is healthy.
The staging interlock was archived as
`/etc/deepseek-ring/FLARE_TRIAL_20261020.finished.json`; no active staging marker
remains. The controller retains its interlock check for future workload changes.
FLARE's native wrapper requires that marker and refuses to overlap vLLM.
The interrupted `old4cap3b` provider trial remains stopped under
`ds41-flare-interrupted-old4cap3b-rN`; it is not the default. The native package
and agents remain staged for a future release. See
[the complete report](results/20261020-flare-trial/REPORT.md). The subsequent
vLLM optimization campaign is now paused at the user's request.

**Paused decode investigation:** the qualified image and profile remain the
recovery baseline. Reversible trials retain exact parent specs and stopped
containers in the private `decode-recovery-20261020` campaign. Read its
`PLAN.md`, the shared maintenance skill and the
[comparison report](results/20261020-decode-recovery/REPORT.md). An experiment
in `/etc/deepseek-ring/optimized-specs.json` is not a promoted default.
Do not start a saved parent independently or replay an already-consumed
`restore-*` receipt. Historical timed screens temporarily locked GPUs at
2418 MHz and restored stock boost afterward. Their private wrappers must be
updated to restore the current **0–2350 MHz** policy before any future use.
All completed trials in that report have now been unwound. The exact
qualified configuration `d86c7e0725ef...` and native `9f26f0b3718cc...`
containers passed the final restoration check; no trial is promoted.
The later live-cost diagnostic failed during startup and was also unwound;
`restore-livecost` is consumed. No live-cost result or scheduler correction was
obtained. Do not resume experiments without the user's direction.

**CRS812 conversion, October 20 UTC:** host networking is converted and the
controller now validates switched RoCE without starting the retired mesh.
The selected RoCEnante two-shot profile is qualified. Follow the installed selection and the
[switch campaign](results/20261019-switch-migration/PLAN.md); do not replay the
historical ring network or rollback configurations.

| Mode | Nodes | API | Model |
|---|---|---|---|
| DeepSeek vLLM TP4 | all four | `http://192.168.50.219:8015/v1` | `DeepSeek-V4.1-Flash-TP4` |

DeepSeek needs all four nodes. There are no API keys. Qwen serving on this ring
was retired on 2026-10-12 UTC; the former port-8000 endpoints are no longer
served. The [GLM handoff](../GLM/HANDOFF.md) records the storage cleanup and
GLM assignment. On 2026-10-14 the user requested stopping GLM and restoring
DeepSeek for the HF inference-change audit. DeepSeek's selected endpoint is 8015;
GLM's historical Weightless alpha-2 recipe remains saved, but all GLM checkpoint
copies were deleted at the user's request on October 17. GLM start/restart and
profile selection are blocked by its retirement marker until a new build is
downloaded and qualified. See [GLM operations](../GLM/README.md),
[storage retirement](../GLM/results/checkpoint-retirement-20261017/REPORT.md),
and [the prior audit](results/20261014-hf-runtime-audit/REPORT.md).

## Switching from the Mac

```bash
cd ~/Agent/Builds/deepseek-v41-flash-ring
./scripts/ring-mode.sh ds
./scripts/ring-mode.sh recover-ds
./scripts/ring-mode.sh stop
./scripts/ring-mode.sh status
```

`ds` and `recover-ds` return when the selected API is healthy; allow roughly
4–20 minutes for startup. `recover-ds` first stops workloads and disables the
retired mesh, then validates the switched fabric and starts all four ranks. Both retired Qwen pair stop entry points remain idempotent for DS recovery.
`ring-mode.sh qwen` reports retirement before any SSH, DS stop or mesh change.

## Using DeepSeek

```bash
curl http://192.168.50.219:8015/v1/chat/completions \
  -H 'Content-Type: application/json' -d '{
    "model": "DeepSeek-V4.1-Flash-TP4",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 1024,
    "chat_template_kwargs": {"thinking": false}
  }'
```

Thinking is on by default. Set `thinking: false` explicitly for ordinary
non-thinking requests and comparable benchmarks. Send `max_tokens` to bound
the answer. Tools and images passed the retained functional checks.

The official checkpoint has no `generation_config.json`. The selected command
therefore explicitly sets temperature 1, top_p 1, top_k -1 (disabled), min_p 0
and repetition penalty 1. Presence/frequency penalties default to zero. Clients
can override these values. No implicit output-token cap is added by a generation
config; keep sending a suitable `max_tokens` for the task and remaining context.

KV uses `--kv-cache-memory-bytes 21474836480`: **20 GiB per GPU**, exposing
16,344,051 logical tokens. This **overrides `--gpu-memory-utilization 0.83`**;
changing that fraction alone has no effect while the explicit byte budget is
present. The head's **initial loaded memory target is at most about 118 GiB
total used**, measured as `MemTotal - MemAvailable`, not Docker RSS or GPU
allocation alone. The selected profile started at **117.31 GiB used**,
leaving **4.38 GiB available**. This is a startup budget,
not a runtime ceiling; do not install an automatic 118 GiB stop guard.
KV capacity is largely preallocated at startup; other caches and working
buffers can grow afterward.
[Current qualification and memory evidence](results/20261019-switch-migration/REPORT.md).

The context limit is 1,048,576 tokens, with 16 active sequences. The 8K batch
ceiling controls work per iteration; it is not a per-request reservation. The
adaptive plugin uses 4K steps when at least one runnable decoder contends
with prefill. Aggregate KV capacity limits simultaneous long contexts.
Greedy byte-repeatability is not guaranteed by this pinned runtime.

The serving profile uses native DSpark with four proposals, probabilistic draft
sampling, block rejection and adaptive verification. Its native batch-size cap
is `[[1,1,3],[2,16,4]]`: C1 passes at most three proposals to target verification;
the draft model still computes four. This is not a variable-width draft engine.
The graph ladder covers the union of `4*n` and `5*n` for `n=1..16`, through 80
rows. The target head remains BF16, with NVFP4 draft and Markov heads and the
full vocabulary. See `results/deployment.json` for the exact speculation and
compilation configuration.

RoCEnante uses both switched rails, a 128 MiB pipe and a 512 KiB two-shot
threshold. Small reductions and eligible gathers use one-shot; unsupported
operations retain patched NCCL fallback. There is no SIRCL serving path.
The complete image recipe is `image/rocenante-switch/README.md`.

LIL's generic NVIDIA local-P2P override warning is not a switched-RDMA
qualification result. Both rails and RoCEnante collectives were validated
directly on this fleet. Do not change NVIDIA module options or reboot merely
to clear that harness warning.

## Images and chat history

The installed selection uses `--limit-mm-per-prompt '{"image":999}'` on
all four ranks. This counts every image across the **entire request**, including
images in earlier chat turns. The previous value of 4 caused HTTP 400 when a
conversation accumulated a fifth image; the engine itself stayed healthy.
Retry the failed message after the change. A client may need its own retry or
conversation recovery if it retained the earlier error.

999 is the upstream vLLM default count ceiling, not a guarantee that every
999-image workload fits in RAM. The model processor exposes no separate fixed
image-count cap. Resolution, image tokens, text/history, concurrency and
available memory still matter. The 1,048,576-token context limit and original
image preprocessing are unchanged. No resizing or quality reduction was added.
The encoder retains an 8192-token compute/cache budget (eight maximum-size
1024-token images); it does not reserve 999-image GPU batches.
Distinct images at counts 5 (1024px square), 16 and 64 (64px fixtures), image
history, streamed follow-up, and recovery after an over-limit request passed.
[Validation](results/20261017-image-limit/REPORT.md).

This is a serving flag in root-owned `/etc/deepseek-ring/optimized-specs.json`,
not an edit to the checkpoint's `config.json`. Container commands must match the
installed selection on every rank; changing a local README does not deploy it.

**Historical ring-only rollback:** the private command below predates the switch
and must not be run against the switched selection. To change only image count,
retain the current switched image/environment and coordinate a fresh selection.
The old command is recorded for history:

```bash
python3 ~/Agent/Diagnostics/deepseek-v41-flash-ring/image-limit-20261017/change_limit.py rollback
```

On the former physical ring, that operation restored the four-image selection
with the **October 17 image, 1017 checkpoint and 20 GiB KV**, from
`ds41-before-images-rN`. Its historical head backup is
`/var/lib/deepseek-ring/experiments/image-limit-20261017/original-selection.json`.
That old rollback chain is incompatible with switched networking. Use the
[supported switched fallback](#rollback-on-the-switch) for software recovery.
Ordinary `ds` / `recover-ds` keeps 999 images and needs no rollback.

## Lifecycle on spark-r0

When no competing model workload is running:

```bash
sudo -n /usr/local/sbin/deepseek-ring-control up
sudo -n /usr/local/sbin/deepseek-ring-control down
sudo -n /usr/local/sbin/deepseek-ring-control status
```

These fixed actions already have passwordless sudo. The root-owned helper
validates recorded images, commands, mounts and plugin hashes, then checks
addresses, both 200G rails, MTU, GID 3, jumbo reachability and disabled legacy
services before starting `ds41-optimized-r0` through `r3`.
Inspect rank 0 with `docker logs --tail 100 ds41-optimized-r0`.

`status` reports the selected deployment and switched topology. The old
installer stock configuration requires the physical ring and is rejected by
`stock-up` before any running workload is stopped. Keep the installed SparkRing
package: its container-spec library and seccomp profile are still dependencies;
its fabric, hairpin, agent, mesh and model services stay disabled.

## Switched fabric

Each node uses **physical port 1**, exposing two Socket Direct rails sharing
one 200G cable. They are not two independent 200G links. Use MTU 9000 and IPv4
RoCEv2 GID **3** on both rails:

| Rank | Node | Rail A: enp1s0f1np1 / rocep1s0f1 | Rail B: enP2p1s0f1np1 / roceP2p1s0f1 |
|---|---|---|---|
| 0 | spark-r0 | 10.10.10.1/24 | 10.10.11.1/24 |
| 1 | spark-r1 | 10.10.10.2/24 | 10.10.11.2/24 |
| 2 | gx10-r1 | 10.10.10.4/24 | 10.10.11.4/24 |
| 3 | gx10-r0 | 10.10.10.3/24 | 10.10.11.3/24 |

Host configuration is `/etc/netplan/40-switch-fabric.yaml`, rendered by
NetworkManager, with `/etc/sysctl.d/60-switch-fabric.conf` ARP policy. Do not run
`netplan apply` or restore old SparkRing profiles. The unused port-0 interfaces
stay without IPv4 addresses. Management Ethernet `enP7s7` is unchanged.
The full switch setup is in `../spark-cluster-network.md`.

On CRS812, the four breakout legs use 200G-baseCR4, no autonegotiation,
L2MTU 9216, and an isolated hardware-offloaded fabric bridge. Switch management
is on a separate bridge. QoS/PFC/ECN were not recorded or changed in this
campaign; passing host tests does not establish that those policies are enabled.

## After a node reboot

Wait for SSH on all four nodes, then run on the Mac:

```bash
./scripts/ring-mode.sh recover-ds
```

From **spark-r0**, with no competing model workload running, the equivalent sequence is:

```bash
sudo -n /usr/local/sbin/deepseek-ring-control down
sudo -n /usr/local/sbin/deepseek-ring-control mesh-off
sudo -n /usr/local/sbin/deepseek-ring-control up
```

Restart the fleet together; the selected containers do not serve automatically
after reboot. The controller never re-enables the old mesh in switched mode.

### Switched link or GID failure

Read the failing interface and node from the startup gate. Check `ip -br addr`,
`rdma link`, and the HCA's `/sys/class/infiniband/<hca>/ports/1/gids/3` and
`gid_attrs/types/3`. GID 3 must be IPv4-mapped to that rail's address above and
its type must be `RoCE v2`. Check all four peers and both rails before startup.
Use `nmcli connection show` to identify the **current switch profile** if a
link bounce is needed, and stop the fleet first. Do not bounce management
Ethernet, activate a `sparkring-*` profile, or substitute GID 4 blindly.
The October 7 counterclockwise-ring repair is historical and no longer applies
on this switch; its evidence remains in Git and the retained recovery audit.

### Decode slows to roughly half speed

Check clocks **during generation**, on every node:

```bash
nvidia-smi --query-gpu=clocks.sm,utilization.gpu,power.draw,temperature.gpu --format=csv
```

After the October 6 HST reboot, spark-r1 stayed at **611 MHz** under
94–96% load and drew about 10–14 W. The other three nodes ran near 2350 MHz.
Reapplying the clock ceiling and briefly requesting a fixed 2350 MHz both
reported success but left the actual clock at 611 MHz. The mesh and selected
image/configuration were intact. A physical power disconnect restored its
clock to 2320–2333 MHz under load. The underlying power-delivery/firmware cause
is inferred from the symptoms; stock telemetry did not expose the platform cap.

The investigation also included a clean spark-r0 reboot after a memory-bandwidth
imbalance. Final sustained LIL 8K C1 measured **60.96 tokens/s**, matching the
retained original-checkpoint baseline of **60.98 tokens/s**. Three short prose
C1 probes measured 64.05–69.06 tokens/s. A fresh 125K-token retrieval passed.
The original image, checkpoint, plugins and 2350 MHz ceiling remained selected.

[Similar GB10 reports](https://forums.developer.nvidia.com/t/dgx-spark-gb10-gpu-clock-pinned-at-721-mhz-under-full-load-no-throttling-not-liftable-via-nvidia-smi/376039)
were resolved by a full power disconnect. Stop DeepSeek and all mesh
supervisors as above, shut down the affected node cleanly, then disconnect its
power adapter from both the wall and node for 1–2 minutes. Reconnect and boot,
wait for SSH, then run `./scripts/ring-mode.sh recover-ds`. Check GID 3 if the
switched-fabric gate fails. Verify all four clocks under generation and repeat a short C1
probe before declaring recovery. A healthy API alone does not prove normal speed.

## Fabric and host maintenance

Rank order remains spark-r0, spark-r1, gx10-r1, gx10-r0. All nodes now connect
directly to CRS812 using port 1; see the [switched map](#switched-fabric).
SSH and APIs remain on the management LAN.

All four hosts run kernel `7.0.0-1019-nvidia`, driver `580.178.04`, with
NetworkManager wait-online enabled. The enabled
[clock-policy service](host/systemd/gb10-gpu-clock-cap.service) applies
**`nvidia-smi -lgc 0,2350`** before Docker at boot. This is a 2350 MHz ceiling;
idle downclocking remains enabled. The user restored this policy after the
stock-clock trials showed no consistent decode gain. After a manual GPU/driver reset,
reapply the selected policy with:

```bash
sudo systemctl reload gb10-gpu-clock-cap.service
```

The previous stock-boost unit is backed up on every node under
`/var/lib/deepseek-ring/experiments/clock-cap-2350-20261020/`.
The clock service is enabled and active on all four nodes; applying it did not
restart the model. [Installation and loaded verification](results/20261020-clock-cap/REPORT.md).
Stock boost did not establish a consistent decode gain in the focused clock
trials. A temporary 2700 MHz ceiling also failed to improve decode; do not
infer actual operating frequency from a requested clock.

Keep retired mesh services disabled and never overlap DeepSeek with another GPU
workload. Avoid `netplan apply` on GX10s: it can stop NetworkManager. The scripts
in `ring/` describe the old cabling and are historical; use
`scripts/switched_fabric.py` with the installed selected fabric document for
current checks. Run bandwidth/latency stress only with serving stopped.

## Validation and benchmarks

From this checkout:

```bash
python3 bench/functional.py http://192.168.50.219:8015/v1
python3 bench/cold-needle.py --url http://192.168.50.219:8015 \
  --tokens 131072 --output /tmp/deepseek-needle.json
python3 scripts/run-full-benchmark.py
```

The full runner uses the already-installed LIL v0.6.2 harness and environment
on gx10-r0. It runs the 20-cell sustained grid, burst grid, coding probes and
fresh retrieval through 1M tokens, recording request settings and configuration
hashes. It requires an already healthy selected service and does not change
serving settings. Benchmark traffic affects interactive latency; run when idle.
`bench/indexer-startup-check.py` is the local CPU activation regression check.
Use `--no-hw-monitor` and verify temporary benchmark collectors exit. Fourteen
old detached GPU-polling loops were removed after the October 17 timed comparisons;
never use broad process-name killing to clean up collectors.

### Comparing with public SparkRing results

The runner above uses `lil_matched.py`, which explicitly forces thinking off,
top_p=1 and top_k=-1. The public SparkRing LIL invocation does not apply those
overrides. Both are LIL benchmarks, but the request settings differ.
On October 14, the original build measured 197.67/271.32 tokens/s at 8K C8/C16
with the public invocation; the clean upstream copy was slower at C8.
See the [matched comparison](results/20261014-upstream-baseline/REPORT.md).

The comparison's unmodified LIL 0.7.6 script is pinned at
`~/bench/upstream-baseline-20261014/lil-0.7.6.py` on gx10-r0. Run it directly,
without `lil_matched.py`, with `LLM_BENCH_NO_UPDATE_CHECK=1` and:

```text
--host 192.168.50.219 --port 8015 --model DeepSeek-V4.1-Flash-TP4
--no-hw-monitor --display-mode plain --no-resume --temperature 1
--concurrency 1,2,4,8,16 --contexts 8k,16k,32k,64k,128k
--duration 20 --max-tokens 2048 --coding-peak --output <unique-result.json>
```

The October 17 runtime campaign uses this public 0.7.6 protocol;
`bench/lil_top_p.py` can inject only top_p without changing thinking. The
request-parser audit confirms the server defaults above. Preserve both protocols' labels and raw results. Matching a public command does
not control different hardware clocks, client placement or stochastic variation.

## Installed paths

| Item | Path |
|---|---|
| Selected config | `/etc/deepseek-ring/optimized-specs.json` on spark-r0 |
| Selected plugins | `/usr/local/lib/deepseek-ring/plugins` on each node |
| Selected 1017 checkpoint | `/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash-1017/1bae0e1088993b9b82de08f59de5be5a34e42170` on every node |
| Rollback checkpoint | `/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277` on the two Sparks; GX10 weight shards removed |
| Tuning cache | `/srv/sparkring/sparkring/cache` on every node |
| SparkRing deployment | `/var/lib/sparkring/controller/deployments/deepseek-v41-flash-tp4-iba1b36389e5d` on spark-r0 |
| Retired Qwen source/config and stop compatibility | `~/builds/qwen-tp2` on every node; weights/caches/images removed |
| Benchmark environment | `~/bench` on gx10-r0 |

The switch campaign at
`~/Agent/Diagnostics/deepseek-v41-flash-ring/switch-migration-20261019/`
contains the baseline and candidate selections, exact image IDs, retained
container receipts, and test results. Check the installed root-owned selection
against the current deployment manifest before changing it.

## Rollback on the switch

The software fallback is the same October 17 image and official 1017 checkpoint
with **switched networking**, saved as `baseline-specs.json`. Once the two-shot
candidate is selected, the baseline containers are `ds41-before-switch-baseline-rN`.
Stop all benchmark/client traffic and the fleet before running the private
campaign's `restore_baseline.py`, then use the fixed-action controller to start.
The helper checks current and retained identities; it does not start serving
or change host networking. Update the deployment manifest after a rollback.

The helper accepts the qualified `c1cap3` serving specification even after
external qualification metadata is added. It checks the stopped fallback's
image, complete argument vector, selected environment and mounts before
renaming any container. Root configuration replacement requires the normal
admin method; fixed-action `up`/`down` remain passwordless.

The earlier `ds41-before-images-rN`, `ds41-before-tuning-rN`,
`ds41-rollback-runtime-rN`, `ds41-rollback-1017-rN`, and
`ds41-before-ring-rN` containers encode the **retired physical ring**.
Do not start them or run their historical rollback helpers on this switch.
Their configuration guards intentionally reject the current selection. If an
older runtime or checkpoint is needed, create and qualify a new switched
selection while preserving the current fabric and lifecycle controller.

The previous checkpoint remains verified on the Sparks only; restoring it to
GX10s would require a separate fabric transfer and hash verification. No weight
transfer is needed for the current switched transport fallback. Historical
configuration/weight receipts remain in the prior campaign directories and Git.

The earlier GLM compatibility receipt remains historical. Its checkpoint copies
were subsequently deleted and its startup controls now reject the retirement
marker. A future GLM rebuild must qualify against the current DS selection and
reconcile its workload guards; do not use the historical starter to switch back.
