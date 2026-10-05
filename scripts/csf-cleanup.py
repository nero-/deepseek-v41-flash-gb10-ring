#!/usr/bin/env python3
"""Remove only the inventoried original checkpoint after healthy CSF promotion."""
import importlib.util
import json
from pathlib import Path

s = importlib.util.spec_from_file_location('campaign', Path(__file__).with_name('csf-upgrade.py'))
c = importlib.util.module_from_spec(s)
s.loader.exec_module(c)
OLD = '/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277'
NEW = '/srv/sparkring/sparkring/checkpoints/local-inference-lab--DeepSeek-V4.1-Flash-lossless-CSF/c5c41fe301c4c1d24fc09376883d9168e521dc66'

DELETE = '''import json,subprocess,sys
from pathlib import Path
old=Path(sys.argv[1]);new=Path(sys.argv[2]);inventory={x['name']:x for x in json.load(sys.stdin)}
assert old.resolve()==old and new.resolve()==new and old!=new
assert json.loads((new/'verified-shards.json').read_text())['revision']=='c5c41fe301c4c1d24fc09376883d9168e521dc66'
assert len(list((new/'tensors').glob('*.safetensors')))==48
running=subprocess.check_output(['docker','ps','-q'],text=True).split()
for identifier in running:
 info=json.loads(subprocess.check_output(['docker','inspect',identifier],text=True))[0]
 for mount in info['Mounts']:
  assert not Path(mount['Source']).is_relative_to(old), 'Original checkpoint still mounted by a live container'
deleted=[]
if old.exists():
 for file in old.iterdir():
  assert file.name in inventory and not file.is_symlink() and file.is_file(),str(file)
  row=inventory[file.name];stat=file.stat()
  assert stat.st_size==row['size'] and stat.st_ino==row['inode'] and stat.st_nlink==row['links'],str(file)
 for file in old.iterdir():
  deleted.append({'file':file.name,'bytes':file.stat().st_size});file.unlink()
 old.rmdir()
print(json.dumps({'old_removed':not old.exists(),'deleted':deleted,'new_preserved':new.exists()}))
'''


def main():
    deployment = json.loads((c.F / 'deployment.json').read_text())
    assert deployment['selected'] == 'csf-beta' and deployment['healthy']
    selected = json.loads(c.t.remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout)
    assert selected['stock_checkpoint_retired']
    assert selected == json.loads((c.F / 'selected-candidate.json').read_text())
    c.record('cleanup-health', 0, ['curl', '-fsS', '--max-time', '10', 'http://127.0.0.1:8015/health'])
    for rank in range(4):
        info = json.loads(c.t.remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0]
        assert info['State']['Running'] and info['Image'] == selected['specs'][rank]['image_id']
    def one(rank):
        inventory = (c.F / f'checkpoint-layout-r{rank}.json').read_text()
        result = c.record(f'old-checkpoint-cleanup-r{rank}', rank,
                          ['python3', '-c', DELETE, OLD, NEW], inventory, admin=True)
        receipt = json.loads(result.stdout)
        assert receipt['old_removed'] and receipt['new_preserved']
        print(rank, 'original checkpoint removed', flush=True)
    c.t.parallel(one)
    for rank in (0, 1):
        c.record(f'artifact-server-stop-r{rank}', rank,
                 ['systemctl', 'stop', 'ds41-csf-artifacts.service'], admin=True, check=False)
    c.t.parallel(lambda rank: c.record(f'final-space-r{rank}', rank,
                  ['df', '-h', NEW], admin=True))
    c.record('cleanup-final-health', 0, ['curl', '-fsS', '--max-time', '10', 'http://127.0.0.1:8015/health'])


if __name__ == '__main__':
    main()
