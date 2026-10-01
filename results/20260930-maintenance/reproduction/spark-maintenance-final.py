import importlib.util,json,time
s=importlib.util.spec_from_file_location('m','/tmp/spark-maintenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for name in ['stock','2300','stock-repeat','2300-repeat']:
 j=json.loads((m.F/(name+'-screen.json')).read_text())
 assert all(not any(r.get(k) for k in ['loop_detected','capacity_limited','failure_reason','num_errors','warmup_timed_out']) for r in j['results'])
for rank in range(4):
 r=m.record(rank,'final-stock-clocks',['nvidia-smi','-rgc'],True);assert r.returncode==0
 code="import hashlib,json,os;from pathlib import Path\nassert os.environ.get('VLLM_USE_FASTOKENS','0')=='0'\nm=json.loads(Path('/opt/kk926/manifest.json').read_text())\nfor name,pin in m['files'].items():assert hashlib.sha256((Path('/usr/local/lib/python3.12/dist-packages')/name).read_bytes()).hexdigest()==pin['after']\nprint('KK926 source hashes verified; HF tokenizer retained')"
 r=m.record(rank,'final-model-hashes',['docker','exec',f'ds41-optimized-r{rank}','python3','-c',code]);assert r.returncode==0
r=m.record(0,'final-functional',['python3','/home/nero/fastokens-20260929/functional.py','http://127.0.0.1:8015/v1']);assert r.returncode==0,r.stdout
r=m.record(0,'final-serving-status',['sudo','-n','/usr/local/sbin/deepseek-ring-control','status']);assert r.returncode==0
j={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'kernel':'7.0.0-1019-nvidia','driver':'580.178.04','firmware_updates_offered':False,'os_updates_completed':True,'obsolete_617_boot_pin_removed':True,'network_wait_online_enabled':True,'clock_decision':'stock','persistent_clock_cap_installed':False,'reason':'2300 MHz saves approximately 32% GPU-reported decode power, but both capped 8K/C8 runs are below both stock runs. Minimal loss across workloads is not established.','performance_scope':'three six-cell screens and one 60-second 8K/C8 repeat; not a full benchmark or randomized trial','endpoint':'http://192.168.50.219:8015/v1','functional_passes':7,'kk926_correction_retained':True}
(m.F/'decision.json').write_text(json.dumps(j,indent=2)+'\n');print('FINAL HEALTHY; STOCK CLOCKS',flush=True)
