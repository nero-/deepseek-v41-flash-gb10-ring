#!/usr/bin/env python3
"""Resume interrupted CSF reconstruction with verified original fabric copies."""
import importlib.util,json,time
from pathlib import Path

def module(name,file):
 s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
c=module('campaign','csf-upgrade.py');cleanup=module('cleanup','csf-cleanup-candidate.py')

def main():
 decision=json.loads((c.F/'promotion-decision.json').read_text());assert decision['decision']=='reject' and decision['restore_original']
 before=json.loads((c.F/'selected-before.json').read_text());assert json.loads(c.t.remote(0,['cat','/etc/deepseek-ring/optimized-specs.json']).stdout)==before
 assert all(not c.t.remote(rank,['docker','ps','-q']).stdout.strip() for rank in range(4))
 for rank in (0,1):
  proof=json.loads((c.F/f'original-restore-r{rank}.json').read_text());assert proof['complete'] and len(proof['shards'])==48
 writer='import sys;from pathlib import Path;Path(sys.argv[1]).write_text(sys.stdin.read())'
 for rank in range(4):
  file='original-artifact-server.py' if rank<2 else 'restore-original-fabric.py'
  c.t.remote(rank,['python3','-c',writer,c.REMOTE+'/'+file],(c.ROOT/'image/csf'/file).read_text())
 for rank,address in ((0,'10.11.3.11'),(1,'10.10.1.10')):
  c.record(f'original-fabric-server-start-r{rank}',rank,['systemd-run','--unit=ds41-original-artifacts','python3',c.REMOTE+'/original-artifact-server.py','--bind',address,'--manifest',c.REMOTE+'/original-hub-file-manifest.json'],admin=True)
 def one(rank):
  if rank<2:return
  # User explicitly selected deleting CSF and restoring from verified Sparks.
  # Originals on both sources are complete; every model container is stopped.
  proof_path=c.REMOTE+f'/original-restore-r{rank}.json'
  proof=json.loads(c.t.remote(rank,['cat',proof_path]).stdout)
  (c.F/f'original-reconstruction-final-progress-r{rank}.json').write_text(json.dumps(proof,indent=2)+'\n')
  result=c.record(f'candidate-fabric-space-cleanup-r{rank}',rank,['python3','-c',cleanup.DELETE,cleanup.NEW],admin=True)
  receipt=json.loads(result.stdout);assert receipt['candidate_removed']
  receipt['removed_before_original_start']=True;receipt['reason']='User selected fabric transfer from complete hash-verified original Spark copies.'
  (c.F/f'candidate-checkpoint-cleanup-r{rank}.json').write_text(json.dumps(receipt,indent=2)+'\n')
  source='http://10.10.1.10:8985' if rank==2 else 'http://10.11.3.11:8985'
  c.record(f'original-fabric-transfer-r{rank}',rank,['python3','-u',c.REMOTE+'/restore-original-fabric.py','--source',source,'--manifest',c.REMOTE+'/original-hub-file-manifest.json','--proof',proof_path],admin=True)
  document=json.loads(c.t.remote(rank,['cat',proof_path]).stdout);assert document['complete'] and len(document['shards'])==48
  (c.F/f'original-restore-r{rank}.json').write_text(json.dumps(document,indent=2)+'\n');print(rank,'fabric recovery complete',flush=True)
 c.t.parallel(one)
 for rank in (0,1):c.record(f'original-fabric-server-stop-r{rank}',rank,['systemctl','stop','ds41-original-artifacts.service'],admin=True)
 assert json.loads(c.t.remote(0,['cat','/etc/deepseek-ring/optimized-specs.json']).stdout)==before
 c.record('restored-up',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','up'])
 c.record('restored-functional',0,['python3','-u',c.REMOTE+'/tests/functional.py','http://127.0.0.1:8015/v1'])
 c.record('restored-status',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','status'])
 for rank in range(4):
  info=json.loads(c.t.remote(rank,['docker','inspect',f'ds41-optimized-r{rank}']).stdout)[0]
  assert info['State']['Running'] and info['Image']==before['specs'][rank]['image_id']
 (c.F/'deployment.json').write_text(json.dumps({'selected':'previous-kk926-corrected','healthy':True,'checkpoint':'dba1be0a40aa45a94ad051997016db3960a90277','endpoint':'http://192.168.50.219:8015/v1','image_ids':[x['image_id'] for x in before['specs']],'selected_configuration_unchanged':True,'candidate_promoted':False,'unix_time':time.time(),'reason':'Rejected slower integrated CSF runtime; exact original recipe restored. GX10 recovery switched from reconstruction to fabric copies at user direction.','repeat_original_benchmark':False},indent=2)+'\n')
 cleanup.main()
 print('FABRIC RECOVERY AND CLEANUP PASS',flush=True)

if __name__=='__main__':main()
