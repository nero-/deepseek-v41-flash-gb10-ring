#!/usr/bin/env python3
"""Run pinned LIL with only top_p overridden; preserve all other request fields."""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def install(httpx, top_p):
    if not 0 < top_p <= 1:
        raise ValueError('top_p must be in (0, 1]')

    def wrap(original):
        def build(self, method, url, *args, **kwargs):
            body = kwargs.get('json')
            if str(url).split('?', 1)[0].endswith('/v1/chat/completions') and isinstance(body, dict):
                kwargs['json'] = {**body, 'top_p': top_p}
            return original(self, method, url, *args, **kwargs)
        return build

    for cls in (httpx.Client, httpx.AsyncClient):
        cls.build_request = wrap(cls.build_request)


if __name__ == '__main__':
    import httpx
    harness = Path(sys.argv[1]).resolve()
    top_p = float(sys.argv[2])
    args = sys.argv[3:]
    output = Path(args[args.index('--output') + 1])
    output.with_suffix('.request-settings.json').write_text(json.dumps({
        'request_overrides': {'top_p': top_p},
        'harness': str(harness),
        'harness_sha256': hashlib.sha256(harness.read_bytes()).hexdigest(),
        'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }, indent=2) + '\n')
    install(httpx, top_p)
    sys.argv = [str(harness), *args]
    runpy.run_path(str(harness), run_name='__main__')
