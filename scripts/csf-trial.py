#!/usr/bin/env python3
"""Launch the CSF campaign only after all four immutable checkpoints verify."""
import importlib.util
import json
from pathlib import Path
import time
import urllib.request

s = importlib.util.spec_from_file_location('campaign', Path(__file__).with_name('csf-upgrade.py'))
c = importlib.util.module_from_spec(s)
s.loader.exec_module(c)
CHECKPOINT = '/srv/sparkring/sparkring/checkpoints/local-inference-lab--DeepSeek-V4.1-Flash-lossless-CSF/c5c41fe301c4c1d24fc09376883d9168e521dc66'


def spec(document):
    fields = dict(document)
    fields['mounts'] = tuple(c.t.Bind(**m) for m in fields['mounts'])
    for key in ('entrypoint', 'command', 'devices', 'cap_add', 'security_opt', 'health_command'):
        fields[key] = tuple(fields[key])
    return c.t.ContainerSpec(**fields)


def main():
    documents = json.loads((c.F / 'trial-specs.json').read_text())
    assert len(documents) == 4
    for rank in range(4):
        assert not c.t.remote(rank, ['docker', 'ps', '-q']).stdout.strip()
        receipt = c.record(f'checkpoint-complete-r{rank}', rank,
                           ['cat', CHECKPOINT + '/verified-shards.json'], admin=True)
        assert json.loads(receipt.stdout)['revision'] == 'c5c41fe301c4c1d24fc09376883d9168e521dc66'
    # The checkpoint transfer fills unified-memory page cache. Release only
    # clean reclaimable cache before GPU initialization; no files are removed.
    c.t.parallel(lambda r: c.record(f'pre-serving-memory-r{r}', r,
                 ['sh', '-c', 'sync; echo 3 > /proc/sys/vm/drop_caches; free -h'], admin=True))
    for rank, document in enumerate(documents):
        assert document['name'] == f'ds41-csf-r{rank}'
        assert c.t.remote(rank, ['docker', 'inspect', document['name']], check=False).returncode != 0
        c.record(f'trial-create-r{rank}', rank, c.t.docker_create(spec(document)))
    c.t.parallel(lambda r: c.record(f'trial-start-r{r}', r, ['docker', 'start', documents[r]['name']]))
    print('CSF trial started', flush=True)
    deadline = time.monotonic() + 3000
    while time.monotonic() < deadline:
        states = c.t.parallel(lambda r: json.loads(c.t.remote(r, ['docker', 'inspect', documents[r]['name']]).stdout)[0]['State'])
        if any(not state['Running'] for state in states):
            c.t.parallel(lambda r: c.record(f'trial-startup-r{r}', r, ['docker', 'logs', documents[r]['name']], check=False))
            raise RuntimeError('A CSF trial rank stopped; inspect startup receipts')
        try:
            with urllib.request.urlopen('http://192.168.50.219:8015/health', timeout=5) as response:
                if response.status == 200:
                    c.t.parallel(lambda r: c.record(f'trial-startup-r{r}', r, ['docker', 'logs', documents[r]['name']]))
                    (c.F / 'trial-ready.json').write_text(json.dumps({'healthy': True, 'unix_time': time.time()}, indent=2))
                    print('CSF trial healthy', flush=True)
                    return
        except Exception:
            pass
        time.sleep(5)
    raise TimeoutError('CSF startup exceeded 50 minutes')


if __name__ == '__main__':
    main()
