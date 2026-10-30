# FLARE package update: gb10 `ab4f07af` on `a161b17f` (2026-10-30)

The publisher updated `local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE@gb10`
to a package with **8192-token prefill chunks**, which needs
`flare-inference` `a161b17f` or newer, and recommended a new launch flag,
`--mtp-adaptive-verification-alpha 0.5`. Both are now serving. The old
package was removed from all four nodes.

| Item | Before | After |
|---|---|---|
| Engine | `0.1.0~git20261027170349.7c22369f-1` | `0.1.0~git20261030013211.a161b17f-1`, `/usr/bin/flare` SHA-256 `531f04f28c8f4914…` on all four nodes and agents |
| Package commit | `607c1abf` | `ab4f07af7b4a515b768baa3c7d8343c54f8144e9` |
| Deployment | `0a377833…` | `7cf40bec5c5b4026a4abc801e615226c`, TP4, native expert scales, signatures verified |
| Local version | `gb10-tp4-202610271726`, 489.39 GiB | `gb10-tp4-202610302102`, 476.80 GiB; peers `gb10-tp4-202610302308`, 260.85 GiB each |
| Prefill chunk | 4,096 tokens | 8,192 tokens |
| Loaded per GPU | about 89.0–89.3 GiB | 88.13–88.47 GiB |
| KV (`--memory-limit=-2G`) | 16.6 GiB per GPU, 19,306,112 tokens | **17.9 GiB per GPU, 20,942,336 tokens** |
| Memory after loading | 110.86 GiB used on spark-r0 | 111.46 GiB used on spark-r0 (others 111.26–111.35), 10.2 GiB available |
| Verification alpha | 1.0 (default) | **0.5** |

## Steps (UTC)

1. **Download, while the old package served.** The new CLI was unpacked from
   the `.deb` (`apt-get download`, `dpkg-deb -x`) into a private folder on
   spark-r0, so the download could start before the Sparks were upgraded.
   `flare download … --revision gb10 --filename model.safetensors
   --tensor-parallel 4 --model-cache /home/nero/flare-models` resolved
   `ab4f07af` and fetched 309 GB in 95.5 minutes. The rest was reused from
   the old version's local files, and all 512 GB were verified.
2. **Upgrade.** APT on all four nodes. The package has no maintainer scripts,
   so the running ranks weren't affected. The user ran the two Spark
   upgrades, which need the sudo password.
3. **Cutover at 23:08:16.** Stopped the group and reinstalled all four agents
   (`flare agent install --listen 0.0.0.0:29900`; the limits drop-in stayed).
   Pairing survived. `flare/launch.sh` created the group from the new
   version. Distribution over the fabric took 776 s (spark-r1 567 s, gx10-r1
   721 s, gx10-r0 776 s). **Health returned 200 at 23:22:39, 829 s after the
   launch.** Relaunches with the cached package took 29–30 s.
4. **Removal of the old version.** See below.
5. **Benchmarks.** Alpha 0.5 and 1.0 were run back to back, and the final
   relaunch used 0.5 at 23:41.

## GX10 disk during the first launch

The new share was staged in `~/.cache/flare/staging` next to the old version
and then moved, not copied, into `~/.cache/flare/models`. Each GX10 went from
405–409 GiB free to a low of **145–149 GiB**, so it would have fitted with
room to spare. At the user's request, future package swaps stop the model and
remove the old version first.

## Removal of the old version

| Node | Removed | Free before → after |
|---|---|---|
| spark-r0 | version `gb10-tp4-202610271726` (`flare models remove`), then 178 unreferenced blobs (300.5 GiB) with `flare models gc`; old `~/flare-models.keep` replaced by a fresh hardlink snapshot of the new store; `~/flare-staging` (Oct 27 CLI builds, 101 MB) and the unpacked `a161b17f` CLI (39 MB) | 1,455 → 1,755 GiB |
| spark-r1 | rank version `gb10-tp4-202610272052` | 1,779 → 2,043 GiB |
| gx10-r1 | rank version `gb10-tp4-202610272052` | 145 → 409 GiB |
| gx10-r0 | rank version `gb10-tp4-202610272052` | 149 → 413 GiB |

Before removing anything:
- the running rank 0 held the Engram tables open under the old version's
  path, but they are the same inodes as the new version's (link count 5), so
  they stayed;
- no unreferenced blob was open;
- the store's 181 remaining blobs are exactly the new version's 476.8 GiB.

`flare models remove` deletes only the version directory and leaves its
blobs, so on a store with a hardlink snapshot, run `flare models gc` and
recreate the snapshot afterwards. The download log moved to
`~/flare-logs/download-ab4f07af-20261030.log`. The retired vLLM containers
and images were not touched.

## Quick grid

The same LIL 0.7.6 arguments as before, with no other traffic: 20-second cells,
max 2048 tokens, `--concurrency 1,4,8,16 --contexts 8k,64k,128k`. Every run
had 0 errors, 0 loops and 0 underfilled cells. Values are aggregate output
tok/s; prefill is tok/s.

| Context | Run | C1 | C4 | C8 | C16 | Prefill |
|---|---|---:|---:|---:|---:|---:|
| 8K | old package, after reboot (Oct 28) | 68.0 | 145.3 | 189.2 | 275.6 | 4,000 |
| | new, alpha 1.0 | 65.9 | 147.5 | 191.1 | 262.2 | 3,895 |
| | **new, alpha 0.5 (selected)** | 68.4 | 143.6 | **202.0** | 272.3 | 4,000 |
| 64K | old | 66.0 | 143.0 | 182.1 | 259.6 | 4,499 |
| | alpha 1.0 | 66.4 | 152.1 | 180.9 | 255.7 | 4,854 |
| | **alpha 0.5** | 66.9 | 158.8 | **197.4** | 267.2 | **4,871** |
| 128K | old | 66.5 | 152.4 | 188.6 | 260.0 | 4,589 |
| | alpha 1.0 | 70.6 | 145.9 | 177.5 | 249.3 | 4,946 |
| | **alpha 0.5** | 64.3 | 143.8 | **201.4** | 255.9 | **4,832** |

- **Prefill** at 64K–128K is 5–8% higher with the new package, which fits
  its larger chunks. At 8K it is unchanged.
- **C8** is the clear gain from alpha 0.5: 197–202 tok/s against 177–191 with
  1.0, and 182–189 with the old package. The publisher reported the same
  (175–182 → 199–210).
- **C1, C4 and C16** are within single-cell noise of each other and of the
  old package: C1 64–71, C4 143–159, C16 249–276. One run per arm, so
  differences under about 5% are not established.

Files: `quick-grid-alpha05.{json,log}`, `quick-grid-alpha10.{json,log}` and
their `-command.json`.

## Checks

- `bench/functional.py`: 6/7 on the first launch and **7/7** after the final
  relaunch. The forced named tool call ("Tell me about Rome." forced to
  `get_weather`) is intermittent: seeds 0 and 1 returned HTTP 500 `required
  tool choice was not satisfied`, and seed 2 made the call. It was flaky on
  the old build too. A forced call that fits the question works with
  thinking on and off, and `tool_choice: "required"` works.
- `check_images.py`: pass, health 200 afterwards.
- **Stray tokens ([NVIDIA/local-inference#118](https://github.com/NVIDIA/local-inference/issues/118))
  still reproduce**, with the same blank distribution at the same positions
  (`'\n'` −2.25, `'#'` −2.37, `'<'` −2.75 at prompt length 42 with the
  effort prefix; clean without it or past position 128). Workarounds are
  unchanged.
- The 2350 MHz clock cap service is active on all four nodes.
