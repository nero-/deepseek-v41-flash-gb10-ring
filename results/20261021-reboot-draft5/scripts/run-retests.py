"""One unchanged startup, reliability gates, then three isolated LIL screens."""
import datetime,json,re,subprocess,sys,time,urllib.request,hashlib
from common import *
CLIENT=Path('/Users/jg/Agent/Diagnostics/deepseek-v41-flash-ring/decode-recovery-20261020/external-client')
LABEL='reboot-draft5'
def capture_script(args,name,timeout=900):
    with (RESULTS/name).open('x') as log:
        r=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,text=True,timeout=timeout)
    assert r.returncode==0,(name,r.returncode)
def kernels(since,name):
    def one(rank):
        r=remote(rank,['journalctl','-k','--since','@'+str(int(since)),'--no-pager'])
        events=[x for x in r.stdout.splitlines() if re.search(r'out of memory|oom-kill|killed process|NVRM|Xid|page allocation failure',x,re.I)]
        return {'rank':rank,'events':events,'stdout':r.stdout}
    rows=parallel(one);save(name,{'since_epoch':since,'nodes':rows});return rows
def identity(name):
    before=json.loads((RESULTS/'preflight.json').read_text())
    def one(rank):
        live,old=json.loads(remote(rank,['docker','inspect',f'ds41-optimized-r{rank}',f'ds41-before-mia-five-r{rank}']).stdout)
        assert live['Id']==before['nodes'][rank]['canonical_id'] and live['Image']==FALLBACK and live['State']['Running'] and not live['State']['OOMKilled']
        assert live['Args']==before['nodes'][rank]['canonical_args']
        assert old['Id']==before['nodes'][rank]['fallback_id'] and not old['State']['Running']
        host=host_snapshot(rank);host.update(canonical_id=live['Id'],fallback_id=old['Id'],image=live['Image'])
        assert host['boot_id']==json.loads((RESULTS/'post-reboot-hosts.json').read_text())['nodes'][rank]['boot_id']
        return host
    nodes=parallel(one);assert sha_selected()==SELECTION
    with urllib.request.urlopen('http://192.168.50.219:8015/health',timeout=5) as r:assert r.status==200
    save(name,{'api_health':200,'configuration_sha256':SELECTION,'nodes':nodes})

assert (RESULTS/'post-reboot-hosts.json').exists()
assert not (RESULTS/'startup-result.json').exists()
assert sha_selected()==SELECTION
assert all(not remote(r,['docker','ps','-q']).stdout.strip() for r in range(4))
monitor_log=(RESULTS/'startup-monitor.log').open('x')
monitor=subprocess.Popen([sys.executable,'-u',str(RESULTS/'scripts/watch-startup.py'),LABEL],stdout=monitor_log,stderr=subprocess.STDOUT)
save('startup-monitor-process.json',{'pid':monitor.pid})
stop=RESULTS/f'startup-{LABEL}.stop'
try:
    print('STARTING_UNCHANGED_FIVE_DRAFT_SELECTION',flush=True)
    started=time.time()
    r=remote(0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','up'],check=False,timeout=2500)
    save('startup-result.json',{'returncode':r.returncode,'elapsed_seconds':time.time()-started,'stdout':r.stdout,'stderr':r.stderr});assert r.returncode==0
    identity('startup-identities.json')
    for rank in range(4):
        logs=remote(rank,['docker','logs',f'ds41-optimized-r{rank}'])
        (RESULTS/f'startup-r{rank}.log').write_text(logs.stdout+logs.stderr)
    print('API_READY; functional, loaded-clock and cold-retrieval gates starting.',flush=True)
    capture_script([sys.executable,'-u',str(MIA/'scripts/validate-api.py'),'--output',str(RESULTS/'functional')],'functional.log')
    capture_script([sys.executable,'-u',str(RESULTS/'scripts/load-observation.py'),LABEL],'loaded-clocks.log')
    capture_script([sys.executable,'-u',str(MIA/'scripts/cold-needle.py'),'--tokens','128000','--output',str(RESULTS/'cold-needle.json')],'cold-needle.log')
finally:
    stop.touch(exist_ok=True)
    try:monitor.wait(timeout=45)
    finally:monitor_log.close()
audit=json.loads((RESULTS/f'startup-{LABEL}-summary.json').read_text())
assert audit['first_api_healthy_epoch'] is not None
assert all(not n['ssh_failures'] and n['kernel_read_returncode']==0 for n in audit['nodes']),audit
assert not any(re.search(r'oom-kill|killed process|Xid',e,re.I) for n in audit['nodes'] for e in n['kernel_events']),audit
post=kernels(int(audit['first_api_healthy_epoch'])+1,'post-ready-kernel.json')
assert all(not n['events'] for n in post),post
save('validation-passed.json',{'functional_passes':20,'cold_retrieval':True,'clock_pass':True,'startup_clean':not any(n['kernel_events'] for n in audit['nodes']),
                             'startup_event_counts':[len(n['kernel_events']) for n in audit['nodes']]})
print('VALIDATION_PASS; diagnostic monitor stopped. Three matched screens begin.',flush=True)
harness=CLIENT/'lil-0.7.6.py';assert hashlib.sha256(harness.read_bytes()).hexdigest()=='c4c7eaed934d41b8e24f1bb9e81c635af599409276dbe580f14de5f837b09553'
for i in range(1,4):
    label=f'five-draft-run-{i}';dest=RESULTS/(label+'.json');assert not dest.exists()
    with urllib.request.urlopen('http://192.168.50.219:8015/health',timeout=5) as r:assert r.status==200
    command=[str(CLIENT/'.venv/bin/python'),str(harness),'--host',HOSTS[0],'--port','8015','--model','DeepSeek-V4.1-Flash-TP4','--no-hw-monitor','--display-mode','plain','--no-resume','--temperature','1','--concurrency','1,8,16','--contexts','8k,32k','--duration','20','--max-tokens','2048','--coding-peak','--output',str(dest)]
    save(label+'-command.json',{'argv':command,'one_reboot_three_repeats':True})
    print('BENCHMARK_START',i,datetime.datetime.now(datetime.timezone.utc).isoformat(),flush=True)
    start=time.time()
    import os
    with (RESULTS/(label+'.log')).open('x') as log:
        run=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'LLM_BENCH_NO_UPDATE_CHECK':'1'},timeout=1800)
    save(label+'-execution.json',{'returncode':run.returncode,'elapsed_seconds':time.time()-start});assert run.returncode==0
    data=json.loads(dest.read_text());assert len(data['results'])==6 and data['coding_peak']['runs_ok']==5
    for row in data['results']:
        assert row['aggregate_source']=='openai_continuous_usage'
        assert not any(row.get(k) for k in ['num_errors','underfilled','capacity_limited','warmup_timed_out','loop_detected','failure_reason']),row
    after=kernels(start,label+'-kernel.json');assert not any(n['events'] for n in after),after
    save(label+'-host-state.json',{'nodes':parallel(host_snapshot)})
    print('BENCHMARK_DONE',i,[(x['context_tokens'],x['concurrency'],round(x['aggregate_tps'],2)) for x in data['results']],flush=True)
capture_script([sys.executable,'-u',str(RESULTS/'scripts/load-observation.py'),'post-retests'],'post-retests-clocks.log')
identity('final-state.json')
save('three-runs-complete.json',{'completed_runs':3,'startup_clean':not any(n['kernel_events'] for n in audit['nodes']),'selected_drafts':5,'port':8015,'configuration_unchanged':True})
print('THREE_MATCHED_RUNS_COMPLETE; five drafts on 8015 and exact fallback preserved.',flush=True)
