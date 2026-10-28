import json, sys, urllib.request
url = sys.argv[1] + "/chat/completions"
def ask(extra, stream=False):
    b = {"model": "DeepSeek-V4.1-Flash-TP4", "max_tokens": 64, "stream": stream,
         "messages": [{"role": "user", "content": "Say hi."}], **extra}
    r = urllib.request.urlopen(urllib.request.Request(url, json.dumps(b).encode(), {"Content-Type": "application/json"}), timeout=120)
    if not stream:
        m = json.loads(r.read())["choices"][0]["message"]; return m.get("content"), m.get("reasoning_content") or ""
    c, rz = [], []
    for line in r:
        line = line.strip()
        if line.startswith(b"data:") and line != b"data: [DONE]":
            for ch in json.loads(line[5:]).get("choices", []):
                c.append(ch["delta"].get("content") or ""); rz.append(ch["delta"].get("reasoning_content") or "")
    return "".join(c), "".join(rz)
for label, extra in [("enable_thinking=false", {"chat_template_kwargs": {"enable_thinking": False}}),
                     ("thinking_mode=chat", {"thinking_mode": "chat"}), ("default (thinking)", {})]:
    for stream in (False, True):
        for i in range(3):
            c, rz = ask(extra, stream)
            print(f"{label:22} stream={stream!s:5} content={c!r:60.60} reasoning={rz[:50]!r}")
