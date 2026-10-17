# Operating the ring

| Mode | Nodes | API | Model |
|---|---|---|---|
| DeepSeek vLLM TP4 | all four | `http://192.168.50.219:8015/v1` | `DeepSeek-V4.1-Flash-TP4` |

DeepSeek needs all four nodes. There are no API keys. Qwen serving on this ring
was retired on 2026-10-12 UTC; the former port-8000 endpoints are no longer
served. The [GLM handoff](../GLM/HANDOFF.md) records the storage cleanup and
GLM assignment. On 2026-10-14 the user requested stopping GLM and restoring
DeepSeek for the HF inference-change audit. DeepSeek is now serving on 8015;
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
4–20 minutes for startup. `recover-ds` first stops workloads and the entire
mesh. Both retired Qwen pair stop entry points remain idempotent for DS recovery.
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

KV uses `--kv-cache-memory-bytes 17716740096`: **16.5 GiB per GPU**, exposing
13,483,747 logical tokens. This **overrides `--gpu-memory-utilization 0.83`**;
changing that fraction alone has no effect while the explicit byte budget is
present. The head's operating ceiling is **118 GiB total used**, measured as
`MemTotal - MemAvailable`, not Docker RSS or GPU allocation alone. Qualification
peaked at 115.10 GiB across startup, concurrency, mixed prefill/decode and
fresh 1M retrieval. Preserve this headroom for growth. The temporary trial abort
guard is no longer running; the allocation is qualified with margin, not an
OS-wide hard limit against unrelated host processes.

The context limit is 1,048,576 tokens, with 16 active sequences. The 8K batch
ceiling controls work per iteration; it is not a per-request reservation. The
adaptive plugin uses 4K steps only when at least four runnable decoders contend
with prefill. Aggregate KV capacity limits simultaneous long contexts.
Greedy byte-repeatability is not guaranteed by this pinned runtime.

## Lifecycle on spark-r0

When no competing model workload is running:

```bash
sudo -n /usr/local/sbin/deepseek-ring-control up
sudo -n /usr/local/sbin/deepseek-ring-control down
sudo -n /usr/local/sbin/deepseek-ring-control status
```

These fixed actions already have passwordless sudo. The root-owned helper
validates recorded images, commands, mounts and plugin hashes, then checks the
mesh before starting `ds41-optimized-r0` through `r3`.
Inspect rank 0 with `docker logs --tail 100 ds41-optimized-r0`.

`status` reports the selected deployment first, then the installer stock
fallback. Stopped stock containers are expected. Its status can also report
missing broad fabric routes; the selected mesh gate and API health check
establish serving readiness. `ds-vllm-stock` remains an emergency fallback,
but its older image predates the compressor-state fidelity fix.

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

Restart the fleet together; do not restart one mesh supervisor under surviving
DeepSeek workers. The selected containers do not serve automatically after
reboot. SparkRing manages NetworkManager fabric profiles; do not reapply the
old setup recipe or netplan snapshots.

### RoCE GID differs after a peer reboot

In the October 6 HST incident, spark-r1 rebooted and gx10-r1's two
counterclockwise interfaces placed IPv4 RoCE v2 in GID **4**, leaving required
GID **3** empty. The checkpoint and images were intact. Restarting supervisors
alone did not repair that allocation.

First stop all workloads and mesh supervisors from the Mac:

```bash
./scripts/ring-mode.sh stop
ssh -o HostName=192.168.50.219 -o ProxyCommand=none spark-r0 \
  'sudo -n /usr/local/sbin/deepseek-ring-control mesh-off'
```

Read the affected node's error:

```bash
ssh -o HostName=192.168.50.192 -o ProxyCommand=none gx10-r1 \
  'journalctl -u sparkring-sparkring-deepseek-v41-flash-adaefa-mesh.service -n 30 --no-pager'
```

For the **same gx10-r1 counterclockwise failure**, run on **gx10-r1**:

```bash
sudo -n nmcli connection down sparkring-sparkring-r2-ccw-primary
sudo -n nmcli connection down sparkring-sparkring-r2-ccw-secondary
sudo -n nmcli connection up sparkring-sparkring-r2-ccw-primary
sudo -n nmcli connection up sparkring-sparkring-r2-ccw-secondary
for hca in rocep1s0f1 roceP2p1s0f1; do
  cat /sys/class/infiniband/$hca/ports/1/gids/3
  cat /sys/class/infiniband/$hca/ports/1/gid_attrs/types/3
done
```

Expected GID 3 values are `0000:0000:0000:0000:0000:ffff:0a0a:010b`
and `0000:0000:0000:0000:0000:ffff:0a0b:010b`, both **RoCE v2**.
Then run `./scripts/ring-mode.sh ds` from the Mac. The mesh gate checks all ranks.

For another node or port, identify its existing `sparkring-*` profile and
expected address first. Do not change the recipe to GID 4 or bounce the
management LAN. `recover-ds` resets supervisors; it does not bounce fabric links.
[Recovery audit](results/recovery-20261007T094058Z/final-audit.json).

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
mesh gate fails. Verify all four clocks under generation and repeat a short C1
probe before declaring recovery. A healthy API alone does not prove normal speed.

## Fabric and host maintenance

Rank order is spark-r0 → spark-r1 → gx10-r1 → gx10-r0 → spark-r0.
Each rank's f0 cable connects to the next rank's f1. Every cable carries two
Socket Direct RoCE planes, `10.10.N.10/11` and `10.11.N.10/11`. MTU is 9000;
IPv4 RoCE v2 uses GID 3. SSH and APIs use the management LAN.

All four hosts run kernel `7.0.0-1019-nvidia`, driver `580.178.04`, with
NetworkManager wait-online enabled. The enabled
[clock-cap service](host/systemd/gb10-gpu-clock-cap.service) applies a 2350 MHz
upper limit before Docker at boot; idle downclocking remains enabled. After a
manual GPU/driver reset, reapply it with:

```bash
sudo systemctl reload gb10-gpu-clock-cap.service
```

Do not restart the mesh while serving or overlap DeepSeek with another model. Avoid
`netplan apply` on GX10s: it can stop NetworkManager. For stopped-fleet fabric
diagnostics, `bash ring/rdma_links.sh` checks direct links;
`ring/mesh_paths.sh` checks hardware-forwarded opposite paths and requires
Bash 4+ on Linux or an explicitly selected newer Bash on the Mac. Do not run
fabric bandwidth/latency tests during serving.

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

The private local `results/20261017-runtime-upgrade/selected-runtime.json`
matches the live selection and is excluded from Git. The earlier
`results/20261017-checkpoint-upgrade/selected-1017.json` records the prior
September GPU runtime on the same 1017 weights. The September 29
`selected-corrected.json` predates the checkpoint update. Preserve these;
never replace the root-owned selection without checking live image identities,
plugin manifests and container state.

## Rolling back the runtime without changing weights

The previous qualified runtime is retained on every node as
`ds41-rollback-runtime-rN`. It uses the SAME official 1017 checkpoint, so no
weight transfer or deletion is needed. Root-owned config backups are on
spark-r0 in `/var/lib/deepseek-ring/experiments/runtime-20261017/`.

After inspecting the current configuration and stopping benchmark traffic,
the campaign helper on the workstation can coordinate the rollback:

```bash
python3 ~/Agent/Diagnostics/deepseek-v41-flash-ring/runtime-20261017/runtime_cutover.py \
  rollback --specs kv-specs.json
```

It checks the known selection, stops the new fleet, restores names and the
previous root config, and starts the old runtime. It refuses an unknown later
selection. Reconcile `results/deployment.json` using the retained
`results/20261017-runtime-upgrade/previous-deployment.json` and update the
operating docs after a rollback. Do not use checkpoint downgrade for an image
or KV-budget problem.

## Rolling back the 1017 checkpoint upgrade

Normal `ds` / `recover-ds` uses the qualified 1017 selection. Do not use
`stock-up` or start the retained `ds41-rollback-1017-rN` containers directly:
the old GX10 weight shards no longer exist. Both Sparks retain verified old
weights and all four original images remain available.

The campaign at `~/Agent/Diagnostics/deepseek-v41-flash-ring/upgrade-1017-20261017/`
contains `cutover.py rollback`, the original/qualified configurations and full
hash/deletion receipts. Inspect current live state and those receipts first.
First roll back the newer runtime as above so this older campaign recognizes
the selection. Its checkpoint rollback action then stops the fleet, restores
old container names and selection, removes only the new GX10 weight shards, copies and hash-verifies
the old shards from adjacent Sparks over the fabric, then starts the old model.
It needs substantial transfer/startup time and must run with all GPU workloads
stopped. Its temporary artifact servers must be cleaned up afterward using
recorded PID/command ownership. Do not overwrite a later unknown selection.

The earlier GLM compatibility receipt remains historical. Its checkpoint copies
were subsequently deleted and its startup controls now reject the retirement
marker. A future GLM rebuild must qualify against the current DS selection and
reconcile its workload guards; do not use the historical starter to switch back.
