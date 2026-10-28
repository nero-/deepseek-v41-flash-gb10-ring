"""FLARE image budget probe: distinct small images per request, one large image, health after rejection."""
import base64, json, struct, sys, urllib.error, urllib.request, zlib
URL = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.50.219:8015"
def png(rgb, tag, size):
    def chunk(k, d): return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d) & 0xFFFFFFFF)
    px = bytearray(bytes(rgb) * size * size)
    for i in range(4): px[i * 3] = (tag >> (8 * i)) & 255  # distinct content per image
    rows = b"".join(b"\x00" + px[y * size * 3:(y + 1) * size * 3] for y in range(size))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
def ask(n, size):
    parts = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png((255, 0, 0) if i == 0 else (0, 0, 255), i, size)).decode()}} for i in range(n)]
    parts.append({"type": "text", "text": f"There are {n} images. What color is the first image? One word."})
    body = {"model": "DeepSeek-V4.1-Flash-TP4", "max_tokens": 16, "chat_template_kwargs": {"enable_thinking": False}, "messages": [{"role": "user", "content": parts}]}
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(URL + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=600).read())
        return {"images": n, "px": size, "status": 200, "reply": d["choices"][0]["message"]["content"], "prompt_tokens": d["usage"]["prompt_tokens"]}
    except urllib.error.HTTPError as e:
        return {"images": n, "px": size, "status": e.code, "error": e.read().decode(errors="replace")[:240]}
rows = [ask(n, 64) for n in (1, 8, 16, 64)] + [ask(1, 1024), ask(4, 1024)]
rows.append({"health_after": urllib.request.urlopen(URL + "/health", timeout=10).status})
print(json.dumps(rows, indent=1))
