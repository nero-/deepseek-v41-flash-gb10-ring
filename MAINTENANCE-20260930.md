# GB10 maintenance and 2300 MHz evaluation — September 30, 2026 HST

The maintenance took place on October 1 UTC. Scope: both DGX Sparks and both
ASUS GX10s, using each node's existing vendor/Ubuntu update sources. The user
requested current kernel/firmware and a 2300 MHz GPU cap only if performance
loss is minimal. This campaign treats roughly 3% as the screening threshold;
noisy or mixed results are not proof of performance equivalence.

## Update findings

All four nodes initially ran kernel `7.0.0-1019-nvidia` and NVIDIA driver
`580.178.04`. Fresh APT metadata and LVFS metadata offered no newer kernel,
GPU driver, or device firmware. No cross-vendor firmware was installed.
The public NVIDIA guide listed an older stack than the configured repositories;
installed versions and fresh package candidates were used for the fleet check.

Regular OS/security updates were applied: 79 packages on spark-r0, 52 on
spark-r1, and 80 on each GX10. No packages were removed and old kernels were
retained. Six Mesa packages remain deferred by Ubuntu phased rollout on the
Sparks; no phase override was used. Post-update package simulations showed
no other pending upgrades. Firmware update lists were empty on every node.

Root-only backups are retained on each node under
`/var/backups/deepseek-maintenance-20260930/`, including APT, NetworkManager,
netplan, systemd, Docker and available serving configuration, plus package
state. These backups stay on the machines rather than in this repository.
DeepSeek was stopped before package installation. The first GX10's service
restarts interrupted the `systemd-run` caller's D-Bus connection; the supervised
APT job continued and completed successfully. Its state and journal were
checked before proceeding, without starting a duplicate package operation.
Subsequent updates deferred service restarts to the coordinated reboot.

## Reboot findings

An old `/etc/default/grub.d/zz-sparkring-kernel.cfg` on all four nodes pinned
kernel `6.17.0-1032-nvidia` for an earlier RoCE comparison. The first GX10
reboots therefore selected 6.17 despite having run 7.0 before maintenance.
The reboot sequence was stopped, that specific obsolete pin was backed up and
removed, and `update-grub` restored automatic newest-installed-kernel selection.
All four nodes subsequently booted `7.0.0-1019-nvidia` with driver `580.178.04`.
The first-attempt receipts remain beside the successful final reboot receipts.

The boot-time fabric service also raced DHCP: NetworkManager's wait-online
service was disabled, and the fabric guard ran before the management address
was ready. Read-only observations after boot confirmed the expected management
address, interface and witness route on all nodes. The standard
`NetworkManager-wait-online.service` was enabled and successfully run on each
node for future boots. That readiness change has not yet been exercised by
another reboot. The existing controller restored the authenticated serving
mesh and passed its normal gates; no fabric guard or transport check was bypassed.

## Clock evaluation method

The user's [forum source](https://forums.developer.nvidia.com/t/cooler-gb10-temps-almost-no-performance-lost/372662)
reports substantial power reductions at 2000 MHz, with workload-dependent
performance losses. This is motivation for measurement, not evidence of
identical behavior in four-node DS4.1 serving.

The trial compares stock clocks (`nvidia-smi -rgc`) with an upper GPU clock
limit (`nvidia-smi -lgc 0,2300`), preserving idle downclocking. It does not
change CPU clocks, memory clocks, model weights, quantization, KV allocation,
DSpark settings, plugins or the HF tokenizer. Each phase runs the pinned LIL
six-cell screen: 8K/128K × C1/C8/C16, 30-second sustained measurements, normal
warmups and repetition detection, plus standalone cold-prefill measurements.
This is not the full historical 40-cell benchmark.

Each node records GPU clocks, reported GPU power, temperature, utilization and
clock-event masks once per second. These readings are GPU-reported power,
not whole-machine power at the wall. The 2300 MHz test resets stock clocks in
its cleanup path; persistence requires a separate evidence-based decision.

Sources for maintenance: [NVIDIA update procedure](https://docs.nvidia.com/dgx/dgx-spark/os-and-component-update.html),
[ASUS GX10 update procedure](https://rog.asus.com/support/faq/1056213/).

## Measured clocks, throughput and power

All three six-cell screens (stock, 2300 MHz, restored stock) completed without
request errors, repetition, capacity limits or warmup timeouts. This is a
sequential A/B/A campaign with sampled continuations, not a randomized trial.

| Context | Clients | Stock first tok/s | 2300 MHz tok/s | Stock repeat tok/s |
|---|---:|---:|---:|---:|
| 8K | 1 | 66.54 | 64.31 | 64.77 |
| 128K | 1 | 61.65 | 79.31 | 63.14 |
| 8K | 8 | 185.50 | 179.43 | 195.77 |
| 8K | 16 | 253.62 | 242.74 | 243.40 |
| 128K | 8 | 181.06 | 171.12 | 167.38 |
| 128K | 16 | 238.29 | 239.10 | 230.97 |

Rates above C1 are aggregate. The capped 128K/C1 sample is an outlier:
effective acceptance rose from 2.390 to 3.311 tokens/step, while step rate
fell from 25.79 to 23.96/s. It is not evidence that lower clocks accelerate
GPU execution. This reinforces why one sample cannot establish a clock benefit.

| Cold prefill | Stock first prompt tok/s | 2300 MHz | Stock repeat |
|---|---:|---:|---:|
| 8K | 4579 | 4390 | 4460 |
| 128K | 4480 | 4408 | 4501 |

Compared with the stock repeat, capped prefill was about 1.6% lower at 8K and
2.1% lower at 128K. The first stock 8K prefill was faster, making that first
pair's difference 4.1%. Short-prefill results used five samples; each 128K
standalone result used one sample.

Power is aligned to each LIL sustained decode window using its ready/done
log events and one-second GPU telemetry. Approximate window boundaries have
one-second precision. Reported fleet GPU watts sum each node's mean; peak
temperature is the highest GPU reading across nodes during that window.

| Context / clients | Stock GPU W | Capped GPU W | Stock peak °C | Capped peak °C |
|---|---:|---:|---:|---:|
| 8K / 1 | 159.1 | 106.6 | 72 | 66 |
| 128K / 1 | 162.5 | 109.9 | 74 | 68 |
| 8K / 8 | 171.9 | 117.0 | 73 | 69 |
| 8K / 16 | 170.1 | 116.5 | 75 | 70 |
| 128K / 8 | 174.4 | 118.7 | 76 | 71 |
| 128K / 16 | 177.2 | 121.6 | 77 | 71 |

GPU-reported power was roughly 31–33% lower. The first paired windows were
4–6°C cooler; against the warmed stock repeat, capped windows were 5–8°C
cooler. These are short benchmark observations, not a long thermal-soak test.
CPU, network, SSD and power-supply consumption are not included, so this is
not a claim of 32% lower wall power for the entire cluster.

Raw measurements and analysis: [comparison](results/20260930-maintenance/clock-comparison.json),
[stock](results/20260930-maintenance/stock-screen.json),
[capped](results/20260930-maintenance/2300-screen.json),
[stock repeat](results/20260930-maintenance/stock-repeat-screen.json).


## Focused repeat and final decision

A further 60-second capped 8K/C8 run produced **183.10 aggregate tok/s**, with
no request errors or repetition. Both capped results (179.43 and 183.10)
were below both stock results (185.50 and 195.77). The longer repeat narrows
the concern but does not establish a loss below the roughly 3% screen threshold
across workloads. See the [focused repeat](results/20260930-maintenance/2300-repeat-screen.json).

**Stock GPU clocks remain selected on all four nodes.** No persistent clock cap
was installed. A 2300 MHz cap is a useful efficiency option, but the measured
C8 tradeoff does not meet the user's condition confidently enough to make it
the default. These sequential samples do not establish a precise causal loss.

Final checks confirmed all four selected containers running, the API healthy,
and seven functional probes passing: counting, arithmetic, code, automatic and
forced tools, image input, and thinking mode. KK926 correction source hashes
were verified on every rank; the HF tokenizer and serving profile are retained.
The status receipt also includes the separate, stopped upstream stock deployment
and its fabric observations; those entries do not describe the running selected
containers. No stock deployment was started to clear its status display.

The serving endpoint remains `http://192.168.50.219:8015/v1`, model
`DeepSeek-V4.1-Flash-TP4`. See the [decision](results/20260930-maintenance/decision.json),
[functional checks](results/20260930-maintenance/final-functional-r0.json), and
[container status](results/20260930-maintenance/final-serving-status-r0.json).
