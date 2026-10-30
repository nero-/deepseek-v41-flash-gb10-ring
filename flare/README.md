# FLARE on this fleet

DeepSeek-V4.1-Flash-1017 is served by **FLARE** (`flare-inference`, Local
Inference Lab) from the signed TP4 package
[`local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE@gb10`](https://huggingface.co/local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE/tree/gb10).
It follows the publisher's [TP4 README](https://huggingface.co/local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE/blob/gb10/README.md)
and [SPARK-DS4-GUIDE](https://huggingface.co/local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE/blob/gb10/SPARK-DS4-GUIDE.md),
with the site differences listed below. Serving needs no Docker, Python or
root: an APT package, a user-level agent on every node, and one controller.
To set up another cluster, use [INSTALL.md](INSTALL.md) instead.

| Role | Where |
|---|---|
| Controller, rank 0, API | spark-r0 (`~/.config/flare/orbit.toml`, key `~/.config/flare/orbit/controller.key`) |
| Ranks 1–3 | spark-r1, gx10-r1, gx10-r0, in that order (never reorder the GX10s) |
| Cluster | `ds41` in `orbit.toml` |
| Group | persistent `ds41-flare` (package, flags and endpoint saved in `orbit.toml`) |
| Agents | user service `flare-agent` on every node, `0.0.0.0:29900`, lingering enabled |
| Rendezvous | `10.10.10.1:29800` (rail A); RoCE uses both rails per peer |
| API | `http://192.168.50.219:8015/v1`, model `DeepSeek-V4.1-Flash-TP4` |

## Day to day

Use `./cluster.sh` (actions `start`, `stop`, `recover`, `status`, `logs`,
`packages`, `fabric check`). The underlying commands, on spark-r0:

```bash
flare orbit run --name ds41-flare --cluster ds41 --detach   # start the saved group
flare orbit stop ds41-flare --cluster ds41                  # stop (rank zero first)
flare orbit ls --cluster ds41                               # group and rank state
flare orbit status --cluster ds41                           # agents, GPUs, free disk
flare orbit attach ds41-flare --cluster ds41                # follow output; Ctrl-C detaches only
flare orbit dashboard --cluster ds41                        # live metrics (interactive)
```

Agents start at boot, but they do **not** restart groups: after a reboot run
`./cluster.sh recover`. A start with cached packages takes under 30 seconds (26 s right after a reboot);
the API answers `/health` 200 when rank zero serves.

## Install or rebuild a node

1. **APT package** (needs sudo; the Sparks ask for a password, the GX10s do not):

   ```bash
   sudo install -d -m 0755 /etc/apt/keyrings
   sudo curl -fsSLo /etc/apt/keyrings/lil-flare-archive.asc https://ppa.local-inference-lab.ai/lil-flare-archive.asc
   sudo curl -fsSLo /etc/apt/sources.list.d/flare.sources https://ppa.local-inference-lab.ai/flare.sources
   gpg --show-keys --with-fingerprint /etc/apt/keyrings/lil-flare-archive.asc
   #   expect 22C4 6BE0 A4C3 F708 F74C  1E75 213A 79D3 3E50 FC06
   sudo apt update && sudo apt install flare-inference
   ```

2. **Agent limits.** Keep `~/.config/systemd/user/flare-agent.service.d/limits.conf`:

   ```ini
   [Service]
   LimitNOFILE=65536
   LimitMEMLOCK=infinity
   ```

   The default 1024 open files fails on the full package.

3. **Agent**, as `nero`, listening on all interfaces:

   ```bash
   /usr/bin/flare agent install --listen 0.0.0.0:29900
   ```

   Pushes and launches stream over **both** rails (`10.10.10.x` and
   `10.10.11.x`); an agent bound to one rail's address refuses the other
   (`cannot reach fabric agent 10.10.11.1:29900 … Connection refused`). The
   port is also open on management Ethernet; agents accept only paired
   controller keys. A new node is paired from spark-r0 with
   `flare orbit pair NODE --code CODE` and must be added to `[cluster.ds41]` in
   rank order.

## Download a package

Download on spark-r0 into a **dedicated model store**, never the default
`~/.cache/flare/packages`:

```bash
flare download local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE --revision gb10 \
  --filename model.safetensors --tensor-parallel 4 --model-cache /home/nero/flare-models
flare models list --plain --model-cache /home/nero/flare-models
cp -al ~/flare-models ~/flare-models.keep        # hardlink snapshot, no extra space
```

- `--filename` is required (the revision has many `.safetensors` companions)
  and `--tensor-parallel 4` selects the TP4 deployment.
- A fresh download is about 525 GB from Hugging Face (2–2.3 hours at
  70–100 MB/s), and staging peaks near twice that on spark-r0. An update
  reuses unchanged files already in the store: the 2026-10-30 package
  (`ab4f07af`, **476.8 GiB**) fetched 309 GB in 95 minutes.
- The new CLI can download before the nodes are upgraded: `apt-get download
  flare-inference=VERSION` and `dpkg-deb -x` into a folder in `~`, then run
  its `usr/bin/flare download …`. The old version keeps serving meanwhile.
- On 2026-10-27 an `ec0a3126` agent deleted a finished download that lived
  in `~/.cache/flare/packages` ("removed superseded … blobs/models/…"): the
  agent and `flare download` share that default root. `~/flare-models` is
  outside the agents' store; the snapshot guards against a repeat.

## Launch (new package or changed flags)

```bash
ssh spark-r0 'bash -s' < flare/launch.sh
```

[`launch.sh`](launch.sh) recreates the persistent group from the newest
version in `~/flare-models`. Rank zero reads the package in place; on the first
launch every peer receives and verifies its **261 GiB** share over the fabric
(about 1.7 GB/s out of spark-r0, 13–14 minutes with verification) into
`~/.cache/flare/models/…` and reuses it afterwards. The share is staged in
`~/.cache/flare/staging` and then moved, so it needs its own size free, not
twice that.

**Do not `flare orbit push` first.** Push stores a separate
`~/.cache/flare/packages/<deployment>-rankN` copy that `orbit run` does not
use: run copies the data again, so each GX10 briefly held two 264 GiB copies
(145 GB free). Remove such leftovers once the group is serving.

Site differences from the publisher's launch command:

| Setting | Here | Publisher | Why |
|---|---|---|---|
| `--port` | 8015 | 8000 | existing clients |
| `--served-model-name` | `DeepSeek-V4.1-Flash-TP4` | package name | existing clients |
| `--memory-limit` | `-2G` | package reserve | 17.9 GiB KV per GPU, **20,942,336 tokens** (default about 10.6 GiB, 12.1M) |
| `--persistent --name ds41-flare` | yes | optional | restart by name |

The publisher's command also has `--mtp-adaptive-verification-alpha 0.5`,
which `launch.sh` uses (`FLARE_VERIFY_ALPHA=1.0` restores the default
scoring). Here it raised C8 decode by 7–9% and left C1, C4 and C16 within
noise ([update report](../results/20261030-flare-ab4f07af/REPORT.md)).

The startup `Plan cache` line reports per GPU about 88.1–88.5 GiB loaded and
17.9–18.3 GiB cache budget. Head memory after loading is 111.5 GiB used
(`MemTotal - MemAvailable`), within the 118 GiB budget, with 10.2 GiB
available. A smaller reserve buys more KV directly out of that headroom.

## Upgrade

Updates arrive often (three builds on 2026-10-27). Stop, upgrade every node,
reinstall every agent, start:

```bash
./cluster.sh down
sudo apt update && sudo apt install --only-upgrade flare-inference      # every node
/usr/bin/flare agent install --listen 0.0.0.0:29900                      # every node, as nero
./cluster.sh up
```

APT does not restart the agent; the agent runs its own copy in
`~/.local/lib/flare-agent/flare`. Keep the controller, all agents and the
package on one release: check with
`sha256sum /usr/bin/flare ~/.local/lib/flare-agent/flare` on each node.
The package has no install scripts, so upgrading APT on a node while the
group serves is safe; only the agent reinstall stops it.

### New package

A package revision can require a newer `flare-inference` (`ab4f07af` needs
`a161b17f` or later). In this order:

1. Download it into `~/flare-models` while the old version serves (see
   above).
2. Upgrade APT on every node.
3. `./cluster.sh down`, reinstall every agent, then **remove the old
   version** from every node before launching the new one:

   ```bash
   # peers (spark-r1, gx10-r1, gx10-r0)
   flare models remove checkpoint-expanded-scales@OLD_PEER_VERSION --model-cache ~/.cache/flare
   # spark-r0
   flare models remove checkpoint-expanded-scales@OLD_VERSION --model-cache ~/flare-models
   rm -rf ~/flare-models.keep
   flare models gc --model-cache ~/flare-models     # remove only frees the version folder, not its blobs
   cp -al ~/flare-models ~/flare-models.keep
   ```

   `flare models list --plain --model-cache …` shows the version names.
   Removing the old version first is the user's preference, even though the
   GX10s can hold both versions.
4. `ssh spark-r0 'bash -s' < flare/launch.sh`, then run the validation in
   `OPERATIONS.md`.

## Disk

| Node | FLARE data | Free (2026-10-30) |
|---|---|---|
| spark-r0 | `~/flare-models` 477 GiB (+ `.keep` hardlinks) | 1,755 GiB |
| spark-r1 | `~/.cache/flare/models` 261 GiB | 2,043 GiB |
| gx10-r1 / gx10-r0 | `~/.cache/flare/models` 261 GiB each | 409 / 413 GiB |

Each rank stores its layer shards plus **both full Engram tables** (about
183 GiB). The GX10s (916 GB disks) only fit after their vLLM 1017 checkpoints
were removed. Remove the old version before launching a new one (see
[New package](#new-package)).

## Client notes

- Thinking is on by default. Turn it off with
  `"chat_template_kwargs": {"enable_thinking": false}` (or
  `"thinking_mode": "chat"`). vLLM's `{"thinking": false}` is rejected with
  HTTP 400 `unsupported DeepSeek prompt option: thinking`.
- The package fixes temperature 1 and top_p 1; `temperature: 0` is rejected.
  The default `seed` is 0, so identical requests give identical outputs; pass
  a `seed` for varied samples.
- A forced named `tool_choice` returns HTTP 500 (`required tool choice was not
  satisfied`) when the model does not produce the call; it is enforced, not
  constrained. A forced call that fits the question works with thinking on or
  off.
- Images: 1000 distinct 64 px images in one request (185,021 prompt tokens)
  and four 1024 px images pass; the limit is context and memory, not a count.
- Known issue: about 2 of 60 short chat replies contained spliced stray tokens,
  once the model's internal `<ds_safety>…` annotation. These come from
  context-free logits at a few positions below 128 tokens when the thinking-mode
  `Reasoning Effort` header is present; `enable_thinking: false` avoids it. Still
  present with package `ab4f07af` on `a161b17f`. See
  [the report](../results/20261027-flare/REPORT.md#known-issue-stray-tokens)
  and [upstream #118](https://github.com/NVIDIA/local-inference/issues/118).
- `flare download` must not use the default `~/.cache/flare/packages`: the agent
  evicts everything there after a transfer
  ([upstream #119](https://github.com/NVIDIA/local-inference/issues/119)).
