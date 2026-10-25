#!/usr/bin/env python3
"""GPU clock policy on the TileLang selection: 2350 ceiling, stock boost, 2800 floor.

Usage: clocks.py run. Each arm gets one LIL 0.7.6 screen (8K/32K/128K at C1/C8/C16,
with prefill at each context), driver throttle counters before and after it, then a
separate telemetry pass (C16 decode, then a nonce-prefixed 32K prefill) sampled every
2 s on every rank. The persistent gb10-gpu-clock-cap.service policy (0-2350) is
reloaded afterwards whatever happens. Writes new files only.
"""
import concurrent.futures, datetime, hashlib, json, os, random, subprocess, sys, threading, time, urllib.request
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1]
REPO = RESULTS.parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import fleet  # noqa: E402

SELECTION = '4d2bc32eb4f2e9a2540ee18ca2eafbe2c7da95c4ec7f4c7e2ac8c3052fc54dfc'
IMAGE = 'sha256:2fc5565e9c15b005f3297a552131b8973a2f19fb811868a8358a3e99b33491d0'
# Any local image with nsenter will do; it only enters the host namespaces.
HELPER = 'sha256:9f26f0b3718ccca889cfd93cb72e2165b6d4c11dd9dc93fe65f585883537f2db'
API = 'http://192.168.50.219:8015'
MODEL = 'DeepSeek-V4.1-Flash-TP4'
LIL = Path('/Users/jg/Agent/Diagnostics/deepseek-v41-flash-ring/decode-recovery-20261020/external-client')
LIL076 = LIL / 'lil-0.7.6.py'
LIL076_SHA256 = 'c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553'
ARMS = [('cap2350', ['-lgc', '0,2350']), ('stock', ['-rgc']), ('floor2800', ['-lgc', '2800,3003'])]
SCREEN = ['--temperature', '1', '--duration', '20', '--max-tokens', '2048', '--coding-peak',
          '--concurrency', '1,8,16', '--contexts', '8k,32k,128k']
QUERY = 'clocks.sm,temperature.gpu,power.draw,utilization.gpu,clocks_event_reasons.active'
COUNTERS = ('SW Power Capping', 'SW Thermal Slowdown', 'HW Thermal Slowdown', 'HW Power Braking')


def log(*parts):
    print(datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%SZ'), *parts, flush=True)


def save(name, value):
    with (RESULTS / name).open('x') as f:
        json.dump({'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), **value}, f, indent=2)
        f.write('\n')


def as_root(rank, argv):
    """Host root: passwordless sudo on the GX10s, a privileged nsenter container on the Sparks."""
    if rank >= 2:
        return fleet.remote(rank, ['sudo', '-n', *argv], check=False)
    return fleet.remote(rank, ['docker', 'run', '--rm', '--privileged', '--pid', 'host', '--network', 'none',
                               '--entrypoint', 'nsenter', HELPER, '-t', '1', '-m', '-u', '-i', '-p', '--', *argv],
                        check=False)


def everywhere(argv):
    rows = fleet.parallel(lambda rank: as_root(rank, argv))
    return [{'rank': i, 'returncode': r.returncode, 'stdout': r.stdout[-2000:], 'stderr': r.stderr[-2000:]}
            for i, r in enumerate(rows)]


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


def counters():
    def one(rank):
        out = fleet.remote(rank, ['nvidia-smi', '-q', '-d', 'PERFORMANCE']).stdout
        found = {}
        for line in out.splitlines():
            key, _, value = line.partition(':')
            if key.strip() in COUNTERS and value.strip().endswith('us'):
                found[key.strip()] = int(value.split()[0])
        return {'rank': rank, **found}
    return fleet.parallel(one)


def sample():
    def one(rank):
        row = fleet.remote(rank, ['nvidia-smi', f'--query-gpu={QUERY}', '--format=csv,noheader,nounits']).stdout
        sm, temp, power, util, reasons = [v.strip() for v in row.strip().split(',')]
        return {'rank': rank, 'sm_mhz': int(sm), 'temp_c': int(temp), 'power_w': float(power),
                'util_pct': int(util), 'reasons': reasons}
    return {'t': time.time(), 'ranks': fleet.parallel(one)}


def chat(prompt, max_tokens):
    body = json.dumps({'model': MODEL, 'messages': [{'role': 'user', 'content': prompt}],
                       'max_tokens': max_tokens, 'temperature': 1}).encode()
    request = urllib.request.Request(API + '/v1/chat/completions', body, {'Content-Type': 'application/json'})
    started = time.time()
    with urllib.request.urlopen(request, timeout=900) as r:
        usage = json.load(r)['usage']
    return {'seconds': time.time() - started, **usage}


def sampled(phase, work):
    rows, done = [], threading.Event()
    def sampler():
        while not done.is_set():
            rows.append({'phase': phase, **sample()})
            done.wait(2)
    thread = threading.Thread(target=sampler)
    thread.start()
    try:
        result = work()
    finally:
        done.set()
        thread.join()
    return result, rows


def telemetry(arm):
    """Untimed load for clock/temperature/power observation, separate from the LIL screen."""
    def decode():
        prompt = 'Write a long, detailed technical history of suspension bridges, section by section.'
        with concurrent.futures.ThreadPoolExecutor(16) as pool:
            return list(pool.map(lambda _: chat(prompt, 1500), range(16)))
    def prefill():
        rng = random.Random()
        prompt = f'{rng.getrandbits(64):x} ' + ' '.join(str(rng.randrange(100000)) for _ in range(16000)) + \
                 '\nHow many numbers are above? Answer with one number.'
        return chat(prompt, 1)
    decode_result, decode_rows = sampled('decode-c16', decode)
    prefill_result, prefill_rows = sampled('prefill-32k', prefill)
    save(f'{arm}-telemetry.json', {'decode': decode_result, 'prefill': prefill_result,
                                   'samples': decode_rows + prefill_rows})


def screen(arm):
    dest = RESULTS / f'{arm}-screen.json'
    assert not dest.exists()
    assert hashlib.sha256(LIL076.read_bytes()).hexdigest() == LIL076_SHA256
    command = [str(LIL / '.venv/bin/python'), str(LIL076), '--host', '192.168.50.219', '--port', '8015',
               '--model', MODEL, '--no-hw-monitor', '--display-mode', 'plain', '--no-resume', *SCREEN,
               '--output', str(dest)]
    ids = identity()
    before, started = counters(), time.time()
    log('START', arm)
    with (RESULTS / f'{arm}-screen.log').open('x') as out:
        rc = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT, timeout=5400,
                            env={**os.environ, 'LLM_BENCH_NO_UPDATE_CHECK': '1'}).returncode
    save(f'{arm}-screen-execution.json', {'argv': command, 'returncode': rc, 'elapsed_seconds': time.time() - started,
                                          'containers': ids, 'counters_before': before, 'counters_after': counters()})
    log('DONE', arm, 'rc', rc)
    return rc


def restore():
    reload = everywhere(['/usr/bin/systemctl', 'reload', 'gb10-gpu-clock-cap.service'])
    state = everywhere(['/usr/bin/systemctl', 'show', 'gb10-gpu-clock-cap.service',
                        '-p', 'ActiveState', '-p', 'UnitFileState', '-p', 'ExecReload'])
    ok = all(r['returncode'] == 0 for r in reload) and all(
        'ActiveState=active' in s['stdout'] and 'UnitFileState=enabled' in s['stdout'] and '-lgc 0,2350' in s['stdout']
        for s in state)
    _, rows = sampled('restored-c16', lambda: [chat('Count from 1 to 300, one number per line.', 900)
                                                for _ in range(1)])
    save('restored.json', {'reload': reload, 'service': state, 'service_ok': ok, 'samples': rows})
    log('RESTORED_2350', 'service_ok', ok, 'max_sm_mhz', max(r['sm_mhz'] for s in rows for r in s['ranks']))


def main():
    assert sys.argv[1:] == ['run']
    try:
        for arm, args in ARMS:
            applied = everywhere(['/usr/bin/nvidia-smi', *args])
            save(f'{arm}-applied.json', {'nvidia_smi_args': args, 'ranks': applied})
            if any(r['returncode'] for r in applied):
                log('APPLY_FAILED', arm, [r['stderr'] or r['stdout'] for r in applied if r['returncode']])
                continue
            log('APPLIED', arm, args)
            screen(arm)
            telemetry(arm)
            log('TELEMETRY', arm)
    finally:
        restore()


if __name__ == '__main__':
    main()
