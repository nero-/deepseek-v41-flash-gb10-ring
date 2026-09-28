#!/usr/bin/env python3
"""Run unchanged LIL with an explicit cross-engine chat request contract.

The pinned LIL matrix has no chat-template override. This client-side adapter
sets only documented request fields, records them beside the JSON report, and
leaves timing, token accounting, prompts, and scheduling logic unchanged.
"""
import hashlib
import json
from pathlib import Path
import runpy
import sys

SETTINGS = {"temperature": 1.0, "top_p": 1.0, "top_k": -1,
            "chat_template_kwargs": {"thinking": False}}


def install(httpx):
    def wrap(original):
        def build(self, method, url, *args, **kwargs):
            body = kwargs.get("json")
            if str(url).split("?", 1)[0].endswith("/v1/chat/completions") and isinstance(body, dict):
                body = dict(body)
                body.update({k: v for k, v in SETTINGS.items() if k != "chat_template_kwargs"})
                body["chat_template_kwargs"] = {**body.get("chat_template_kwargs", {}), **SETTINGS["chat_template_kwargs"]}
                kwargs["json"] = body
            return original(self, method, url, *args, **kwargs)
        return build
    for cls in (httpx.Client, httpx.AsyncClient):
        cls.build_request = wrap(cls.build_request)


if __name__ == "__main__":
    import httpx
    harness = Path(sys.argv[1]).resolve()
    args = sys.argv[2:]
    output = Path(args[args.index("--output") + 1])
    output.with_suffix(".matched-request.json").write_text(json.dumps({
        "request_overrides": SETTINGS, "harness": str(harness),
        "harness_sha256": hashlib.sha256(harness.read_bytes()).hexdigest(),
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }, indent=2))
    install(httpx)
    sys.argv = [str(harness), *args]
    runpy.run_path(str(harness), run_name="__main__")
