#!/usr/bin/env python3
"""Remove the rejected CSF checkpoint only after original serving is healthy."""
import importlib.util
import json
from pathlib import Path
import time

s = importlib.util.spec_from_file_location('campaign', Path(__file__).with_name('csf-upgrade.py'))
c = importlib.util.module_from_spec(s)
s.loader.exec_module(c)
NEW = '/srv/sparkring/sparkring/checkpoints/local-inference-lab--DeepSeek-V4.1-Flash-lossless-CSF/c5c41fe301c4c1d24fc09376883d9168e521dc66'
DELETE = '''import collections,json,stat,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);assert root.resolve()==root
assert root.name=='c5c41fe301c4c1d24fc09376883d9168e521dc66'
for identifier in subprocess.check_output(['docker','ps','-q'],text=True).split():
 info=json.loads(subprocess.check_output(['docker','inspect',identifier],text=True))[0]
 for mount in info['Mounts']:
  source=Path(mount['Source'])
  assert not source.is_relative_to(root), 'Candidate still mounted by a live container'
paths=list(root.rglob('*'));files=[];directories=[];counts=collections.Counter()
for path in paths:
 assert not path.is_symlink() and path.resolve()==path
 if path.is_dir():directories.append(path);continue
 st=path.stat();assert stat.S_ISREG(st.st_mode)
 row={'file':str(path.relative_to(root)),'bytes':st.st_size,'inode':st.st_ino,'links':st.st_nlink}
 files.append(row);counts[st.st_ino]+=1
for row in files:assert row['links']==counts[row['inode']], 'Candidate has a hard link outside its own checkpoint'
unique={row['inode']:row['bytes'] for row in files}
for row in files:(root/row['file']).unlink()
for path in sorted(directories,key=lambda p:len(p.parts),reverse=True):path.rmdir()
root.rmdir()
print(json.dumps({'candidate_removed':not root.exists(),'unique_bytes_removed':sum(unique.values()),'files':files}))
'''


def main():
    deployment = json.loads((c.F / 'deployment.json').read_text())
    assert deployment['selected'] == 'previous-kk926-corrected' and deployment['healthy']
    decision = json.loads((c.F / 'promotion-decision.json').read_text())
    assert decision['decision'] == 'reject' and decision['delete_candidate_checkpoint_after_restored_health']
    before = json.loads((c.F / 'selected-before.json').read_text())
    assert json.loads(c.t.remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout) == before
    for rank in range(4):
        proof = json.loads((c.F / f'original-restore-r{rank}.json').read_text())
        assert proof['complete'] and len(proof['shards']) == 48
        info = json.loads(c.t.remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0]
        assert info['State']['Running'] and info['Image'] == before['specs'][rank]['image_id']
    c.record('candidate-cleanup-health', 0, ['curl', '-fsS', '--max-time', '10', 'http://127.0.0.1:8015/health'])
    for rank in (0, 1):
        c.record(f'artifact-server-stop-r{rank}', rank,
                 ['systemctl', 'stop', 'ds41-csf-artifacts.service'], admin=True)
    final = json.loads((c.F / 'images.json').read_text())
    initial = json.loads((c.F / 'images-before-sparkring-update.json').read_text())
    for rank in range(4):
        for stem in ('ds41-csf', 'ds41-csf-omp1', 'ds41-csf-inline0', 'ds41-csf-omp16'):
            name = f'{stem}-r{rank}'
            result = c.t.remote(rank, ['docker', 'inspect', name], check=False)
            if result.returncode:
                continue
            info = json.loads(result.stdout)[0]
            assert not info['State']['Running']
            assert info['Image'] in (final[rank]['image_id'], initial[rank]['image_id'])
            assert info['Config']['Labels'].get('io.local.deepseek-correction', '').startswith('csf')
            c.record(f'candidate-container-remove-{stem}-r{rank}', rank, ['docker', 'rm', name])

    def one(rank):
        prior = c.F / f'candidate-checkpoint-cleanup-r{rank}.json'
        exists = c.root(rank, ['python3', '-c', 'from pathlib import Path;import sys;print(Path(sys.argv[1]).exists())', NEW]).stdout.strip()
        if exists == 'False':
            assert prior.exists() and json.loads(prior.read_text())['candidate_removed']
            c.record(f'final-space-r{rank}', rank, ['df', '-h', '/srv/sparkring/sparkring/checkpoints'], admin=True)
            return
        assert exists == 'True'
        result = c.record(f'candidate-checkpoint-cleanup-r{rank}', rank,
                          ['python3', '-c', DELETE, NEW], admin=True)
        receipt = json.loads(result.stdout)
        assert receipt['candidate_removed']
        (c.F / f'candidate-checkpoint-cleanup-r{rank}.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(rank, 'candidate checkpoint removed', flush=True)
        c.record(f'final-space-r{rank}', rank, ['df', '-h', '/srv/sparkring/sparkring/checkpoints'], admin=True)
    c.t.parallel(one)
    c.record('post-cleanup-up', 0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'up'])
    c.record('post-cleanup-status', 0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'status'])
    c.record('post-cleanup-health', 0, ['curl', '-fsS', '--max-time', '10', 'http://127.0.0.1:8015/health'])
    deployment.update(candidate_checkpoint_removed=True, cleanup_unix_time=time.time())
    (c.F / 'deployment.json').write_text(json.dumps(deployment, indent=2) + '\n')
    print('Rejected CSF checkpoints removed; original serving retained', flush=True)


if __name__ == '__main__':
    main()
