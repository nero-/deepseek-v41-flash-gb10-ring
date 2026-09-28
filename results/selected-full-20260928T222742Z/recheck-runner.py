import importlib.util,json
from pathlib import Path
root=Path('/Users/jg/Agent/Builds/deepseek-v41-flash-ring')
s=importlib.util.spec_from_file_location('trial',root/'scripts/research-trial.py');t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
f=root/'results/selected-full-20260928T222742Z'
assert (f/'final-health.json').exists(), 'Wait for the main run and cold probes to finish'
config=t.remote(0,['cat','/etc/deepseek-ring/optimized-specs.json']).stdout
out='/home/nero/bench/results/selected-full-20260928T222742Z-recheck-128k-c2.json'
argv=['/home/nero/bench/.venv/bin/python','-u','/home/nero/bench/lil_matched.py','/home/nero/bench/llm-inference-bench/llm_decode_bench.py','--host','192.168.50.219','--port','8015','--model','DeepSeek-V4.1-Flash-TP4','--no-hw-monitor','--display-mode','plain','--no-resume','--temperature','1.0','--contexts','131072','--concurrency','2','--duration','30','--max-tokens','2048','--skip-prefill','--output',out]
launcher="import json,subprocess,sys\nargv=json.loads(sys.stdin.readline())\nwith open(sys.argv[1],'w') as log:\n r=subprocess.run(argv,input='n'+chr(10),text=True,stdout=log,stderr=subprocess.STDOUT)\nraise SystemExit(r.returncode)\n"
(f/'recheck-runner.py').write_text(Path(__file__).read_text())
(f/'recheck-argv.json').write_text(json.dumps(argv,indent=2))
r=t.remote(3,['python3','-c',launcher,out+'.txt'],json.dumps(argv)+'\n',check=False)
(f/'recheck-status.json').write_text(json.dumps({'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2))
for remote,local in [(out,'recheck.json'),(out.replace('.json','.matched-request.json'),'recheck.matched-request.json'),(out+'.txt','recheck.txt')]:
 (f/local).write_text(t.remote(3,['cat',remote]).stdout)
assert r.returncode==0
assert t.remote(0,['cat','/etc/deepseek-ring/optimized-specs.json']).stdout==config
health=t.remote(0,['curl','-fsS','--max-time','10','http://127.0.0.1:8015/health'])
nodes=t.parallel(lambda rank: json.loads(t.remote(rank,['docker','inspect',f'ds41-optimized-r{rank}']).stdout)[0])
assert all(n['State']['Running'] for n in nodes)
(f/'post-recheck-health.json').write_text(json.dumps({'api_healthy':True,'configuration_unchanged':True,'nodes':[{'name':n['Name'],'running':n['State']['Running'],'started_at':n['State']['StartedAt']} for n in nodes]},indent=2))
print('RECHECK COMPLETE',flush=True)
