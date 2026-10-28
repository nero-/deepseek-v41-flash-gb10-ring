import json, sys, urllib.request
url = sys.argv[1] + "/chat/completions"
want = ", ".join(str(i) for i in range(1, 31))
for label, extra in [("default", {}), ("enable_thinking=false", {"chat_template_kwargs": {"enable_thinking": False}}),
                     ("enable_thinking=true", {"chat_template_kwargs": {"enable_thinking": True}}), ("reasoning_effort=high", {"reasoning_effort": "high"})]:
    ok = 0; bad = []
    for i in range(6):
        b = {"model": "DeepSeek-V4.1-Flash-TP4", "max_tokens": 1500, "messages": [{"role": "user", "content": "Count from 1 to 30, comma separated. Output only the numbers."}], **extra}
        m = json.loads(urllib.request.urlopen(urllib.request.Request(url, json.dumps(b).encode(), {"Content-Type": "application/json"}), timeout=300).read())["choices"][0]["message"]
        c = (m.get("content") or "").strip()
        if c == want: ok += 1
        else: bad.append((c[:90], len(m.get("reasoning_content") or "")))
    print(f"{label:24} exact {ok}/6"); [print("    ", repr(x), "reasoning_chars", r) for x, r in bad[:3]]
