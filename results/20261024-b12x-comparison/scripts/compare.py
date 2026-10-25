#!/usr/bin/env python3
"""B12X versus TileLang: the same functional check, tool-eval and full grid.

Usage: compare.py ARM STEP [LABEL]; ARM is b12x or tilelang, STEP is
functional | grid | tooleval | gpqa | mmlu. Every run checks that ARM's selection, image and
containers are the installed ones, and writes new files only.
"""
import datetime, hashlib, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1]
REPO = RESULTS.parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import fleet  # noqa: E402

ARMS = {
    'b12x': ('c87a397ccc4614c6f3fee59e566bb7599e7165c80e858bb12c84d78ef5e27775',
             'sha256:9f26f0b3718ccca889cfd93cb72e2165b6d4c11dd9dc93fe65f585883537f2db'),
    'tilelang': ('4d2bc32eb4f2e9a2540ee18ca2eafbe2c7da95c4ec7f4c7e2ac8c3052fc54dfc',
                 'sha256:2fc5565e9c15b005f3297a552131b8973a2f19fb811868a8358a3e99b33491d0'),
}
ARM = sys.argv[1]
SELECTION, IMAGE = ARMS[ARM]
API = 'http://192.168.50.219:8015'
LIL = Path('/Users/jg/Agent/Diagnostics/deepseek-v41-flash-ring/decode-recovery-20261020/external-client')
LIL076 = LIL / 'lil-0.7.6.py'
LIL076_SHA256 = 'c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553'
LIL077 = RESULTS.parent / '20261024-tilelang/lil-0.7.7.py'
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


def functional():
    ids = identity()
    label = sys.argv[3] if len(sys.argv) > 3 else '1'
    rc = run([sys.executable, '-u', str(REPO / 'bench/functional.py'), API + '/v1'], f'{ARM}-functional-{label}.log', 900)
    save(f'{ARM}-functional-{label}.json', {'functional_failures': rc, 'containers': ids, 'hosts': fleet.parallel(host)})
    log('FUNCTIONAL', ARM, rc)


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
LABEL = sys.argv[3] if len(sys.argv) > 3 else '1'


def grid():
    lil(f'{ARM}-full-grid-{LABEL}', [*DECODE, '--concurrency', '1,2,4,8,16', '--contexts', '8k,16k,32k,64k,128k'], 7200)


def tooleval():
    # tool-eval exists from LIL 0.7.7; leaderboard settings are its defaults.
    lil(f'{ARM}-tool-eval-{LABEL}', ['--tool-eval'], 7200, LIL077)


# The model's recommended sampling (DeepSeek: temperature 1, top_p 1; also the server default), no seed so
# repeats are independent samples, and the server's 16 sequences. Profile defaults otherwise.
ACCURACY = ['--completion-stats-concurrency', '16', '--completion-stats-temperature', '1',
            '--completion-stats-top-p', '1']


def gpqa():
    # 198 GPQA Diamond questions, exact option-letter scoring.
    lil(f'{ARM}-gpqa-diamond-{LABEL}', ['--test-profile', 'gpqa-diamond', *ACCURACY], 6 * 3600)


def mmlu():
    # Pinned stratified 1000-question MMLU-Pro subset, exact option-letter scoring.
    lil(f'{ARM}-mmlu-pro-{LABEL}', ['--test-profile', 'mmlu-pro', *ACCURACY], 10 * 3600)


if __name__ == '__main__':
    {'functional': functional, 'grid': grid, 'tooleval': tooleval, 'gpqa': gpqa, 'mmlu': mmlu}[sys.argv[2]]()
