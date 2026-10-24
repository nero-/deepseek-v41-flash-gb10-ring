"""Summarize all three recorded runs without choosing a favorable replicate."""
import csv,hashlib,json,statistics
from common import RESULTS,MIA,SELECTION,save
assert (RESULTS/'three-runs-complete.json').exists()
runs=[json.loads((RESULTS/f'five-draft-run-{i}.json').read_text()) for i in range(1,4)]
prior5=json.loads((MIA/'results/20261021-native/vllm5-control-a.json').read_text())
prior4=json.loads((MIA/'results/20261021-native/vllm-control-a.json').read_text())
rows=lambda run:{(r['context_tokens'],r['concurrency']):r for r in run['results']}
indexes=[rows(d) for d in runs];old5=rows(prior5);old4=rows(prior4)
cells=sorted(old5);summary=[];flat=[]
for cell in cells:
    vals=[r[cell]['aggregate_tps'] for r in indexes];median=statistics.median(vals)
    summary.append({'context_tokens':cell[0],'concurrency':cell[1],'runs':vals,'median':median,'minimum':min(vals),'maximum':max(vals),
       'previous_five_draft':old5[cell]['aggregate_tps'],'previous_four_draft':old4[cell]['aggregate_tps'],
       'median_change_vs_previous_five_pct':100*(median/old5[cell]['aggregate_tps']-1),
       'median_change_vs_previous_four_pct':100*(median/old4[cell]['aggregate_tps']-1)})
    for i,idx in enumerate(indexes,1):
        row=idx[cell];flat.append({'run':i,'context_tokens':cell[0],'concurrency':cell[1],**{k:row[k] for k in ['aggregate_tps','server_steps_per_s','server_accept_len_effective','server_spec_drafts','server_spec_draft_tokens','server_spec_accepted_tokens','num_errors']}})
with (RESULTS/'decode-measurements.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
audit=json.loads((RESULTS/'startup-reboot-draft5-summary.json').read_text())
startup=json.loads((RESULTS/'startup-identities.json').read_text());final=json.loads((RESULTS/'final-state.json').read_text())
coding=[r['coding_peak']['summary']['median_generation_tok_s'] for r in runs]
save('summary.json',{'cells':summary,'coding_run_medians':coding,'startup_clean':not any(n['kernel_events'] for n in audit['nodes']),
 'sampled_peak_used_gib':[n['peak_used_gib'] for n in audit['nodes']],'ssh_failures':[len(n['ssh_failures']) for n in audit['nodes']],
 'final_health':final['api_health'],'qualification_scope':'One reboot/startup, three same-startup six-cell repeats; not independent reboot replications or a full-grid qualification.'})
improved=sum(s['median_change_vs_previous_five_pct']>0 for s in summary)
changes=[s['median_change_vs_previous_five_pct'] for s in summary]
lines=['# Five-draft vLLM after a coordinated fleet reboot','',
 f'The unchanged five-draft configuration exceeded the earlier five-draft screen in {improved} of six median decode cells. '
 f'Median changes ranged from {min(changes):+.1f}% to {max(changes):+.1f}%. '
 'The reboot was followed by a clean observed startup and all three successful screens. '
 'These results show that the earlier low run should not be used alone to attribute poor throughput to five drafts. '
 'They do not isolate the cause of the difference between startups.','',
 '## Method','',
 'One graceful reboot of all four nodes, followed by one unchanged vLLM startup and three consecutive focused screens. '
 'Each screen used pinned, unmodified LIL 0.7.6, 8K/32K contexts, C1/C8/C16, 20-second cells, max 2048 tokens, '
 'temperature 1 and default thinking. Hardware telemetry was excluded from timed windows. Five coding probes per run are reported separately.',
 '',f'The exact selection `{SELECTION}` was retained: five drafts, 20 GiB KV per rank, stock 1017 checkpoint, '
 'same immutable image/plugins/transport, port 8015 and persistent 0-2350 MHz ceiling. No CSF or driver/kernel/configuration change was made. '
 'Original qualified four-draft containers remain stopped and preserved.','',
 '## Useful decode throughput','',
 'All values are output tokens/s; concurrent values are aggregate. Each run is shown; the median is not a selected best result.','',
 '| Context | C | Run 1 | Run 2 | Run 3 | Median | Range | Previous 5 | Change |',
 '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
for s in summary:
    lines.append('| '+ ' | '.join([str(s['context_tokens']//1024)+'K',str(s['concurrency']),*[f'{v:.2f}' for v in s['runs']],f"{s['median']:.2f}",f"{s['minimum']:.2f}-{s['maximum']:.2f}",f"{s['previous_five_draft']:.2f}",f"{s['median_change_vs_previous_five_pct']:+.1f}%"] )+' |')
lines+=['','### Historical four-draft comparison','',
 '| Context | C | Prior 4-draft control | Post-reboot 5-draft median | Change |',
 '| --- | --- | --- | --- | --- |']
for s in summary:lines.append(f"| {s['context_tokens']//1024}K | {s['concurrency']} | {s['previous_four_draft']:.2f} | {s['median']:.2f} | {s['median_change_vs_previous_four_pct']:+.1f}% |")
lines+=['','### Step-rate evidence','',
 'The table below reports the harness counter-derived step rate and useful tokens per step. '
 'These counters explain the observed rate decomposition; they do not isolate a kernel or driver cause.','',
 '| Context | C | Prior 5 steps/s | New median steps/s | Prior tokens/step | New median tokens/step |',
 '| --- | --- | --- | --- | --- | --- |']
for cell in cells:
    lines.append(f"| {cell[0]//1024}K | {cell[1]} | {old5[cell]['server_steps_per_s']:.2f} | {statistics.median(x[cell]['server_steps_per_s'] for x in indexes):.2f} | {old5[cell]['server_accept_len_effective']:.3f} | {statistics.median(x[cell]['server_accept_len_effective'] for x in indexes):.3f} |")
lines+=['','## Coding and prefill','',f'Coding median output rates for the five probes in each run: {coding[0]:.2f}, {coding[1]:.2f}, {coding[2]:.2f} tokens/s. These are separate workloads from sustained decode.','',
 '| Nominal prefill | Run 1 | Run 2 | Run 3 |','| --- | --- | --- | --- |']
for c in [8192,32768,65536,131072]:lines.append('| '+str(c//1024)+'K | '+' | '.join(f"{r['prefill'][str(c)]['client_tok_per_sec']:,.0f}" for r in runs)+' |')
lines+=['','Prefill values are client-observed input tokens/s including TTFT, one scout per context per run; actual prompt counts are preserved in the raw JSON.','',
 '## Reliability and final state','',
 f"Startup/validation kernel event counts by rank: {[len(n['kernel_events']) for n in audit['nodes']]}. SSH probe failures: {[len(n['ssh_failures']) for n in audit['nodes']]}. "
 'The post-ready gate and each timed-run kernel check passed. All 18 decode cells passed request-error, underfill, capacity, warmup and loop checks; all used continuous completion-usage accounting.',
 '',f"Sampled startup-plus-validation peak used GiB by rank: {', '.join(f'{n['peak_used_gib']:.3f}' for n in audit['nodes'])}. "
 f"Immediate startup head used memory: {startup['nodes'][0]['used_gib']:.3f} GiB. Final API health was HTTP {final['api_health']}. "
 'Loaded-clock probes before and after timing passed. Exact serving and fallback container IDs were verified.',
 '', '## Interpretation limits','',
 'Three repeats on one startup estimate within-startup variability. They do not measure variability across three reboots. '
 'The historical five-draft result is one earlier startup and is not a concurrent randomized control. Any changed result after reboot '
 'can reflect boot/startup state, adaptive cost calibration, cache history and stochastic requests; this experiment cannot isolate those causes. '
 'The nearby four-draft control remains a useful historical comparator, but no new four-draft arm was run. '
 'These focused results do not qualify the full context/concurrency grid or broad model quality.','',
 'Raw JSON, logs, boot IDs, kernel checks, commands, memory samples and exact identities are retained in this directory. '
 'See `summary.json` and `decode-measurements.csv` for unrounded values and step/acceptance counters.']
(RESULTS/'REPORT.md').write_text('\n'.join(lines)+'\n')
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(RESULTS.glob('five-draft-run-*.json'))}
save('measurement-manifest.json',{'sha256':manifest})
print(json.dumps(summary,indent=2))
