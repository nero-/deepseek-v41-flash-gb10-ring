#!/usr/bin/env python3
"""Qualify the installed TileLang selection: gates, then the timed LIL runs.

Usage: qualify.py gates | screens | grid | tooleval. Each step writes new
files in this results directory and never overwrites one.
"""
import datetime, hashlib, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1]
REPO = RESULTS.parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import fleet  # noqa: E402

SELECTION = '4d2bc32eb4f2e9a2540ee18ca2eafbe2c7da95c4ec7f4c7e2ac8c3052fc54dfc'
IMAGE = 'sha256:2fc5565e9c15b005f3297a552131b8973a2f19fb811868a8358a3e99b33491d0'
API = 'http://192.168.50.219:8015'
LIL = Path('/Users/jg/Agent/Diagnostics/deepseek-v41-flash-ring/decode-recovery-20261020/external-client')
LIL076 = LIL / 'lil-0.7.6.py'
LIL076_SHA256 = 'c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553'
LIL077 = RESULTS / 'lil-0.7.7.py'
EVENTS = ('out of memory', 'oom-kill', 'killed process', 'nvrm', 'xid', 'page allocation failure')


def log(*parts):
    print(datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%SZ'), *parts, flush=True)


def save(name, value):
    with (RESULTS / name).open('x') as f:
        json.dump({'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), **value}, f, indent=2)
        f.write('\n')


def host(rank):
    code = ("import json,pathlib;m={l.split()[0].rstrip(':'):int(l.split()[1]) for l in "
            "pathlib.Path('/proc/meminfo').read_text().splitlines()};"
            "print(json.dumps({'used_gib':(m['MemTotal']-m['MemAvailable'])/1024**2,"
            "'available_gib':m['MemAvailable']/1024**2}))")
    return {'rank': rank, **json.loads(fleet.remote(rank, ['python3', '-c', code]).stdout)}


def kernel_events(since):
    def one(rank):
        out = fleet.remote(rank, ['journalctl', '-k', '--since', f'@{int(since)}', '--no-pager']).stdout
        return [line for line in out.splitlines() if any(e in line.lower() for e in EVENTS)]
    return fleet.parallel(one)


def identity():
    installed = hashlib.sha256(fleet.remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout.encode())
    assert installed.hexdigest() == SELECTION, 'installed selection differs'
    def one(rank):
        info = json.loads(fleet.remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0]
        assert info['Image'] == IMAGE and info['State']['Running'], (rank, info['State'])
        return {'rank': rank, 'id': info['Id']}
    with urllib.request.urlopen(API + '/health', timeout=5) as r:
        assert r.status == 200
    return fleet.parallel(one)


def run(args, name, timeout=7200, env=None):
    with (RESULTS / name).open('x') as out:
        return subprocess.run(args, stdout=out, stderr=subprocess.STDOUT, timeout=timeout,
                              env={**os.environ, **(env or {})}).returncode


def gates():
    ids = identity()
    started = time.time()
    rc = {'functional_failures': run([sys.executable, '-u', str(REPO / 'bench/functional.py'), API + '/v1'],
                                     'functional.log', 900),
          'images_rc': run([sys.executable, '-u', str(RESULTS / 'scripts/check_images.py')], 'images.log', 1800),
          'cold_needle_rc': run([sys.executable, '-u', str(REPO / 'bench/cold-needle.py'), '--url', API,
                                 '--tokens', '128000', '--output', str(RESULTS / 'cold-needle.json')],
                                'cold-needle.log', 1800)}
    images = json.loads((RESULTS / 'multi-image-checks.json').read_text())
    save('gates.json', {**rc, 'containers': ids, 'hosts': fleet.parallel(host), 'kernel_events': kernel_events(started),
                        'image_checks': [{k: v for k, v in row.items() if k != 'response'} for row in images],
                        'note': 'cold-needle exits 1 while cached_tokens is absent from usage; see needle_pass.'})
    log('GATES', rc)


def lil(label, extra, timeout=3600, script=LIL076):
    dest = RESULTS / f'{label}.json'
    assert not dest.exists()
    if script == LIL076:
        assert hashlib.sha256(script.read_bytes()).hexdigest() == LIL076_SHA256
    command = [str(LIL / '.venv/bin/python'), str(script), '--host', '192.168.50.219', '--port', '8015',
               '--model', 'DeepSeek-V4.1-Flash-TP4', '--no-hw-monitor', '--display-mode', 'plain', '--no-resume',
               *extra, '--output', str(dest)]
    save(f'{label}-command.json', {'argv': command})
    ids = identity()
    started = time.time()
    log('START', label)
    rc = run(command, f'{label}.log', timeout, {'LLM_BENCH_NO_UPDATE_CHECK': '1'})
    save(f'{label}-execution.json', {'returncode': rc, 'elapsed_seconds': time.time() - started, 'containers': ids,
                                     'hosts': fleet.parallel(host), 'kernel_events': kernel_events(started)})
    log('DONE', label, 'rc', rc)
    return rc


DECODE = ['--temperature', '1', '--duration', '20', '--max-tokens', '2048', '--coding-peak']


def screens():
    for i in range(1, 4):
        lil(f'screen-run-{i}', [*DECODE, '--concurrency', '1,8,16', '--contexts', '8k,32k'])


def grid():
    lil('full-grid', [*DECODE, '--concurrency', '1,2,4,8,16', '--contexts', '8k,16k,32k,64k,128k'], 7200)


def tooleval():
    # tool-eval exists from LIL 0.7.7; leaderboard settings are its defaults.
    lil('tool-eval', ['--tool-eval'], 7200, LIL077)


if __name__ == '__main__':
    {'gates': gates, 'screens': screens, 'grid': grid, 'tooleval': tooleval}[sys.argv[1]]()
