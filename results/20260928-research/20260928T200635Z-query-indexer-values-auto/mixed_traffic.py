#!/usr/bin/env python3
"""Measure decoder stream stalls while cold prompts arrive.

SSE chunks can contain multiple speculative tokens. Report chunk gaps, never
mislabel them as individual-token latency. Raw timestamps and usage are saved.
Only this benchmark's own requests are cancelled at the end of each round.
"""
import argparse
import concurrent.futures as cf
import json
import random
import threading
import time
import urllib.request
from pathlib import Path


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * q))]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("label")
    p.add_argument("--url", default="http://127.0.0.1:8015")
    p.add_argument("--model", default="DeepSeek-V4.1-Flash-TP4")
    p.add_argument("--decoders", type=int, default=8)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--output", required=True)
    p.add_argument("--prefill-records", type=int, default=1950)
    p.add_argument("--min-uncached-tokens", type=int, default=0)
    p.add_argument("--integrity", action="store_true", help="separate under-load needle correctness test; not comparable latency traffic")
    a = p.parse_args()
    report = {"args": vars(a), "metric": "client SSE content-chunk gaps, not token ITL", "rounds": []}
    words = "harbour lantern meadow copper violin orchard compass thistle ember granite".split()
    for trial in range(a.rounds):
        origin = time.monotonic()
        stop = threading.Event()
        ready = [threading.Event() for _ in range(a.decoders)]

        def stream(kind, index):
            rng = random.Random(8000 + trial * 100 + index + (10000 if kind == "prefill" else 0))
            # Different first content per request/round/run defeats prefix reuse.
            nonce = f"{a.label}-{trial}-{kind}-{index}-{time.time_ns()}"
            count = a.prefill_records if kind == "prefill" else 28
            context = nonce + "\n" + "".join(
                f"Record {j}: the {rng.choice(words)} keeper counted {rng.randint(1,999)} {rng.choice(words)} crates. "
                for j in range(count))
            instruction = ("Summarize the records in four sentences." if kind == "prefill" else
                           "Write a very long detailed tutorial on building a database, with many worked SQL examples. Continue until the output limit.")
            expected = None
            if a.integrity and kind == "prefill":
                expected = f"KEY-{trial}-{index}-COBALT-{rng.randrange(10**8):08d}"
                middle = len(context) // 2
                context = context[:middle] + f"\nThe access code is {expected}.\n" + context[middle:]
                instruction = "What is the access code? Reply with the code only."
            body = {"model": a.model, "messages": [{"role": "user", "content": context + "\n" + instruction}],
                    "temperature": 0, "max_tokens": (32 if expected else 128) if kind == "prefill" else 4096,
                    "ignore_eos": expected is None, "chat_template_kwargs": {"thinking": False},
                    "stream": True, "stream_options": {"include_usage": True}}
            result = {"kind": kind, "index": index, "start": time.monotonic() - origin, "chunks": [], "chars": 0}
            answer = []
            req = urllib.request.Request(a.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=300) as response:
                    for line in response:
                        if stop.is_set() and kind == "decode":
                            result["cancelled_by_benchmark"] = True
                            break
                        if not line.startswith(b"data: "):
                            continue
                        payload = line[6:].strip()
                        if payload == b"[DONE]":
                            break
                        data = json.loads(payload)
                        if data.get("usage"):
                            result["usage"] = data["usage"]
                        for choice in data.get("choices", []):
                            content = choice.get("delta", {}).get("content") or ""
                            if content:
                                result["chunks"].append(time.monotonic() - origin)
                                result["chars"] += len(content)
                                if expected:
                                    answer.append(content)
                                if kind == "decode":
                                    ready[index].set()
                result["end"] = time.monotonic() - origin
                if expected:
                    result.update(expected=expected, answer="".join(answer), needle_pass=expected in "".join(answer))
            except Exception as exc:
                result["error"] = repr(exc)
                if kind == "decode":
                    ready[index].set()
            return result

        with cf.ThreadPoolExecutor(a.decoders + 2) as pool:
            decoders = [pool.submit(stream, "decode", i) for i in range(a.decoders)]
            for event in ready:
                if not event.wait(120):
                    stop.set()
                    raise TimeoutError("Decoder failed to start")
            time.sleep(5)
            arrival = time.monotonic() - origin
            prefills = [pool.submit(stream, "prefill", i) for i in range(2)]
            fresh = [f.result() for f in prefills]
            recovery = time.monotonic() - origin
            time.sleep(5)
            stop.set()
            ongoing = [f.result() for f in decoders]
        groups = {"before": [], "during": [], "after": []}
        for request in ongoing:
            for left, right in zip(request["chunks"], request["chunks"][1:]):
                phase = "before" if right < arrival else "after" if left > recovery else "during"
                groups[phase].append(right - left)
        summary = {phase: {"count": len(gaps), "p50_s": percentile(gaps, .5),
                          "p95_s": percentile(gaps, .95), "p99_s": percentile(gaps, .99),
                          "max_s": max(gaps, default=None)} for phase, gaps in groups.items()}
        summary["fresh_ttft_s"] = [r["chunks"][0] - r["start"] if r["chunks"] else None for r in fresh]
        summary["errors"] = [r["error"] for r in ongoing + fresh if "error" in r]
        if a.min_uncached_tokens:
            for request in fresh:
                usage = request.get("usage") or {}
                cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                uncached = usage.get("prompt_tokens", 0) - cached if cached is not None else 0
                if uncached < a.min_uncached_tokens:
                    summary["errors"].append("Insufficient uncached prefill tokens")
        if a.integrity:
            summary["needle_pass"] = all(r.get("needle_pass") for r in fresh)
            if not summary["needle_pass"]:
                summary["errors"].append("Under-load needle failed")
        report["rounds"].append({"arrival": arrival, "recovery": recovery, "summary": summary,
                                 "requests": ongoing + fresh})
        Path(a.output).write_text(json.dumps(report, indent=2))
        print(json.dumps({"round": trial, **summary}), flush=True)
        time.sleep(3)
    if any(r["summary"]["errors"] for r in report["rounds"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
