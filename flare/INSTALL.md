# Install on your own GB10 cluster

How to run DeepSeek-V4.1-Flash-1017 at TP4 with FLARE on any four GB10 nodes
(DGX Spark, ASUS GX10 or similar), the way this fleet does, with the
problems we hit already worked around. It follows the publisher's
[TP4 README](https://huggingface.co/local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE/blob/gb10/README.md);
where this guide differs, it says why. [README.md](README.md) in this folder
covers our own fleet.

The examples call the nodes **`spark1`** to **`spark4`**, the Orbit cluster
**`sparks`** and the group **`deepseek`**, as the publisher does. `spark1` is
the controller: it downloads the model, runs rank 0 and serves the API.
Replace the names with yours.

## What you need

| | |
|---|---|
| Nodes | Four GB10 nodes with 128 GB, DGX OS (Ubuntu) and the NVIDIA driver. Sparks and GX10s can be mixed. |
| Fabric | RoCE between all four: a switch or direct cables. Agents need TCP 29900 between nodes, peers need TCP 29800 on `spark1`, and clients need the API port. |
| Disk | About **1 TB free on `spark1`** (the download is 477 GiB and staging peaks near twice that) and **about 270 GiB free on each peer** (each rank's 261 GiB share). |
| Workstation | SSH keys to all four nodes as the same user, and Python 3.11+ for `./cluster.sh`. |
| Time | About 2–2.3 hours of download at 70–100 MB/s, then about 14 minutes for the first launch. |

Serving needs no Docker, Python or root. Root is only needed to install the
APT package and to enable lingering.

## 0. Coming from vLLM

FLARE needs the GPUs and most of the memory to itself:

```bash
docker ps                          # on every node: stop the vLLM containers
docker stop CONTAINER ...
nvidia-smi                         # no processes left on any GPU
df -h ~                            # check the free space above
```

Keep the vLLM images if you want to switch back. On nodes with small disks,
the vLLM checkpoint copies may have to go to make room (our 916 GB GX10s only
fit after we removed theirs).

## 1. Install FLARE on every node

```bash
sudo apt update && sudo apt install ca-certificates curl
sudo install -d -m 0755 /etc/apt/keyrings
sudo curl -fsSLo /etc/apt/keyrings/lil-flare-archive.asc https://ppa.local-inference-lab.ai/lil-flare-archive.asc
sudo curl -fsSLo /etc/apt/sources.list.d/flare.sources https://ppa.local-inference-lab.ai/flare.sources
gpg --show-keys --with-fingerprint /etc/apt/keyrings/lil-flare-archive.asc
#   expect 22C4 6BE0 A4C3 F708 F74C  1E75 213A 79D3 3E50 FC06
sudo apt update && sudo apt install flare-inference
```

Install the same version on all four nodes.

## 2. Start the agents

On every node, as your ordinary user (not root):

```bash
mkdir -p ~/.config/systemd/user/flare-agent.service.d
printf '[Service]\nLimitNOFILE=65536\nLimitMEMLOCK=infinity\n' \
  > ~/.config/systemd/user/flare-agent.service.d/limits.conf
sudo loginctl enable-linger "$USER"
flare agent install --listen 0.0.0.0:29900
```

- **The limits file is not in the publisher's guide.** The default limit of
  1024 open files fails on the full package.
- **Lingering** lets the agent start at boot without a login.
- **Listen on `0.0.0.0`**, not on one address. FLARE streams over every RoCE
  rail, and an agent bound to one rail refuses connections on the other
  (`cannot reach fabric agent … Connection refused`).
- On a trusted local network you can add `--accept-first`, so the first
  controller to pair is accepted. Otherwise, note the join code each agent
  prints.

## 3. Pair the nodes

On `spark1`:

```bash
flare orbit pair spark1 spark2 spark3 spark4        # with --accept-first agents
flare orbit pair spark2 --code CODE                 # otherwise, once per node
```

Check the fingerprints against the ones the agents printed. Then add this
block **once** to `~/.config/flare/orbit.toml`, keeping the records that
pairing wrote:

```toml
[cluster.sparks]
nodes = ["spark1", "spark2", "spark3", "spark4"]
```

The order assigns ranks 0 to 3. Never reorder it after the first launch,
because each rank's share is cached on its node.

```bash
flare orbit status --cluster sparks                 # all four agents, GPUs and free disk
```

## 4. Download the model once

On `spark1`, into a **dedicated folder**:

```bash
flare download local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE --revision gb10 \
  --filename model.safetensors --tensor-parallel 4 --model-cache ~/flare-models
flare models list --plain --model-cache ~/flare-models
```

The current package (commit `ab4f07af`, 2026-10-30) needs
`flare-inference` **0.1.0~git20261030013211.a161b17f-1 or newer**. Older
builds can't load it.

**Always pass `--model-cache`.** The default store, `~/.cache/flare/packages`,
is also the agent's own cache folder, and the agent deletes everything there
after a transfer. We lost a finished 490 GiB download that way
([NVIDIA/spark-local-inference#119](https://github.com/NVIDIA/spark-local-inference/issues/119)).
Optionally, make a hardlinked backup that takes no extra space:
`cp -al ~/flare-models ~/flare-models.keep`.

Accept the publisher and model license when prompted.

## 5. Launch

From a clone of this repository on your workstation:

```bash
ssh spark1 'FLARE_HEAD=spark1 FLARE_CLUSTER=sparks FLARE_GROUP=deepseek FLARE_PORT=8000 bash -s' < flare/launch.sh
```

[`launch.sh`](launch.sh) creates a **persistent** group from the newest
version in `~/flare-models`, with the publisher's TP4 flags plus the settings
below. It replaces an existing group of the same name.

| Variable | Default | Meaning |
|---|---|---|
| `FLARE_HEAD` | `spark-r0` | the controller's name in `orbit.toml` |
| `FLARE_CLUSTER` | `ds41` | the `[cluster.NAME]` block |
| `FLARE_GROUP` | `ds41-flare` | the group name used to start and stop it |
| `FLARE_MODELS` | `~/flare-models` | the `--model-cache` from step 4 |
| `FLARE_PORT` | `8015` | the API port (the publisher uses 8000) |
| `FLARE_MODEL_NAME` | `DeepSeek-V4.1-Flash-TP4` | the model name clients send |
| `FLARE_MEMORY_LIMIT` | `-2G` | memory to leave free on each node |
| `FLARE_VERIFY_ALPHA` | `0.5` | `--mtp-adaptive-verification-alpha`; `1.0` is FLARE's default scoring |

- **The memory reserve:** `-2G` leaves 2 GiB free on each node instead of the
  package's default reserve. That gives 17.9 GiB of KV cache per GPU
  (20.9 million tokens) instead of about 10.6 GiB, with about 111.5 GiB in
  use after loading. If the nodes run anything else, use a larger reserve such as
  `FLARE_MEMORY_LIMIT=-8G`.
- **Verification alpha 0.5** is the publisher's recommendation. On our
  cluster it raised decode with 8 concurrent requests by 7–9% and changed
  nothing measurable at 1, 4 or 16.
- **The first launch** sends every peer its 261 GiB share over the fabric and
  verifies it, which took us about 14 minutes. Later starts reuse the copy and
  take under 30 seconds.
- **Don't run `flare orbit push` first.** It stores a separate copy that
  `orbit run` doesn't use, so each peer briefly holds two copies of its share.

Watch startup (Ctrl-C detaches without stopping the ranks), then test:

```bash
ssh -t spark1 flare orbit attach deepseek --cluster sparks
curl --fail http://spark1:8000/health
python3 bench/functional.py http://spark1:8000/v1
```

## 6. The cluster TUI

```bash
cp config/cluster.example.toml config/cluster.local.toml
```

Edit the node names, addresses and `ssh_user` in
`config/cluster.local.toml`, plus the cluster, group and port if you changed
them. `./cluster.sh` uses this file when it exists, and Git ignores it, so
`git pull` won't conflict with it.

```bash
./cluster.sh              # TUI: nodes, health, actions, live output
./cluster.sh status
./cluster.sh up           # start the saved group
./cluster.sh down         # stop it
./cluster.sh recover      # after a reboot, once SSH answers on all four
```

**After a reboot, nothing serves until you run `recover` (or `up`).** The
agents start at boot, but they don't restart groups.

## Upgrading

FLARE updates often. Stop the group, upgrade every node, reinstall every
agent, then start:

```bash
./cluster.sh down
sudo apt update && sudo apt install --only-upgrade flare-inference   # every node
flare agent install --listen 0.0.0.0:29900                           # every node, as your user
./cluster.sh up
```

APT doesn't restart the agent, which runs its own copy in
`~/.local/lib/flare-agent/flare`. Keep the controller and all agents on one
release: `sha256sum /usr/bin/flare ~/.local/lib/flare-agent/flare` should
match on every node.

**A new package version** may need a newer FLARE first. Download it while the
old one serves, upgrade every node, then stop the group, reinstall the
agents, remove the old version from every node, and launch:

```bash
flare models list --plain --model-cache ~/.cache/flare          # on each peer: find the old version
flare models remove checkpoint-expanded-scales@OLD --model-cache ~/.cache/flare
flare models remove checkpoint-expanded-scales@OLD --model-cache ~/flare-models   # on spark1
flare models gc --model-cache ~/flare-models                    # frees the old version's data
```

`flare models remove` only deletes the version's folder; `gc` frees its data.
If you keep a `cp -al` backup of `~/flare-models`, delete it before `gc` and
make it again afterwards, or the old data stays on disk.

## Using the API

- **Thinking is on by default.** Turn it off per request with
  `"chat_template_kwargs": {"enable_thinking": false}`. vLLM's
  `{"thinking": false}` is rejected with HTTP 400.
- **Temperature and top_p are fixed at 1** by the package, and
  `temperature: 0` is rejected. The default seed is 0, so identical requests
  give identical replies. Pass a `seed` for variety.
- **Known issue:** short chats in thinking mode can get stray tokens spliced
  into the reply, sometimes `<ds_safety>…` text. It only happens while the
  reply is still in the first 128 tokens of the context
  ([NVIDIA/spark-local-inference#118](https://github.com/NVIDIA/spark-local-inference/issues/118)).
  `enable_thinking: false` or a longer system prompt avoids it.

More client notes: [README.md](README.md#client-notes).

## What to skip in this repository

These parts are specific to our fleet:

- `scripts/fabric_check.py`, `scripts/fabric_repair.py`,
  `scripts/deepseek-ring-control.py`, `scripts/ring-mode.sh` and
  `host/sudoers-deepseek-ring-control`: our switch, rail names and root
  helper.
- `host/systemd/gb10-gpu-clock-cap.service` is optional: it caps the GPU
  clock at 2350 MHz (`nvidia-smi -lgc 0,2350`). In our vLLM tests, higher clocks
  used about 40% more power without a consistent decode gain.
- `image/` and the vLLM entries in `results/`: the retired vLLM builds.
