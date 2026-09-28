import importlib.util
import json
from pathlib import Path
import sys
import time
ROOT = Path('/Users/jg/Agent/Builds/deepseek-v41-flash-ring')
spec = importlib.util.spec_from_file_location('trial', ROOT / 'scripts/research-trial.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)
folder = Path(sys.argv[1])
status = json.loads((folder / 'post-deploy-statuses.json').read_text()) if (folder / 'post-deploy-statuses.json').exists() else {}
def run(name, command):
    (folder / (name + '-command.json')).write_text(json.dumps({'rank': 0, 'argv': command}, indent=2))
    r = trial.remote(0, command, check=False)
    (folder / (name + '.txt')).write_text(r.stdout + r.stderr)
    status[name] = r.returncode
    (folder / 'post-deploy-statuses.json').write_text(json.dumps(status, indent=2))
    print(name, r.returncode, flush=True)
    if r.returncode:
        raise RuntimeError(name + ' failed')
if '--verify-only' not in sys.argv:
    run('post-deploy-functional', ['python3', '/home/nero/sparkring-migration-20260927/probes/functional.py', 'http://127.0.0.1:8015/v1'])
    output = trial.REMOTE + '/' + folder.name + '-post-deploy-long-functional.json'
    run('post-deploy-long-functional', ['python3', trial.REMOTE + '/long-functional.py', '--suite', '/home/nero/sparkring-migration-20260927/probes/functional.py', '--output', output])
    long = json.loads(trial.remote(0, ['cat', output]).stdout)
    assert long['all_long_prefills'] and long['exit_code'] == 0
    (folder / 'post-deploy-long-functional.json').write_text(json.dumps(long, indent=2))
    output = trial.REMOTE + '/' + folder.name + '-post-deploy-cold-1m.json'
    run('post-deploy-cold-1m', ['python3', trial.REMOTE + '/cold-needle.py', '--tokens', '1048576', '--output', output])
    cold = json.loads(trial.remote(0, ['cat', output]).stdout)
    assert cold['needle_pass'] and cold['cold_confirmed']
    (folder / 'post-deploy-cold-1m.json').write_text(json.dumps(cold, indent=2))
selected = json.loads(trial.remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout)
checkpoint = '/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277'
def verify(rank):
    name = f'ds41-optimized-r{rank}'
    info = json.loads(trial.remote(rank, ['docker', 'inspect', name]).stdout)[0]
    assert info['State']['Running'] and info['Config']['Labels']['io.local.deepseek-optimized'] == selected['profile']
    running = trial.remote(rank, ['docker', 'ps', '--format', '{{.Names}}']).stdout.splitlines()
    assert running == [name], running
    script = 'import hashlib,json,sys;from pathlib import Path;r=Path(sys.argv[1]);m=json.loads(sys.argv[2]);assert all((r/n).stat().st_uid==0 and not (r/n).stat().st_mode & 0o022 and hashlib.sha256((r/n).read_bytes()).hexdigest()==v for n,v in m.items());print("manifest verified")'
    trial.remote(rank, ['python3', '-c', script, '/usr/local/lib/deepseek-ring/plugins', json.dumps(selected['plugin_manifest'])])
    weights = trial.remote(rank, ['docker', 'exec', name, 'find', '/models/target', '-type', 'f', '-name', '*.safetensors']).stdout.splitlines()
    assert len(weights) == 48, len(weights)
    logs = trial.remote(rank, ['docker', 'logs', name])
    lines = [s for s in (logs.stdout + logs.stderr).splitlines() if '[local-indexer-tp]' in s or '[context-indexer]' in s]
    startup = next((i for i,s in enumerate(lines) if 'worker startup complete' in s), None)
    real = next((i for i,s in enumerate(lines) if 'first real request observed' in s), None)
    first_guard = next((i for i,s in enumerate(lines) if 'exact=' in s), None)
    # Exactness result is logged on TP rank 0; all ranks participate in its MIN.
    if rank == 0:
        assert startup is not None and real is not None and first_guard is not None and startup < real < first_guard
        assert any('exact=ON' in s for s in lines) and not any('exact=OFF' in s for s in lines)
    mesh = trial.remote(rank, ['systemctl', 'show', '--property=ActiveState', '--property=UnitFileState', 'sparkring-sparkring-deepseek-v41-flash-adaefa-mesh.service']).stdout
    assert 'ActiveState=active' in mesh and 'UnitFileState=enabled' in mesh
    return {'rank': rank, 'name': name, 'running': True, 'mesh': mesh, 'started_at': info['State']['StartedAt'], 'image': info['Image'],
            'profile': selected['profile'], 'manifest_verified': True, 'checkpoint_safetensors': len(weights),
            'free_space': trial.remote(rank, ['docker', 'exec', name, 'df', '-B1', '/models/target']).stdout, 'indexer_lines': lines}
nodes = trial.parallel(verify)
run('post-deploy-health', ['curl', '-fsS', '--max-time', '10', 'http://127.0.0.1:8015/health'])
(folder / 'final-health.json').write_text(json.dumps({'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'profile': selected['profile'], 'nodes': nodes, 'api_healthy': True}, indent=2))
print('FINAL HEALTH PASSED', flush=True)
