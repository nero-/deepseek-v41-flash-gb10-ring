#!/usr/bin/env python3
"""Explicitly restore the saved pre-KK926 selection on this fleet."""
import importlib.util,json
from pathlib import Path
s=importlib.util.spec_from_file_location('promotion',Path(__file__).with_name('kk926-promote.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
k=m.k;F=k.F
if __name__=='__main__':
 selected=json.loads(k.t.remote(0,['cat','/etc/deepseek-ring/optimized-specs.json']).stdout)
 assert selected==m.read('selected-corrected.json'),'Current selection has changed; refusing rollback'
 deployment=m.read('deployment.json');images=m.read('images.json')
 for rank in range(4):
  old=json.loads(k.t.remote(rank,['docker','inspect',f'ds41-before-kk926-r{rank}']).stdout)[0]
  current=json.loads(k.t.remote(rank,['docker','inspect',f'ds41-optimized-r{rank}']).stdout)[0]
  assert old['Image']==k.BASE and not old['State']['Running']
  assert current['Image']==images[rank]['image_id'] and current['Config']['Labels'].get('io.local.deepseek-correction')=='kk926'
 k.run('manual-rollback-stop',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','down'])
 for rank in range(4):
  k.t.remote(rank,['docker','rm',f'ds41-optimized-r{rank}'])
 m.p.bundle(0,m.p.CONFIG_DIR,deployment['backup_tag'],'rollback')
 for rank in range(4):k.t.remote(rank,['docker','rename',f'ds41-before-kk926-r{rank}',f'ds41-optimized-r{rank}'])
 k.run('manual-rollback-start',0,['sudo','-n','/usr/local/sbin/deepseek-ring-control','up'])
 (F/'manual-rollback.json').write_text(json.dumps({'restored_original':True,'backup_tag':deployment['backup_tag']},indent=2))
