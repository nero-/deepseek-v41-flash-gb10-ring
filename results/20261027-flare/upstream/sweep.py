"""For each word-boundary prefix of TAIL after HEAD, ask for one token (prefill-only); flag the 'blank' distribution.
Usage: sweep.py URL HEAD TAIL"""
import json, sys, urllib.request
url, head, tail = sys.argv[1], sys.argv[2], sys.argv[3]
def req(prompt):
    b = {"model": "DeepSeek-V4.1-Flash-TP4", "prompt": prompt, "max_tokens": 1, "logprobs": 3}
    return json.loads(urllib.request.urlopen(urllib.request.Request(url + "/completions", json.dumps(b).encode(),
        {"Content-Type": "application/json"}), timeout=300).read())
words = tail.split(" ")
for k in range(len(words) + 1):
    p = head + " ".join(words[:k])
    d = req(p); tl = d["choices"][0]["logprobs"]["top_logprobs"]
    top = sorted(tl[0].items(), key=lambda kv: -kv[1]) if tl and tl[0] else []
    blank = bool(top) and top[0][0] in ("\n", "#") and -2.6 < top[0][1] < -2.0
    print(f"{'BLANK' if blank else 'ok   '} pt={d['usage']['prompt_tokens']:3} ...{p[-30:]!r:36} " +
          " | ".join(f"{t!r}:{l:.2f}" for t, l in top), flush=True)
