import importlib.util,json
from pathlib import Path
s=importlib.util.spec_from_file_location('m','/tmp/spark-maintenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
unit=(m.ROOT/'host/systemd/gb10-gpu-clock-cap.service').read_text()
writer="from pathlib import Path;import sys;p=Path('/etc/systemd/system/gb10-gpu-clock-cap.service');s=sys.argv[1];assert not p.exists() or p.read_text()==s,'Existing unit differs';p.write_text(s);p.chmod(0o644)"
for rank in range(4):
 for label,args in [('install',['python3','-c',writer,unit]),('verify',['systemd-analyze','verify','/etc/systemd/system/gb10-gpu-clock-cap.service']),('reload',['systemctl','daemon-reload']),('enable',['systemctl','enable','--now','gb10-gpu-clock-cap.service']),('status',['systemctl','show','gb10-gpu-clock-cap.service','-p','ActiveState','-p','SubState','-p','UnitFileState','-p','ExecMainStatus']),('clock',['nvidia-smi','-q','-d','CLOCK'])]:
  r=m.record(rank,'default-2350-'+label,args,True);assert r.returncode==0,(rank,label,r.stdout,r.stderr)
  if label=='status':assert 'ActiveState=active' in r.stdout and 'UnitFileState=enabled' in r.stdout and 'ExecMainStatus=0' in r.stdout
 print(rank,'2350 cap applied and boot service enabled',flush=True)
