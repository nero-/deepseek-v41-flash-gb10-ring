#!/usr/bin/env python3
"""Decode and cold-prefill benchmark for an OpenAI-compatible DeepSeek-V4.1-Flash endpoint.

    python3 ringbench.py OUT.json [--url http://192.168.50.219:8888] [--quick] [--prefill 4096,16384,...]

Run it from a worker, not the head. Greedy, thinking off, 256 new tokens (Mia's sparkDash settings).

Decode: four prompt types, each with 16 distinct prompts, at concurrency 1/2/4/8/16. At c1 each
type runs five different prompts and reports the median, so one prompt's draft acceptance does not
decide the number. Token counts come from the usage block, never from SSE events:
    per-stream decode tok/s = (completion_tokens - 1) / (t_last_delta - t_first_delta)
    aggregate tok/s         = sum(completion_tokens) / wave wall time

Prefill: real text (Python sources from the node's stdlib) with a random nonce at the very start,
so nothing is served from the prefix cache; max_tokens=1 and prompt_tokens / TTFT.
"""
import argparse
import concurrent.futures as cf
import glob
import json
import random
import statistics as st
import time
import urllib.request

TOPICS = ["hash maps", "TCP congestion control", "photosynthesis", "the Roman republic", "B-trees",
          "garbage collection", "plate tectonics", "public-key cryptography", "jazz harmony",
          "vaccines", "compilers", "black holes", "supply chains", "the printing press",
          "neural networks", "coral reefs"]
PROMPTS = {
    "prose": [f"Write a clear, detailed essay explaining {t} to a curious adult." for t in TOPICS],
    "code": [f"Write a complete, well-commented Python module that implements {t}-themed utilities: "
             f"a class, three functions and unit tests. Topic: {t}." for t in TOPICS],
    "structured": [f"Produce a markdown table comparing ten facts about {t}, then a numbered list "
                   f"of five follow-up questions." for t in TOPICS],
    "json": [f"Return only JSON: an array of 12 objects describing concepts in {t}, each with "
             f"keys name, summary, difficulty (1-5), related (array of strings)." for t in TOPICS],
}


def stream(url, prompt, max_tokens, timeout=1800):
    body = {"model": "deepseek-v4.1-flash", "temperature": 0, "max_tokens": max_tokens, "stream": True,
            "stream_options": {"include_usage": True}, "chat_template_kwargs": {"thinking": False},
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time(); first = last = None; usage = {}
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            d = json.loads(line[5:])
            if d.get("usage"):
                usage = d["usage"]
            for c in d.get("choices") or []:
                delta = c.get("delta") or {}
                if delta.get("content") or delta.get("reasoning_content"):
                    now = time.time(); first = first or now; last = now
    n = usage.get("completion_tokens", 0)
    return {"t0": t0, "ttft": (first or t0) - t0, "end": last or t0, "tokens": n,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "decode": (n - 1) / (last - first) if first and last and last > first and n > 1 else 0.0}


def wave(url, prompts, max_tokens):
    t0 = time.time()
    with cf.ThreadPoolExecutor(len(prompts)) as ex:
        res = list(ex.map(lambda p: stream(url, p, max_tokens), prompts))
    wall = max(r["end"] for r in res) - t0
    return {"aggregate": sum(r["tokens"] for r in res) / wall, "per_stream": st.mean(r["decode"] for r in res),
            "ttft_ms": 1000 * st.mean(r["ttft"] for r in res), "tokens": [r["tokens"] for r in res]}


def decode(url, max_tokens, concs, c1_reps):
    out = {}
    for kind, prompts in PROMPTS.items():
        out[kind] = {}
        for c in concs:
            if c == 1:
                runs = [wave(url, [p], max_tokens) for p in prompts[:c1_reps]]
                out[kind]["c1"] = {"median": st.median(r["aggregate"] for r in runs),
                                   "runs": [round(r["aggregate"], 1) for r in runs],
                                   "ttft_ms": st.median(r["ttft_ms"] for r in runs)}
            else:
                out[kind][f"c{c}"] = wave(url, prompts[:c], max_tokens)
            print(kind, f"c{c}", json.dumps(out[kind][f"c{c}"])[:160], flush=True)
    return out


def real_text(n_chars, rnd):
    files = sorted(glob.glob("/usr/lib/python3*/**/*.py", recursive=True))
    rnd.shuffle(files)
    parts, size = [], 0
    for f in files:
        try:
            t = open(f, errors="ignore").read()
        except OSError:
            continue
        parts.append(f"# file: {f}\n{t}\n"); size += len(t)
        if size >= n_chars:
            break
    return "".join(parts)[:n_chars]


def prefill(url, targets):
    rnd = random.Random(time.time_ns())
    out = []
    for target in targets:
        nonce = f"{rnd.getrandbits(64):016x}"
        text = real_text(int(target * 3.1), rnd)  # ~3.1 chars/token on Python source
        prompt = f"[{nonce}] Summarise what this code does in one sentence.\n\n{text}"
        r = stream(url, prompt, 1, timeout=3600)
        rate = r["prompt_tokens"] / r["ttft"] if r["ttft"] > 0 else 0
        out.append({"target": target, "prompt_tokens": r["prompt_tokens"], "ttft_s": round(r["ttft"], 2),
                    "tok_s": round(rate)})
        print("prefill", json.dumps(out[-1]), flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--url", default="http://192.168.50.219:8888")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--quick", action="store_true", help="c1 and c8 only, 3 c1 prompts, prefill 16k/64k")
    ap.add_argument("--prefill", default="4096,16384,32768,65536,131072")
    ap.add_argument("--no-prefill", action="store_true")
    ap.add_argument("--no-decode", action="store_true")
    a = ap.parse_args()
    concs, reps = ([1, 8], 3) if a.quick else ([1, 2, 4, 8, 16], 5)
    targets = [16384, 65536] if a.quick else [int(x) for x in a.prefill.split(",")]
    stream(a.url, "Say hi.", 8)  # warm-up
    res = {"url": a.url, "max_tokens": a.max_tokens, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if not a.no_decode:
        res["decode"] = decode(a.url, a.max_tokens, concs, reps)
    if not a.no_prefill:
        res["prefill"] = prefill(a.url, targets)
    json.dump(res, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
