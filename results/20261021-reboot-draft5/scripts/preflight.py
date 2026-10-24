import json
from common import *
assert sha_selected()==SELECTION
prior=json.loads((MIA/'results/20261021-native/final-state.json').read_text())
def one(rank):
    row=host_snapshot(rank)
    live,old=json.loads(remote(rank,['docker','inspect',f'ds41-optimized-r{rank}',f'ds41-before-mia-five-r{rank}']).stdout)
    assert live['Image']==FALLBACK and live['Id']==prior['nodes'][rank]['container_id'] and live['State']['Running']
    assert old['Id']==prior['nodes'][rank]['qualified_four_draft_container_id'] and not old['State']['Running']
    row['canonical_id']=live['Id'];row['fallback_id']=old['Id'];row['canonical_args']=live['Args'];row['image']=live['Image']
    # Confirm the available host-administration route with a read-only command.
    args=['docker','run','--rm','--pull','never','--privileged','--pid=host','--network','none','--read-only','--memory','64m','--cpus','1','--entrypoint','nsenter',FALLBACK,'-t','1','-m','-u','-i','-n','--','/usr/bin/cat','/proc/sys/kernel/random/boot_id']
    assert remote(rank,args).stdout.strip()==row['boot_id']
    kernel=remote(rank,['journalctl','-k','--since','2026-10-21 11:42:00 UTC','--no-pager'])
    (RESULTS/f'pre-reboot-kernel-r{rank}.log').write_text(kernel.stdout)
    return row
save('preflight.json',{'selection_sha256':SELECTION,'nodes':parallel(one)})
print('Exact five-draft selection and fallback verified; graceful reboot route available on every node.',flush=True)
