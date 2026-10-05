#!/usr/bin/env python3
"""Select a qualified CSF trial by renaming its live containers, without reload."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time


def load(name, filename):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(s)
    s.loader.exec_module(module)
    return module


c = load('csf', 'csf-upgrade.py')
p = load('promotion', 'promote-research.py')


def read(name):
    return json.loads((c.F / name).read_text())


def main():
    statuses = read('qualification-statuses.json')
    for name in ('functional', 'long-functional', 'csf-screen', 'consistency', 'mixed-integrity', 'cold-1m'):
        assert statuses.get(name) == 0, name
    for rank in range(4):
        for name in ('csf-kernel-tests', 'compressor-ring'):
            assert read(f'{name}-r{rank}-status.json')['exit_code'] == 0
        assert read(f'transport-probe-attempt4-r{rank}.json')['status'] == 'passed'
    assert read('sparkring-update-cpu-tests-status.json')['exit_code'] == 0
    for rank in range(4):
        assert read(f'transport-probe-peerwait-r{rank}.json')['status'] == 'passed'
        assert read(f'final-nvml-after-reload-r{rank}-status.json')['exit_code'] == 0
    assert read('final-tool-policy-api-status.json')['exit_code'] == 0
    assert read('long-functional.json')['all_long_prefills']
    assert len(read('consistency.json')['requests']) == 8
    cold = read('cold-1m.json')
    assert cold['needle_pass'] and cold['cold_confirmed']
    assert cold['usage']['prompt_tokens'] >= 1_000_000
    for row in read('mixed-integrity.json')['rounds']:
        assert row['summary']['needle_pass'] and not row['summary']['errors']
    decision = read('promotion-decision.json')
    assert decision['decision'] == 'promote' and decision['performance_reviewed']
    full = Path(decision['full_benchmark'])
    full_statuses = json.loads((full / 'statuses.json').read_text())
    for name in ('lil', 'cold-256000', 'cold-524288', 'cold-1048576', 'health'):
        assert full_statuses.get(name) == 0, name
    for size in (256000, 524288, 1048576):
        probe = json.loads((full / f'cold-{size}.json').read_text())
        assert probe['needle_pass'] and probe['cold_confirmed']
        assert probe['cached_tokens'] == 0
        assert probe['usage']['prompt_tokens'] >= int(size * 0.95)
    health = json.loads((full / 'final-health.json').read_text())
    assert health['api_healthy'] and health['indexer_guards_enabled'] > 0
    assert health['indexer_guards_disabled'] == 0
    benchmark = json.loads((full / 'lil.json').read_text())
    assert len(benchmark['results']) == 20 and len(benchmark['burst_results']) == 20
    for row in benchmark['results'] + benchmark['burst_results']:
        assert row['aggregate_tps'] > 0 and not row['num_errors']
        assert not row['failure_reason'] and not row['loop_detected']
        assert not row['capacity_limited'] and not row['warmup_timed_out']
    assert benchmark['coding_peak']['runs_ok'] == 5
    assert read('variant-functional-status.json')['exit_code'] == 0
    final_quality = read('final-quality-statuses.json')
    for name in ('variant-functional', 'final-long-functional', 'final-consistency', 'final-mixed-integrity'):
        assert final_quality.get(name) == 0, name
    assert read('final-long-functional.json')['all_long_prefills']
    assert len(read('final-consistency.json')['requests']) == 8
    for row in read('final-mixed-integrity.json')['rounds']:
        assert row['summary']['needle_pass'] and not row['summary']['errors']
    before_text = c.t.remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout
    before = json.loads(before_text)
    assert before == read('selected-before.json')
    documents = read('trial-specs.json')
    after = copy.deepcopy(before)
    after.update(source_receipt=str(c.F), specs=copy.deepcopy(documents),
                 stock_checkpoint_retired=True,
                 runtime_correction={'name': 'csf-beta',
                                     'manifest': read('final-image-manifest.json'),
                                     'retained_fidelity_fix': 'vLLM #926/#943'})
    for rank, document in enumerate(after['specs']):
        document['name'] = f'ds41-optimized-r{rank}'
        # The existing kernel profile is identical, but future recreation uses
        # its root-owned policy source rather than the trial's staging copy.
        document['security_opt'] = before['specs'][rank]['security_opt']
    (c.F / 'selected-candidate.json').write_text(json.dumps(after, indent=2) + '\n')
    tag = '.before-csf-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    old_names = [f'ds41-before-csf-r{r}' for r in range(4)]
    for rank in range(4):
        old = json.loads(c.t.remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0]
        new = json.loads(c.t.remote(rank, ['docker', 'inspect', documents[rank]['name']]).stdout)[0]
        assert not old['State']['Running'] and old['Image'] == before['specs'][rank]['image_id']
        assert new['State']['Running'] and new['Image'] == documents[rank]['image_id']
        assert c.t.remote(rank, ['docker', 'inspect', old_names[rank]], check=False).returncode != 0
    controller_before = (c.F / 'controller-before.py').read_text()
    controller_after = (c.ROOT / 'image/csf/lifecycle/deepseek-ring-control.py').read_text()
    writer = '''import hashlib,os,shutil,sys
from pathlib import Path
p=Path('/usr/local/sbin/deepseek-ring-control'); expected=sys.argv[1]
assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
backup=p.with_name(p.name+'.before-csf-20261004'); assert not backup.exists()
shutil.copy2(p,backup)
tmp=p.with_name(p.name+'.csf-new');tmp.write_text(sys.stdin.read());tmp.chmod(0o755);os.chown(tmp,0,0);tmp.replace(p)
'''
    c.record('controller-upgrade', 0, ['python3', '-c', writer,
             hashlib.sha256(controller_before.encode()).hexdigest()], controller_after, admin=True)
    optimized_before = (c.F / 'optimized-controller-before.py').read_text()
    optimized_after = (c.ROOT / 'image/csf/lifecycle/optimized_vllm.py').read_text()
    optimized_writer = writer.replace('/usr/local/sbin/deepseek-ring-control',
                                      '/usr/local/lib/deepseek-ring/optimized_vllm.py')
    c.record('optimized-controller-upgrade', 0, ['python3', '-c', optimized_writer,
             hashlib.sha256(optimized_before.encode()).hexdigest()], optimized_after, admin=True)
    renamed_old, renamed_new, installed = [], [], False
    try:
        for rank in range(4):
            c.t.remote(rank, ['docker', 'rename', f'ds41-optimized-r{rank}', old_names[rank]])
            renamed_old.append(rank)
            c.t.remote(rank, ['docker', 'rename', documents[rank]['name'], f'ds41-optimized-r{rank}'])
            renamed_new.append(rank)
        p.bundle(0, p.CONFIG_DIR, tag, 'install',
                 {'optimized-specs.json': json.dumps(after, indent=2) + '\n'},
                 {'optimized-specs.json': hashlib.sha256(before_text.encode()).hexdigest()})
        installed = True
        c.record('permanent-up', 0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'up'])
        c.record('permanent-functional', 0, ['python3', '-u', c.REMOTE + '/tests/functional.py', 'http://127.0.0.1:8015/v1'])
        c.record('permanent-status', 0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'status'])
    except BaseException:
        if installed:
            p.bundle(0, p.CONFIG_DIR, tag, 'rollback')
        for rank in reversed(renamed_new):
            c.t.remote(rank, ['docker', 'rename', f'ds41-optimized-r{rank}', documents[rank]['name']])
        for rank in reversed(renamed_old):
            c.t.remote(rank, ['docker', 'rename', old_names[rank], f'ds41-optimized-r{rank}'])
        # Keep the verified CSF trial alive. The GX10 original shards have been
        # replaced, so blindly starting the old service cannot recover it.
        raise
    (c.F / 'deployment.json').write_text(json.dumps({
        'selected': 'csf-beta', 'healthy': True, 'backup_tag': tag,
        'endpoint': 'http://192.168.50.219:8015/v1', 'images': read('images.json'),
        'promoted_without_reload': True, 'unix_time': time.time()}, indent=2) + '\n')
    print('CSF promoted; serving retained without reload', flush=True)


if __name__ == '__main__':
    main()
