"""Reconcile the completed retest without erasing historical trial evidence."""
from pathlib import Path
import datetime,hashlib,json,shutil,zipfile
from common import RESULTS,REPO,MIA
assert (RESULTS/'three-runs-complete.json').exists()
data=json.loads((RESULTS/'summary.json').read_text());cells={(s['context_tokens'],s['concurrency']):s for s in data['cells']}
startup=json.loads((RESULTS/'startup-identities.json').read_text());audit=json.loads((RESULTS/'startup-reboot-draft5-summary.json').read_text())
assert data['startup_clean']
rates=lambda c:' / '.join(f"{cells[c,n]['median']:.1f}" for n in [1,8,16])
headline=f"Three post-reboot five-draft screens completed. Median C1/C8/C16: {rates(8192)} tok/s at 8K and {rates(32768)} at 32K."
p=REPO/'results/deployment.json';d=json.loads(p.read_text());d['latest_validation']='results/20261021-reboot-draft5/REPORT.md'
d['host_memory'].update(observed_startup_used_gib=startup['nodes'][0]['used_gib'],observed_startup_available_gib=startup['nodes'][0]['available_gib'],observed_qualification_peak_gib=audit['nodes'][0]['peak_used_gib'],receipt='results/20261021-reboot-draft5/startup-reboot-draft5-summary.json',peak_scope='Sampled post-reboot startup plus API/loaded-clock/cold-retrieval validation. No NVIDIA allocation events or SSH failures observed.')
d['decode_tuning']['selected'].update(qualification_complete=False,focused_retest_passed=True,startup_clean_after_reboot=True,qualification_limitation='One clean post-reboot startup and three focused screens passed. Full-grid and independent reboot replication not performed; earlier allocation-warning root cause remains unproven.')
d['operational_state'].update(state='serving-five-drafts-after-clean-reboot-and-three-passed-retests',recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),next_investigation='None queued; broader tuning remains paused.',active_retest_receipt=None,latest_recovery_receipt='results/20261021-reboot-draft5/final-state.json',final_state_receipt='results/20261021-reboot-draft5/final-state.json',report='results/20261021-reboot-draft5/REPORT.md',startup_head_system_used_gib=startup['nodes'][0]['used_gib'],post_reboot_startup_clean=True,post_reboot_retests_completed=3,active_retest=False,performance_note=headline)
d['operational_state']['historical_mia_closing_control_completed']=d['operational_state'].pop('closing_vllm5_control_completed',False)
p.write_text(json.dumps(d,indent=2)+'\n')
p=REPO/'README.md';s=p.read_text();a=s.index('> **Current state,');b=s.index('> **Stock-native',a)
s=s[:a]+f'''> **Current state, October 21 UTC:** five-draft vLLM serves on 8015 with 20 GiB
> KV. A coordinated four-node reboot cleared the observed allocation warnings
> on this startup. Three focused repeats passed: median 8K C1/C8/C16
> **{rates(8192)} tok/s**; 32K **{rates(32768)}**. Exact fallback preserved.
> [Reboot protocol, individual runs and limitations](results/20261021-reboot-draft5/REPORT.md).

'''+s[b:]
s=s.replace('Startup allocation warnings remain unresolved.','The post-reboot startup and three focused repeats logged no allocation warnings.')
s=s.replace('**117.328 GiB immediately after the final recovery**',f"**{startup['nodes'][0]['used_gib']:.3f} GiB immediately after the reboot recovery**")
s=s.replace('**4.360 GiB available**',f"**{startup['nodes'][0]['available_gib']:.3f} GiB available**")
s=s.replace('(startup qualification incomplete)','(clean reboot and three focused retests passed)');p.write_text(s)
p=REPO/'OPERATIONS.md';s=p.read_text();a=s.index('**Current selection,');b=s.index('**Stock-native source FLARE',a)
s=s[:a]+f'''**Current selection, October 21 UTC:** five-draft vLLM with 20 GiB KV serves
on 8015, configuration `c87a397ccc4614c6f3fee59e566bb7599e7165c80e858bb12c84d78ef5e27775`.
The user requested a coordinated four-node reboot and three matched retests.
The unchanged configuration passed a clean startup, 20 API checks, loaded-clock
checks, cold 122,280-token retrieval and all three focused screens. No NVIDIA
allocation warning, Linux OOM kill, Xid or SSH probe failure was observed in
startup/validation; each timed-run kernel check was clear. {headline}

The earlier allocation warnings are historical evidence. One clean boot does
not establish their root cause or guarantee they cannot recur. Preserve the
0-2350 MHz ceiling and monitor memory/kernel events during necessary recovery.
The qualified four-draft fallback remains `ds41-before-mia-five-rN`; its unused
exact restore helper is `../DS41-sglang-mia/scripts/vllm-five.py restore`.
Mia was not promoted and its payload was retired. No retest or experiment is
active. [Current evidence](results/20261021-reboot-draft5/REPORT.md).
Historical restoration snapshots below do not override this latest state.

'''+s[b:]
s=s.replace('**117.328 GiB used**',f"**{startup['nodes'][0]['used_gib']:.3f} GiB used**").replace('**4.360 GiB available**',f"**{startup['nodes'][0]['available_gib']:.3f} GiB available**")
s=s.replace('NVIDIA allocation warnings remained unresolved.','The post-reboot startup had no allocation warnings.')
s=s.replace('not a claim of performance improvement or clean startup.','a policy choice; the latest clean startup and focused retest evidence is linked above.');p.write_text(s)
p=REPO/'RESULTS.md';s=p.read_text();where=s.index('## October 21 stock-native')
s=s[:where]+f'''## October 21 five-draft reboot and three-run retest

The same five-draft image/configuration was restarted after a coordinated reboot
of all four hosts. Startup/functional validation and all timed-run kernel checks
were clear. No clock, KV, checkpoint, image or serving-setting change was made.

| Context | Median C1 | Median C8 | Median C16 |
| --- | --- | --- | --- |
| 8K | {cells[8192,1]['median']:.2f} | {cells[8192,8]['median']:.2f} | {cells[8192,16]['median']:.2f} |
| 32K | {cells[32768,1]['median']:.2f} | {cells[32768,8]['median']:.2f} | {cells[32768,16]['median']:.2f} |

Three repeated focused screens on one boot, not three independent boot samples.
All 18 cells passed request/error/loop/capacity checks. The earlier low five-draft
run is retained; it is not representative of these post-reboot measurements.
The root cause of the earlier startup/performance difference remains unproven.
[All runs, ranges, step counters and limits](results/20261021-reboot-draft5/REPORT.md).

'''+s[where:];p.write_text(s)
p=REPO.parent/'SKILL.md';s=p.read_text();a=s.index('## Authorized reboot and five-draft retest');b=s.index('## Stock-native FLARE',a)
s=s[:a]+f'''## Current five-draft selection after clean reboot and retests - October 21 UTC

The user's coordinated four-node reboot and three matched five-draft retests are
complete. {headline}
Read [the retest report](deepseek-v41-flash-ring/results/20261021-reboot-draft5/REPORT.md)
and its final-state.json before further fleet work. No retest or experiment is
active; the broader tuning campaign remains paused.

Five-draft vLLM serves on 8015 with the same stock 1017 checkpoint, 20 GiB KV,
16.34M logical tokens, 0-2350 MHz ceiling, image `9f26f0b3718cc...` and selection
`c87a397ccc4614c6f3fee59e566bb7599e7165c80e858bb12c84d78ef5e27775`.
Canonical IDs remain `ds41-optimized-rN`. Graphs cover 5*n/6*n through 96;
the old C1 proposal cap is removed. The post-reboot startup, 20 API checks,
loaded-clock checks, cold 122,280-token retrieval and three screens passed.
No allocation warning/OOM kill/Xid or SSH probe failure was observed in that
startup/validation window, and all timed-run kernel checks were clear.
The earlier warnings remain historical evidence; their cause and recurrence
across future boots are unproven. Do not use one healthy API check as complete
startup qualification. Normal recovery retains this five-draft selection.

The exact qualified four-draft fallback remains stopped as `ds41-before-mia-five-rN`,
selection `d86c7e0725ef...`. The unused `DS41-sglang-mia/scripts/vllm-five.py restore`
is available for actual fallback recovery. Do not replay consumed FLARE/tuning,
headroom, retirement, or reboot actions. The three-run retest has fresh receipts
and is consumed. No further reboot or tuning is queued.

Mia was not promoted. Its twelve containers, four rejected 19 GiB containers,
candidate images and 188.83 GiB packed payload were retired; stock weights,
source, useful compiler caches and fallback identities remain. Its report is
historical and its developer bundle includes a post-reboot retest addendum.

'''+s[b:]
s=s.replace('(startup qualification incomplete): official','(three focused post-reboot retests passed): official')
s=s.replace('The final five-draft recovery started at 117.328 GiB used\n  (4.360 GiB available), with unresolved NVIDIA allocation warnings.',f"The post-reboot five-draft recovery started at {startup['nodes'][0]['used_gib']:.3f} GiB used\n  ({startup['nodes'][0]['available_gib']:.3f} GiB available), without observed allocation warnings.")
p.write_text(s)
p=MIA/'README.md';s=p.read_text();s=s.replace('# Mia SGLang stock-checkpoint trial: completed\n\n','# Mia SGLang stock-checkpoint trial: completed\n\n**Later reboot retest:** the same five-draft vLLM configuration passed a clean\nstartup and three focused repeats after a coordinated fleet reboot. Read\n[the addendum](../deepseek-v41-flash-ring/results/20261021-reboot-draft5/REPORT.md)\nfor current performance and state. The Mia trial-close findings below are historical.\n\n',1);p.write_text(s)
p=MIA/'HANDOFF.md';s=p.read_text();a=s.index('**Later authorized work in progress:**');b=s.index('Read `../SKILL.md`',a)
s=s[:a]+'''**Latest state:** the authorized four-node reboot and three five-draft retests
are COMPLETE. The exact same selection is serving on 8015, with a clean observed
startup and all three focused screens passed. Read
`../deepseek-v41-flash-ring/results/20261021-reboot-draft5/REPORT.md` and
`final-state.json` for current evidence. No process or benchmark remains active.
The Mia trial-close incident and restoration snapshot below is historical;
its earlier unresolved warnings did not recur in the post-reboot audit.

'''+s[b:];p.write_text(s)
p=REPO.parent/'DS41-flare-source/HANDOFF.md';s=p.read_text();s=s.replace('on 8015 with unresolved allocation warnings and the exact qualified four-draft\nfallback preserved.','on 8015 with the exact qualified four-draft fallback preserved. A later fleet\nreboot produced a clean startup and three passed five-draft retests; see the\n[current retest report](../deepseek-v41-flash-ring/results/20261021-reboot-draft5/REPORT.md).');p.write_text(s)
# Keep the historical PDF/Markdown unchanged; add the new evidence to the bundle.
out=MIA/'output/pdf';shutil.copyfile(RESULTS/'REPORT.md',out/'Reboot-retest-addendum.md')
shutil.copyfile(RESULTS/'summary.json',out/'Reboot-retest-summary.json')
shutil.copyfile(RESULTS/'decode-measurements.csv',out/'Reboot-retest-decode.csv')
raw_manifest=[]
for i in range(1,4):
    src=RESULTS/f'five-draft-run-{i}.json';raw=json.loads(src.read_text())
    exported={k:raw[k] for k in ['metadata','results','prefill','coding_peak','methodology']}
    exported['metadata']['server']='<MANAGEMENT_HOST>:8015'
    exported['export_note']='Selected raw sections; management host redacted; measurements unchanged.'
    dest=out/f'reboot-five-draft-run-{i}.json';dest.write_text(json.dumps(exported,indent=2)+'\n')
    raw_manifest.append({'original_file':src.name,'original_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'export_file':dest.name,'export_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
(out/'Reboot-retest-validation.json').write_text(json.dumps({'raw_results':raw_manifest,'configuration_sha256':d['configuration_sha256'],
 'api_health':200,'functional_passes':20,'cold_prompt_tokens':122280,'startup_event_counts':[len(n['kernel_events']) for n in audit['nodes']],
 'startup_ssh_failures':[len(n['ssh_failures']) for n in audit['nodes']],'benchmark_kernel_checks_clear':True,'completed_runs':3,
 'preserved_original_qualified_fallback':True,'one_reboot_three_same_startup_repeats':True},indent=2)+'\n')
(out/'BUNDLE-README.txt').write_text('Pinned local deployment study. The original Mia report is historical and explicitly lacks a closing vLLM control. A later coordinated reboot and three unchanged five-draft retests recovered throughput and passed clean startup checks; read Reboot-retest-addendum.md before interpreting the earlier low baseline. This follow-up did not rerun Mia and does not establish a causal reboot or engine effect. PDF/Markdown, CSVs and selected raw evidence are retained. Private recovery specifications and credentials are excluded. Reports have not been submitted upstream.\n')
items=[p for p in out.iterdir() if p.suffix in ['.pdf','.md','.csv','.svg','.png','.json'] or p.name=='BUNDLE-README.txt']
(out/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(items)))
with zipfile.ZipFile(out/'Mia-developer-feedback.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in items+[out/'SHA256SUMS.txt']:z.write(p,p.name)
with zipfile.ZipFile(out/'Mia-developer-feedback.zip') as z:
    assert z.testzip() is None
    assert all(z.read(name)==(out/name).read_bytes() for name in z.namelist())
print(headline)
print('Current operating docs reconciled; historical developer bundle now includes the retest addendum.')
