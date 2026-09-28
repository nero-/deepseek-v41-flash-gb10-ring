#!/usr/bin/env python3
"""Promote a qualified, request-armed indexer receipt with rollback on failure.

Uses the site's existing SSH/Docker administration access. Root writes are
restricted to the selected plugin directory and configuration directory. The
checkpoint, upstream installation, stock containers and image are untouched.
Without --execute, validate the receipt and print the concrete installation.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

spec = importlib.util.spec_from_file_location('trial', Path(__file__).with_name('research-trial.py'))
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)
PLUGIN_DIR = '/usr/local/lib/deepseek-ring/plugins'
CONFIG_DIR = '/etc/deepseek-ring'
IMAGE = 'sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf'

BUNDLE_WRITER = r'''
import hashlib,json,shutil,sys
from pathlib import Path
root=Path('/bundle'); action,tag=sys.argv[1:3]; backup=root/tag
assert tag.startswith('.before-') and '/' not in tag
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def path(name):
 p=root/name
 if not p.resolve().is_relative_to(root) or p.is_symlink(): raise ValueError('Invalid bundle path')
 return p
if action=='install':
 doc=json.load(sys.stdin)
 for name,want in doc['expected'].items():
  if digest(path(name)) != want: raise RuntimeError('Existing file changed: '+name)
 backup.mkdir(mode=0o755)
 receipt={}
 for name,data in doc['files'].items():
  p=path(name); old=digest(p)
  receipt[name]={'old':old,'new':hashlib.sha256(data.encode()).hexdigest()}
  if old is not None:
   saved=backup/name; saved.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,saved)
 (backup/'receipt.json').write_text(json.dumps(receipt))
 for name,data in doc['files'].items():
  p=path(name); p.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
  temp=p.with_name(p.name+'.new-'+tag); temp.write_text(data); temp.chmod(0o644); temp.replace(p)
elif action=='rollback':
 marker=backup/'receipt.json'
 if marker.exists():
  receipt=json.loads(marker.read_text())
  for name,hashes in receipt.items():
   p=path(name)
   if digest(p) not in (hashes['old'],hashes['new']): raise RuntimeError('Refusing to overwrite changed file: '+name)
  for name,hashes in receipt.items():
   p=path(name)
   if hashes['old'] is None:
    p.unlink(missing_ok=True)
   else:
    temp=p.with_name(p.name+'.rollback-'+tag); shutil.copy2(backup/name,temp); temp.replace(p)
else: raise ValueError('Unknown bundle operation')
print(action+' complete')
'''

def bundle(rank, directory, tag, action, files=None, expected=None):
    assert directory in (PLUGIN_DIR, CONFIG_DIR)
    command = ['docker', 'run', '--rm', '-i', '--network', 'none', '--user', '0', '--read-only',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--mount', 'type=bind,src=' + directory + ',dst=/bundle',
               '--entrypoint', 'python3', IMAGE, '-c', BUNDLE_WRITER, action, tag]
    return trial.remote(rank, command, json.dumps({'files': files, 'expected': expected}) if action == 'install' else None)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('receipt', type=Path)
    p.add_argument('--profile', choices=['engram-adaptive4k-query-indexer', 'engram-adaptive4k-context-indexer'], required=True)
    p.add_argument('--execute', action='store_true')
    args = p.parse_args()
    receipt = args.receipt.resolve()
    statuses = json.loads((receipt / 'statuses.json').read_text())
    for name in ('functional', 'long-functional', 'mixed', 'mixed-integrity', 'cold-256k', 'cold-1m', 'tune'):
        assert statuses.get(name) == 0, 'Qualification missing or failed: ' + name
    cold = json.loads((receipt / 'cold-1m.json').read_text())
    assert cold['needle_pass'] and cold['cold_confirmed'] and cold['usage']['prompt_tokens'] >= 1_000_000
    long_checks = json.loads((receipt / 'long-functional.json').read_text())
    assert long_checks['all_long_prefills']
    def uncached(record):
        usage = record.get('usage') or {}
        cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
        return usage.get('prompt_tokens', 0) - cached if cached is not None else 0
    assert len(long_checks['requests']) == 7 and all(uncached(r) >= 65536 for r in long_checks['requests'])
    integrity = json.loads((receipt / 'mixed-integrity.json').read_text())
    assert integrity['rounds'] and all(r['summary']['needle_pass'] and not r['summary']['errors'] for r in integrity['rounds'])
    fresh = [q for r in integrity['rounds'] for q in r['requests'] if q['kind'] == 'prefill']
    assert len(fresh) >= 2 and all(uncached(r) >= 65536 for r in fresh)
    gate = json.loads((receipt / 'startup-gate.json').read_text())
    assert gate['real_request_before_guards'] and gate['startup_complete_before_real_request']
    guards = json.loads((receipt / 'guards-final.json').read_text())
    assert guards['enabled'] > 0 and guards['disabled'] == 0
    decision = json.loads((receipt / 'promotion-decision.json').read_text())
    assert decision['decision'] == 'selected' and decision['baseline_receipt']
    before_text = trial.remote(0, ['cat', CONFIG_DIR + '/optimized-specs.json']).stdout
    before = json.loads(before_text)
    assert before == json.loads((receipt / 'selected.json').read_text()), 'Selected configuration changed since trial'
    docs = json.loads((receipt / 'specs.json').read_text())
    assert len(docs) == 4
    module = 'dsv41_indexer_tp' if 'query-indexer' in args.profile else 'dsv41_context_indexer'
    modules = ['dsv41_adaptive_prefill', module]
    hashes = json.loads((receipt / 'plugin-sha256.json').read_text())
    files = {name + '.py': (receipt / (name + '.py')).read_text() for name in modules}
    for name, data in files.items():
        assert hashlib.sha256(data.encode()).hexdigest() == hashes[name]
    files['dsv41_local-0.1.dist-info/METADATA'] = 'Metadata-Version: 2.1\nName: dsv41-local\nVersion: 0.1\n'
    files['dsv41_local-0.1.dist-info/entry_points.txt'] = '[vllm.general_plugins]\n' + ''.join(f'{name} = {name}:register\n' for name in modules)
    for rank, doc in enumerate(docs):
        assert doc['image_id'] == IMAGE
        assert doc['command'] == before['specs'][rank]['command']
        assert doc['environment']['DSV41_INDEXER_ARM_ON_REQUEST'] == '1'
        assert set(doc['environment']['VLLM_PLUGINS'].split(',')) == {'b12x_loader', 'sparkring_status', *modules}
        if module == 'dsv41_indexer_tp':
            assert doc['environment']['DSV41_QUERY_VALUE_GUARD'] == '1'
        else:
            assert doc['environment']['DSV41_INDEXER_GUARD'] == 'local-scores'
        doc['name'] = f'ds41-optimized-r{rank}'
        doc['labels'] = {'io.local.deepseek-optimized': args.profile, 'io.local.rank': str(rank)}
        doc['security_opt'] = before['specs'][rank]['security_opt']
        for mount in doc['mounts']:
            if mount['target'] == '/opt/dsv41-local-plugins':
                assert mount['read_only']
                mount['source'] = PLUGIN_DIR
    document = {'profile': args.profile, 'source_receipt': str(receipt),
                'plugin_manifest': {n: hashlib.sha256(d.encode()).hexdigest() for n, d in files.items()}, 'specs': docs}
    print(json.dumps({'profile': args.profile, 'source_receipt': str(receipt), 'plugin_manifest': document['plugin_manifest'],
                      'configuration': CONFIG_DIR + '/optimized-specs.json', 'execute': args.execute}, indent=2), flush=True)
    if not args.execute:
        return
    # Verify the exact helper runtime and existing files before stopping the
    # qualified service or removing any old selected container.
    reader = """import hashlib,json,sys
from pathlib import Path
root=Path('/bundle')
for name,want in json.load(sys.stdin).items():
 p=root/name
 assert p.stat().st_uid==0 and not p.stat().st_mode & 0o022
 assert hashlib.sha256(p.read_bytes()).hexdigest()==want
print('writer-ready')
"""
    trial.parallel(lambda rank: trial.remote(rank, ['docker', 'run', '--rm', '-i', '--network', 'none',
        '--user', '0', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--mount', 'type=bind,src=' + PLUGIN_DIR + ',dst=/bundle,readonly',
        '--entrypoint', 'python3', IMAGE, '-c', reader], json.dumps(before['plugin_manifest'])))
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    tag = '.before-' + stamp
    record = trial.RESULTS / (stamp + '-selection')
    record.mkdir()
    (record / 'selected.json').write_text(before_text)
    (record / 'specs.json').write_text(json.dumps(document, indent=2))
    trial.stop()
    trial.remote(0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'down'])
    def remove_old(rank):
        name = f'ds41-optimized-r{rank}'
        info = json.loads(trial.remote(rank, ['docker', 'inspect', name]).stdout)[0]
        assert not info['State']['Running'] and info['Image'] == IMAGE
        assert info['Config']['Labels']['io.local.deepseek-optimized'] == before['profile']
        trial.remote(rank, ['docker', 'rm', name])
    try:
        trial.parallel(remove_old)
        trial.parallel(lambda rank: bundle(rank, PLUGIN_DIR, tag, 'install', files, before['plugin_manifest']))
        bundle(0, CONFIG_DIR, tag, 'install', {'optimized-specs.json': json.dumps(document, indent=2) + '\n'},
               {'optimized-specs.json': hashlib.sha256(before_text.encode()).hexdigest()})
        result = trial.remote(0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'up'])
        (record / 'startup.log').write_text(result.stdout + result.stderr)
    except BaseException:
        # Also restore the previous service if promotion is interrupted.
        # Only remove newly selected containers. An old container left by a
        # failed removal retains its original recorded identity for rollback.
        for rank in range(4):
            name = f'ds41-optimized-r{rank}'
            result = trial.remote(rank, ['docker', 'inspect', name], check=False)
            if result.returncode == 0 and json.loads(result.stdout)[0]['Config']['Labels'].get('io.local.deepseek-optimized') == args.profile:
                trial.remote(rank, ['docker', 'stop', '--time', '15', name])
                trial.remote(rank, ['docker', 'rm', name])
        trial.parallel(lambda rank: bundle(rank, PLUGIN_DIR, tag, 'rollback'))
        bundle(0, CONFIG_DIR, tag, 'rollback')
        result = trial.remote(0, ['sudo', '-n', '/usr/local/sbin/deepseek-ring-control', 'up'])
        (record / 'rollback.log').write_text(result.stdout + result.stderr)
        raise
    (record / 'deployment.json').write_text(json.dumps({'profile': args.profile, 'receipt': str(receipt),
        'plugin_manifest': document['plugin_manifest'], 'backup_directory_name': tag, 'startup_health_passed': True}, indent=2))
    print('SELECTED', args.profile, record, flush=True)

if __name__ == '__main__':
    main()
