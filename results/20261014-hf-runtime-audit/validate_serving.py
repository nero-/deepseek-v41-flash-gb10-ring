"""Sequential checks of the unchanged restored DS recipe; retains raw evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from fleet import remote, parallel

BASE = 'http://192.168.50.219:8015'
REMOTE = '/home/nero/bench/results/hf-runtime-audit-20261014'
statuses = {}

def record(name, result):
    (OUT / (name + '.log')).write_text(result.stdout + result.stderr)
    statuses[name] = result.returncode
    (OUT / 'validation-status.json').write_text(json.dumps(statuses, indent=2))
    print('DONE', name, result.returncode, flush=True)
    if result.returncode:
        raise RuntimeError(name + ' failed; inspect its log before continuing')

deadline = time.monotonic() + 2400
while True:
    try:
        with urllib.request.urlopen(BASE + '/v1/models', timeout=5) as r:
            models = json.load(r)
        assert models['data'][0]['id'] == 'DeepSeek-V4.1-Flash-TP4'
        break
    except Exception:
        if time.monotonic() > deadline: raise
        time.sleep(15)
print('DS READY', flush=True)
config = remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout
expected = json.loads((REPO / 'results/deployment.json').read_text())
assert hashlib.sha256(config.encode()).hexdigest() == expected['configuration_sha256']

record('functional', subprocess.run([sys.executable, str(REPO / 'bench/functional.py'), BASE + '/v1'],
                                    text=True, capture_output=True))
argv = ['/home/nero/bench/.venv/bin/python', '-u', '/home/nero/bench/lil_matched.py',
        '/home/nero/bench/llm-inference-bench/llm_decode_bench.py',
        '--host', '192.168.50.219', '--port', '8015', '--model', 'DeepSeek-V4.1-Flash-TP4',
        '--no-hw-monitor', '--display-mode', 'plain', '--no-resume', '--temperature', '1.0',
        '--contexts', '8192,131072', '--concurrency', '1,8,16', '--duration', '30',
        '--max-tokens', '2048', '--standalone-prefill', '--prefill-contexts', '8k,128k',
        '--output', REMOTE + '.json']
(OUT / 'lil-command.json').write_text(json.dumps(argv, indent=2))
launcher = """import json,subprocess,sys
argv=json.loads(sys.stdin.readline())
with open(sys.argv[1],'w') as log:
 r=subprocess.run(argv,input='n\\n',text=True,stdout=log,stderr=subprocess.STDOUT)
raise SystemExit(r.returncode)
"""
print('START matched LIL screen', flush=True)
record('lil', remote(3, ['python3', '-c', launcher, REMOTE + '.log'], json.dumps(argv) + '\n', check=False))
for suffix in ('.json', '.matched-request.json', '.log'):
    (OUT / ('lil' + suffix)).write_text(remote(3, ['cat', REMOTE + suffix]).stdout)
record('cold-128k', subprocess.run([sys.executable, str(REPO / 'bench/cold-needle.py'),
       '--url', BASE, '--tokens', '131072', '--output', str(OUT / 'cold-128k.json')],
       text=True, capture_output=True))
source = (REPO / 'bench/decode-prefill-consistency.py').read_text()
dest = '/home/nero/bench/hf-audit-consistency-20261014.py'
remote(0, ['python3', '-c', 'import sys;from pathlib import Path;Path(sys.argv[1]).write_text(sys.stdin.read())', dest], source)
print('START long-answer consistency', flush=True)
record('consistency', remote(0, ['python3', '-u', dest, '--tokens', '2048', '--limit', '8',
       '--output', REMOTE + '-consistency.json'], check=False))
(OUT / 'consistency.json').write_text(remote(0, ['cat', REMOTE + '-consistency.json']).stdout)
assert remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout == config
nodes = parallel(lambda rank: json.loads(remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0])
assert all(n['State']['Running'] and n['Image'] == expected['images'][r]['image_id'] for r,n in enumerate(nodes))
health = urllib.request.urlopen(BASE + '/health', timeout=10).status
(OUT / 'final-serving.json').write_text(json.dumps({'healthy': health == 200,
    'configuration_unchanged': True, 'images_unchanged': True,
    'nodes': [{'name':n['Name'],'image':n['Image'],'started':n['State']['StartedAt']} for n in nodes]},indent=2))
print('VALIDATION COMPLETE', flush=True)
