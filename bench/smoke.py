#!/usr/bin/env python3
"""Functional smoke test: arithmetic, greedy determinism, tool calling, thinking mode, 128k needle.

    python3 smoke.py [--url http://192.168.50.219:8888] [--needle]
"""
import argparse
import json
import random
import time
import urllib.request


def ask(url, body, timeout=1800):
    t = time.time()
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    return r, time.time() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://192.168.50.219:8888")
    ap.add_argument("--needle", type=int, default=0, help="also run a needle test of ~N prompt tokens")
    a = ap.parse_args()
    base = {"model": "deepseek-v4.1-flash", "temperature": 0, "chat_template_kwargs": {"thinking": False}}
    ok = True

    r, _ = ask(a.url, dict(base, max_tokens=16, messages=[{"role": "user", "content": "What is 19 + 23? Answer with the number only."}]))
    ans = r["choices"][0]["message"]["content"].strip()
    print("arithmetic:", repr(ans)); ok &= ans == "42"

    haiku = dict(base, max_tokens=60, messages=[{"role": "user", "content": "Write a haiku about a ring of GPUs."}])
    outs = [ask(a.url, haiku)[0]["choices"][0]["message"]["content"] for _ in range(3)]
    print("greedy identical x3:", len(set(outs)) == 1, repr(outs[0][:70])); ok &= len(set(outs)) == 1

    tool = dict(base, max_tokens=200, messages=[{"role": "user", "content": "What is the weather in Paris right now?"}],
                tools=[{"type": "function", "function": {"name": "get_weather", "description": "Current weather for a city",
                        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}])
    r, _ = ask(a.url, tool)
    calls = r["choices"][0]["message"].get("tool_calls") or []
    good = bool(calls) and calls[0]["function"]["name"] == "get_weather" and "Paris" in calls[0]["function"]["arguments"]
    print("tool call:", good, json.dumps(calls)[:160]); ok &= good

    think = dict(base, max_tokens=3000, chat_template_kwargs={"thinking": True},
                 messages=[{"role": "user", "content": "A bat and a ball cost 1.10 in total. The bat costs 1.00 more than the ball. How much is the ball? End with the answer."}])
    r, dt = ask(a.url, think)
    m = r["choices"][0]["message"]
    good = len(m.get("reasoning_content") or "") > 0 and "0.05" in (m.get("content") or "")
    print(f"thinking: {good} reasoning={len(m.get('reasoning_content') or '')} chars, answer tail={(m.get('content') or '')[-60:]!r}, "
          f"{r['usage']['completion_tokens']} tok in {dt:.1f}s"); ok &= good

    if a.needle:
        rnd = random.Random(7)
        words = ["harbour", "lantern", "meadow", "copper", "violin", "orchard", "compass", "thistle", "ember", "granite"]
        para = lambda i: f"Record {i}: the {rnd.choice(words)} keeper counted {rnd.randint(1, 999)} {rnd.choice(words)} crates. "
        n = int(a.needle / 16)
        code = f"RING-{rnd.randint(1000, 9999)}-COBALT"
        body = "".join(para(i) for i in range(n // 2)) + f"\nThe access code is {code}.\n" + "".join(para(n // 2 + i) for i in range(n // 2))
        r, dt = ask(a.url, dict(base, max_tokens=20, messages=[{"role": "user", "content": body + "\nWhat is the access code? Reply with the code only."}]))
        got = r["choices"][0]["message"]["content"].strip()
        pt = r["usage"]["prompt_tokens"]
        print(f"needle {pt} tokens: {'PASS' if code in got else 'FAIL'} got={got!r} in {dt:.1f}s ({pt / dt:.0f} tok/s incl. decode)")
        ok &= code in got

    print("SMOKE", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
