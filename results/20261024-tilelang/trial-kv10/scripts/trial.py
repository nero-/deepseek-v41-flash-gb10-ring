#!/usr/bin/env python3
"""Phased spark-ds41f-1022 TileLang trial on the switched SparkRing fleet.

Phases, in order (each writes receipts under results/20261024-trial and
refuses to repeat a completed phase):

  preflight   read-only: production identity, selection, staged inputs
  stop        DOWNTIME: controller down, then claim the fleet with the
              start interlock the root controller honours
  build       build the pinned image on spark-r1 with spark-ds41f's own builder
  distribute  stream the image to the other ranks over rail A; verify layers
  start       render, prebuild FlashInfer, start ranks 1-3 then 0, wait for
              the API, then functional, loaded-clock and cold retrieval gates
  bench       three LIL 0.7.6 screens, the October 21 protocol unchanged
  restore     stop the trial, archive the interlock, controller up, verify
  control     LIL screen(s) of restored production, same protocol

The trial never edits /etc/deepseek-ring/optimized-specs.json or the
canonical ds41-optimized-rN containers.
"""
import argparse
import datetime
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (ALIASES, HOSTS, PRODUCTION_IMAGE, RAIL_A, REPO, RESULTS, SELECTION, TRIAL,  # noqa: E402
                    TRIAL_CONTAINER, host_snapshot, kernels, parallel, remote, save, sha_selected)

BUILD_RANK = 1
BUILD_DIR = '/home/nero/builds/ds41f-tilelang-20261024/spark-ds41f'
BUILD_INPUTS = '.work/build/vllm-19f2c20ed4d6-b12x-236ddff04a5f-99695427'
TAG = 'ds41f-tilelang:19f2c20ed4d6-1022-sparkring'
BASE = 'docker.io/vllm/vllm-openai@sha256:3cf14c52765a0f0c2f09035e05fa79e1e4b2f9788b64afa90fa41c1ff12d29cf'
EXPECTED_LABELS = {
    'local.spark3.vllm.tree': 'e68aa19c8027c34a3dcfeb3ed203f6d285fc4d67',
    'local.spark3.b12x.tree': '1a647a311ca55d45070ab83d60668d9c8fb8886c',
    'local.spark3.nccl.tree': '6af10aa730a64fcee8781d62340a9c9184e79469',
    'local.spark3.tilelang.tree': '222b895d04ee6cd75179155d06e0c0d450636f51',
    'local.spark3.tile_kernels.tree': 'cb2fa41c8af290204c81c547ed678ebf957cca53',
    'local.spark3.sparknet.tree': 'f997a594f03a696897e6ad8e50bb027ed877ebe9',
}
SECCOMP = '/home/nero/ds41f-tilelang-20261024/seccomp.json'
SECCOMP_SHA256 = 'fd0fdc80514c838515518e079f1b4ef956d6dcb20984097621c44b45ccc42513'
CACHE = '/srv/sparkring/sparkring/cache/ds41f-tilelang-20261024'
MARKER = '/etc/deepseek-ring/FLARE_STAGING.json'
ARCHIVE = 'DS41F_TILELANG_20261024.finished.json'
API = 'http://192.168.50.219:8015'
LIL = Path('/Users/jg/Agent/Diagnostics/deepseek-v41-flash-ring/decode-recovery-20261020/external-client')
LIL_SHA256 = 'c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553'
STARTUP_GUARD_GIB = 1.5


def log(*parts):
    print(datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%SZ'), *parts, flush=True)


def done(name):
    return (RESULTS / name).exists()


def require(*names):
    missing = [n for n in names if not done(n)]
    if missing:
        raise SystemExit(f'complete the earlier phases first: {missing}')


def once(name):
    if done(name):
        raise SystemExit(f'{name} already exists; this phase is complete')


def health():
    try:
        with urllib.request.urlopen(API + '/health', timeout=5) as response:
            return response.status
    except OSError:
        return None


def running(rank):
    return remote(rank, ['docker', 'ps', '--format', '{{.Names}}']).stdout.split()


def control_container(code):
    """Run Python as root in a network-less container with /etc/deepseek-ring at /control."""
    return remote(0, ['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python3',
                      '-v', '/etc/deepseek-ring:/control', PRODUCTION_IMAGE, '-c', code], timeout=120)


def wait_remote_job(rank, directory, label, timeout):
    """Wait for a nohup job started by start_remote_job; return its exit code."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = remote(rank, ['cat', f'{directory}/{label}.rc'], check=False)
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip())
        time.sleep(15)
    raise TimeoutError(f'{label} did not finish in {timeout}s')


def start_remote_job(rank, directory, label, script):
    remote(rank, ['bash', '-c', f'cd {shlex.quote(directory)} && rm -f {label}.rc && '
                  f'nohup bash -c {shlex.quote(script + f"; echo $? > {label}.rc")} > {label}.log 2>&1 < /dev/null &'])


def remote_job_running(rank, directory, label):
    """True while a job started by start_remote_job has neither exited nor written its code."""
    r = remote(rank, ['bash', '-c', f'test ! -e {directory}/{label}.rc && pgrep -f {shlex.quote(label + ".rc")}'],
               check=False)
    return r.returncode == 0


def phase_preflight(_):
    once('preflight.json')
    assert health() == 200, 'production API is not healthy'
    assert sha_selected() == SELECTION, 'installed selection changed'

    def one(rank):
        info = json.loads(remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0]
        assert info['State']['Running'] and info['Image'] == PRODUCTION_IMAGE, (rank, info['State'])
        names = remote(rank, ['docker', 'ps', '-a', '--format', '{{.Names}}']).stdout.split()
        assert TRIAL_CONTAINER.format(rank=rank) not in names, f'rank {rank}: trial container already exists'
        assert remote(rank, ['sha256sum', SECCOMP]).stdout.split()[0] == SECCOMP_SHA256
        free = int(remote(rank, ['df', '--output=avail', '-B1G', '/var/lib/docker']).stdout.split()[-1])
        assert free >= 80, f'rank {rank}: only {free} GiB free for the image'
        return {**host_snapshot(rank), 'canonical_id': info['Id'], 'canonical_args': info['Args'],
                'docker_free_gib': free}
    nodes = parallel(one)
    assert remote(0, ['test', '!', '-e', MARKER], check=False).returncode == 0, 'an interlock marker exists'
    check = remote(BUILD_RANK, ['bash', '-c', f'cd {BUILD_DIR} && git rev-parse HEAD && git status --porcelain '
                                f'&& ./bin/spark --cluster-config config/cluster.json --shape tp4-ring build check'],
                   timeout=600)
    assert check.stdout.splitlines()[0] == '9f1565f060ad84a6f06a745a9b7b4191393cc842', check.stdout
    assert 'build inputs OK' in check.stdout, check.stdout
    lil = LIL / 'lil-0.7.6.py'
    assert hashlib.sha256(lil.read_bytes()).hexdigest() == LIL_SHA256
    save('preflight.json', {'api_health': 200, 'configuration_sha256': SELECTION, 'nodes': nodes,
                            'build_check': check.stdout})
    log('PREFLIGHT_PASS')


def phase_stop(_):
    require('preflight.json')
    once('stop.json')
    log('DOWNTIME_BEGINS: stopping qualified vLLM with the fixed-action controller')
    r = remote(0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'down'], check=False, timeout=300)
    assert r.returncode == 0, r.stderr
    leftovers = parallel(running)
    assert not any(leftovers), f'containers still running: {leftovers}'
    claim = control_container(f'''
import datetime, hashlib, json
from pathlib import Path
selection = Path('/control/optimized-specs.json')
digest = hashlib.sha256(selection.read_bytes()).hexdigest()
assert digest == {SELECTION!r}, digest
marker = Path('/control/FLARE_STAGING.json')
with marker.open('x') as f:
    json.dump({{
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'owner': 'DS41-ds41f-tilelang trial (spark-ds41f-1022 TileLang image, switched clique)',
        'note': 'The controller names FLARE in its refusal; this marker is the shared start interlock.',
        'trial_readme': '~/Agent/Builds/DS41-ds41f-tilelang/README.md',
        'fallback_selection_sha256': digest,
        'fallback_image': {PRODUCTION_IMAGE!r},
        'fallback_containers': 'ds41-optimized-rN (stopped, unchanged)',
        'clock_cap_mhz': 2350,
        'api_port': 8015,
    }}, f, indent=2)
    f.write('\\n')
marker.chmod(0o644)
print('claimed')
''')
    assert claim.returncode == 0 and 'claimed' in claim.stdout, claim.stderr
    marker = remote(0, ['cat', MARKER]).stdout
    states = parallel(lambda rank: json.loads(remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0]['State'])
    save('stop.json', {'controller_down': r.stdout, 'marker': json.loads(marker), 'canonical_states': states})
    log('FLEET_STOPPED_AND_CLAIMED')


def phase_build(_):
    require('stop.json')
    once('build.json')
    assert remote(0, ['test', '-e', MARKER], check=False).returncode == 0, 'interlock marker missing'
    assert not running(BUILD_RANK), 'the build host is not idle'
    started = time.time()
    finished = remote(BUILD_RANK, ['cat', f'{BUILD_DIR}/build-image.rc'], check=False)
    if finished.returncode == 0 and finished.stdout.strip() == '0':
        log('BUILD_ALREADY_FINISHED; recording it', TAG)
    elif remote_job_running(BUILD_RANK, BUILD_DIR, 'build-image'):
        log('BUILD_ALREADY_RUNNING; waiting for it', TAG)
    else:
        log('PULL_BASE', BASE)
        pull = remote(BUILD_RANK, ['docker', 'pull', BASE], check=False, timeout=3600)
        assert pull.returncode == 0, pull.stderr
        log('BUILD_START', TAG)
        start_remote_job(BUILD_RANK, BUILD_DIR, 'build-image',
                         f'./bin/spark --cluster-config config/cluster.json --shape tp4-ring build image --apply --tag {TAG}')
    rc = wait_remote_job(BUILD_RANK, BUILD_DIR, 'build-image', 3 * 3600)
    output = remote(BUILD_RANK, ['tail', '-c', '20000', f'{BUILD_DIR}/build-image.log']).stdout
    (RESULTS / 'build-image.log.tail').write_text(output)
    assert rc == 0, f'build failed ({rc}); see build-image.log.tail'
    image = json.loads(remote(BUILD_RANK, ['docker', 'image', 'inspect', TAG]).stdout)[0]
    labels = image['Config']['Labels'] or {}
    # Builds after spark-ds41f-1022 label trees as local.spark-ds41f.*; the recipe still names local.spark3.*.
    current = lambda k: labels.get(k, labels.get(k.replace('local.spark3.', 'local.spark-ds41f.')))
    wrong = {k: current(k) for k, v in EXPECTED_LABELS.items() if current(k) != v}
    assert not wrong, f'source tree labels differ: {wrong}'
    receipts = remote(BUILD_RANK, ['bash', '-c', f'cat {BUILD_DIR}/{BUILD_INPUTS}/images/*.json'], check=False).stdout
    save('build.json', {'tag': TAG, 'image_id': image['Id'], 'elapsed_seconds': time.time() - started,
                        'labels': labels, 'layers': image['RootFS']['Layers'], 'builder_receipt': receipts,
                        'base': BASE})
    log('BUILD_DONE', image['Id'])


def phase_distribute(_):
    require('build.json')
    once('distribute.json')
    image_id = json.loads((RESULTS / 'build.json').read_text())['image_id']

    def send(rank):
        if rank == BUILD_RANK:
            return {'rank': rank, 'seconds': 0}
        started = time.monotonic()
        # spark-r1's managed ring key reaches every peer; rail A keeps the copy off the LAN.
        r = remote(BUILD_RANK, ['bash', '-o', 'pipefail', '-c',
                                f'docker save {TAG} | ssh -o BatchMode=yes -o HostName={RAIL_A[rank]} '
                                f'{ALIASES[rank]} docker load'], check=False, timeout=3600)
        assert r.returncode == 0, (rank, r.stderr[-2000:])
        return {'rank': rank, 'seconds': time.monotonic() - started, 'stdout': r.stdout[-500:]}
    copies = parallel(send)

    def verify(rank):
        info = json.loads(remote(rank, ['docker', 'image', 'inspect', image_id]).stdout)[0]
        return {'rank': rank, 'id': info['Id'], 'layers': info['RootFS']['Layers'], 'tags': info['RepoTags']}
    images = parallel(verify)
    assert len({json.dumps(i['layers']) for i in images}) == 1 and all(i['id'] == image_id for i in images), images
    save('distribute.json', {'image_id': image_id, 'copies': copies, 'images': images})
    log('IMAGE_ON_ALL_RANKS', image_id)


def phase_start(_):
    require('distribute.json')
    once('startup.json')
    assert remote(0, ['test', '-e', MARKER], check=False).returncode == 0, 'interlock marker missing'
    image_id = json.loads((RESULTS / 'distribute.json').read_text())['image_id']
    launch = RESULTS / 'launch'
    if not launch.exists():
        subprocess.run([sys.executable, str(TRIAL / 'scripts/render.py'), '--image', image_id,
                        '--output', str(launch)], check=True)
    manifest = json.loads((launch / 'manifest.json').read_text())
    assert manifest['image'] == image_id
    leftovers = parallel(running)
    assert not any(leftovers), f'containers running: {leftovers}'

    log('PREBUILD_FLASHINFER')
    prebuild = '''set -e
mkdir -p /cache/kkref/flashinfer/.cache
[ -d /cache/kkref/flashinfer/.cache/flashinfer ] || cp -a /root/.cache/flashinfer /cache/kkref/flashinfer/.cache/ 2>/dev/null || true
python3 -c "
import time; t=time.time()
from flashinfer.sampling import get_sampling_module
m=get_sampling_module(); print('sampling module ready', type(m).__name__, round(time.time()-t,1), 's')
"'''

    def prebuild_rank(rank):
        r = remote(rank, ['docker', 'run', '--rm', '--gpus', 'all', '--memory=24g', '--memory-swap=24g', '--cpus=8',
                          '-e', 'FLASHINFER_WORKSPACE_BASE=/cache/kkref/flashinfer', '-e', 'MAX_JOBS=4',
                          '-v', f'{CACHE}:/cache:rw', '--entrypoint', '/bin/bash', image_id, '-c', prebuild],
                   check=False, timeout=1800)
        assert r.returncode == 0, (rank, r.stderr[-2000:])
        return {'rank': rank, 'stdout': r.stdout[-2000:]}
    prebuilt = parallel(prebuild_rank)

    # Same host preparation as the production controller's start.
    parallel(lambda rank: remote(rank, ['docker', 'run', '--rm', '--privileged', '--network', 'none',
                                        '--entrypoint', 'sh', PRODUCTION_IMAGE, '-c',
                                        'sync && echo 3 > /proc/sys/vm/drop_caches && echo 1 > /proc/sys/vm/compact_memory'],
                                 timeout=300))
    before = parallel(host_snapshot)

    monitor_log = (RESULTS / 'startup-monitor.log').open('x')
    monitor = subprocess.Popen([sys.executable, '-u', str(TRIAL / 'scripts/watch-startup.py'), 'trial',
                                '--seconds', '3600', '--guard-gib', str(STARTUP_GUARD_GIB)],
                               stdout=monitor_log, stderr=subprocess.STDOUT)
    stop = RESULTS / 'startup-trial.stop'
    started = time.time()
    launched = []
    try:
        for rank in manifest['start_order']:
            argv = json.loads((launch / f'rank{rank}.json').read_text())
            r = remote(rank, argv, check=False, timeout=120)
            launched.append({'rank': rank, 'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr[-2000:]})
            assert r.returncode == 0, launched[-1]
            log('STARTED_RANK', rank)
        deadline = time.monotonic() + 3600
        while health() != 200:
            assert time.monotonic() < deadline, 'API not ready in 60 minutes'
            assert monitor.poll() is None, 'startup monitor exited (memory guard?)'
            states = parallel(lambda rank: remote(rank, ['docker', 'inspect', '--format', '{{.State.Status}}',
                                                         TRIAL_CONTAINER.format(rank=rank)]).stdout.strip())
            assert all(s == 'running' for s in states), f'a rank stopped during startup: {states}'
            time.sleep(10)
        ready = time.time()
        log('API_READY', round(ready - started), 's')
        head = host_snapshot(0)
        nodes = parallel(host_snapshot)
        for rank in range(4):
            logs = remote(rank, ['docker', 'logs', TRIAL_CONTAINER.format(rank=rank)], timeout=120)
            (RESULTS / f'startup-r{rank}.log').write_text(logs.stdout + logs.stderr)
        save('startup.json', {'image_id': image_id, 'launch_manifest': manifest, 'launched': launched,
                              'prebuild': prebuilt, 'before': before, 'ready_seconds': ready - started,
                              'head_used_gib_at_ready': head['used_gib'],
                              'head_available_gib_at_ready': head['available_gib'], 'nodes': nodes})
        log('HEAD_USED_GIB', round(head['used_gib'], 3), 'AVAILABLE', round(head['available_gib'], 3))

        def gate(args, name, timeout=1800):
            with (RESULTS / name).open('x') as out:
                r = subprocess.run(args, stdout=out, stderr=subprocess.STDOUT, text=True, timeout=timeout)
            return r.returncode
        results = {
            'functional_failures': gate([sys.executable, '-u', str(REPO / 'bench/functional.py'), API + '/v1'],
                                        'functional.log'),
            'loaded_clocks_rc': gate([sys.executable, '-u', str(TRIAL / 'scripts/load-observation.py'), 'trial'],
                                     'loaded-clocks.log'),
            'cold_needle_rc': gate([sys.executable, '-u', str(REPO / 'bench/cold-needle.py'), '--url', API,
                                    '--tokens', '128000', '--output', str(RESULTS / 'cold-needle.json')],
                                   'cold-needle.log'),
        }
        log('GATES', results)
    finally:
        stop.touch(exist_ok=True)
        try:
            monitor.wait(timeout=60)
        finally:
            monitor_log.close()
    audit = json.loads((RESULTS / 'startup-trial-summary.json').read_text())
    post = kernels(int(started), 'startup-kernel.json')
    save('validation.json', {**results, 'monitor': audit, 'kernel_events': [n['events'] for n in post],
                             'passed': not any(results.values()) and not audit.get('guard_tripped')
                             and not any(n['events'] for n in post)})
    log('VALIDATION', 'PASS' if not any(results.values()) else 'FAIL', results)


def lil_run(label):
    dest = RESULTS / f'{label}.json'
    assert not dest.exists() and health() == 200
    command = [str(LIL / '.venv/bin/python'), str(LIL / 'lil-0.7.6.py'), '--host', HOSTS[0], '--port', '8015',
               '--model', 'DeepSeek-V4.1-Flash-TP4', '--no-hw-monitor', '--display-mode', 'plain', '--no-resume',
               '--temperature', '1', '--concurrency', '1,8,16', '--contexts', '8k,32k', '--duration', '20',
               '--max-tokens', '2048', '--coding-peak', '--output', str(dest)]
    save(f'{label}-command.json', {'argv': command, 'protocol': 'results/20261021-reboot-draft5 run-retests.py'})
    log('BENCHMARK_START', label)
    start = time.time()
    with (RESULTS / f'{label}.log').open('x') as out:
        run = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT, timeout=1800,
                             env={**os.environ, 'LLM_BENCH_NO_UPDATE_CHECK': '1'})
    save(f'{label}-execution.json', {'returncode': run.returncode, 'elapsed_seconds': time.time() - start})
    assert run.returncode == 0, label
    data = json.loads(dest.read_text())
    assert len(data['results']) == 6 and data['coding_peak']['runs_ok'] == 5
    for row in data['results']:
        assert row['aggregate_source'] == 'openai_continuous_usage'
        assert not any(row.get(k) for k in ['num_errors', 'underfilled', 'capacity_limited', 'warmup_timed_out',
                                            'loop_detected', 'failure_reason']), row
    after = kernels(start, f'{label}-kernel.json')
    assert not any(n['events'] for n in after), after
    save(f'{label}-host-state.json', {'nodes': parallel(host_snapshot)})
    log('BENCHMARK_DONE', label, [(x['context_tokens'], x['concurrency'], round(x['aggregate_tps'], 2))
                                  for x in data['results']])


def phase_bench(args):
    require('validation.json')
    validation = json.loads((RESULTS / 'validation.json').read_text())
    if not validation['passed'] and not args.accept_failed_validation:
        raise SystemExit('validation did not pass; inspect it (or pass --accept-failed-validation)')
    states = parallel(lambda rank: remote(rank, ['docker', 'inspect', '--format', '{{.State.Status}} {{.Image}}',
                                                 TRIAL_CONTAINER.format(rank=rank)]).stdout.split())
    image_id = json.loads((RESULTS / 'distribute.json').read_text())['image_id']
    assert all(s == ['running', image_id] for s in states), states
    for i in range(1, args.runs + 1):
        if not done(f'tilelang-run-{i}.json'):
            lil_run(f'tilelang-run-{i}')


def phase_restore(_):
    require('stop.json')
    once('restore.json')
    log('RESTORING_QUALIFIED_VLLM')
    stopped = parallel(lambda rank: remote(rank, ['docker', 'stop', '--time', '30', TRIAL_CONTAINER.format(rank=rank)],
                                           check=False, timeout=120).returncode)
    leftovers = parallel(running)
    assert not any(leftovers), f'containers still running: {leftovers}'
    archived = control_container(f'''
import datetime, json
from pathlib import Path
marker = Path('/control/FLARE_STAGING.json')
record = json.loads(marker.read_text())
assert record['owner'].startswith('DS41-ds41f-tilelang'), record
record['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
archive = Path('/control/{ARCHIVE}')
with archive.open('x') as f:
    json.dump(record, f, indent=2)
    f.write('\\n')
archive.chmod(0o644)
marker.unlink()
print('archived')
''')
    assert archived.returncode == 0 and 'archived' in archived.stdout, archived.stderr
    started = time.time()
    up = remote(0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'up'], check=False, timeout=2500)
    assert up.returncode == 0, up.stderr[-3000:]
    assert health() == 200
    head = host_snapshot(0)
    preflight = json.loads((RESULTS / 'preflight.json').read_text())

    def identity(rank):
        info = json.loads(remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0]
        assert info['State']['Running'] and info['Image'] == PRODUCTION_IMAGE
        assert info['Id'] == preflight['nodes'][rank]['canonical_id']
        assert info['Args'] == preflight['nodes'][rank]['canonical_args']
        return {**host_snapshot(rank), 'canonical_id': info['Id']}
    nodes = parallel(identity)
    assert sha_selected() == SELECTION
    events = kernels(int(started), 'restore-kernel.json')
    save('restore.json', {'trial_stop_returncodes': stopped, 'controller_up': up.stdout[-2000:],
                          'elapsed_seconds': time.time() - started, 'head_used_gib_at_ready': head['used_gib'],
                          'head_available_gib_at_ready': head['available_gib'], 'configuration_sha256': SELECTION,
                          'nodes': nodes, 'kernel_events': [n['events'] for n in events],
                          'archived_marker': f'/etc/deepseek-ring/{ARCHIVE}'})
    log('PRODUCTION_RESTORED', 'head used GiB', round(head['used_gib'], 3))


def phase_control(args):
    require('restore.json')
    assert sha_selected() == SELECTION and health() == 200
    if not done('control-functional.log'):
        with (RESULTS / 'control-functional.log').open('x') as out:
            subprocess.run([sys.executable, '-u', str(REPO / 'bench/functional.py'), API + '/v1'],
                           stdout=out, stderr=subprocess.STDOUT, timeout=900)
    for i in range(1, args.runs + 1):
        if not done(f'control-run-{i}.json'):
            lil_run(f'control-run-{i}')


def require_trial_serving():
    image_id = json.loads((RESULTS / 'distribute.json').read_text())['image_id']
    states = parallel(lambda rank: remote(rank, ['docker', 'inspect', '--format', '{{.State.Status}} {{.Image}}',
                                                 TRIAL_CONTAINER.format(rank=rank)]).stdout.split())
    assert all(s == ['running', image_id] for s in states), states
    assert health() == 200


def phase_fullgrid(_):
    """The public 25-cell LIL 0.7.6 grid exactly as OPERATIONS.md records it."""
    require_trial_serving()
    dest = RESULTS / 'tilelang-full-grid.json'
    assert not dest.exists()
    command = [str(LIL / '.venv/bin/python'), str(LIL / 'lil-0.7.6.py'), '--host', HOSTS[0], '--port', '8015',
               '--model', 'DeepSeek-V4.1-Flash-TP4', '--no-hw-monitor', '--display-mode', 'plain', '--no-resume',
               '--temperature', '1', '--concurrency', '1,2,4,8,16', '--contexts', '8k,16k,32k,64k,128k',
               '--duration', '20', '--max-tokens', '2048', '--coding-peak', '--output', str(dest)]
    save('tilelang-full-grid-command.json', {'argv': command, 'protocol': 'OPERATIONS.md public LIL 0.7.6 grid'})
    log('FULL_GRID_START')
    start = time.time()
    with (RESULTS / 'tilelang-full-grid.log').open('x') as out:
        run = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT, timeout=7200,
                             env={**os.environ, 'LLM_BENCH_NO_UPDATE_CHECK': '1'})
    save('tilelang-full-grid-execution.json', {'returncode': run.returncode, 'elapsed_seconds': time.time() - start})
    assert run.returncode == 0
    data = json.loads(dest.read_text())
    flagged = [(r['context_tokens'], r['concurrency']) for r in data['results']
               if any(r.get(k) for k in ['num_errors', 'underfilled', 'capacity_limited', 'warmup_timed_out',
                                         'loop_detected', 'failure_reason'])]
    after = kernels(start, 'tilelang-full-grid-kernel.json')
    save('tilelang-full-grid-host-state.json', {'nodes': parallel(host_snapshot), 'flagged_cells': flagged,
                                                'kernel_events': [n['events'] for n in after]})
    log('FULL_GRID_DONE', len(data['results']), 'cells; flagged', flagged)


def phase_needle1m(_):
    """Uncached retrieval near the 1,048,576-token limit, with memory before and after."""
    require_trial_serving()
    before = parallel(host_snapshot)
    start = time.time()
    with (RESULTS / 'cold-needle-1m.log').open('x') as out:
        rc = subprocess.run([sys.executable, '-u', str(REPO / 'bench/cold-needle.py'), '--url', API,
                             '--tokens', '1000000', '--output', str(RESULTS / 'cold-needle-1m.json')],
                            stdout=out, stderr=subprocess.STDOUT, timeout=3600).returncode
    after = parallel(host_snapshot)
    events = kernels(start, 'cold-needle-1m-kernel.json')
    save('cold-needle-1m-state.json', {'returncode': rc, 'before': before, 'after': after,
                                       'kernel_events': [n['events'] for n in events]})
    log('NEEDLE_1M rc', rc, 'min available after', min(n['available_gib'] for n in after))


def phase_serve(_):
    """Recover the kept TileLang deployment (for example after a reboot): restart the
    existing trial containers, workers first, under the interlock. Idempotent."""
    require('distribute.json')
    if remote(0, ['test', '-e', MARKER], check=False).returncode:
        raise SystemExit('no interlock marker: production owns the fleet; run stop first to switch')
    image_id = json.loads((RESULTS / 'distribute.json').read_text())['image_id']
    if health() == 200:
        require_trial_serving()
        log('TILELANG_ALREADY_SERVING')
        return
    for rank in range(4):
        foreign = [n for n in running(rank) if n != TRIAL_CONTAINER.format(rank=rank)]
        assert not foreign, f'rank {rank}: stop {foreign} first'
    parallel(lambda rank: remote(rank, ['docker', 'stop', '--time', '30', TRIAL_CONTAINER.format(rank=rank)],
                                 check=False, timeout=120))
    parallel(lambda rank: remote(rank, ['docker', 'run', '--rm', '--privileged', '--network', 'none',
                                        '--entrypoint', 'sh', PRODUCTION_IMAGE, '-c',
                                        'sync && echo 3 > /proc/sys/vm/drop_caches && echo 1 > /proc/sys/vm/compact_memory'],
                                 timeout=300))
    started = time.time()
    for rank in (1, 2, 3, 0):
        remote(rank, ['docker', 'start', TRIAL_CONTAINER.format(rank=rank)])
    deadline = time.monotonic() + 2400
    while health() != 200:
        assert time.monotonic() < deadline, 'API not ready in 40 minutes'
        states = parallel(lambda k: remote(k, ['docker', 'inspect', '--format', '{{.State.Status}}',
                                               TRIAL_CONTAINER.format(rank=k)]).stdout.strip())
        assert all(s == 'running' for s in states), f'a rank stopped during startup: {states}'
        time.sleep(10)
    require_trial_serving()
    head = host_snapshot(0)
    log('TILELANG_SERVING in', round(time.time() - started), 's; head used GiB', round(head['used_gib'], 2),
        'image', image_id)


PHASES = {'serve': phase_serve, 'fullgrid': phase_fullgrid, 'needle1m': phase_needle1m, 'preflight': phase_preflight, 'stop': phase_stop, 'build': phase_build, 'distribute': phase_distribute,
          'start': phase_start, 'bench': phase_bench, 'restore': phase_restore, 'control': phase_control}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('phase', choices=PHASES)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--accept-failed-validation', action='store_true')
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    PHASES[args.phase](args)


if __name__ == '__main__':
    main()
