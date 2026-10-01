import importlib.util,json,time
s=importlib.util.spec_from_file_location('m','/tmp/spark-maintenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for rank in range(4):
 script="""set -eu
umask 077
mkdir -p /var/backups/deepseek-maintenance-20260930
test ! -f /var/backups/deepseek-maintenance-20260930/packages.txt || exit 0
if test -f /var/backups/deepseek-maintenance-20260930/config.tar.gz; then mv /var/backups/deepseek-maintenance-20260930/config.tar.gz /var/backups/deepseek-maintenance-20260930/config.incomplete.tar.gz; fi
set -- /etc/apt /etc/NetworkManager /etc/netplan /etc/systemd/system /etc/docker /var/lib/dpkg/status
for p in /etc/deepseek-ring /usr/local/sbin/deepseek-ring-control; do if test -e "$p"; then set -- "$@" "$p"; fi; done
tar -czf /var/backups/deepseek-maintenance-20260930/config.tar.gz "$@"
cp /proc/sys/kernel/random/boot_id /var/backups/deepseek-maintenance-20260930/boot-id
uname -a > /var/backups/deepseek-maintenance-20260930/kernel.txt
dpkg-query -W > /var/backups/deepseek-maintenance-20260930/packages.txt
"""
 r=m.record(rank,'backup',['sh','-c',script],True);assert r.returncode==0,(rank,r.stderr)
r=m.record(0,'stop-serving',['sudo','-n','/usr/local/sbin/deepseek-ring-control','down']);assert r.returncode==0
# Canary first, then the remaining nodes; do not remove packages or old kernels.
for rank in [2,3,1,0]:
 unit='deepseek-os-maintenance-20260930'
 r=m.record(rank,'update-start',['systemd-run','--unit='+unit,'--property=Type=oneshot','/usr/bin/env','DEBIAN_FRONTEND=noninteractive','NEEDRESTART_MODE=a','/usr/bin/apt-get','-y','--no-remove','-o','Dpkg::Options::=--force-confold','dist-upgrade'],True);assert r.returncode==0,(rank,r.stderr)
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
