# Operating the ring

Four GB10 nodes, one fabric, two kinds of workload:

| Mode | Nodes | API | Model name |
|---|---|---|---|
| SparkRing vLLM TP4 | all four | `http://192.168.50.219:8015/v1` | `DeepSeek-V4.1-Flash-TP4` |
| Qwen3.8 TP2, Spark pair | spark-r0 + spark-r1 | `http://192.168.50.219:8000/v1` | `qwen3.8-flash-next-4p89bpw` |
| Qwen3.8 TP2, GX10 pair | gx10-r0 + gx10-r1 | `http://192.168.50.23:8000/v1` | `qwen3.8-flash-next-4p89bpw` |

DeepSeek needs all four nodes' memory, so it runs alone. The two Qwen pairs are independent: run
either one or both. No API keys are set.

## Host maintenance baseline

All four nodes were updated and rebooted on September 30, 2026 HST. They run
kernel `7.0.0-1019-nvidia` and driver `580.178.04`; no newer kernel or firmware
was offered by their configured feeds. An obsolete 6.17 GRUB pin was removed,
restoring newest-installed-kernel selection. NetworkManager wait-online is now
enabled to prevent the observed DHCP/fabric startup race; its next-boot behavior
has not yet been retested. Host backups are under
`/var/backups/deepseek-maintenance-20260930/`.

All four nodes use a persistent **2350 MHz upper GPU clock limit**, selected by
the user after the clock trials. The GPU can still downclock when idle; observed
sustained clocks were about 2335 MHz. The cap applies to both DeepSeek and Qwen.
`gb10-gpu-clock-cap.service` applies it at boot before Docker, retries failures,
and remains enabled. Its source is [here](host/systemd/gb10-gpu-clock-cap.service).
See the [maintenance and clock report](MAINTENANCE-20260930.md).

After a manual GPU/driver reset, reapply with
`sudo systemctl reload gb10-gpu-clock-cap.service`. The unit does not periodically
poll or enforce clocks. To deliberately return to stock, disable the unit with
`sudo systemctl disable --now gb10-gpu-clock-cap.service`, then run
`sudo nvidia-smi -rgc`. Stopping the unit alone does not reset clocks.

## Switching (from the Mac, in this repo)

```bash
scripts/ring-mode.sh status              # mesh state and containers on every node
scripts/ring-mode.sh ds                  # selected vLLM configuration (~7 min warm)
scripts/ring-mode.sh ds-vllm-stock        # unchanged official SparkRing defaults
scripts/ring-mode.sh qwen gx10           # stop DeepSeek and both meshes; start the GX10 Qwen pair
scripts/ring-mode.sh qwen spark          # same for the Spark pair
scripts/ring-mode.sh qwen both           # both Qwen pairs
scripts/ring-mode.sh stop                # stop everything (mesh left as is)
```

`ds` returns once the selected vLLM API is healthy. `qwen` returns once each pair's
`/health` answers. The root-owned `/usr/local/sbin/deepseek-ring-control` helper on
spark-r0 has fixed passwordless lifecycle actions. It coordinates the SparkRing
mesh, which is disabled in Qwen mode. The retired SGLang mesh is removed. A local selected profile is stored separately from the official
installer deployment, under `/etc/deepseek-ring/optimized-specs.json`.

Your existing Qwen controller still works for the pairs themselves
(`~/Agent/Builds/qwen38-flash-next-spark/spark-ctl.sh start|stop|status [spark|gx10]`), but it does
not stop DeepSeek first. Use `ring-mode.sh` when switching between the two.

## Using DeepSeek

```bash
curl http://192.168.50.219:8015/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "DeepSeek-V4.1-Flash-TP4",
  "messages": [{"role": "user", "content": "Hello"}],
  "max_tokens": 1024,
  "chat_template_kwargs": {"thinking": false}
}'
```

- **Thinking is on by default in the new vLLM profile.** Set `"chat_template_kwargs": {"thinking": false}` explicitly for non-thinking requests and comparable benchmarks.
- Send `max_tokens` to bound the response. Tools and images passed the functional probes.
- Configured context limit is 1,048,576 tokens, with 16 active sequences. The 8K batch ceiling controls scheduler work per iteration; it is not the context limit or per-request reservation. The selected adaptive plugin lowers a step to 4K only when at least four runnable decoders contend with prefill. Sixteen active sequences does not imply sixteen simultaneous 1M-token contexts; aggregate KV capacity still applies.
- Greedy repeatability currently fails in the pinned vLLM stack, including the untouched stock profile. See the migration report for quality results and the rejected deterministic-kernel trial.

## vLLM lifecycle on spark-r0

```bash
sudo -n deepseek-ring-control up
sudo -n deepseek-ring-control down
sudo -n deepseek-ring-control status
sudo -n deepseek-ring-control stock-up
```

Use `ring-mode.sh` when changing engines: the fixed helper does not stop Qwen
containers for you. The selected local containers use `ds41-optimized-r0`
through `r3`; official stock containers retain their installer-generated names.
Inspect a selected rank with `docker logs --tail 100 ds41-optimized-r0`.

The selected images include the complete KK #926/#943 compressor-state
correction, layered on the pinned SparkRing/eugr stack. Per-rank immutable
image IDs and source hashes are in
[the correction receipt](results/20260929-kk926/images.json) and
[manifest](image/kk926/manifest.json). The endpoint and performance profile
are unchanged. `VLLM_USE_FASTOKENS` remains unset after the completed
[serving trial](FASTOKENS-SERVING-20260929.md): long-prompt TTFT improved, but
C8 decode was lower in both candidate runs. The trial restored the exact
KK926-corrected HF configuration and verified the live source hashes on all
four ranks. [Final selection receipt](results/20260929-fastokens/deployment.json).

The unused candidate images `dsv41-sparkring:kk926-fastokens-032` are retained;
[per-rank IDs](results/20260929-fastokens/images.json) distinguish them from
the selected corrected HF parents. The temporary `ds41-before-fastokens-r*`
containers were renamed back to `ds41-optimized-r*` during rollback. The trial
backup is `/etc/deepseek-ring/.before-fastokens-20260929T203153Z/optimized-specs.json`.
Do not rerun the trial's `rollback` now: it has already completed. The trial
scripts are campaign-specific and preserve local launch receipts.

The pre-correction optimized containers are retained, stopped, as
`ds41-before-kk926-r0` through `r3`, with restart policy `no`. Their old image
and the checkpoint are retained too. The original root-owned configuration is
backed up under
`/etc/deepseek-ring/.before-kk926-20260929T182649Z/optimized-specs.json` on spark-r0.
From this existing Mac checkout, explicit rollback is:

```bash
/opt/homebrew/bin/python3.12 scripts/kk926-rollback.py
```

That script verifies the current selection and both generations of images,
stops/removes only the corrected selected containers, restores the configuration
through the checked root-owned bundle writer, renames the old containers, and
starts them through the normal controller. Host-specific launch receipts remain
local and are required by this fleet-specific script. The rollback and
`ds-vllm-stock` images both predate the compressor fix; they are operational
fallbacks with the known model-fidelity defect.

`status` reports the local selected deployment first, then the official stock
deployment; a stopped stock deployment is expected while the selected one runs.

## After a reboot

- SparkRing manages the fabric through NetworkManager. The enabled mesh service follows the last selected mode; old netplan files are preserved in the migration backup. Do not reapply the original setup recipe over the installed fabric.
- Nothing starts serving by itself: run `scripts/ring-mode.sh ds` or `qwen ...`.
- Check the fabric if anything looks off: `ring/rdma_links.sh` (8 direct links, ~13.3 GB/s each) The startup controller also runs the installer's mesh gate on every rank. `ring/mesh_paths.sh` is the historical path probe; do not run fabric benchmarks during serving.

## Health checks

```bash
ssh spark-r0 'python3 ~/sparkring-migration-20260927/smoke.py --url http://127.0.0.1:8015 --model DeepSeek-V4.1-Flash-TP4 --needle 131072'
ssh gx10-r0 'MATCHED=1 PORT=8015 MODEL=DeepSeek-V4.1-Flash-TP4 bash ~/bench/lilbench.sh mytag matrix'     # LIL v0.6.2, same cases as the Qwen campaign
```

## Where things live

| What | Where |
|---|---|
| SparkRing checkpoint | `/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277` on all ranks (independent regular files; the old hard-link names were removed) |
| Local selected configuration | `/etc/deepseek-ring/optimized-specs.json`; root-owned plugins under `/usr/local/lib/deepseek-ring/plugins` |
| SparkRing deployment | `/var/lib/sparkring/controller/deployments/deepseek-v41-flash-tp4-iba1b36389e5d` on spark-r0 |
| Migration evidence | spark-r0 `~/sparkring-migration-20260927` and local `results/20260928` |
| Fabric | SparkRing NetworkManager profiles; pre-migration netplan snapshots in the migration evidence |
| Qwen TP2 | `~/builds/qwen-tp2` on each pair; GX10s keep only `model-5500h` |
| Bench tools and results | gx10-r0 `~/bench` |

## Things not to do

- Do not restart the SparkRing mesh while DeepSeek is serving: fabric reinitialization drops RDMA connections.
- Don't `netplan apply` on the GX10s (it stops NetworkManager there); use `netplan generate` and
  `sudo systemctl restart NetworkManager`.
- Don't run DeepSeek and a Qwen pair at the same time: DeepSeek needs every node's memory.

## Recording a local selection

The installer owns its stock deployment. `bench/installer_variant.py` records separate experimental specs and source hashes on the head; it never overwrites the upstream receipt. After reviewing a qualified adaptive-budget trial, stop serving and use `scripts/install-selected.py RECEIPT --profile engram-adaptive4k` as root on the head. It checks the pinned image and per-rank plugin hashes, installs only the selected plugin in a root-owned directory on all four nodes, and writes `/etc/deepseek-ring/optimized-specs.json`. It refuses to replace an existing selection automatically.

The root-owned lifecycle helper verifies the selected configuration, image/command/environment/mounts, plugin ownership and SHA-256 hashes before startup. Its sudoers rule grants only fixed lifecycle actions. It runs the installed SparkRing mesh gate before starting the selected containers. To change a selection later, stop it, archive its configuration and logs, then explicitly replace its owned containers/configuration with the newly qualified specs. Do not edit a live shell script or plugin in place.

For a qualified follow-up indexer receipt, the workstation controller supports
replacement with automatic rollback:

```bash
/opt/homebrew/bin/python3.12 scripts/promote-research.py RECEIPT --profile engram-adaptive4k-query-indexer
/opt/homebrew/bin/python3.12 scripts/promote-research.py RECEIPT --profile engram-adaptive4k-query-indexer --execute
```

The first command validates evidence and prints the proposed manifest. Execution
requires the recorded selection decision, passing long-input/mixed checks,
request-based startup activation and zero rejected numerical geometries. It
checks that the current selection still matches the trial snapshot, preserves
root-owned backups, and replaces only the selected plugin bundle, configuration
and stopped optimized containers. It retains the checkpoint and stock fallback.
If startup fails, it restores the previous bundle/configuration and starts that
profile. Trial launch receipts are host-specific and kept locally; measurement
and source/hash evidence are tracked in Git. The query-indexer plugin arms on
real requests after each worker starts, without an activation sentinel.
