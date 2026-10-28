# Operating the switched TP4 cluster

**Selected (2026-10-27):** DeepSeek-V4.1-Flash-1017 on **FLARE**
`flare-inference 0.1.0~git20261027170349.7c22369f-1`, package
`local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE@gb10` (commit `607c1abf`,
deployment `0a377833…`), persistent Orbit group `ds41-flare` controlled from
spark-r0, 16.6 GiB KV per GPU (19,306,112 tokens), persistent 0–2350 MHz GPU
ceiling. [FLARE guide](flare/README.md),
[cutover report](results/20261027-flare/REPORT.md).

| Workload | Nodes | API | Model |
|---|---|---|---|
| DeepSeek TP4 | all four | `http://192.168.50.219:8015/v1` | `DeepSeek-V4.1-Flash-TP4` |

DeepSeek needs all four nodes. There is no API key. Never overlap it with
another GPU workload; vLLM (B12X, TileLang), Qwen and GLM serving on this
fleet are retired.

## Cluster control

```bash
cd ~/Agent/Builds/deepseek-v41-flash-spark
./cluster.sh               # TUI: nodes, workload health, actions, live output
./cluster.sh status        # one-shot node and workload status
./cluster.sh up            # start the FLARE group (asks first)
./cluster.sh down          # stop it (asks first)
./cluster.sh recover       # after a reboot: stop leftovers, GID 3 check, start
./cluster.sh list          # every configured workload action
./cluster.sh run deepseek logs
```

In the TUI, the arrow keys select, `Tab` switches between nodes and
workloads, `Enter` opens the selected item's actions, `PgUp`/`PgDn` scroll
output, `k` stops a running action, `p` pauses polling and `q` quits.
Actions marked `!` ask for confirmation. Node rows show running containers
and GPU processes (`flare:rN` is a FLARE rank). Node actions (clocks, GPU
processes, FLARE agent, containers, memory, kernel events, fabric links) run
on the selected node.

The cluster is defined in [`config/cluster.toml`](config/cluster.toml):
nodes, SSH options, polling interval, per-node actions and workloads, each
with a health URL and named commands run locally or on one node. Point at
another file with `CLUSTER_CONFIG=path ./cluster.sh` or `--config`. The tool
needs Python 3.11+ (standard library only). Polling probes every node over
SSH (`nvidia-smi`, `docker ps`); **close the TUI or pause polling during
timed benchmarks.**

`scripts/ring-mode.sh ds|recover-ds|stop|status` remains as a non-interactive
wrapper for the same actions.

## Lifecycle

The workload actions run on spark-r0 as `nero`; no root is involved:

```bash
flare orbit run --name ds41-flare --cluster ds41 --detach   # start (up)
flare orbit stop ds41-flare --cluster ds41                  # stop (down)
flare orbit ls --cluster ds41                               # group state per rank
flare orbit status --cluster ds41                           # agents, GPUs, free disk
flare orbit attach ds41-flare --cluster ds41                # rank output; Ctrl-C detaches
```

The saved group in spark-r0's `~/.config/flare/orbit.toml` holds the package
path, serving flags and endpoint; [`flare/launch.sh`](flare/launch.sh)
recreates it for a new package or flag change. Each node runs the user
service `flare-agent` (port 29900 on all interfaces, `LimitNOFILE=65536`);
agents start at boot through lingering but do not restart groups. Startup
with cached packages takes under 30 seconds; a package's first launch copies
each peer's 264 GiB share over the fabric first (about 15 minutes). Installing,
downloading, upgrading and storage rules are in the
[FLARE guide](flare/README.md).

The root controller `/usr/local/sbin/deepseek-ring-control` on spark-r0 is
no longer used to serve. The installed copy (Oct 20) still has passwordless
`up`, `down`, `status`; do **not** run `up`: it starts the retired B12X
containers, which cannot load on the GX10s. The repository copy refuses `up`
and adds `fabric-check` and `fabric-repair`, but is not installed (installing
needs root on spark-r0: copy `scripts/deepseek-ring-control.py` to
`/usr/local/sbin/deepseek-ring-control`, `scripts/fabric_repair.py` to
`/usr/local/lib/deepseek-ring/`, and the
[sudoers rule](host/sudoers-deepseek-ring-control) to `/etc/sudoers.d/`).

## Using DeepSeek

```bash
curl http://192.168.50.219:8015/v1/chat/completions \
  -H 'Content-Type: application/json' -d '{
    "model": "DeepSeek-V4.1-Flash-TP4",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 1024,
    "chat_template_kwargs": {"enable_thinking": false}
  }'
```

- Thinking is on by default. Turn it off with `enable_thinking: false` or
  `"thinking_mode": "chat"`; vLLM's `{"thinking": false}` returns HTTP 400.
  `reasoning_effort` is accepted.
- The package declares temperature 1 and top_p 1 (DeepSeek's reference) as
  fixed. Other values such as 0.6 are accepted without error; `temperature: 0`
  is rejected. The default `seed` is 0, so identical requests return
  identical text; send a `seed` to vary.
- Context 1,048,576 tokens, 32 concurrent requests, 4,096-token prefill
  chunks, MTP with up to five drafts and adaptive verification.
- Tools, tool continuation, streaming usage and images pass the functional
  checks. A forced named `tool_choice` is enforced: if the model does not
  produce the call the request fails with HTTP 500 (`required tool choice was
  not satisfied`); the server stays healthy.
- Images: 1000 distinct small images in one request (185K prompt tokens) and
  four 1024 px images pass; the limit is context and memory, not a count.
- **Known issue:** occasional spliced stray tokens in short chat replies, once
  the model's internal `<ds_safety>` annotation
  ([report](results/20261027-flare/REPORT.md#known-issue-stray-tokens)).

## Memory budget

Measure spark-r0 as `MemTotal - MemAvailable`. The startup budget is **at
most about 118 GiB used just after loading**; it is not a runtime stop guard.
FLARE plans KV from free memory: with `--memory-limit=-2G` (a 2 GiB reserve
per GPU) the startup `Plan cache` line reads about 89 GiB loaded and 16.6 GiB
cache per GPU, and spark-r0 used **110.86 GiB** with 10.8 GiB available
(other ranks 111.1–111.3 GiB). The Engram row cache (1 GiB) and resident
scales (about 1.4 GiB) come out of the same memory. A smaller reserve raises KV
one-for-one out of that headroom; `--kv-cache-limit context` shrinks it to one
1M context.

## After a node reboot

Wait for SSH on all four nodes, then `./cluster.sh recover` (or
`scripts/ring-mode.sh recover-ds`). It stops any leftover group, runs the
read-only GID 3 check on all eight rails (`scripts/fabric_check.py`) and
starts `ds41-flare`. `flare orbit status --cluster ds41` shows whether every
agent is back. Restart the fleet together; never restart one rank under
surviving ranks.

### Switched link or GID failure

FLARE connects RoCE on both rails to every peer at startup. If a start fails
in "Connect RoCE transport" or a running group reports RDMA errors, run
`./cluster.sh run deepseek "fabric check"`. Check `ip -br addr`, `rdma link`,
and `/sys/class/infiniband/<hca>/ports/1/gids/3` and `gid_attrs/types/3`:
GID 3 must be the rail's IPv4-mapped address and type `RoCE v2`. Compare GIDs
numerically. Do not bounce management Ethernet, activate `sparkring-*`
profiles, run `netplan apply`, or substitute GID 4.

A switch-side link drop can re-register the IPv4 RoCEv2 GID at index 4 and
leave index 3 empty on every rail. On 2026-10-26 all eight rails dropped at
15:01:36 UTC for about 50 s; the idle vLLM engine then failed with
`RDMA write to rank 3 failed: transport retry counter exceeded`. The TUI's
**repair fabric** action stops the group, bounces only rails whose GID 3 is
wrong (their active profile must be `netplan-<interface>`), waits for GID 3
and restarts the group. It needs the root controller's `fabric-repair`
installed (see Lifecycle); until then, repair by hand with the group stopped:
`sudo nmcli connection down id netplan-<iface> && sudo nmcli connection up id netplan-<iface>`
on the affected node. A rail that stays wrong after a bounce, or has no
active profile, points to the cable or switch port.

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

FLARE's Orbit rendezvous is `10.10.10.1:29800` (rail A); ranks connect RoCE
over both rails per peer, and package transfers stream TCP over both rails
(agents must listen on all interfaces). Bandwidth or latency stress needs a
stopped fleet.

## Host policy

All four hosts run kernel `7.0.0-1019-nvidia` (4 KiB pages), driver
`580.178.04`. The [clock-policy service](host/systemd/gb10-gpu-clock-cap.service)
applies `nvidia-smi -lgc 0,2350` at boot and reload: a 2350 MHz ceiling with
idle downclocking. After a manual GPU or driver reset run
`sudo systemctl reload gb10-gpu-clock-cap.service`. Stock boost and a 2700 MHz
ceiling did not give a consistent decode gain on vLLM
([clock receipt](results/20261020-clock-cap/REPORT.md)); under FLARE all
four nodes run 2327–2333 MHz under load. `flare-inference` comes from
`ppa.local-inference-lab.ai`; upgrade all four nodes and their agents together
([guide](flare/README.md#upgrade)).

## Validation and benchmarks

```bash
python3 bench/functional.py http://192.168.50.219:8015/v1
python3 bench/cold-needle.py --url http://192.168.50.219:8015 --tokens 128000 --output /tmp/needle.json
python3 results/20261027-flare/check_images.py
```

`functional.py` and `cold-needle.py` use FLARE's request options
(`enable_thinking`, package sampling). `cold-needle.py` exits 1 even when it
passes: FLARE reports `cached_tokens: 1` (the BOS token), so `cold_confirmed`
stays false. Read `needle_pass`; the prompt starts with a fresh nonce, so it
cannot hit the prefix cache.

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

LIL finds no Prometheus metrics on FLARE and measures from the OpenAI stream
(`openai_continuous_usage`), as it did for vLLM's headline numbers. Keep the
Mac on AC power and run long benchmarks under `caffeinate -i`: an idle sleep
during GPQA on 2026-10-24 left 16 streams stalled.

Tool-calling quality uses LIL **0.7.7**'s `--tool-eval` (tool-eval-bench at
the community leaderboard settings: hard mode, seed 42, temperature 0,
parallel 4); the pinned script is `results/20261024-tilelang/lil-0.7.7.py`.
FLARE rejects temperature 0, so a FLARE tool-eval needs that setting changed
and is not directly comparable with the vLLM scores. Keep the fleet free of
other traffic, retain raw results, and compare only matching protocols: C8/C16
are aggregate output throughput, and short probes are not the sustained
benchmark.

## Retired vLLM builds

The five-draft B12X selection (`c87a397c…`, image `9f26f0b3718c…`, production
until 2026-10-27) and the TileLang selection (`4d2bc32e…`, image
`2fc5565e9c15…`) are retired. Each node still has their stopped containers
(`ds41-optimized-rN`, `ds41-tilelang-rN`, `ds41-before-switch-baseline-rN`) and
images (about 73 GB per node), and `/etc/deepseek-ring/optimized-specs.json`
still holds the B12X selection. The GX10 copies of the 1017 checkpoint (476 GB
each) were deleted on 2026-10-27 so each GX10 could hold FLARE's 264 GiB share;
manifests are in `~/Agent/Diagnostics/deepseek-v41-flash-ring/20261027-flare-cutover/`.
Restoring vLLM would mean stopping FLARE, copying the checkpoint back from a
Spark over the fabric (about 510 GB per GX10, as on 2026-10-20) and removing
or relocating FLARE data on the GX10s. The B12X and TileLang procedures are in
`image/` and at the Git history of this file.

## Installed paths

| Item | Path |
|---|---|
| FLARE package (rank 0, source) | `~/flare-models/models/checkpoint-expanded-scales/gb10-tp4-202610271726` on spark-r0 |
| Hardlink snapshot | `~/flare-models.keep` on spark-r0 |
| Rank packages | `~/.cache/flare/models/checkpoint-expanded-scales/gb10-tp4-202610272052` on spark-r1, gx10-r1, gx10-r0 |
| Orbit file, controller key | `~/.config/flare/orbit.toml`, `~/.config/flare/orbit/controller.key` on spark-r0 |
| Agent | `~/.local/lib/flare-agent/flare`, `~/.config/systemd/user/flare-agent.service.d/limits.conf` on every node |
| Logs | `~/flare-logs/` on spark-r0 (download, push, launch) |
| 1017 checkpoint (vLLM format) | `/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash-1017/1bae0e1088993b9b82de08f59de5be5a34e42170` on the two Sparks only |
| Original checkpoint | `/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277` on the two Sparks |
| Retired vLLM selection | `/etc/deepseek-ring/optimized-specs.json` on spark-r0 (B12X; used for its fabric definition) |
| Benchmark client | `~/Agent/Diagnostics/deepseek-v41-flash-ring/decode-recovery-20261020/external-client` on the Mac |

Superseded campaign reports were removed from the active checkout on
2026-10-24 and remain at the Git tag `pre-tilelang-cleanup-20261024`.
