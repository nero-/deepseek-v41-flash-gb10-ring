#!/usr/bin/env python3
"""Nonce-prefixed long-context retrieval with usage and client timing evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import time
import urllib.request
import uuid

p = argparse.ArgumentParser()
p.add_argument("--tokens", type=int, default=256000)
p.add_argument("--output", required=True)
p.add_argument("--url", default="http://127.0.0.1:8015")
a = p.parse_args()
rng = random.Random(7)
words = "harbour lantern meadow copper violin orchard compass thistle ember granite".split()
code = f"RING-{rng.randint(1000,9999)}-COBALT"
nonce = uuid.uuid4().hex
paragraphs = [f"Record {i}: the {rng.choice(words)} keeper counted {rng.randint(1,999)} {rng.choice(words)} crates. " for i in range(a.tokens // 16)]
paragraphs.insert(len(paragraphs)//2, f"\nThe access code is {code}.\n")
content = nonce + "\n" + "".join(paragraphs) + "\nWhat is the access code? Reply with the code only."
body = {"model": "DeepSeek-V4.1-Flash-TP4", "messages": [{"role": "user", "content": content}],
        "temperature": 0, "max_tokens": 32, "chat_template_kwargs": {"thinking": False},
        "stream": True, "stream_options": {"include_usage": True}}
request = urllib.request.Request(a.url + "/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
started = time.monotonic()
answer, usage, ttft = [], None, None
with urllib.request.urlopen(request, timeout=1800) as response:
    for line in response:
        if not line.startswith(b"data: ") or line[6:].strip() == b"[DONE]":
            continue
        item = json.loads(line[6:])
        if item.get("usage"):
            usage = item["usage"]
        for choice in item.get("choices", []):
            text = choice.get("delta", {}).get("content") or ""
            if text:
                if ttft is None:
                    ttft = time.monotonic() - started
                answer.append(text)
elapsed = time.monotonic() - started
cached = ((usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens")
document = {"args": vars(a), "nonce": nonce, "prompt_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "expected": code, "answer": "".join(answer), "usage": usage,
            "ttft_seconds": ttft, "elapsed_seconds": elapsed, "cached_tokens": cached,
            "needle_pass": code in "".join(answer), "cold_confirmed": cached == 0}
Path(a.output).write_text(json.dumps(document, indent=2) + "\n")
print(json.dumps(document), flush=True)
if not document["needle_pass"] or not document["cold_confirmed"]:
    raise SystemExit(1)
