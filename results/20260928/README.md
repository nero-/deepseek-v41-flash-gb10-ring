# Evidence index

These are measurements from the pinned four-node SparkRing vLLM deployment. `installer-*-tune.json` files use LIL v0.6.2 with engine-default thinking/sampling and identical 8K decode cases. `installer-stock-matrix.json` adds 8K/32K/64K contexts; the separate stock C16 file covers 8K/32K.

`measure-*` directories contain command/status receipts and the 75-task qeval output. A `smoke` exit of 1 reflects the known greedy-repeatability failure where the accompanying functional/needle checks passed; it must not be described as an unconditional smoke pass. `measure-engram-top20/wrapper-failure.json` records its separate shell-wrapper exit 127 after the benchmark JSON completed. Rejected projection/indexer trials record how many exactness guards enabled and why their performance results were not used.

`mixed-*` reports retain request timestamps, reported usage, first-token times and content-chunk gaps for eight ongoing decoders plus two fresh prompts. Chunk gaps are not individual-token latency. `integrity-*` is a separate under-load retrieval test; its traffic differs from the latency benchmark. `nic-*` snapshots capture error/retry counters without resetting them.

`final-*.matched-request.json` records the explicit request contract (thinking off, temperature 1, top_p 1, top_k -1) and harness/adapter hashes. Do not compare this decode result directly with engine-default screens as if only the runtime configuration changed.

The original SGLang comparison files remain under `../20260927`. No fresh SGLang return test ran. Historical cross-engine decode numbers have differing thinking defaults.

Full startup logs and host-specific trial specs are retained on spark-r0 under `~/sparkring-migration-20260927`; local copies of host specs and session notes are ignored by Git. Controller credentials, runtime identity bindings and upstream private site configuration are not published.
