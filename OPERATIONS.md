# Operating the switched TP4 cluster

**Selected (re-selected 2026-10-24):** DeepSeek-V4.1-Flash-1017 on the
five-draft B12X build (image `9f26f0b3718c…`), selection
`c87a397ccc4614c6f3fee59e566bb7599e7165c80e858bb12c84d78ef5e27775`, containers
`ds41-optimized-rN`, 20 GiB KV per rank, 999 images per request, persistent
0–2350 MHz GPU ceiling. The faster spark-ds41f TileLang selection (`4d2bc32e…`,
image `2fc5565e9c15…`) is a stopped, exact alternative (`ds41-tilelang-rN`).
[Recipe](image/rocenante-switch/README.md),
[comparison](results/20261024-b12x-comparison/REPORT.md).

| Workload | Nodes | API | Model |
|---|---|---|---|
| DeepSeek TP4 | all four | `http://192.168.50.219:8015/v1` | `DeepSeek-V4.1-Flash-TP4` |

DeepSeek needs all four nodes. There is no API key. Never overlap it with
another GPU workload; Qwen and GLM serving on this fleet are retired.

## Cluster control

```bash
cd ~/Agent/Builds/deepseek-v41-flash-spark
./cluster.sh               # TUI: nodes, workload health, actions, live output
./cluster.sh status        # one-shot node and workload status
./cluster.sh up            # start the default workload (asks first)
./cluster.sh down          # stop it (asks first)
./cluster.sh recover       # after a reboot: down, retired mesh off, switch gate, up
./cluster.sh list          # every configured workload action
./cluster.sh run deepseek logs
```

In the TUI, the arrow keys select, `Tab` switches between nodes and
workloads, `Enter` opens the selected item's actions, `PgUp`/`PgDn` scroll
output, `k` stops a running action, `p` pauses polling and `q` quits.
Actions marked `!` ask for confirmation. Node actions (clocks, containers,
memory, kernel events, fabric links) run on the selected node.

The cluster is defined in [`config/cluster.toml`](config/cluster.toml):
nodes, SSH options, polling interval, per-node actions and workloads, each
with a health URL and named commands run locally or on one node. Add a
workload or node by adding a block; point at another file with
`CLUSTER_CONFIG=path ./cluster.sh` or `--config`. The tool needs Python 3.11+
(standard library only). Polling probes every node over SSH (`nvidia-smi`,
`docker ps`); **close the TUI or pause polling during timed benchmarks.**

`scripts/ring-mode.sh ds|recover-ds|stop|status` remains as a non-interactive
compatibility wrapper for the same actions.

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

Thinking is on by default; set `thinking: false` explicitly for ordinary
non-thinking requests and comparable benchmarks. Sampling defaults are
temperature 1 and top_p 1 (DeepSeek's reference). Clients can override them.
Tools, tool continuation, streaming usage and images pass the functional checks.

Context is 1,048,576 tokens with 16 sequences, 8,192 batched tokens and one
concurrent prefill. KV is **20 GiB per rank**
(`--kv-cache-memory-bytes 21474836480`), which overrides the 0.82 memory
fraction. Speculation is DSpark with five greedy drafts, block rejection and a
rule-based draft budget; a single request's first token waits one extra step
for sink rejection (about 0.1 s).

**Images:** up to 999 images per request, counted across the whole
conversation history. Five 1024 px images, 16 and 64 distinct images, six
images in history, streamed follow-ups and recovery after a rejected 1000-image
request all pass. The count is a ceiling, not a memory guarantee: resolution,
context and concurrency still limit large requests. A request with more than
999 images returns HTTP 400 and the engine stays healthy.

## Memory budget

Measure spark-r0 as `MemTotal - MemAvailable`. The startup budget is **at
most about 118 GiB used just after loading**; it is not a runtime stop guard.
The B12X selection started at **117.83 GiB used** on 2026-10-25 with 20 GiB
KV; the other ranks were about 116.8–117.0 GiB. TileLang starts lower, at
109.95 GiB. Docker RSS is not a
valid unified-memory measure. Raising KV further is possible within the
budget but would need a new selection and qualification.

## Lifecycle on spark-r0

```bash
sudo -n /usr/local/sbin/deepseek-ring-control up
sudo -n /usr/local/sbin/deepseek-ring-control down
sudo -n /usr/local/sbin/deepseek-ring-control status
```

These fixed actions have passwordless sudo
([sudoers rule](host/sudoers-deepseek-ring-control)). The root-owned helper
reads `/etc/deepseek-ring/optimized-specs.json`, verifies every container's
image, arguments, environment and mounts, checks addresses, both 200G rails,
MTU, GID 3, jumbo reachability and disabled legacy services, drops caches and
starts `ds41-optimized-r0..r3`. It refuses to start while another container
is running or while `/etc/deepseek-ring/FLARE_STAGING.json` (the shared trial
interlock) exists. Startup takes about 2 minutes with warm caches.

The repository copies of the controller are `scripts/deepseek-ring-control.py`
and `scripts/optimized_vllm.py`; editing them does not change the installed
root-owned files. Keep the installed SparkRing package: its container-spec
library and the loader seccomp profile are still used.

## After a node reboot

Wait for SSH on all four nodes, then `./cluster.sh recover` (or
`scripts/ring-mode.sh recover-ds`). The containers do not start themselves
after a reboot. Restart the fleet together; never restart one rank under
surviving workers.

### Switched link or GID failure

Read the failing node and interface from the gate. Check `ip -br addr`,
`rdma link`, and `/sys/class/infiniband/<hca>/ports/1/gids/3` and
`gid_attrs/types/3`: GID 3 must be the rail's IPv4-mapped address and type
`RoCE v2`. Compare GIDs numerically. Use `nmcli connection show` to find the
current switch profile if a bounce is needed, and stop the fleet first. Do not
bounce management Ethernet, activate `sparkring-*` profiles, run
`netplan apply`, or substitute GID 4.

### Decode slows to roughly half speed

Check clocks **during generation** on every node (TUI node action "GPU
clocks"). After the October 6 reboot, spark-r1 stayed at 611 MHz under load
while drawing 10–14 W; reapplying the ceiling did not help. A clean shutdown
and a 1–2 minute physical disconnect of its power adapter (wall and node)
restored 2320–2333 MHz. Stop the fleet before the intervention, then
`./cluster.sh recover`, verify all four clocks under load and run a short C1
probe. A healthy API alone does not prove normal speed.

## Switched fabric

Each node uses **physical port 1**: two Socket Direct rails sharing one 200G
cable. MTU 9000, IPv4 RoCEv2 GID **3** on both rails.

| Rank | Node | Rail A: enp1s0f1np1 / rocep1s0f1 | Rail B: enP2p1s0f1np1 / roceP2p1s0f1 |
|---|---|---|---|
| 0 | spark-r0 | 10.10.10.1/24 | 10.10.11.1/24 |
| 1 | spark-r1 | 10.10.10.2/24 | 10.10.11.2/24 |
| 2 | gx10-r1 | 10.10.10.4/24 | 10.10.11.4/24 |
| 3 | gx10-r0 | 10.10.10.3/24 | 10.10.11.3/24 |

Never reorder the two GX10 ranks. Host configuration is
`/etc/netplan/40-switch-fabric.yaml`, rendered by NetworkManager, with
`/etc/sysctl.d/60-switch-fabric.conf` ARP policy. Management `enP7s7` is
unchanged. The CRS812 uses 200G-baseCR4 breakout legs, no autonegotiation,
L2MTU 9216 and an isolated hardware-offloaded bridge; QoS/PFC/ECN are not
configured. Full switch setup: `../spark-cluster-network.md`.

The B12X build carries collectives on RoCEnante ABI 8: one-shot all-reduce
below 512 KiB, pipelined two-shot from 512 KiB to 128 MiB, one-shot
all-gather to 16 MiB shards, and a patched NCCL fallback
([recipe](image/rocenante-switch/README.md)). The TileLang alternative uses
sparknet 0.5.0's one-shot collectives in switched clique mode
(`SPARKNET_ROCE_TOPOLOGY=direct`) with patched NCCL 2.30.7. Bandwidth or latency stress needs a stopped fleet.

## Host policy

All four hosts run kernel `7.0.0-1019-nvidia` (4 KiB pages), driver
`580.178.04`. The [clock-policy service](host/systemd/gb10-gpu-clock-cap.service)
applies `nvidia-smi -lgc 0,2350` at boot and reload: a 2350 MHz ceiling with
idle downclocking. After a manual GPU or driver reset run
`sudo systemctl reload gb10-gpu-clock-cap.service`. Stock boost and a 2700 MHz
ceiling did not give a consistent decode gain
([clock receipt](results/20261020-clock-cap/REPORT.md)).
The spark-ds41f recipe's 64 KiB kernel and memory-saver DKMS are **not**
installed or needed for this sizing.

## Validation and benchmarks

```bash
python3 bench/functional.py http://192.168.50.219:8015/v1
python3 bench/cold-needle.py --url http://192.168.50.219:8015 --tokens 128000 --output /tmp/needle.json
python3 results/20261017-image-limit/check_images.py      # writes beside itself; copy it first
```

`cold-needle.py` exits 1 on this build even when it passes: the server omits
`cached_tokens`, so `cold_confirmed` stays false. Read `needle_pass`; the
prompt starts with a fresh nonce, so it cannot hit the prefix cache.

Timed benchmarks use unmodified **LIL 0.7.6**
(`~/Agent/Diagnostics/deepseek-v41-flash-ring/decode-recovery-20261020/external-client`,
SHA-256 `c4c7eaed…9553`) from the Mac, with `LLM_BENCH_NO_UPDATE_CHECK=1`:

```text
--host 192.168.50.219 --port 8015 --model DeepSeek-V4.1-Flash-TP4
--no-hw-monitor --display-mode plain --no-resume --temperature 1
--duration 20 --max-tokens 2048 --coding-peak --output <new-file>.json
focused screen: --concurrency 1,8,16  --contexts 8k,32k
full grid:      --concurrency 1,2,4,8,16 --contexts 8k,16k,32k,64k,128k
```

Keep the Mac on AC power and run long benchmarks under `caffeinate -i`: an
idle sleep during GPQA on 2026-10-24 left 16 streams stalled and 3 requests
failed while the server finished them normally
([comparison](results/20261024-b12x-comparison/REPORT.md)).

Tool-calling quality uses LIL **0.7.7**'s `--tool-eval` (tool-eval-bench at
the community leaderboard settings: hard mode, seed 42, temperature 0,
parallel 4). The pinned script is `results/20261024-tilelang/lil-0.7.7.py`,
kept local and recreated from `lil-0.7.7.source.json` (tag, commit, SHA-256);
its first run installs tool-eval-bench into `~/.cache/llm_decode_bench`.
`results/20261024-tilelang/scripts/qualify.py` runs the gates, screens, grid
and tool-eval with receipts. Keep the fleet free of other traffic, retain raw
results, and compare only matching protocols: C8/C16 are aggregate output
throughput, and short or greedy probes are not the sustained benchmark.

## Switching between B12X and TileLang

B12X is selected. To serve TileLang instead:

```bash
python3 image/tilelang-ds41f/promote.py reselect \
  --selection ../DS41-ds41f-tilelang/results/20261024-promotion/optimized-specs.json \
  --receipts results/reselect-<utc>
```

This is also the TUI action *switch to TileLang selection*. It checks that the
B12X selection is installed, stages and verifies the TileLang selection
(`4d2bc32e…`), stops the controller, renames the B12X containers
`ds41-before-tilelang-rN` and `ds41-tilelang-rN` back to `ds41-optimized-rN`,
installs the selection and starts it. Return to B12X with
`promote.py rollback --receipts results/rollback-<utc>`, which restores
`/etc/deepseek-ring/optimized-specs.pre-tilelang-20261024.json` (`c87a397c…`).
No weight transfer is needed either way. Update `results/deployment.json` and
the docs after any switch.

Each node keeps exactly three DeepSeek containers: the running B12X
`ds41-optimized-rN` (image `ds41-b12x-rollback:20261021`, `9f26f0b3718c…`), the
stopped TileLang `ds41-tilelang-rN` (`2fc5565e9c15…`) and the October 17 switched
baseline `ds41-before-switch-baseline-rN` (image
`ds41-b12x-switch-baseline:20261017`, `a182696cb59f…`), the older-runtime
fallback described in the [switch report](results/20261019-switch-migration/REPORT.md).
All retired trial, probe and ring-era containers and the GLM, FLARE, Mia and
candidate images were removed on 2026-10-24, freeing about 108 GiB
([manifest](results/20261024-tilelang/fleet-cleanup.json)).

## Installed paths

| Item | Path |
|---|---|
| Selected config | `/etc/deepseek-ring/optimized-specs.json` on spark-r0 |
| B12X selection backup | `/etc/deepseek-ring/optimized-specs.pre-tilelang-20261024.json` |
| TileLang selection | `~/Agent/Builds/DS41-ds41f-tilelang/results/20261024-promotion/optimized-specs.json` on the Mac |
| 1017 checkpoint | `/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash-1017/1bae0e1088993b9b82de08f59de5be5a34e42170` on every node |
| Original checkpoint | `/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277` on the two Sparks |
| TileLang cache | `/srv/sparkring/sparkring/cache/ds41f-tilelang-20261024` on every node |
| B12X caches | `/srv/sparkring/sparkring/cache` on every node |
| B12X plugins | `/usr/local/lib/deepseek-ring/plugins` on each node |
| Image build checkout | `~/builds/ds41f-tilelang-20261024/spark-ds41f` on spark-r1 |
| Benchmark client | `~/Agent/Diagnostics/deepseek-v41-flash-ring/decode-recovery-20261020/external-client` on the Mac |

Superseded campaign reports were removed from the active checkout on
2026-10-24 and remain at the Git tag `pre-tilelang-cleanup-20261024`.
