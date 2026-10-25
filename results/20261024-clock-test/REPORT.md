# GPU clock policy on the TileLang selection

After the fleet was moved to a cooler room (under 70 °C under load), the user asked whether to push clocks back to maximum, or higher. On 2026-10-24 the TileLang selection (`4d2bc32e…`) was measured under three policies applied to all four nodes ([script](scripts/clocks.py)): one LIL 0.7.6 screen each (temperature 1, 20 s cells, 2,048 max tokens, C1/C8/C16 at 8K/32K/128K, cold prefill at 8K–128K, coding probes), driver throttle counters before and after the screen, then a separate untimed telemetry pass (16 concurrent 1,500-token requests, then a nonce-prefixed 32K prefill) sampled every 2 s on every node. The GX10s were set with `sudo nvidia-smi`, the Sparks through a privileged `nsenter` container running the host `nvidia-smi`.

## Policies

| Policy | Active SM clock, decode / prefill (MHz) | Peak GPU W, decode / prefill | Peak °C | Power-cap / thermal throttle during screen |
|---|---|---|---:|---|
| 0–2350 MHz ceiling (selected) | 2320–2340 / 2327–2340 | 34 / 53 | 74 | none |
| driver stock boost (`-rgc`) | 2476–2528 / 2476–2502 | 47 / 66 | 76 | none |
| 2800–3003 MHz lock (`-lgc 2800,3003`) | 2470–2528 / 2470–2528 | 47 / 68 | 80 | none |

The 2800 MHz floor was accepted by the driver but not reached: the GPUs ran at the same 2470–2528 MHz as stock boost, with no power-cap or thermal throttling recorded. Stock boost tops out there on this load; the 3003 MHz maximum is not reachable, and no overclock control is exposed (power limits and supported clocks report N/A).

## Throughput

Aggregate output tok/s; change against the 2350 screen. The last column is the range of the three earlier 2350 screens of the same selection ([report](../20261024-tilelang/REPORT.md)), for scale.

| Cell | 2350 | Stock | 2800 floor | Earlier 2350 range |
|---|---:|---:|---:|---|
| 8K C1 | 68.6 | 69.8 (+1.7%) | 65.7 (-4.2%) | 67.3–68.0 |
| 8K C8 | 216.5 | 218.1 (+0.7%) | 201.3 (-7.0%) | 206.9–214.1 |
| 8K C16 | 304.4 | 297.6 (-2.3%) | 275.2 (-9.6%) | 291.9–296.0 |
| 32K C1 | 68.9 | 65.2 (-5.4%) | 65.8 (-4.6%) | 60.5–68.5 |
| 32K C8 | 204.7 | 205.6 (+0.5%) | 197.0 (-3.8%) | 206.9–220.6 |
| 32K C16 | 294.7 | 292.6 (-0.7%) | 270.5 (-8.2%) | 284.1–290.0 |
| 128K C1 | 69.4 | 65.9 (-5.1%) | 64.3 (-7.4%) | – |
| 128K C8 | 208.2 | 198.7 (-4.6%) | 213.6 (+2.6%) | – |
| 128K C16 | 279.0 | 270.1 (-3.2%) | 265.5 (-4.8%) | – |
| 8K prefill | 5439 | 5558 (+2.2%) | 5597 (+2.9%) | – |
| 32K prefill | 6186 | 6275 (+1.4%) | 6275 (+1.4%) | – |
| 64K prefill | 6143 | 6239 (+1.6%) | 6225 (+1.3%) | – |
| 128K prefill | 5999 | 6095 (+1.6%) | 6084 (+1.4%) | – |

Stock boost raised cold prefill 1.4–2.2% and left decode between −5.4% and +1.7%, mostly within the earlier 2350 screens' spread, for about 40% more GPU power. The 2800 floor was lower in most decode cells. As on 2026-10-20 (B12X), higher clocks give no consistent decode gain, as expected if decode is bound by memory bandwidth rather than SM clock. The 2350 ceiling stays.

## Restoration

`systemctl reload gb10-gpu-clock-cap.service` ran on all four nodes (service active, enabled, `-lgc 0,2350`: verified), and each journal logged `GPU clocks set to "(gpuClkMin 0, gpuClkMax 2350)"`. Samples taken in the first seconds still reported the previous clocks (up to 2496 MHz); under a following C16 load the nodes settled within about 4 s at 2327–2333 MHz ([receipt](restored.json), [verification](restored-verify.json)). Clock readings lag a change by a few seconds.
