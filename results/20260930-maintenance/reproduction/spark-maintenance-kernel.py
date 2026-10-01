import importlib.util,json,time
s=importlib.util.spec_from_file_location('m','/tmp/spark-maintenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for rank in [0,1,2,3]:
 for attempt in range(40):
  r=m.t.remote(rank,['true'],check=False)
  if r.returncode==0:break
  time.sleep(5)
 assert r.returncode==0,'SSH unavailable'
 code="""from pathlib import Path
import shutil,subprocess
p=Path('/etc/default/grub.d/zz-sparkring-kernel.cfg')
assert Path('/boot/vmlinuz-7.0.0-1019-nvidia').exists()
if p.exists():
 text=p.read_text();print(text)
 assert 'Retain kernel 6.17 for the authorized multi-node RoCE regression comparison.' in text
 backup=Path('/var/backups/deepseek-maintenance-20260930/zz-sparkring-kernel.cfg')
 assert not backup.exists()
 shutil.copy2(p,backup);p.unlink()
subprocess.run(['update-grub'],check=True)
text=Path('/boot/grub/grub.cfg').read_text()
assert 'set default="0"' in text
print('Restored automatic newest-installed-kernel selection')
"""
 r=m.record(rank,'kernel-selection',['python3','-c',code],True);assert r.returncode==0,(rank,r.stdout,r.stderr)
 print('KERNEL DEFAULT FIXED',rank,flush=True)
