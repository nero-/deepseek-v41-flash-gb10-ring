# Fastokens assessment — 2026-09-29 UTC

`VLLM_USE_FASTOKENS=1` is supported by our pinned vLLM source and its
`deepseek_v41` tokenizer, which wraps the Hugging Face backend. The package
itself is absent from the serving image and the flag is unset. Setting the
flag alone would raise an import error at tokenizer load. See the
[live inspection](results/20260929-kk926/fastokens-inspection.json) and
[vLLM integration documentation](https://docs.vllm.ai/en/latest/configuration/optimization/#fastokens-backend).

The flag replaces the CPU tokenizer backend and streaming detokenizer. It
does not replace GPU attention, MoE, speculative decoding or KV-cache kernels.
The [upstream package](https://github.com/crusoecloud/fastokens) publishes ARM64
wheels. We inspected and tested **0.3.2**, using the PyPI manylinux 2.28 aarch64
CPython 3.9+ ABI3 wheel, SHA256
`cbb29fae028d39a2020d01dfe587e1774a516b6d28641b70e83a285d460bdfb8`.
[Package metadata](results/20260929-kk926/fastokens-package.json) records its URL.

## Isolated Spark CPU probe

Both processes used the corrected serving image's actual vLLM
`get_tokenizer(..., tokenizer_mode='deepseek_v41')`, the same local checkpoint,
and the flag off/on. The package was mounted only into disposable test
containers. No package or environment setting was changed in the serving
containers. Tests ran after the GPU benchmark ended, on spark-r1, using the
plain runc runtime with no GPU, no network, a read-only root filesystem, a
4 GiB memory limit, two CPU equivalents and two Rayon threads. HF tokenizer
parallelism was disabled in both processes. Each timing is the median of three
warmed samples and excludes tokenizer loading.

All **17 parity cases** matched: token IDs and decoded/streamed output across
ASCII, multilingual text, Unicode combining characters, emoji, whitespace,
code, special-token strings and repetitive inputs; thinking on/off tool
templates; and the image-placeholder chat template. The three large corpora
also had identical token-ID and decoded-output hashes. The separate streaming
sample matched cumulative output. This is bounded parity coverage, not proof
of equivalence on all inputs or a live tools/vision serving qualification.

| Actual input tokens | HF encode | Fastokens encode | Encode speedup |
|---:|---:|---:|---:|
| 7,390 | 8.92 ms | 0.617 ms | 14.46× |
| 125,189 | 185.41 ms | 11.44 ms | 16.21× |
| 1,008,381 | 1,607.15 ms | 106.15 ms | 15.14× |

Batch text decoding was 1.32–1.48× faster. **Single-token streaming
detokenization was slower in this probe**: speed ratio 0.871×, or about 14.8%
more elapsed CPU time for the same sample: **4.37 ms → 5.02 ms for 8,192
tokens**, a small absolute difference. These CPU timings do not measure
GPU model decode tokens/sec, and they are not an end-to-end API benchmark.
The two-CPU allocation is a test constraint, not a proposed production limit.

Evidence: [assessment](results/20260929-kk926/fastokens-assessment.json),
[HF raw timings](results/20260929-kk926/tokenizer-hf.json),
[Fastokens raw timings](results/20260929-kk926/tokenizer-fastokens.json),
[probe](bench/fastokens-probe.py), [runner](scripts/fastokens-probe.py).

## Decision

**Promising for input processing; not enabled in serving yet.** Saving about
1.5 seconds of CPU encoding is small beside the measured 322-second cold
million-token request. It could matter much more when a long prompt's GPU
prefix is cached, or when many incoming prompts contend for frontend CPU.
That is an inference from the CPU results, not a measured API speedup.

A separate immutable image containing the pinned wheel should be tested on
cached and uncached long-prompt TTFT, concurrent arrivals, streaming latency,
tools and real image requests before selection. Keep it separate from the
compressor correction: the GPU benchmark results in the correction report all
use the original tokenizer backend. No KV capacity or scheduler limit needs to
change to evaluate this option.
