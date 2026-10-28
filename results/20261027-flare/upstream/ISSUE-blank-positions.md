**Title:** DeepSeek V4.1 Flash: positions before token 128 return context-free logits when the reasoning-effort prefix is present

## Summary

With the default DeepSeek V4.1 chat render, some positions in the first 128 tokens produce a
next-token distribution that ignores the context. The default render is thinking mode, which
injects `Reasoning Effort: 75 (range 1-100, …)` after `<｜System｜>`, as the official
`encoding.py` does.

Every affected position returns the same flat distribution: `'\n'` −2.25, `'#'` −2.37, `'<'`
−2.74, `'##'` −3.09. The positions before and after it are sharp. At the packaged temperature 1
and top-p 1, the sampler then picks an arbitrary token, and the reply continues around it:

```
"Hi! 👋 What's on your五 mind today?"
"Hi! 👋 How can\n can I help you today?"
"Hi! 👋 What's on yourIt looks like my response got cut off — let me try that again. …"
"Hi! 👋 How can<ds_safety>[用户未成年]否 … </ds_sHome>can I"
```

The last example is the same defect: `'<'` is the third alternative, and after it the model
writes its safety-annotation format. `[{"role":"user","content":"Say hi."}]` with default
settings was corrupted in 6 of 6 Chat Completions requests. The packaged seed is fixed, so an
affected prompt fails the same way on every identical request.

## Environment

- `flare-inference 0.1.0~git20261027170349.7c22369f-1` (`7c22369f`) on every rank
- `local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE@gb10` (commit `607c1abf`), deployment
  `0a377833bb1c431ab417837a50bb18a8`, TP4
- 2× DGX Spark and 2× ASUS GX10 (GB10), RoCE through a switch, launched with `flare orbit run`
- The README's TP4 command plus `--embedding-table-storage disk --embedding-table-resident-scales --embedding-table-cache-size 1GiB --memory-limit=-2G`
- No other requests in flight; `flare_free_kv_pages` ≈ 116k and `flare_cached_kv_pages` ≈ 13k throughout

## Reproduction

Prefill only: `/v1/completions` with `max_tokens: 1` and `logprobs: 5` on the rendered chat
prompt plus the model's own first nine output tokens:

```
<｜begin▁of▁sentence｜><｜System｜>Reasoning Effort: 75 (range 1-100, the higher the value, the more thorough the reasoning)\n\n<｜User｜>Say hi.<｜Assistant｜><think></think>Hi! 👋 What's on your
```

```
BLANK prompt_tokens= 42  default chat render                '\n' -2.25 | '#' -2.37 | '<' -2.74 | '##' -3.09
BLANK prompt_tokens= 42  same, Reasoning Effort 50          '\n' -2.47 | '<' -2.57 | '#' -2.91 | '##' -3.23
ok    prompt_tokens= 16  same, no effort prefix             ' mind' 0.00 | 'mind' -17.56 | ' agenda' -20.26 | ' Mind' -21.36
ok    prompt_tokens=142  same, ~100 tokens after the prefix ' mind' 0.00 | 'mind' -15.10 | ' river' -15.65 | …
```

Five repeats of the first request return bit-identical top-5 logprobs.

<details><summary>Repro script</summary>

```python
"""Prefill-only probe: next-token distribution after each prompt via /v1/completions.
Usage: repro.py http://HOST:PORT/v1 MODEL"""
import json, sys, urllib.request
url, model = sys.argv[1].rstrip("/"), sys.argv[2]
B, S, U, A = "<｜begin▁of▁sentence｜>", "<｜System｜>", "<｜User｜>", "<｜Assistant｜>"
H = lambda n: f"Reasoning Effort: {n} (range 1-100, the higher the value, the more thorough the reasoning)\n\n"
filler = " ".join(["the river runs past old stone walls"] * 14)
tail = f"{U}Say hi.{A}<think></think>Hi! 👋 What's on your"
cases = [("default chat render", f"{B}{S}{H(75)}{tail}"),
         ("same, Reasoning Effort 50", f"{B}{S}{H(50)}{tail}"),
         ("same, no effort prefix", f"{B}{tail}"),
         ("same, ~100 tokens after the prefix", f"{B}{S}{H(75)}Notes: {filler}{tail}")]
for name, prompt in cases:
    body = {"model": model, "prompt": prompt, "max_tokens": 1, "logprobs": 5}
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url + "/completions",
        json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=300).read())
    top = sorted(d["choices"][0]["logprobs"]["top_logprobs"][0].items(), key=lambda kv: -kv[1])
    blank = top[0][0] in ("\n", "#") and top[0][1] < -1.5
    print(f"{'BLANK' if blank else 'ok   '} prompt_tokens={d['usage']['prompt_tokens']:3}  {name:34} "
          + " | ".join(f"{t!r} {l:.2f}" for t, l in top[:4]))
```

</details>

## Evidence

Each probe asks for one token after a prefix extended one word at a time, so every
measurement is the last position of a prefill. Positions are prompt lengths.

| Context | Probes | Blank positions |
|---|---:|---|
| Effort prefix, "Say hi." reply, 0–200 filler words after the prefix | 10 sweeps | 42 46 · 48 · 56 · 68 · 82 84 · 104 · 122 124; none once the reply starts at ≥ 136 |
| Effort prefix, sleep-tip reply, 0–400 filler words | 17 sweeps, 561 | 72 · 84; none at 127–478 |
| Effort prefix, `<think></think>` vs `</think>` | 2 sweeps, 124 | 42 46 vs 41 45 (same tokens, shifted by `<think>`) |
| No system block, non-thinking | 3 sweeps, 176 | none |
| 20-token plain system prompt instead of the effort prefix, both modes | 2 sweeps, 117 | none |

In total there were 16 blank positions out of about 520 below 128, and none out of about 440
at 128 or above.

- Which positions fail depends on content, not offset. Changing the effort score from 75 to 50
  moves the failures but doesn't remove them.
- Decode shows the same signature. Streamed Chat Completions with `logprobs` show the blank
  distribution at the spliced token, and the next position is sharp again (`' your'` −0.25,
  `' mind'` 0.00).
- After `<｜begin▁of▁sentence｜>` alone, the distribution is `'#'` −1.58, `'\n'` −2.34, `'##'`
  −2.94, `'<'` −3.44: the same family, but not identical.

This rules out:
- **Speculative verification:** the failure reproduces at the prefill's last position with
  `max_tokens: 1`.
- **Prefix-cache reuse:** a random tag after BOS (`cached_tokens: 1`) fails the same way.
- **The Helios frontend and output parsers:** raw `/v1/completions` reproduces it.
- **Stale page bytes (#116):** the output is deterministic and the pool is mostly free.

## Not tested

- A reference forward on the same prompts: DeepSeek's `inference/` or
  `ignition debug-serve --direct`. Without one we can't exclude the checkpoint itself.
- TP1/TP2, other GPUs, or Engram tables in memory (they do not fit in host memory here).
- Packages exported after `7c22369f`.

## Possible direction (needs maintainer input)

The boundary is 128 tokens, which is both `sliding_window` and `PAGE_TOKENS`
(`ignition/recipes/deepseek41/pool.py`). Below 128, the queried position sits in a partial
first window and a partial first page, which suggests these paths:

- `PreparedWindowIndices.__call__` (`ignition/components/window_indices.py`) with
  `left = (position - 127).clamp_min(0)` and window lengths below 128.
- The compressed geometry in `AttentionIndices.__call__`
  (`ignition/recipes/deepseek41/attention.py`), where `lengths = (position + 1) // ratio` is small.
- How `PreparedCompressedMLA` combines the partial window, the compressed rows and `sink`.

One `ignition debug-serve --direct` request with the 42-token prompt above would show whether
the prepared graphs or the checkpoint produce the blank distribution. We can run more probes
on this deployment if that helps.
