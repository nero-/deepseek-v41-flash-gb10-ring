"""Print each generated content/reasoning token with its logprob and rank-1 alternative.
Usage: lp.py URL PROMPT [seed] [mode]   mode: default|chat|nothink"""
import json, sys, urllib.request
url, prompt = sys.argv[1], sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv) > 3 else None
mode = sys.argv[4] if len(sys.argv) > 4 else "default"
extra = {"chat": {"thinking_mode": "chat"}, "nothink": {"chat_template_kwargs": {"enable_thinking": False}}}.get(mode, {})
b = {"model": "DeepSeek-V4.1-Flash-TP4", "max_tokens": 200, "logprobs": True, "top_logprobs": 5,
     "messages": [{"role": "user", "content": prompt}], **extra}
if seed is not None: b["seed"] = seed
d = json.loads(urllib.request.urlopen(urllib.request.Request(url + "/chat/completions", json.dumps(b).encode(),
    {"Content-Type": "application/json"}), timeout=300).read())
c = d["choices"][0]
m = c["message"]
print("finish", c.get("finish_reason"), "usage", d.get("usage"))
print("reasoning", repr(m.get("reasoning_content")))
print("content", repr(m.get("content")))
lp = (c.get("logprobs") or {})
for k in lp:
    for e in lp[k] or []:
        alts = " | ".join(f"{a['token']!r}:{a['logprob']:.2f}" for a in e.get("top_logprobs", [])[:3])
        flag = "  <<<" if e["logprob"] < -4 else ""
        print(f"{k[:4]} {e['token']!r:>18} {e['logprob']:8.3f}   {alts}{flag}")
