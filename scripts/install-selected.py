#!/usr/bin/env python3
"""Install the qualified site's recorded trial specs and adaptive plugin.

Run as root on spark-r0 after stopping workloads. This installs configuration;
start through deepseek-ring-control afterwards. It does not alter upstream files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

HOSTS = ('192.168.50.219', '192.168.50.129', '192.168.50.192', '192.168.50.23')
IMAGE = 'sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf'
TARGET = '/usr/local/lib/deepseek-ring/plugins'


def remote(host, command, data=None):
    return subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'root@' + host,
                                   shlex.join(command)], input=data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('receipt', type=Path, help='Qualified trial directory containing specs.json and plugin-sha256.json')
    p.add_argument('--profile', choices=['engram-adaptive4k', 'engram-adaptive4k-graphs'], required=True)
    args = p.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run as root on the head')
    config = Path('/etc/deepseek-ring/optimized-specs.json')
    if config.exists():
        raise SystemExit('A selected configuration already exists; review it before replacing')
    docs = json.loads((args.receipt / 'specs.json').read_text())
    code = (args.receipt / 'dsv41_adaptive_prefill.py').read_bytes()
    digest = hashlib.sha256(code).hexdigest()
    assert json.loads((args.receipt / 'plugin-sha256.json').read_text()) == [digest] * 4
    assert len(docs) == 4
    for rank, doc in enumerate(docs):
        assert doc['name'] == f'ds41-trial-{args.profile}-r{rank}' and doc['image_id'] == IMAGE
        assert 'dsv41_adaptive_prefill' in doc['environment']['VLLM_PLUGINS'].split(',')
        assert not remote(HOSTS[rank], ['docker', 'ps', '-q']).strip(), 'Stop workloads first'
        doc['name'] = f'ds41-optimized-r{rank}'
        doc['labels'] = {'io.local.deepseek-optimized': args.profile, 'io.local.rank': str(rank)}
        for mount in doc['mounts']:
            if mount['target'] == '/opt/dsv41-local-plugins':
                assert mount['read_only']
                mount['source'] = TARGET
    files = {'dsv41_adaptive_prefill.py': code,
             'dsv41_local-0.1.dist-info/METADATA': b'Metadata-Version: 2.1\nName: dsv41-local\nVersion: 0.1\n',
             'dsv41_local-0.1.dist-info/entry_points.txt': b'[vllm.general_plugins]\ndsv41_adaptive_prefill = dsv41_adaptive_prefill:register\n'}
    # Root-owned directories and atomic replacement prevent live partial files.
    writer = """import os,sys
from pathlib import Path
p=Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
t=p.with_suffix(p.suffix+'.new');t.write_bytes(sys.stdin.buffer.read());t.chmod(0o644);os.chown(t,0,0);t.replace(p)
"""
    for host in HOSTS:
        for name, data in files.items():
            remote(host, ['python3', '-c', writer, TARGET + '/' + name], data)
    document = {'profile': args.profile, 'source_receipt': str(args.receipt.resolve()),
                'plugin_manifest': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
                'specs': docs}
    config.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    temp = config.with_suffix('.new')
    temp.write_text(json.dumps(document, indent=2) + '\n')
    temp.chmod(0o644)
    temp.replace(config)
    print('Installed selected configuration:', args.profile)
    print('Start with: sudo -n deepseek-ring-control up')


if __name__ == '__main__':
    main()
