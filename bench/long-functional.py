#!/usr/bin/env python3
"""Run the functional suite through fresh long prefills, recording real usage."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import random
import runpy
import sys
import time
import urllib.request
import uuid

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--suite', required=True)
p.add_argument('--url', default='http://127.0.0.1:8015/v1')
p.add_argument('--output', required=True)
a = p.parse_args()
rng = random.Random(31)
words = 'harbour lantern meadow copper violin orchard compass thistle ember granite'.split()
filler = ''.join(f'Record {i}: the {rng.choice(words)} keeper counted {rng.randint(1,999)} {rng.choice(words)} crates. '
                 for i in range(6144))
requests = []
original_request, original_open = urllib.request.Request, urllib.request.urlopen

def urlopen(req, *args, **kwargs):
    if not isinstance(req, original_request) or not req.full_url.endswith('/chat/completions'):
        return original_open(req, *args, **kwargs)
    body = json.loads(req.data)
    prefix = uuid.uuid4().hex + '\nReference filler; ignore it when answering the question below.\n' + filler + '\nEnd reference.\n'
    message = next(m for m in body['messages'] if m['role'] == 'user')
    content = message['content']
    message['content'] = prefix + content if isinstance(content, str) else [{'type': 'text', 'text': prefix}, *content]
    req.data = json.dumps(body).encode()
    record = {'request_sha256': hashlib.sha256(req.data).hexdigest(), 'body_bytes': len(req.data)}
    requests.append(record)
    started = time.monotonic()
    with original_open(req, *args, **kwargs) as response:
        data = response.read()
    record['elapsed_seconds'] = time.monotonic() - started
    record['usage'] = json.loads(data).get('usage')
    print('LONG-USAGE', json.dumps(record), flush=True)
    return io.BytesIO(data)

urllib.request.urlopen = urlopen
saved_argv = sys.argv
sys.argv = [a.suite, a.url]
exit_code = 1
try:
    runpy.run_path(a.suite, run_name='__main__')
    exit_code = 0
except SystemExit as exc:
    exit_code = exc.code or 0
finally:
    sys.argv = saved_argv
    urllib.request.urlopen = original_open
    # A shared tool-schema prefix can be cached before the nonce in the user
    # message. Require at least 64K actually uncached prompt tokens, and retain
    # the real cache counts instead of labeling such requests fully cold.
    def fresh_tokens(record):
        usage = record.get('usage') or {}
        cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
        return usage.get('prompt_tokens', 0) - cached if cached is not None else 0
    long_prefills = len(requests) == 7 and all(fresh_tokens(r) >= 65536 for r in requests)
    if not long_prefills:
        exit_code = exit_code or 1
    Path(a.output).write_text(json.dumps({'args': vars(a), 'exit_code': exit_code,
        'all_long_prefills': long_prefills, 'requests': requests}, indent=2) + '\n')
raise SystemExit(exit_code)
