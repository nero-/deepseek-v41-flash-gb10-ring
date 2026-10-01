import importlib.util,json
s=importlib.util.spec_from_file_location('m','/tmp/spark-maintenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
expected=json.loads((m.ROOT/'results/20260929-fastokens/deployment.json').read_text())['ranks']
for rank in range(4):
 info=json.loads(m.t.remote(rank,['docker','inspect',f'ds41-optimized-r{rank}']).stdout)[0]
 assert info['Image']==expected[rank]['image'] and info['State']['Running']
 env=dict(v.split('=',1) for v in info['Config']['Env']);assert env.get('VLLM_USE_FASTOKENS','0')=='0'
 r=m.record(rank,'clear-stale-fabric-failure',['systemctl','reset-failed','sparkring-fabric.service'],True);assert r.returncode==0
 r=m.record(rank,'final-host-state',['sh','-c','uname -r; nvidia-smi --query-gpu=driver_version --format=csv,noheader; systemctl --failed --no-pager; systemctl is-enabled NetworkManager-wait-online.service; dpkg --audit; timedatectl show --property=NTPSynchronized'])
 assert r.returncode==0 and '0 loaded units listed.' in r.stdout,r.stdout
 fw=json.loads(m.t.remote(rank,['fwupdmgr','get-devices','--json']).stdout)
 fw=[{'name':d['Name'],'version':d.get('Version'),'latest_available':d.get('Releases',[{}])[0].get('Version')} for d in fw['Devices'] if 'updatable' in d.get('Flags',[])]
 (m.F/f'final-inventory-r{rank}.json').write_text(json.dumps({'rank':rank,'image':info['Image'],'fastokens_enabled':False,'firmware':fw},indent=2))
 print('VERIFIED',rank,flush=True)
