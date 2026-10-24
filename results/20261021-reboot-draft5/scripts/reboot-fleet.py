import json,time,subprocess
from common import *
assert not (RESULTS/'reboot-issued.json').exists()
before=json.loads((RESULTS/'preflight.json').read_text());assert sha_selected()==SELECTION
for action in ['down','mesh-off']:
    r=remote(0,['sudo','-n','/usr/local/sbin/deepseek-ring-control',action],check=False,timeout=240)
    save('control-'+action+'.json',{'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr});assert r.returncode==0
def stopped(rank):
    assert not remote(rank,['docker','ps','-q']).stdout.strip()
    assert not remote(rank,['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader']).stdout.strip()
    services={u:remote(rank,['systemctl','show',u,'-p','ActiveState','-p','UnitFileState']).stdout for u in UNITS}
    assert all('ActiveState=inactive' in v and ('UnitFileState=disabled' in v or 'UnitFileState=masked' in v) for v in services.values()),services
    return {'rank':rank,'services':services,'boot_id':remote(rank,['cat','/proc/sys/kernel/random/boot_id']).stdout.strip()}
save('stopped-before-reboot.json',{'nodes':parallel(stopped)})
def reboot(rank):
    command=['docker','run','--rm','--pull','never','--name',f'ds41-reboot-admin-r{rank}','--privileged','--pid=host','--network','none','--read-only','--memory','64m','--cpus','1','--entrypoint','nsenter',FALLBACK,'-t','1','-m','-u','-i','-n','--','/usr/bin/systemctl','reboot']
    try:
        r=remote(rank,command,check=False,timeout=30);return {'rank':rank,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    except subprocess.TimeoutExpired:return {'rank':rank,'ssh_timeout_during_reboot':True}
save('reboot-issued.json',{'nodes':parallel(reboot)})
print('All four graceful reboot commands issued; waiting for changed boot IDs.',flush=True)
deadline=time.monotonic()+900;ready={}
while time.monotonic()<deadline and len(ready)<4:
    def check(rank):
        if rank in ready:return
        try:
            row=host_snapshot(rank)
            if row['boot_id']!=before['nodes'][rank]['boot_id'] and row['running_containers']['returncode']==0:
                assert 'ActiveState=active' in row['clock']['stdout'] and 'UnitFileState=enabled' in row['clock']['stdout'] and '-lgc 0,2350' in row['clock']['stdout']
                assert not row['running_containers']['stdout'].strip(),row['running_containers']
                ready[rank]=row
        except (RuntimeError,subprocess.TimeoutExpired):pass
    parallel(check)
    print('BOOT_READY',sorted(ready),flush=True)
    if len(ready)<4:time.sleep(10)
assert len(ready)==4,ready
assert sha_selected()==SELECTION
save('post-reboot-hosts.json',{'nodes':[ready[r] for r in range(4)],'selection_sha256':SELECTION})
print('ALL_FOUR_REBOOTED; selection and persistent clock ceiling unchanged.',flush=True)
