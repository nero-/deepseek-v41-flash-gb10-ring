#!/usr/bin/env python3
"""Benchmark the existing selected service without changing its configuration."""
import hashlib
import importlib.util
import json
from pathlib import Path
import time

spec = importlib.util.spec_from_file_location('trial', Path('/Users/jg/Agent/Builds/deepseek-v41-flash-ring/scripts/research-trial.py'))
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)
ROOT = Path('/Users/jg/Agent/Builds/deepseek-v41-flash-ring')
tag = 'csf-full-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
folder = ROOT / 'results' / tag
folder.mkdir(parents=True)
(folder / 'runner.py').write_text(Path(__file__).read_text())
remote_root = '/home/nero/bench/results/' + tag
selected_text = trial.remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout
selected = json.loads(selected_text)
trial_specs = json.loads((ROOT/'results/20261004-csf/trial-specs.json').read_text())
selected['specs'] = trial_specs
assert selected['profile'] == 'engram-adaptive4k-query-indexer'
health = trial.remote(0, ['curl', '-fsS', '--max-time', '10', 'http://127.0.0.1:8015/health'])
(folder / 'configuration.json').write_text(json.dumps({
    'profile': selected['profile'], 'configuration_sha256': hashlib.sha256(selected_text.encode()).hexdigest(),
    'plugin_manifest': selected['plugin_manifest'],
    'image_ids': [s['image_id'] for s in selected['specs']],
    'trial_configuration_sha256': hashlib.sha256((ROOT/'results/20261004-csf/trial-specs.json').read_bytes()).hexdigest(),
    'runtime_parameters': {'omp_num_threads': trial_specs[0]['environment']['OMP_NUM_THREADS'], 'csf_inline': trial_specs[0]['environment']['B12X_W4A8_CSF_INLINE'], 'compile_cache': trial_specs[0]['environment']['B12X_COMPILE_CACHE_DIR'], 'checkpoint': 'c5c41fe301c4c1d24fc09376883d9168e521dc66', 'gpu_clock_upper_mhz': 2350},
    'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'note': 'Trial CSF images with immutable launch specs; selected configuration remains unchanged.',
}, indent=2))
statuses = {}


def run(name, rank, argv, *, input_text=None):
    (folder / (name + '-command.json')).write_text(json.dumps({'rank': rank, 'argv': argv}, indent=2))
    print('START', name, flush=True)
    result = trial.remote(rank, argv, input_text, check=False)
    (folder / (name + '.log')).write_text(result.stdout + result.stderr)
    statuses[name] = result.returncode
    (folder / 'statuses.json').write_text(json.dumps(statuses, indent=2))
    print('DONE', name, result.returncode, flush=True)
    if result.returncode:
        raise RuntimeError(name + ' failed; inspect ' + str(folder))


argv = ['/home/nero/bench/.venv/bin/python', '-u', '/home/nero/bench/lil_matched.py',
        '/home/nero/bench/llm-inference-bench/llm_decode_bench.py',
        '--host', '192.168.50.219', '--port', '8015', '--model', 'DeepSeek-V4.1-Flash-TP4',
        '--no-hw-monitor', '--display-mode', 'plain', '--no-resume', '--temperature', '1.0',
        '--contexts', '8192,32768,65536,131072', '--concurrency', '1,2,4,8,16',
        '--duration', '30', '--max-tokens', '2048', '--standalone-prefill',
        '--prefill-contexts', '8k,32k,64k,128k', '--run-burst',
        '--burst-requests-per-concurrency', '1', '--burst-warmup-request-count', '1',
        '--coding-peak', '--coding-peak-runs', '5', '--coding-peak-max-tokens', '2000',
        '--output', remote_root + '.json']
# Capture stdout remotely too, so progress is visible without interrupting the
# benchmark. Explicitly decline its optional self-update to preserve v0.6.2.
launcher = '''import json,subprocess,sys
argv=json.loads(sys.stdin.readline())
with open(sys.argv[1], 'w') as log:
 r=subprocess.run(argv, input='n' + chr(10), text=True, stdout=log, stderr=subprocess.STDOUT)
raise SystemExit(r.returncode)
'''
print('RESULTS', folder, 'REMOTE', remote_root, flush=True)
(folder / 'lil-argv.json').write_text(json.dumps(argv, indent=2))
run('lil', 3, ['python3', '-c', launcher, remote_root + '.log'], input_text=json.dumps(argv) + '\n')
for suffix in ('.json', '.matched-request.json', '.log'):
    data = trial.remote(3, ['cat', remote_root + suffix]).stdout
    (folder / ('lil' + ('.txt' if suffix == '.log' else suffix))).write_text(data)
# This pinned LIL version caps its prefill grid at 128K. Larger fresh-prefill
# retrieval probes are explicitly separate measurements, with cache counts.
probe = '/home/nero/dsv41-research-20260928/cold-needle.py'
source = (ROOT / 'bench/cold-needle.py').read_text()
trial.remote(0, ['python3', '-c', 'import sys;from pathlib import Path;Path(sys.argv[1]).write_text(sys.stdin.read())', probe], source)
(folder / 'cold-needle.py').write_text(source)
for size in (256000, 524288, 1048576):
    name = 'cold-' + str(size)
    output = '/home/nero/dsv41-research-20260928/' + tag + '-' + name + '.json'
    run(name, 0, ['python3', probe, '--tokens', str(size), '--output', output])
    (folder / (name + '.json')).write_text(trial.remote(0, ['cat', output]).stdout)
assert trial.remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout == selected_text
nodes = trial.parallel(lambda rank: json.loads(trial.remote(rank, ['docker', 'inspect', f'ds41-csf-r{rank}']).stdout)[0])
assert all(n['State']['Running'] for n in nodes)
run('health', 0, ['curl', '-fsS', '--max-time', '10', 'http://127.0.0.1:8015/health'])
logs = trial.remote(0, ['docker', 'logs', 'ds41-csf-r0'])
lines = [s for s in (logs.stdout + logs.stderr).splitlines() if '[local-indexer-tp]' in s]
(folder / 'final-health.json').write_text(json.dumps({
    'profile': selected['profile'], 'configuration_unchanged': True, 'api_healthy': True,
    'nodes': [{'name': n['Name'], 'running': n['State']['Running'], 'started_at': n['State']['StartedAt']} for n in nodes],
    'indexer_guards_enabled': sum('exact=ON' in s for s in lines),
    'indexer_guards_disabled': sum('exact=OFF' in s for s in lines),
    'indexer_lines': lines,
}, indent=2))
print('COMPLETE', folder, flush=True)
