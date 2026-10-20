# Persistent 2350 MHz ceiling restored

At the user's request, all four nodes again use `nvidia-smi -lgc 0,2350`.
`gb10-gpu-clock-cap.service` is enabled and active, with the same command in
ExecStart and ExecReload, and runs before Docker at boot. Idle downclocking
is allowed. This was applied live; all four serving container IDs and start
times were unchanged. The exact qualified configuration remains
`d86c7e0725efae1ced95a4891da59753853992aaad4fda926814531145e43ca2`.

The prior stock-boost unit is backed up on each node at
`/var/lib/deepseek-ring/experiments/clock-cap-2350-20261020/gb10-gpu-clock-cap.service`. The installed unit SHA256 is
`c1a5839ec049a61296cb751c8ccd1ead7be20b41de2051bdc911ecb51b11ebfd`. No drop-ins override it.
[Installation and systemd evidence](policy.json).

One bounded generation request correctly counted 1 through 100. Three clock
samples during that request showed:

| Node | Active SM clock (MHz) | Peak observed GPU utilization |
|---|---:|---:|
| spark-r0 | 2327–2327 | 95% |
| spark-r1 | 2333–2333 | 94% |
| gx10-r1 | 2333–2333 | 94% |
| gx10-r0 | 2333–2333 | 95% |

The API stayed healthy on port 8015. This is a functional/clock check, not a
throughput benchmark or a reboot test. Boot persistence was verified through
the enabled unit, its loaded commands and successful application.
[Loaded verification](loaded-verification.json).

The preceding matched switched draft4 screen measured 64.43 / 198.73 / 273.91
tokens/s at 8K C1/C8/C16 with the 2350 ceiling, and 64.80 / 198.69 / 273.37
with stock boost. Stock prefill was 2.3% / 1.7% higher at 64K / 128K.
Those finite screens did not establish a consistent decode benefit from
stock clocks. Earlier power savings were measured on an older build; no new
energy-saving claim is made here.
[Historical clock comparison](../20261019-switch-migration/REPORT.md).

The optimization campaign remains paused. The optional live-cost diagnostic
failed during startup on nullable metadata, produced no live timing result,
and was fully unwound before this clock change. Its native-parent recovery
check is retained as [recovery-before-cap.json](recovery-before-cap.json);
that receipt correctly records the stock policy at that earlier time.
No diagnostic overlay is selected. Historical private trial wrappers reset
stock clocks; update their restoration behavior to 0–2350 before any future
explicitly requested reuse. Do not resume the paused campaign automatically.
