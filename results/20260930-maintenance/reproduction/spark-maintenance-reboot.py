import importlib.util,json,time
s=importlib.util.spec_from_file_location('m','/tmp/spark-maintenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for rank in range(4):
 j=json.loads((m.F/f'update-result-r{rank}.json').read_text());assert j['Result']=='success' and j['ExecMainStatus']=='0'
for rank in [2,3,1,0]:
 old=m.t.remote(rank,['cat','/proc/sys/kernel/random/boot_id']).stdout.strip()
 r=m.record(rank,'reboot-start',['systemd-run','--no-block','--on-active=3s','--unit=deepseek-maintenance-reboot-20260930','/usr/bin/systemctl','reboot'],True);assert r.returncode==0
 print('REBOOTING',rank,flush=True);deadline=time.monotonic()+600
 while time.monotonic()<deadline:
  time.sleep(10);r=m.t.remote(rank,['cat','/proc/sys/kernel/random/boot_id'],check=False)
  if r.returncode==0 and r.stdout.strip()!=old:
   new=r.stdout.strip();break
 else:raise RuntimeError('Reboot timeout rank '+str(rank))
 # Wait for the driver and Docker, then record boot/fabric health.
 for attempt in range(30):
  r=m.t.remote(rank,['sh','-c','nvidia-smi -L && docker info --format "{{.ServerVersion}}"'],check=False)
  if r.returncode==0:break
  time.sleep(5)
 assert r.returncode==0,(rank,r.stderr)
 (m.F/f'reboot-result-r{rank}.json').write_text(json.dumps({'old_boot_id':old,'new_boot_id':new,'driver_docker':r.stdout},indent=2))
 r=m.record(rank,'post-boot',['sh','-c','uname -r; nvidia-smi --query-gpu=driver_version --format=csv,noheader; systemctl --failed --no-pager; ip -brief link; test ! -e /var/run/reboot-required']);assert r.returncode==0
 assert r.stdout.splitlines()[0]=='7.0.0-1019-nvidia',r.stdout
 print('RETURNED',rank,flush=True)
r=m.record(0,'start-serving',['sudo','-n','/usr/local/sbin/deepseek-ring-control','up']);assert r.returncode==0,(r.stdout,r.stderr)
print('SERVING HEALTHY',flush=True)
