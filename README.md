# DeepSeek-V4.1-Flash on a four-node GB10 ring

SparkRing vLLM on two DGX Sparks and two ASUS Ascent GX10s, connected by four DACs without a switch. The API is `http://192.168.50.219:8015/v1`, model `DeepSeek-V4.1-Flash-TP4`. The former SGLang deployment is retired; historical measurements remain in Git.

This repository contains this fleet's operating scripts, bounded vLLM optimizations and measurement evidence. The upstream installer, image and checkpoint are pinned; the official SparkRing deployment remains available as a stock fallback. Local optimized containers use a separate recorded configuration.

| Component | Pin |
|---|---|
| [SparkRing one-command-installer](https://github.com/FujitsuPolycom/sparkring/tree/8b152d65c701f557f62ae6a9a1c3db90771c1df3) | `8b152d65c701f557f62ae6a9a1c3db90771c1df3` |
| Profile | `deepseek-v41-flash-tp4` |
| Image reference | `ghcr.io/fujitsupolycom/sparkring@sha256:2c45153abf19af4f2b4bf10445cfc96c711c375a6fc5c04d3a2b55496f3acfe3` |
| Runtime image ID | `sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf` |
| vLLM integrated source | `03c4af34fbe6d2ff863bd03a6ed255c4de96785b` |
| B12x integrated source | `c8e461281a3872a0e5de2485ef1df3df6556f07c` |
| DeepSeek checkpoint | `dba1be0a40aa45a94ad051997016db3960a90277` |

The vLLM baseline descends from the Karmic Kraken line. This is a native vLLM/B12x deployment, not SGLang. DSpark5, block rejection and adaptive verification are supplied by the recipe. The checkpoint's target precision and full vocabulary are preserved.

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

The selected profile is `engram-adaptive4k`. Engram projection tensor parallelism improves the replicated projection path. The local adaptive scheduler keeps the 8K allocation ceiling, reducing a step to 4K when at least four runnable decoders contend with prefill. It targets stream stalls without adopting the much slower fresh-request behavior observed with native compute-share fairness. Graph coverage and Qwen-inspired top-20 draft filtering were separately measured.

Read [RESULTS.md](RESULTS.md) for the selected result and its limits, [MIGRATION-20260927.md](MIGRATION-20260927.md) for the experiment record, and [QWEN-TRANSFER.md](QWEN-TRANSFER.md) for which actual Qwen changes apply. Rejected exactness-guarded projection/indexer ports remain clearly marked research code. They are not enabled by installing the plugin directory.

The engine defaults to thinking on. Historical SGLang and new vLLM engine-default decode measurements have different thinking settings and are **not a fully matched comparison**. `MATCHED=1 bench/lilbench.sh ...` explicitly fixes thinking and sampling without changing the benchmark's timing or accounting. The stock vLLM image also fails byte-identical greedy-repeatability checks; task scores do not establish universal quality equivalence.

## Fabric and Qwen

Rank order is `spark-r0 → spark-r1 → gx10-r1 → gx10-r0 → spark-r0`. Each rank's f0 port connects to the next rank's f1 port. Every cable carries two Socket Direct RoCE planes: `10.10.N.10/11` and `10.11.N.10/11`, where N is the originating rank. MTU is 9000 and IPv4 RoCE v2 uses GID 3. SSH, bootstrap and APIs use the management LAN.

SparkRing manages NetworkManager profiles and the hardware-forwarded opposite-node paths. Qwen uses the direct cable inside each pair. Both pairs retain their own `hc-adaptive+cg4+m5500h` profile and 24 GiB KV allocation. The mode switch stops DeepSeek and disables its mesh before starting Qwen.
