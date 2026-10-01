import importlib.util,json
s=importlib.util.spec_from_file_location('m','/tmp/spark-maintenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for rank in range(4):
 r=m.record(rank,'network-wait-before',['systemctl','is-enabled','NetworkManager-wait-online.service'])
 assert r.stdout.strip() in ['enabled','disabled'],r.stdout
 r=m.record(rank,'network-wait-enable',['systemctl','enable','--now','NetworkManager-wait-online.service'],True);assert r.returncode==0,(rank,r.stderr)
 r=m.record(rank,'network-wait-after',['systemctl','show','NetworkManager-wait-online.service','--property=ActiveState,SubState,Result,UnitFileState']);print(rank,r.stdout,flush=True)
