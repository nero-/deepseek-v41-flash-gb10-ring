#!/usr/bin/env python3
"""Re-ask B12X the GPQA Diamond items the client sleep cut off, plus the ones it got wrong.

Usage (LIL's venv python): rerun_gpqa.py SOURCE.json OUTPUT.json. Lost items are every
stalled or errored run in SOURCE (the Mac idle-slept at 21:35 UTC); wrong items are the
remaining incorrect ones. LIL 0.7.6's own dataset builder, streaming request and scorer
are used with the original settings (max_tokens 131072, temperature 1, top_p 1,
concurrency 16, 600 s stall watchdog), so each re-run is scored exactly as in the full run.
"""
import asyncio, dataclasses, datetime, hashlib, importlib.util, json, os, sys, time, urllib.request
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1]
REPO = RESULTS.parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import fleet  # noqa: E402

SELECTION = 'c87a397ccc4614c6f3fee59e566bb7599e7165c80e858bb12c84d78ef5e27775'
IMAGE = 'sha256:9f26f0b3718ccca889cfd93cb72e2165b6d4c11dd9dc93fe65f585883537f2db'
API = 'http://192.168.50.219:8015'
LIL076 = Path('/Users/jg/Agent/Diagnostics/deepseek-v41-flash-ring/decode-recovery-20261020/external-client/lil-0.7.6.py')
LIL076_SHA256 = 'c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553'


def identity():
    installed = hashlib.sha256(fleet.remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout.encode())
    assert installed.hexdigest() == SELECTION, 'installed selection is not B12X'
    def one(rank):
        info = json.loads(fleet.remote(rank, ['docker', 'inspect', f'ds41-optimized-r{rank}']).stdout)[0]
        assert info['Image'] == IMAGE and info['State']['Running'], (rank, info['State'])
        return {'rank': rank, 'id': info['Id']}
    with urllib.request.urlopen(API + '/health', timeout=5) as r:
        assert r.status == 200
    return fleet.parallel(one)


def main(source, output):
    assert hashlib.sha256(LIL076.read_bytes()).hexdigest() == LIL076_SHA256
    os.environ['LLM_BENCH_NO_UPDATE_CHECK'] = '1'
    spec = importlib.util.spec_from_file_location('lil076', LIL076)
    lil = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lil)

    original = json.loads(Path(source).read_text())
    runs = original['runs']
    lost = [r['item_id'] for r in runs if r['finish_reason'] == 'stalled' or r['error']]
    wrong = [r['item_id'] for r in runs if r['correct'] is False and r['item_id'] not in lost]
    profile = lil.BUILTIN_TEST_PROFILES['gpqa-diamond']
    items, meta = lil.load_benchmark_dataset_items('gpqa-diamond', profile)
    assert meta['sha256'].startswith('a8472c5a82ea2df8'), meta['sha256']
    by_id = {item['item_id']: item for item in items}
    todo = [('lost', by_id[i]) for i in lost] + [('wrong', by_id[i]) for i in wrong]

    containers = identity()
    started = time.time()

    async def run_all():
        gate = asyncio.Semaphore(16)
        async with lil.httpx.AsyncClient(timeout=lil.httpx.Timeout(None, connect=30.0)) as client:
            async def one(index, group, item):
                payload = {'model': 'DeepSeek-V4.1-Flash-TP4',
                           'messages': lil.build_user_prompt_messages(item['prompt'], ''),
                           'stream': True, 'stream_options': {'include_usage': True},
                           'max_tokens': 131072, 'temperature': 1.0, 'top_p': 1.0}
                async with gate:
                    run = await lil.stream_completion_stats_request(
                        client, API + '/v1/chat/completions', payload, index, 'rerun', 16, '', 'final_answer',
                        True, profile_config=profile, item=item, stall_timeout=600)
                print(datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%SZ'), group, item['item_id'],
                      run.score_label or run.finish_reason, run.completion_tokens, flush=True)
                return {'group': group, **dataclasses.asdict(run)}
            return await asyncio.gather(*(one(i, g, item) for i, (g, item) in enumerate(todo)))

    reruns = asyncio.run(run_all())
    unaffected = [r for r in runs if r['item_id'] not in lost]
    lost_runs = [r for r in reruns if r['group'] == 'lost']
    wrong_runs = [r for r in reruns if r['group'] == 'wrong']
    clean = all(r['ok'] and not r['error'] and r['finish_reason'] != 'stalled' for r in lost_runs)
    correct = sum(r['correct'] is True for r in unaffected) + sum(r['correct'] is True for r in lost_runs)
    summary = {
        'items': len(runs),
        'unaffected_items': len(unaffected),
        'unaffected_correct': sum(r['correct'] is True for r in unaffected),
        'lost_rerun': len(lost_runs),
        'lost_rerun_correct': sum(r['correct'] is True for r in lost_runs),
        'lost_rerun_all_clean': clean,
        'combined_correct': correct,
        'combined_accuracy': correct / len(runs),
        'wrong_rerun': len(wrong_runs),
        'wrong_rerun_now_correct': sum(r['correct'] is True for r in wrong_runs),
        'note': 'combined_accuracy merges only the lost items; the wrong-item re-asks are a repeat check, not a score',
    }
    with Path(output).open('x') as f:
        json.dump({'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source': str(source),
                   'dataset': meta, 'containers': containers, 'elapsed_seconds': time.time() - started,
                   'summary': summary, 'reruns': reruns}, f, indent=2)
        f.write('\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main(*sys.argv[1:])
