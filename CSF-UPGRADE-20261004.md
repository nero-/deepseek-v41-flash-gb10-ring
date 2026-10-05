# Lossless CSF upgrade — October 4, 2026

The campaign tested replacing the original DeepSeek checkpoint with
[lossless CSF](https://huggingface.co/local-inference-lab/DeepSeek-V4.1-Flash-lossless-CSF/tree/c5c41fe301c4c1d24fc09376883d9168e521dc66),
and rebasing this fleet's SparkRing integration onto vLLM beta
`00a33e23142097f99fef95b1ecab6da4ea271e2e` and B12x
`4bc601a42d9938fc1b33392b5e69b2f2485b4872`, with CUTLASS DSL 4.7.1.
The [image recipe](image/csf/README.md), [source manifest](image/csf/manifest.json)
and [per-node image identities](results/20261004-csf/images.json) record the build.

CSF changes the storage of routed-expert block scales. It preserves their
original bytes and the model's existing quantization. It does not quantize
Engram/PLE or make that disk-backed table GPU resident. The 48 published shards
were verified against their whole-file LFS SHA-256 on every node. Eight shards
with unchanged tensor payloads were reconstructed from local originals behind
the official new headers, then checked against the same official file hashes.
The publisher supplies full reconstruction verification. Initial serving
qualification did not independently expand the whole checkpoint; the subsequent
rollback recovered GX10 originals by byte reconstruction and fabric copying,
checking their complete shard hashes against the original immutable Hub revision.

The source-native ABI comparison is empty, allowing retention of the existing
ARM64 vLLM extensions, CUDA 13.4.2, NCCL 2.32.3 and PyTorch binaries. Their
hashes are checked by the derived runtime. The initial CSF transport's
12 wire/proxy files remain byte-identical; its new profile binds the new B12x
source preimages. Rebased DS4.1 changes retain Engram projection TP, adaptive
4K prefill under contention and guarded query-row indexer sharding. Conflicting
unrelated-model API owners follow the newer upstream source; those models were
not qualified by this campaign.

## First matched screen

Both runs used the same four nodes, persistent 2350 MHz upper GPU cap, HF
tokenizer, explicit thinking off, temperature 1, top_p 1 and top_k -1. Each
sustained decode cell ran for 30 seconds after warmup. The baseline is the
previous selected KK926-corrected checkpoint/runtime, measured immediately
before this upgrade. These are short stochastic measurements, not confidence
intervals.

| Context | Concurrent requests | Previous tok/s | CSF, 16 CPU threads tok/s | Change |
|---|---:|---:|---:|---:|
| 8K | 1 | 60.98 | 71.85 | +17.8% |
| 8K | 8 | 178.40 | 176.43 | −1.1% |
| 8K | 16 | 242.96 | 223.97 | −7.8% |
| 128K | 1 | 59.36 | 61.65 | +3.9% |
| 128K | 8 | 166.88 | 154.87 | −7.2% |
| 128K | 16 | 229.62 | 218.50 | −4.8% |

The 8K/C1 accepted-token length increased from 2.38 to 3.12 while normalized
steps/s fell from 25.67 to 23.00. This run's single-user gain therefore does
not establish a faster target-model kernel. High-concurrency engine step rate
also fell in several cells. Cold prefill changed from 4,434 to 4,116 prompt
tok/s at 8K, and 4,421 to 4,038 at approximately 129K actual prompt tokens.
The longer prompt's TTFT increased from 29.18 to 31.95 seconds. These first
results show a tradeoff, not an across-the-board speedup.

Raw evidence: [baseline](results/20261004-csf/baseline-screen.json),
[CSF screen](results/20261004-csf/csf-screen.json), and their adjacent matched
request sidecars. No benchmark harness or sampling contract was upgraded.

## CPU-thread trial

The same image and inline scale path were restarted with `OMP_NUM_THREADS=1`.
The compiler cache moved into the dedicated CSF namespace; existing objects
were copied rather than changed. B12x keys objects by the complete package
fingerprint, toolchain, architecture, compile options and semantic kernel
specification. The cache directory and OMP thread count are not code-generation
inputs. This restart reused compiled kernels and completed serving startup.

| Context | Concurrent requests | CSF, 16 threads | CSF, 1 thread |
|---|---:|---:|---:|
| 8K | 1 | 71.85 | 52.76 |
| 8K | 8 | 176.43 | 168.57 |
| 8K | 16 | 223.97 | 226.99 |
| 128K | 1 | 61.65 | 52.99 |
| 128K | 8 | 154.87 | 150.36 |
| 128K | 16 | 218.50 | 205.02 |

Cold prefill was 4,128 and 4,156 prompt tok/s. C1 acceptance varied, but the
8K/C8 normalized engine step rate also fell from 79.60 to 66.57 steps/s.
One thread did not improve the overall workload and was rejected. The next
trial restored 16 threads and disabled inline scale reads with the supported
`B12X_W4A8_CSF_INLINE=0` setting. The
[thread-count screen](results/20261004-csf/csf-omp1-screen.json) preserves all
measurements; its existence does not qualify it as the selected configuration.

## Native scale-expansion trial

With 16 threads restored, `B12X_W4A8_CSF_INLINE=0` retained compressed scales
and expanded them for native kernels before each call. The
[matched screen](results/20261004-csf/csf-inline0-screen.json) completed.

| Context | Concurrent requests | Inline CSF | Per-call expansion |
|---|---:|---:|---:|
| 8K | 1 | 71.85 | 55.61 |
| 8K | 8 | 176.43 | 160.13 |
| 8K | 16 | 223.97 | 219.79 |
| 128K | 1 | 61.65 | 66.24 |
| 128K | 8 | 154.87 | 144.63 |
| 128K | 16 | 218.50 | 201.59 |

Cold prefill fell to 3,617 and 3,806 prompt tok/s. The larger 128K/C1 raw
throughput came with greater acceptance (3.18 versus 2.78) and fewer engine
steps/s (20.80 versus 22.22). This mode was rejected. Inline CSF and 16 CPU
threads were chosen for the final image layer and full qualification.

## Memory and startup

Published shard storage decreased from 510,296,708,312 to 495,629,051,096 bytes,
a saving of 13.66 GiB per full checkpoint copy. The final loader reported
71.47 GiB of model memory per node, versus about 74.4 GiB previously. Final
available GPU KV-cache memory is 20.02 GiB per node, versus 15.93 GiB in the
previous selected runtime. Final engine-reported capacity is 13,991,822 tokens,
versus 12,879,953 previously. The first CSF prototype reported 20.48 GiB and
13,676,052 tokens; those figures are not the final image's startup receipt.
LIL reports a separate capacity estimate using 128-token blocks; this engine
uses 256. Treat the engine startup receipt as the engine's capacity report.
The context limit remains 1,048,576, with 16 active sequences and an 8K batch
ceiling. Sixteen simultaneous million-token prompts are not implied.

The first cold startup needed approximately 18 minutes including model loading,
2,022 autotuning requests, graph capture and JIT warmup. Checkpoint loading
alone took 145–192 seconds. This is a startup cost, not a per-request latency.
The inline-CSF decode path is enabled; large-prefill calls use expanded scales
in shared scratch. No blanket claim of fully in-memory inference is made.

## Numerical and serving qualification

All four GPUs passed 124 upstream CSF tests each, including TP4-compatible
inline MoE parity and CUDA graphs. Preparation/cache tests passed 110 cases;
blockscaled lowering passed 14; the retained compressor/block-table tests
passed 16 with one skip. The custom fixed-regime check passed row counts
1, 6, 7 and 16, with zero-tolerance comparisons, stable pointers and replay
without allocations. The four-node prepared transport passed numerical,
ownership, graph replay and proxy checks. Earlier harness, memlock and
page-cache-related probe failures are retained in the evidence.

Seven ordinary and seven fresh long-context functional probes passed. Three
mixed-traffic integrity rounds passed with eight ongoing decoders and fresh
long prompts. The query-indexer guards passed exact raw scores and selected
score values; legal tied indices may differ.

Eight 2,048-token decode/replay consistency probes completed with fresh prefill
and top-20 log probabilities. Late-bin coarsened KL was 0.01307, versus 0.01538
in the September 29 corrected control; top-1 agreement was 97.34% versus
97.49%. This is a finite consistency check and a coarsened lower bound, not
full-distribution equivalence or a general quality score. It does not show a
return of the pre-correction long-answer drift. See the
[raw consistency result](results/20261004-csf/consistency.json).

One older preparation-cache fixture was incompatible with the new source's
state fields. Its failed receipt is preserved; the corresponding newer
preparation/cache suite and actual serving preparation passed. The image's
sealed manifest deliberately retains `serving_qualified: false`: deployment
qualification belongs to the external campaign receipt. The inherited status
dashboard still describes the parent; use the derived manifest for source pins.

The first CSF configuration also retrieved the correct needle from 1,008,432
uncached prompt tokens in 371.26 seconds to first content. The September 29
corrected control took 322.1 seconds; these were separate runs rather than a
new same-session million-token A/B. This long-prefill result is slower.

## Updated SparkRing integration

The upstream branch advanced to `721db585e2050bef93518c6cced1dae57ff43af4`.
A separate [pinned reliability layer](image/csf/sparkring-update/README.md) adds
supervised peer waits (proxy ABI 5), the exact upstream named/required tool-call
contract wrapper, and runtime-status 0.3.3. Its new transport profile changes
six wire/proxy files; it does not claim those files remain identical to the
original transport. Four-node GPU qualification passed, including a 20-second
late peer that remained healthy and a peer exit that stopped the wait. The
updated CPU suites passed 223 tests with one skip. Earlier incomplete fixture
staging and one manifest-field typo are retained as failed attempts.

CDI refresh was already enabled on all hosts, with `nvidia.com/gpu=all` present.
A candidate lifecycle template was prepared to check that prerequisite before
a stopped fleet starts; it was not installed after the candidate was rejected.
The final image layer does not reinstall the fabric, modify unrelated Qwen
profiles or adopt unrelated model-source updates. The original installed
controller receipt stays intact; derived source pins are in the campaign
manifest and new runtime inventory.

The final image retained actual NVML access on all four nodes both before and
after a systemd daemon reload. The live tool-policy API passed eight cases:
named/required calls, complete/truncated budgets and streaming/nonstreaming
responses. The final ordinary and fresh long-context suites each passed seven
cases. Eight new long-answer consistency probes produced late-bin coarsened
KL 0.01498 and top-1 agreement 96.85%, versus 0.01538 and 97.49% in the earlier
corrected control. KL decreased across the measured token bins; this finite
sample does not show renewed growing drift or establish full quality
equivalence. [Final raw result](results/20261004-csf/final-consistency.json),
[tool-policy API receipt](results/20261004-csf/final-tool-policy-api/report.json).

The final mixed-traffic check passed three rounds with eight decoders and two
fresh long prompts per round. Median client stream-chunk gaps rose from
0.092–0.101 seconds before prefill to 1.181–1.239 seconds during it, then fell
to 0.123–0.138 seconds afterward. Fresh first-content latency was 31.56–63.69
seconds. These are stream-chunk observations, not per-token GPU latency, and
passing retrieval/integrity does not mean contention has no user-visible
pause. [Raw mixed-traffic result](results/20261004-csf/final-mixed-integrity.json).

## Final full benchmark

The [full candidate report](FULL-BENCHMARK-CSF-20261004.md) records all 20 sustained
cells, 20 complete-response burst cells, standalone cold prefill, five coding
throughput runs and three fresh large-context retrievals. All sustained cells
were valid; 19/20 burst cells were valid. The 128K/C8 burst warmup repeated
a 945-character passage four times and was rejected. Its negative sentinel
throughput is not a speed result. This single failure does not establish a
general quality regression attributable to CSF.

| Context | Concurrency | Previous corrected tok/s | Final candidate tok/s | Change |
|---|---:|---:|---:|---:|
| 8K | 1 | 60.98 | 76.93 | +26.2% |
| 8K | 8 | 178.40 | 153.76 | -13.8% |
| 8K | 16 | 242.96 | 219.22 | -9.8% |
| 128K | 1 | 59.36 | 58.87 | -0.8% |
| 128K | 8 | 166.88 | 131.46 | -21.2% |
| 128K | 16 | 229.62 | 188.60 | -17.9% |

These overlap the same-day baseline screen; they are short stochastic samples,
not confidence intervals. At 8K/C1, acceptance rose to 3.60 while engine steps/s
fell to 21.34, versus 2.38 and 25.67 before. The higher output rate does not
establish a faster target kernel. Final C8/C16 throughput fell by 9.8–21.2%.

Final cold prefill was 3,308–3,595 prompt tok/s across 8K–128K. At roughly
129K actual tokens, first-content latency was 37.65 seconds versus 29.18
seconds in the previous corrected screen. Five coding prompts completed at
94.26 tok/s mean (87.90–101.89); generated programs were not correctness-scored.

Fresh retrieval passed at 245,588 / 503,898 / 1,008,429 actual prompt tokens
with zero cached tokens, in 68.31 / 150.84 / 351.85 seconds to first content.
The final million-token result is better than the initial CSF prototype, but
slower than the older corrected 322.1-second measurement. That latter comparison
is from separate runs, not a fresh same-session million-token A/B.

## Selection decision

The user rejected the integrated CSF/beta/updated-SparkRing candidate after
slower prefill and high-concurrency measurements. The completed full grid
supported that decision. Promotion was canceled before changing the permanent
root-owned configuration or lifecycle helpers. The previous KK926/#943-corrected
vLLM/B12x configuration was restored, preserving the fidelity
fix, HF tokenizer, local optimizations and 2350 MHz cap. The rejected CSF
checkpoints were removed: GX10 remainder before direct fabric recovery, and
Spark copies after restored original serving passed health checks.

This experiment changed the checkpoint loader, vLLM, B12x, CUTLASS DSL,
transport supervision and tuning cache together. It does not isolate the cause
of the slowdown or show that the lossless checkpoint alone is intrinsically
slower. The CSF format preserves the original weight bytes; the throughput
regression belongs to this tested runtime bundle. Recipe, immutable identities,
failed attempts and benchmark evidence are retained for future targeted work.

## Completed restoration and cleanup

The normal controller restarted the retained `ds41-optimized-r0..3` containers
with their exact pre-campaign image identities. The root-owned selection and
lifecycle helpers were never replaced. The ordinary functional serving check
passed; final API health and all four original image identities were verified.
At the user’s request, no repeat full benchmark or large-context performance
probe was run on the restored recipe.

All 48 original shards on every rank match the original immutable Hub SHA-256.
The Spark originals were retained. GX10 recovery first reconstructed expert
shards byte-for-byte from CSF, then switched to direct fabric copies from the
verified Spark originals at the user’s direction. Remaining GX10 CSF trees were
removed before transfer to free space; complete verified originals remained
on both Sparks. Each copied shard passed its original SHA-256 before
publication. Synthetic reconstruction and guarded deletion checks passed before actual fleet recovery.

| Rank | Original shards verified | Shards reconstructed | Shards copied over fabric | Remaining candidate bytes removed |
|---|---:|---:|---:|---:|
| 0 | 48 | 0 | 0 | 495,679,671,212 |
| 1 | 48 | 0 | 0 | 495,678,852,229 |
| 2 | 48 | 40 | 8 | 226,432,432,805 |
| 3 | 48 | 46 | 2 | 203,122,877,709 |

On GX10s the compressed weight shards were removed incrementally only after
their original replacements passed verification. Remaining GX10 candidate bytes
above were removed before fabric recovery under the updated instruction.
On Sparks, final cleanup after restored serving removed
the full candidate copy. All four exact CSF revision directories are absent.
Stopped candidate trial containers were removed; the temporary CSF and
original-checkpoint artifact servers were stopped. Candidate image layers and tuning caches remain as
build provenance; original images, Qwen and the stock fallback were preserved.

The 2350 MHz upper-cap service remains active and enabled on every node.
The serving endpoint remains `http://192.168.50.219:8015/v1`.

[Deployment receipt](results/20261004-csf/deployment.json),
[final audit](results/20261004-csf/restored-final-audit.json),
[functional check](results/20261004-csf/restored-functional.txt),
[rank 0 weight proof](results/20261004-csf/original-restore-r0.json),
[rank 1 weight proof](results/20261004-csf/original-restore-r1.json),
[rank 2 weight proof](results/20261004-csf/original-restore-r2.json),
[rank 3 weight proof](results/20261004-csf/original-restore-r3.json).

The delegated [TensorFold assessment](TENSORFOLD-ASSESSMENT-20261004.md)
recommends retaining corrected vLLM. A future published-TP2 pilot could test
short independent traffic, but its lossy EXL3 weights, slower reported prefill
and API/concurrency limits prevent treating it as a drop-in upgrade.
No TensorFold runtime changes were made.
