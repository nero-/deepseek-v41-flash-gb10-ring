import json, re, sys, urllib.request, concurrent.futures
url = sys.argv[1] + "/chat/completions"
prompts = ["Say hi.", "Give me one tip for better sleep.", "Describe the color blue in two sentences.", "What is a good name for a cat? One sentence."]
def one(args):
    extra, p, seed = args
    b = {"model": "DeepSeek-V4.1-Flash-TP4", "max_tokens": 400, "seed": seed, "messages": [{"role": "user", "content": p}], **extra}
    m = json.loads(urllib.request.urlopen(urllib.request.Request(url, json.dumps(b).encode(), {"Content-Type": "application/json"}), timeout=300).read())["choices"][0]["message"]
    return m.get("content") or ""
cjk = re.compile(r"[　-鿿]")
for label, extra in [("default", {}), ("enable_thinking=false", {"chat_template_kwargs": {"enable_thinking": False}}), ("enable_thinking=true", {"chat_template_kwargs": {"enable_thinking": True}})]:
    jobs = [(extra, p, s) for p in prompts for s in range(1, 6)]
    with concurrent.futures.ThreadPoolExecutor(1) as ex: outs = list(ex.map(one, jobs))
    flagged = [o for o in outs if cjk.search(o) or re.search(r"[a-z][A-Z][a-z]", o) or "cut off" in o]
    print(f"{label:22} flagged {len(flagged)}/{len(outs)}  distinct {len(set(outs))}")
    for o in flagged[:4]: print("     ", repr(o[:110]))
