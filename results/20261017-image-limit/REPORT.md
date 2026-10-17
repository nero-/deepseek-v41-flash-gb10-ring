# Image request limit raised from 4 to 999

The selected command now sets `--limit-mm-per-prompt '{"image":999}'`
on all four ranks. This is the only command change. Image, checkpoint,
20 GiB KV, plugins, RoCEnante transport, clock policy, generation defaults,
context length and image preprocessing are unchanged.

Profile: `engram-adaptive4k-query-indexer-1017-runtime1015-kv20-images999`.
Configuration SHA256: `b9178b380923cdfaf2e8e7ac56d7e617031bec7b7acd677622eaaa01f53f8034`.

## Cause and meaning of the new limit

A five-image request reproduced HTTP 400: “At most 4 image(s) may be provided
in one prompt.” `/health` remained HTTP 200. The configured count caused this
failure; no engine crash was reproduced. Since OpenAI-compatible chat requests
carry earlier messages, images accumulate across the submitted chat history.
Client-specific session recovery was not inspected; retry the failed message.

999 is vLLM's default count limit, not the model's physical maximum or a
promise that 999 large images fit. The pinned model processor returns no fixed
image-count cap. The existing context limit is 1,048,576 tokens; each image can
consume up to 1024 tokens in this checkpoint. Image preprocessing and transient
host memory also constrain large/concurrent requests.

Pinned upstream sources: [count configuration](https://github.com/local-inference-lab/vllm/blob/8244d1c44348ae8a5bbfc9f1b607021652283ed4/vllm/config/multimodal.py),
[DS41 processor](https://github.com/local-inference-lab/vllm/blob/8244d1c44348ae8a5bbfc9f1b607021652283ed4/vllm/models/deepseek_v41/common/mm_preprocess.py),
and [encoder batching](https://github.com/local-inference-lab/vllm/blob/8244d1c44348ae8a5bbfc9f1b607021652283ed4/vllm/multimodal/encoder_budget.py).
Installed source was inspected before the change. The scheduler's encoder
compute/cache budgets remain 8192 tokens (eight maximum-size 1024-token
images). Raising the request count does not reserve a 999-image GPU batch.
The pre-existing explicit KV allocation continues to skip automatic memory
profiling; no new profiling bypass was added. Default multimodal processor
caching is unchanged and may grow during sustained image use.

## Live checks

| Check | HTTP | Result | Wall seconds |
|---|---:|---|---:|
| 5-distinct-images-1024px | 200 | Pass | 2.47 |
| 16-distinct-images-64px | 200 | Pass | 1.12 |
| 64-distinct-images-64px | 200 | Pass | 4.07 |
| six-images-across-chat-history | 200 | Pass | 0.57 |
| text-followup-with-image-history | 200 | Pass | 0.34 |
| 1000-images-rejected | 400 | Pass | 0.06 |
| text-after-rejection | 200 | Pass | 0.14 |

The first test used five distinct 1024×1024 color fixtures. The 16- and
64-image tests used distinct 64×64 source fixtures, processed by the model's
unchanged minimum-size policy. Colors at the first/last image were correctly
identified. The 16-image test and chat continuation used streaming and received
`[DONE]`. History testing carried four earlier images plus two new images;
a subsequent text turn with the same history also succeeded. The 1000-image
request was intentionally rejected with HTTP 400, now naming the 999 cap;
the following streamed text request succeeded.

These checks do **not** qualify 999 distinct high-resolution images or a
high-concurrency image workload. No text throughput benchmark was required for
this count-only change, and no performance gain is claimed.

Head memory immediately after readiness was **117.43 GiB used**,
with **4.25 GiB available**, using
`MemTotal - MemAvailable`. The passive qualification sampler observed a head
peak of **118.22 GiB** and then exited.
It was not a runtime guard. Sampling can miss short allocation peaks.
All four final containers were running with zero restarts and no OOM kill;
plugins, mesh/clock-cap services, API health and installed-controller identity
checks passed. Read [final audit](final-audit.json),
[raw checks](multi-image-checks.json), and [memory summary](memory-summary.json).

## Recovery

Normal `ds` / `recover-ds` starts this selection. Four-image containers are
retained stopped as `ds41-before-images-rN`; root configuration backups are in
`/var/lib/deepseek-ring/experiments/image-limit-20261017` on spark-r0.
The private campaign is `/Users/jg/Agent/Diagnostics/deepseek-v41-flash-ring/image-limit-20261017`.
`change_limit.py rollback` restores the four-image selection on this same image
and checkpoint. This later selection must be undone before an older KV/runtime
rollback helper can accept its saved configuration. See OPERATIONS.
