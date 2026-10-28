"""DeepSeek V4.1 Flash on Flare: some positions inside the first 128 tokens get context-free logits.

Prefill-only (/v1/completions, max_tokens 1): prints the next-token distribution after each prompt.
Expected after "What's on your" is " mind" at about 0.0; the defect gives the same flat
document-start distribution ('\\n' -2.25, '#' -2.37, '<' -2.74) every time.
Usage: python3 repro_blank_position.py http://HOST:PORT/v1 [model]"""
import json, sys, urllib.request
url = sys.argv[1].rstrip("/")
model = sys.argv[2] if len(sys.argv) > 2 else "DeepSeek-V4.1-Flash-TP4"
B, S, U, A = "<｜begin▁of▁sentence｜>", "<｜System｜>", "<｜User｜>", "<｜Assistant｜>"
H = lambda n: f"Reasoning Effort: {n} (range 1-100, the higher the value, the more thorough the reasoning)\n\n"
# The first prompt is exactly what /v1/chat/completions renders for [{"role":"user","content":"Say hi."}]
# in the default thinking mode, plus the model's own first nine output tokens.
filler = " ".join(["the river runs past old stone walls"] * 14)
cases = [
    ("default chat render, 42 tokens", f"{B}{S}{H(75)}{U}Say hi.{A}<think></think>Hi! 👋 What's on your"),
    ("same, Reasoning Effort 50", f"{B}{S}{H(50)}{U}Say hi.{A}<think></think>Hi! 👋 What's on your"),
    ("same, no effort header", f"{B}{U}Say hi.{A}<think></think>Hi! 👋 What's on your"),
    ("same, ~100 tokens of notes first", f"{B}{S}{H(75)}Notes: {filler}{U}Say hi.{A}<think></think>Hi! 👋 What's on your"),
]
for name, prompt in cases:
    b = {"model": model, "prompt": prompt, "max_tokens": 1, "logprobs": 5}
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url + "/completions", json.dumps(b).encode(),
        {"Content-Type": "application/json"}), timeout=300).read())
    top = sorted(d["choices"][0]["logprobs"]["top_logprobs"][0].items(), key=lambda kv: -kv[1])
    blank = top[0][0] in ("\n", "#") and top[0][1] < -1.5
    print(f"{'BLANK' if blank else 'ok   '} prompt_tokens={d['usage']['prompt_tokens']:3}  {name:34} " +
          " | ".join(f"{t!r} {l:.2f}" for t, l in top[:4]))
