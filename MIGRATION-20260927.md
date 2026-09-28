# SparkRing installer migration and tuning record

Status: SparkRing installed on all four nodes; the selected configuration is
`engram-adaptive4k`. SGLang runtime retirement is complete. Final lifecycle and
selected-deployment checks are recorded in RESULTS.md.

The objective is to improve **both prefill and decode**, including concurrent serving, using applicable execution changes from the Qwen campaign. The user subsequently chose to retire SGLang and cancel further SGLang testing. The records below describe the chronological investigation; current operating state and selection are summarized in RESULTS.md.

## Selected inputs

- Source: FujitsuPolycom/sparkring, branch `one-command-installer`, commit
  `8b152d65c701f557f62ae6a9a1c3db90771c1df3`.
- Profile: `deepseek-v41-flash-tp4` (vLLM, replacing the existing SGLang recipe).
- Image reference from the package lock: `ghcr.io/fujitsupolycom/sparkring@sha256:2c45153abf19af4f2b4bf10445cfc96c711c375a6fc5c04d3a2b55496f3acfe3`.
  Expected image ID: `sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf`.
- Checkpoint pin: `dba1be0a40aa45a94ad051997016db3960a90277`.
  Before retirement, reuse sources were `/home/nero/NewModels/DeepSeek-V4.1-Flash` on every rank.
  The old installation recorded identical weight hashes at its newer revision;
  installer verification preceded hard-link reuse.
- Local source inspection checkout: `../sparkring-installer`.
- Remote clean checkout: spark-r0 `~/sparkring-installer`.
- Built package: `~/sparkring-installer/.sparkring/dist/sparkring_0.1.0~dev.1790565931+git8b152d65c701_arm64.deb`.
- Package SHA-256: `81c3f9cff866960b825067be6c8191eac094809fc1315a25701951a99b26cb95`.

## Pre-migration fleet observations

Rank order remains spark-r0, spark-r1, gx10-r1, gx10-r0. SparkRing preserved
the existing IPv4 fabric addresses and MTU. The old `dsv41-mesh` service is
disabled on all ranks. The mode-switch script needs updating for the new
DeepSeek launcher and mesh; the Qwen pair addresses remain valid.

Free space: spark-r0 2.7 TiB, spark-r1 2.6 TiB, gx10-r1 139 GiB,
gx10-r0 144 GiB. Each has about 476 GiB of DeepSeek checkpoint files and
48 GiB of packed Engram files. The new profile reads Engram directly from
the checkpoint, so packed files are a possible cleanup target if required.
Reuse the checkpoint through verified hard links instead of duplicating it.
Retain the Qwen hybrid checkpoint and package. Apply any old-DeepSeek cleanup
consistently to all four hosts, as requested.

Pre-migration observations and the existing DeepSeek environment are saved
on spark-r0 under `~/sparkring-migration-20260927`, including all four original
netplan files. Setup receipts remain under `/root/.local/state/sparkring/setups`.

Automatic IPv6 discovery failed to match a Socket Direct neighbor. Used the
supported explicit `--node root@LAN_IP` setup on authenticated hosts instead.
Node A's generated controller key is authorized for root SSH on these four
nodes, with host keys pinned from existing LAN SSH. Workers therefore do not
depend on the temporary passwordless sudo rule for `nero`.

The first network setup attempt completed NetworkManager configuration but
failed GID verification: stable-privacy link-local IPv6 occupied GID 3 while
IPv4 landed at GID 5. Set `ipv6.addr-gen-mode eui64` on the new SparkRing fabric
profiles, reactivated them while all workloads were stopped, then repeated
setup. All GID and jumbo-frame checks passed; no driver reload was needed.
`scripts/normalize_installer_ipv6.py` records the site-specific fix.

The reviewed installation plan reuses 48 weight files through hard links on
each rank, copies 26 small files and downloads three differing encoding files
(59.2 KB total) from the pinned revision. It requires 100 GiB of additional
space per node; both GX10s pass without cleanup.

## Installation and qualification sequence

1. Installation and readiness passed on all ranks; first cold startup took about
   16 minutes, including kernel preparation and graph capture.
2. Chat, tools, image input, thinking, concurrent requests and long-context
   retrieval were checked; the final selected LIL v0.6.2 screens completed.
3. Controlled tuning, mode switching and documentation are complete. The
   selected deployment is serving. Temporary broad sudo rules were removed
   from both Sparks, and fixed passwordless up/status actions were verified.

## Decode investigation

The upstream profile already enables DSpark5, probabilistic drafting, block
rejection, adaptive verification, NVFP4 draft layers/head, exact multiples of
5 and 6 in CUDA graphs through 96 rows, and 16 concurrent sequences. It leaves
target checkpoint precision unchanged. Engram overlap is deliberately disabled
because upstream observed problematic synchronization behavior.

Alongside actual Qwen execution changes (see QWEN-TRANSFER.md), compare verification step rates
and acceptance alongside tokens/s; use identical prompts, sampling and contexts;
measure fresh baseline and return-leg repeats; preserve full vocabulary and
target precision. Do not transplant Qwen-only HC or GDN switches.

Prioritize actual adaptive-verification graph coverage at C1/C3/C5/C8/C16,
profiling of dense/MoE/collective time, and GX10 Engram I/O latency. The updated
transport paces forwarded traffic, so the old SGLang 491,520-byte RoCEnante cap
must not be copied blindly. Inspect paced transport behavior and NIC error
counters before changing collective thresholds. Require repeatable improvements
and passing functional checks before selecting an optimization.

## Runtime source findings

The installed image reports vLLM `0.1.dev21510+g1794dcf18.d20260924`;
its receipt records baseline `1794dcf18454900263e0c66711af8ea4a1283ac1`
and integrated source `03c4af34fbe6d2ff863bd03a6ed255c4de96785b`.
GitHub's compare API confirms the baseline is 58 commits ahead of the documented
Karmic Kraken commit `35bab057b1751a6076a457803bcc4b78809689cf`, with none behind.

Native DeepSeek implementation: `vllm/models/deepseek_v4_1`. Its
`_use_sequence_parallel` returns false; the existing SGLang adapter does shard
large prefill residuals and row-local work. Porting that behavior would require
more than toggling the upstream sequence-parallel flag: Engram explicitly
rejects sequence-parallel inputs in this implementation.

`EngramLayout` supports `engram_config.projection_tp`, which column-shards the
large WKV projection and gathers the result; the installer profile leaves it
false. This is a concrete, bounded candidate analogous to the existing SGLang
replicated-projection split. Another candidate fills small CUDA graph sizes
missing between the recipe's multiples of five and six. Both completed independent screens. `bench/installer_variant.py` generates separate trial containers
from the retained installed specs and preserves the managed containers.

## Initial qualification (2026-09-28 UTC)

- Upstream functional probe: 7/7 passed (counting, arithmetic, code, automatic
  tool call, forced tool call, image input, thinking).
- Existing smoke: arithmetic, tools, thinking and the 125,219-token needle
  passed. Needle wall time was 35.2 seconds, including decode (old recorded
  result: 29.0 seconds). This is not the standalone prefill benchmark.
- Greedy repeatability failed: three temperature-zero haiku requests did not
  produce identical text. Subsequent seeded/unseeded checks also failed repeatability.
- First qeval invocation failed before testing because its adjacent
  `qeval_tasks.py` module was absent from the copied harness directory. Corrected
  the runner's Python import path; no model-quality result from that failed run.
- Corrected stock qeval: 71/75, median 79.09 tok/s. Five repeated greedy requests
  produced five different replies both without a seed and with seed 42.

## First engine-default measurements (not a fully matched cross-engine comparison)

LIL v0.6.2, identical case definitions, server-default temperature and thinking.
**Cross-engine limitation:** matrix requests do not set chat-template kwargs.
SGLang defaults thinking off; vLLM defaults thinking on. Within-vLLM trials
keep the same defaults and remain comparable. Historical SGLang numbers are
not a fully matched cross-engine decode comparison. No further SGLang comparison will run, per the user's decision to retire it; functional, qeval and mixed-traffic probes already set
thinking explicitly.

| Context | SGLang prefill | Stock vLLM prefill | SGLang C1 | Stock vLLM C1 | SGLang C8 | Stock vLLM C8 |
|---|---:|---:|---:|---:|---:|---:|
| 8K | 5151 | 3864 | 67.7 | 58.8 | 160.1 | 193.7 |
| 32K | 5613 | 4435 | 64.9 | 56.8 | 145.8 | 183.4 |
| 64K | 4877 | 3664 | 66.8 | 55.2 | 154.2 | 171.5 |

Stock vLLM C16: 256.5 at 8K and 263.5 at 32K (old 224.5 / 196.8).
All throughput units are tokens/s; concurrency columns are aggregate throughput.
All matrix and C16 cells completed without server errors.

The separate 20-second tuning screen at 8K gives:

| Candidate | C1 | C3 | C5 | C8 | C16 | Prefill 8K | Prefill 64K |
|---|---:|---:|---:|---:|---:|---:|---:|
| Stock | 56.4 | 110.6 | 144.3 | 196.2 | 267.5 | 4433 | 3353 |
| Engram projection TP | 63.1 | 113.8 | 157.1 | 203.7 | 277.0 | 4467 | 4232 |
| Engram TP, 16K batch ceiling | 60.5 | 120.4 | 149.7 | 204.2 | 276.9 | 4462 | 4370 |
| Engram TP, 8K return leg | 64.7 | 118.5 | 152.4 | 193.2 | 276.9 | 4127 | 4101 |

Engram TP: functional 7/7, qeval 72/75 (median 83.02 tok/s), no NIC error-counter
increase during the sampled interval; greedy repeatability still fails. Prose,
code and JSON median decode after first token: 56.70 / 100.88 / 110.42 tok/s
(stock 46.97 / 96.35 / 102.90). The 8K return leg reproduced the C1/C16 and
64K-prefill improvement over the stock tuning screen; C8 varied enough that a
small improvement there is not established. Final combined qualification is recorded separately below.

Engram TP plus `B12X_DYNAMIC_DETERMINISTIC_OUTPUT=1` failed before serving:
`b12x preparation failed on rank 2: preparation used undeclared programs for fused_moe ... /m3`.
The setting is rejected for this pinned prepared runtime; no speed or quality
result is attributed to it. Its logs are retained.

The 16K trial completed functional 7/7 and qeval 71/75; greedy repeatability
still fails. Its reported KV capacity was 7,370,240 tokens versus 9,413,760 in
the first Engram-TP 8K run. Its C8/C16 throughput was essentially unchanged,
with only a 3.3% change in the 64K standalone prefill screen. This does not
justify selecting 16K. Keep 8K as the selection baseline.

`bench/mixed_traffic.py` measures eight ongoing decoders while two cold prompts
of about 29K tokens arrive. In three 16K rounds, p95 content-chunk gaps during
the new requests were 2.29–2.40 seconds, maxima 3.87–4.10 seconds. First-token
times for the arrivals were 7.83–8.16 and 14.06–14.37 seconds. All requests were
error-free. These are SSE chunk gaps, **not individual-token latency**; DSpark
can return multiple tokens per chunk. The matched 8K return leg completed three rounds: p95 1.98–2.11 seconds,
maxima 2.05–2.24 seconds, and arriving-prompt first-token times 8.15–8.79
and 14.66–15.50 seconds. No errors. 8K approximately halves the worst observed
decoder stall at a modest arrival-latency cost; 16K is rejected as the default.

An explicit local plugin in `image/vllm-local-plugins` ports the old SGLang
decode-only Q/KV projection strategy. It retains the full prefill path and
requires per-layer, all-rank bit-exact checks before using sliced decode
projections. The corrected plugin reached GPU serving and its fallback passed functional
7/7, but **0 of 43 projections passed the bit-exact guard**. Reject it as a
performance candidate; no speedup is claimed. Initial retries caught the
1,792-column uneven tiling and B12x's requirement for equal prepared geometry
on all ranks. The final attempt pads each rank to 512 output columns. All
three attempts, source hashes and logs are retained locally under the ignored `results/20260928/variants` directory and on the head; host specifications are not published. Full SGLang prefill sequence
parallelism has **not** been ported: it requires changes to residual, Engram,
collective and CED boundaries, not just a launch flag.
A separate old-engine pacing image was built but never tested. Its campaign was cancelled and its runtime/source artifacts retired along with SGLang. Frozen SparkRing installer receipts were not modified.


## Additional experiments requested by the user

The following independent screens retained Engram TP and the 8K scheduler ceiling:

- `engram-fair4k`: native `prefill_compute_share=auto`, responsive half-life,
  and `max_num_prefill_tokens_per_step=4096`. The smaller budget applies under
  prefill/decode contention; unloaded prefill keeps 8K. Test mixed arrival
  latency as well as steady-state throughput.
- `engram-graphs`: add every graph size from 1 through 32 to the existing
  captures. This applies the Qwen lesson about wasted padded verification work.
- `engram-cost125`: increase adaptive verification's cost scale from 1 to 1.25,
  testing whether less low-value speculative work improves verified tokens/s.

`bench/novel_campaign.py` runs these serially and preserves the measurements;
none is selected automatically. All startup geometry and target precision
remain fixed apart from the explicitly recorded trial setting.


The native fair-share 4K trial completed functional 7/7, qeval 71/75, and
C1/C3/C5/C8/C16 throughput of 60.35/121.93/157.85/199.70/273.82 tok/s.
Prefill was 4542/4115 tok/s at 8K/64K. Mixed-traffic maximum chunk gaps
fell to about 1.3 seconds, but incoming first-token times rose to roughly
16/28 seconds. This tradeoff does not meet the balanced objective.

Expanded graph coverage completed functional 7/7 and qeval 73/75 (median
83.7 tok/s). C1/C3/C5/C8/C16: 62.75/120.76/161.92/202.14/276.78 tok/s;
prefill 4274/4242 at 8K/64K. The mid-concurrency result is promising but
requires a repeat; the quality-score difference is not proof of an improvement.

The user's Qwen clarification is tracked in [QWEN-TRANSFER.md](QWEN-TRANSFER.md):
adaptive HC, owned-row prefill, top-20 draft proposals, graph coverage and the
other actual execution changes. Top-20 proposal filtering has a bounded native
DSpark port that passed GPU distribution/cache qualification, then showed no clear full-model gain. Adaptive HC's
channel-gather tradeoff is absent from the current fused DeepSeek mHC path,
so its four-row cutoff cannot simply be copied.

Adaptive verification cost scale 1.25 completed functional 7/7 and qeval 72/75
(median 82.81 tok/s). C1/C3/C5/C8/C16: 64.46/116.74/156.82/204.52/273.66;
prefill 4386/4013 at 8K/64K. At C8 the request-step equivalent rate rose to
89.65/s but effective acceptance fell to 2.281 tokens/step. C16 similarly rose
to 117.84 steps/s with 2.322 tokens/step. This does not establish a balanced
improvement over Engram TP; it remains unselected.

The native indexer-row TP attempt was rejected: 0 ON / 12 OFF real-input
selection guards. Fallback functional checks passed 7/7; the 122,260-token
needle passed in 33.6 seconds including decode. Its tuning screen was
interrupted after confirming zero enabled cases; no performance result is
attributed to this optimization. No guard was relaxed. The precise source
of the mismatches remains unestablished. The serial campaign continued with
the separate adaptive 4K-under-contention scheduler.

For explicitly fixed request settings, `MATCHED=1` runs the unchanged LIL
harness through `bench/lil_matched.py`. It sets chat requests to thinking off,
temperature 1.0, top_p 1.0 and top_k -1. The adapter records these fields and
both source hashes beside each result as `.matched-request.json`. It leaves
prompts, timings, token accounting and case scheduling unchanged. The SGLang return leg was cancelled before execution at the user's request.

Adaptive token quantum (`engram-adaptive4k`) completed functional 7/7, qeval
72/75 (median 81.82 tok/s), and all three mixed rounds without errors. It keeps
the ordinary scheduler and uses a 4K budget only with >=4 runnable decoders
and pending prefill. C1/C3/C5/C8/C16: 57.51/117.02/166.84/193.69/274.43;
prefill 4449/4160 at 8K/64K. C1's effective acceptance was 2.142 and step
rate 26.85/s, so its lower token rate alone is not a demonstrated compute
regression. Mixed p95 chunk gaps: 1.089–1.097 seconds; maxima 1.157–1.240.
Fresh first-token times: 8.954–9.021 and 15.997–16.104 seconds. The separate
under-load two-needle test passed. Compared with the 8K return leg, this
approximately halves the worst pauses at a modest arrival-latency cost.
The combined `engram-adaptive4k-graphs` candidate is qualified separately.

The top-20 proposal port passed 19/19 GPU component checks: adversarial
truncated proposals at depth five, FP32/BF16 cached logits, temperatures
0.6/1.0, standard/block rejection, plus full 129,280-column cache and graph
replay checks at temperatures 0/0.6/1.0. The first runner stopped because
pytest was absent; no assertions ran then. The same assertions were rerun
directly without changing the serving image. The full-model trial passed functional 7/7 and qeval 71/75. Its C1/C3/C5/C8/C16 throughput was 62.41/119.66/160.18/193.80/278.65, prefill 4006/4053 at 8K/64K. No clear overall gain: top-20 is not selected. The tune JSON completed, but an in-place edit of the running shell wrapper caused a trailing `one: command not found` (exit 127). Its campaign is preserved as failed; this is not a serving failure or a clean qualification pass. Script updates now use atomic replacement.


## Final selection

Selected `engram-adaptive4k`: Engram projection TP plus the ordinary scheduler
with a 4K token quantum only when >=4 runnable decoders contend with prefill.
The configured allocation ceiling remains 8K, max sequences 16, context limit
1,048,576. Stock graph sizes, adaptive-verification cost and draft sampling remain.

The combined expanded-graph trial passed functional 7/7 and qeval 72/75
(median 81.22 tok/s). C1/C3/C5/C8/C16: 54.8/120.1/157.9/188.9/277.1;
prefill 4458/4121 at 8K/64K. This did not establish a balanced gain. Its completed
screens are retained; the subsequently started mixed test was cancelled once
the selection decision was made. Queued matched and near-1M checks for that
unselected configuration were cancelled before execution and moved to the
selected profile. No combined mixed result or graph speedup is claimed.


## SGLang retirement

After vLLM qualification, all workloads were stopped. On each node all 48 new
weight files were verified as regular files, with matching old/new inodes and
no checkpoint symlinks. The old checkpoint names, packed Engram shards, SGLang
recipe/cache, custom NCCL library, mesh units/tools/sudo rule, and all three
old serving/trial image tags were removed. All 48 new weights remained present
with unchanged sizes afterwards. No global Docker prune or Qwen cleanup ran.

`results/20260928/retirement.json` records the scoped removals and free-space
change: approximately 47.7 GiB reclaimed per node, GX10 free space 161.7/166.9
GiB. Model bytes shared through hard links remain under SparkRing. Historical
benchmark/quality evidence is retained; no further SGLang serving test ran.


## Lifecycle qualification

The permanent selected containers reached readiness after SGLang retirement.
`ring-mode.sh qwen both` then stopped those owned containers, disabled the native
mesh, and brought both Qwen pairs to healthy APIs. Both returned `391` for
17×23 using their correct `enable_thinking=false` request option. Their selected
`hc-adaptive+cg4+m5500h` profiles and 24 GiB KV allocation were unchanged.
An earlier optional client probe used DeepSeek's `thinking` key by mistake; it
is recorded as a client error and was corrected, not scored as a Qwen failure.
The following `ring-mode.sh ds` completed the permanent selected restart path;
its post-restart functional probes passed 7/7. Logs and hashes are recorded in
`results/20260928/lifecycle.json`.


## Permanent-deployment throughput repeat

After the selected → Qwen both → selected lifecycle round trip, functional
checks passed 7/7 and the final engine-default tuning screen completed without
errors. C1/C3/C5/C8/C16: 63.1/122.6/148.5/202.7/280.4 tok/s; prefill
4201/4117 at 8K/64K. C1/C16/64K-prefill gains over stock were reproduced
(about 12%/5%/23%). Short-prefill and mid-concurrency results vary; neither
a uniform speedup nor a universal acceptance improvement is claimed.


The separate explicit-request run (thinking off, temperature 1, top_p 1,
top_k -1) completed without errors: C1/C3/C5/C8/C16
60.2/116.0/131.0/168.9/225.5, prefill 4433/4071 at 8K/64K. This is a new
selected-profile baseline. It must not be conflated with the 280.4 tok/s
engine-default C16 result or treated as an isolated thinking-only A/B. No
stock-vLLM or fresh SGLang result with this complete explicit contract exists.


## Completed long-context and access checks

The selected deployment returned the correct needle from 1,008,411 prompt
tokens in 526.4 seconds (1,916 prompt tokens/s including decode). Arithmetic,
tools and thinking passed; smoke's exit 1 is the known greedy-repeatability
failure. The request initially appeared stalled because engine progress metrics
were stale during the long operation. It finished without restart or cancellation; subsequent
stack samples showed idle engine workers. No OOM kill or RDMA error/retry-counter
increase was observed. The model remained healthy.

Historical SGLang: 1,000,169-token needle in 247.6 seconds. The new result does
not match that very-long-context performance, despite the controlled 64K gain
over stock vLLM. Full residual sequence parallelism remains future work.

Temporary migration-wide sudo grants were removed from both Sparks after
qualification; fixed passwordless lifecycle controls and controller root SSH
remain. GX10 pre-existing permissions were unchanged.


Final state: all four `ds41-optimized-rN` containers are running and their
SparkRing meshes are active. Fixed passwordless `up` and `status` passed after
the broad sudo grants were removed. A fresh post-long-context request returned
27×19 = 513 in 0.17 seconds. The final NIC snapshots show no changed error/retry
counters. Evidence is in `final-health.json`, `sudo-retirement.json` and
`nic-selected-delta.json`.
