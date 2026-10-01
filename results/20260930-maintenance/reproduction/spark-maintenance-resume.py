import importlib.util,json,time
s=importlib.util.spec_from_file_location('m','/tmp/spark-maintenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
# Canary first, then the remaining nodes; do not remove packages or old kernels.
for rank in [2,3,1,0]:
 unit='deepseek-os-maintenance-20260930'
 current=m.root(rank,['systemctl','show',unit,'--property=LoadState']);assert current.returncode==0
 if 'LoadState=not-found' in current.stdout:
  r=m.record(rank,'update-start',['systemd-run','--no-block','--unit='+unit,'--property=Type=oneshot','/usr/bin/env','DEBIAN_FRONTEND=noninteractive','NEEDRESTART_MODE=l','/usr/bin/apt-get','-y','--no-remove','-o','Dpkg::Options::=--force-confold','dist-upgrade'],True)
  if r.returncode!=0:
   check=m.root(rank,['systemctl','show',unit,'--property=LoadState']);assert 'LoadState=loaded' in check.stdout,(rank,r.stderr)
 print('UPDATING',rank,flush=True)
 while True:
  r=m.root(rank,['systemctl','show',unit,'--property=ActiveState,SubState,Result,ExecMainStatus']);state=dict(x.split('=',1) for x in r.stdout.splitlines() if '=' in x)
  if state.get('ActiveState') not in ['activating','active','reloading']:break
  time.sleep(5)
 m.record(rank,'update-journal',['journalctl','-u',unit,'--no-pager'],True)
 (m.F/f'update-result-r{rank}.json').write_text(json.dumps(state,indent=2))
 assert state.get('Result')=='success' and state.get('ExecMainStatus')=='0',state
 print('UPDATED',rank,flush=True)
 m.record(rank,'post-update-audit',['sh','-c','dpkg --audit; test ! -f /var/run/reboot-required || cat /var/run/reboot-required; apt-get --simulate dist-upgrade'],True)
