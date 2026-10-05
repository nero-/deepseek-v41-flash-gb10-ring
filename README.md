# DeepSeek-V4.1-Flash on a four-node GB10 ring

SparkRing vLLM on two DGX Sparks and two ASUS Ascent GX10s, connected by four DACs without a switch. The API is `http://192.168.50.219:8015/v1`, model `DeepSeek-V4.1-Flash-TP4`. The former SGLang deployment is retired; historical measurements remain in Git.

This repository contains this fleet's operating scripts, bounded vLLM optimizations and measurement evidence. The upstream installer, image and checkpoint are pinned; the official SparkRing deployment remains available as a stock fallback. Local optimized containers use a separate recorded configuration.

| Component | Pin |
|---|---|
| [SparkRing one-command-installer](https://github.com/FujitsuPolycom/sparkring/tree/8b152d65c701f557f62ae6a9a1c3db90771c1df3) | `8b152d65c701f557f62ae6a9a1c3db90771c1df3` |
| Profile | `deepseek-v41-flash-tp4` |
| SparkRing parent reference | `ghcr.io/fujitsupolycom/sparkring@sha256:2c45153abf19af4f2b4bf10445cfc96c711c375a6fc5c04d3a2b55496f3acfe3` |
| Parent image ID | `sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf` |
| Selected derived images | `dsv41-sparkring:kk926-20260929`; [immutable per-rank IDs](results/20260929-kk926/images.json) |
| vLLM integrated source | `03c4af34fbe6d2ff863bd03a6ed255c4de96785b` plus [KK #926 complete correction](image/kk926/manifest.json) at `7b935cb78a3f1f256b04006e82504a651685f72d` |
| B12x integrated source | `c8e461281a3872a0e5de2485ef1df3df6556f07c` |
| DeepSeek checkpoint | `dba1be0a40aa45a94ad051997016db3960a90277` |

The vLLM baseline descends from the Karmic Kraken line. This is a native vLLM/B12x deployment, not SGLang. DSpark5, block rejection and adaptive verification are supplied by the recipe. The checkpoint's target precision and full vocabulary are preserved.

The selected image now includes the complete compressor-state correction from
KK #926/#943 on SparkRing's eugr nightly base. In eight 2,048-token probes,
late-answer decode/prefill divergence fell 89.6%. Prefill and high-concurrency
throughput were broadly retained, while 128K single-user decode was slower in
the matched screens. See the [correction report](KK926-CORRECTION-20260929.md)
for the speed tradeoff, initial intermittent long-tool miss, passing repeat,
and qualification evidence. This is a fidelity upgrade, not a claimed general
decode speedup.

All four hosts are updated and running kernel `7.0.0-1019-nvidia`. All four use a persistent
2350 MHz upper GPU clock limit after measured efficiency trials; see the
[maintenance results and clock tradeoff](MAINTENANCE-20260930.md).

The October 4 CSF/beta/SparkRing upgrade was rejected for slower prefill and
concurrent decode. The original corrected recipe remains selected; its pins
above are unchanged. See [the upgrade record](CSF-UPGRADE-20261004.md),
[the candidate full benchmark](FULL-BENCHMARK-CSF-20261004.md), and
[the TensorFold assessment](TENSORFOLD-ASSESSMENT-20261004.md).

## Operating

```bash
scripts/ring-mode.sh ds                 # selected local vLLM profile
scripts/ring-mode.sh ds-vllm-stock      # official SparkRing defaults
scripts/ring-mode.sh qwen both          # switch to both existing Qwen TP2 pairs
scripts/ring-mode.sh stop
scripts/ring-mode.sh status
```

See [OPERATIONS.md](OPERATIONS.md) for endpoints, thinking mode, lifecycle and recovery. These are site-specific scripts with fixed LAN addresses; they are not a universal bootstrap. For a new cluster, start from the pinned upstream installer and adapt its site configuration. Do not copy another fleet's controller credentials or host identity receipts.

## Optimizations and evidence

The selected profile is `engram-adaptive4k-query-indexer`: Engram projection TP, adaptive 4K steps under contention, and guarded query-row sharding for long-prefill indexing. The scheduler retains its 8K allocation ceiling. The new indexer port reduced uncached million-token first-content latency from 529.5 to 315.8 seconds after permanent installation (333.9 seconds in qualification), with native DSpark decode retained. Its guard requires exact scores and selected score values; alternative legal tied indices are allowed. Worker warmup must finish before real requests can activate it.

Read [RESULTS.md](RESULTS.md) for the selected result and its limits, [RESEARCH-20260928.md](RESEARCH-20260928.md) for all six follow-up directions, [MIGRATION-20260927.md](MIGRATION-20260927.md) for the experiment record, and [QWEN-TRANSFER.md](QWEN-TRANSFER.md) for which actual Qwen changes apply. The projection split, context-axis indexer, timed scheduler, Engram read-ahead, mHC ownership and Markov shortlists remain unselected research code. Plugin installation alone does not enable them.

The [historical pre-correction full benchmark](FULL-BENCHMARK-20260928.md) includes the
20-cell sustained grid, 20-cell burst grid, coding throughput and cold retrieval
through one million tokens. Two original 128K cells were rejected for output
repetition; their diagnostic repeats are reported separately.

[Fastokens was tested end to end](FASTOKENS-SERVING-20260929.md). Cached 1M
first-token latency improved from 2.57 to 1.11 seconds at C1 and 9.80 to 3.74
seconds at C8, but both Fastokens C8 decode runs were below both HF runs.
The corrected HF backend remains selected to preserve decode/concurrency
performance. Candidate images and all comparison evidence are retained.

The engine defaults to thinking on. Historical SGLang and new vLLM engine-default decode measurements have different thinking settings and are **not a fully matched comparison**. `MATCHED=1 bench/lilbench.sh ...` explicitly fixes thinking and sampling without changing the benchmark's timing or accounting. The stock vLLM image also fails byte-identical greedy-repeatability checks; task scores do not establish universal quality equivalence.

## Fabric and Qwen

Rank order is `spark-r0 → spark-r1 → gx10-r1 → gx10-r0 → spark-r0`. Each rank's f0 port connects to the next rank's f1 port. Every cable carries two Socket Direct RoCE planes: `10.10.N.10/11` and `10.11.N.10/11`, where N is the originating rank. MTU is 9000 and IPv4 RoCE v2 uses GID 3. SSH, bootstrap and APIs use the management LAN.

SparkRing manages NetworkManager profiles and the hardware-forwarded opposite-node paths. Qwen uses the direct cable inside each pair. Both pairs retain their own `hc-adaptive+cg4+m5500h` profile and 24 GiB KV allocation. The mode switch stops DeepSeek and disables its mesh before starting Qwen.
