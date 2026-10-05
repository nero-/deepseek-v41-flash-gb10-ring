#!/usr/bin/env python3
"""Recover the exact pre-CSF selection after the completed rejected benchmark.

The root-owned configuration/controllers were never replaced. Restore missing
GX10 weights from lossless CSF, verify all original shards on all ranks, then
start the retained original containers. Candidate cleanup is a separate phase.
"""
import importlib.util
import json
from pathlib import Path
import time

s = importlib.util.spec_from_file_location('campaign', Path(__file__).with_name('csf-upgrade.py'))
c = importlib.util.module_from_spec(s)
s.loader.exec_module(c)
OLD = '/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277'
NEW = '/srv/sparkring/sparkring/checkpoints/local-inference-lab--DeepSeek-V4.1-Flash-lossless-CSF/c5c41fe301c4c1d24fc09376883d9168e521dc66'
VERIFY = '''import hashlib,json,sys,time
from pathlib import Path
root=Path(sys.argv[1]);manifest=json.loads(Path(sys.argv[2]).read_text());assert manifest['sha']=='dba1be0a40aa45a94ad051997016db3960a90277'
records=[]
for row in manifest['siblings']:
 name=row['rfilename']
 if not name.endswith('.safetensors'):continue
 assert Path(name).name==name
 p=root/name;assert p.is_file() and not p.is_symlink() and p.stat().st_nlink==1
 assert p.stat().st_size==row['size']
 with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 assert digest==row['lfs']['sha256'],name
 records.append({'file':name,'bytes':p.stat().st_size,'sha256':digest,'restored':False})
 print(json.dumps(records[-1]),flush=True)
assert len(records)==48
Path(sys.argv[3]).write_text(json.dumps({'revision':manifest['sha'],'complete':True,'shards':records},indent=2)+chr(10))
print('ORIGINAL CHECKPOINT VERIFIED',flush=True)
'''


def main():
    decision = json.loads((c.F / 'promotion-decision.json').read_text())
    assert decision['decision'] == 'reject' and decision['restore_original']
    full = Path(decision['full_benchmark'])
    statuses = json.loads((full / 'statuses.json').read_text())
    for key in ('lil', 'cold-256000', 'cold-524288', 'cold-1048576', 'health'):
        assert statuses.get(key) == 0, 'Benchmark must finish before recovery: ' + key
    before = json.loads((c.F / 'selected-before.json').read_text())
    selected = json.loads(c.t.remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout)
    assert selected == before, 'Original root-owned selection must still match'
    final_images = json.loads((c.F / 'images.json').read_text())
    for rank in range(4):
        trial = json.loads(c.t.remote(rank, ['docker', 'inspect', f'ds41-csf-r{rank}']).stdout)[0]
        original = json.loads(c.t.remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0]
        assert trial['Image'] == final_images[rank]['image_id']
        assert original['Image'] == before['specs'][rank]['image_id'] and not original['State']['Running']
    c.t.parallel(lambda rank: c.record(f'rollback-candidate-logs-r{rank}', rank,
                 ['docker', 'logs', f'ds41-csf-r{rank}']))
    c.t.parallel(lambda rank: c.record(f'rollback-stop-r{rank}', rank,
                 ['docker', 'stop', '--time', '15', f'ds41-csf-r{rank}']))
    assert all(not c.t.remote(rank, ['docker', 'ps', '-q']).stdout.strip() for rank in range(4))
    writer = 'import sys;from pathlib import Path;Path(sys.argv[1]).write_text(sys.stdin.read())'
    sources = {'restore-original.py': (c.ROOT / 'image/csf/restore-original.py').read_text(),
               'original-hub-file-manifest.json': (c.F / 'original-hub-file-manifest.json').read_text()}
    for rank in range(4):
        for name, source in sources.items():
            c.t.remote(rank, ['python3', '-c', writer, c.REMOTE + '/' + name], source)

    def recover(rank):
        output = c.REMOTE + f'/original-restore-r{rank}.json'
        if rank < 2:
            c.record(f'original-restore-r{rank}', rank,
                     ['python3', '-u', '-c', VERIFY, OLD,
                      c.REMOTE + '/original-hub-file-manifest.json', output], admin=True)
        else:
            name = f'ds41-original-restore-r{rank}'
            assert c.t.remote(rank, ['docker', 'inspect', name], check=False).returncode != 0
            argv = ['docker', 'run', '--rm', '--name', name,
                    '--user', '0:0',
                    '--label', 'io.local.deepseek-recovery=csf-20261004',
                    '--network', 'none', '--runtime', 'runc', '--env', 'NVIDIA_VISIBLE_DEVICES=void',
                    '--env', 'LD_PRELOAD=', '--env', 'LD_LIBRARY_PATH=',
                    '--env', 'CUDA_VISIBLE_DEVICES=', '--entrypoint', 'python3']
            for host, target, readonly in (
                (OLD, OLD, False), (NEW, NEW, False), (c.REMOTE, '/recovery', False),
                ('/var/run/docker.sock', '/var/run/docker.sock', True),
                ('/usr/bin/docker', '/usr/bin/docker', True),
            ):
                argv += ['--mount', f'type=bind,src={host},dst={target}' + (',readonly' if readonly else '')]
            argv += [final_images[rank]['image_id'], '-u', '/recovery/restore-original.py',
                     '--original-manifest', '/recovery/original-hub-file-manifest.json',
                     '--output', f'/recovery/original-restore-r{rank}.json',
                     '--recovery-container', name, '--replace-candidate']
            c.record(f'original-restore-r{rank}', rank, argv)
        document = json.loads(c.t.remote(rank, ['cat', output]).stdout)
        assert document['complete'] and len(document['shards']) == 48
        (c.F / f'original-restore-r{rank}.json').write_text(json.dumps(document, indent=2) + '\n')
        print(rank, 'original checkpoint verified', flush=True)
    c.t.parallel(recover)
    assert json.loads(c.t.remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout) == before
    # Starting through the normal original helper also checks the immutable
    # container specs and root-owned plugin hashes; no live config is rewritten.
    c.record('restored-up', 0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'up'])
    c.record('restored-functional', 0, ['python3', '-u', c.REMOTE + '/tests/functional.py', 'http://127.0.0.1:8015/v1'])
    # User requested no repeat benchmark of the known original recipe.
    c.record('restored-status', 0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'status'])
    for rank in range(4):
        info = json.loads(c.t.remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0]
        assert info['State']['Running'] and info['Image'] == before['specs'][rank]['image_id']
    (c.F / 'deployment.json').write_text(json.dumps({
        'selected': 'previous-kk926-corrected', 'healthy': True,
        'checkpoint': 'dba1be0a40aa45a94ad051997016db3960a90277',
        'endpoint': 'http://192.168.50.219:8015/v1',
        'image_ids': [x['image_id'] for x in before['specs']],
        'selected_configuration_unchanged': True,
        'candidate_promoted': False, 'unix_time': time.time(),
        'reason': 'User rejected slower integrated CSF/beta/SparkRing candidate; original shard hashes verified on all four nodes.',
    }, indent=2) + '\n')
    print('Previous corrected runtime restored and healthy', flush=True)


if __name__ == '__main__':
    main()
