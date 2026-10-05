#!/usr/bin/env python3
"""Pinned CSF upgrade helpers; receipts are kept per campaign."""
import importlib.util,json,subprocess,sys,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];F=ROOT/'results/20261004-csf';REMOTE='/home/nero/csf-20261004'
s=importlib.util.spec_from_file_location('trial',ROOT/'scripts/research-trial.py');t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
BASE='sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf'
def root(rank,argv,data=None,check=True):
 prefix=['docker','run','--rm','--privileged','--pid=host','--network=host','--env','LD_PRELOAD=','--env','LD_LIBRARY_PATH=','--entrypoint','nsenter',BASE,'--target','1','--mount','--uts','--ipc','--net','--pid','--'] if rank<2 else ['sudo','-n']
 if rank<2 and data is not None:prefix.insert(3,'-i')
 return t.remote(rank,prefix+argv,data,check)
def record(name,rank,argv,data=None,admin=False,check=True):
 (F/(name+'-command.json')).write_text(json.dumps({'rank':rank,'argv':argv,'host_admin':admin},indent=2))
 r=(root if admin else t.remote)(rank,argv,data,False);(F/(name+'.txt')).write_text(r.stdout+r.stderr);(F/(name+'-status.json')).write_text(json.dumps({'exit_code':r.returncode},indent=2))
 if check and r.returncode:raise RuntimeError(f'{name}: {r.stderr[-2000:]}')
 return r
if __name__=='__main__':
 print('Import this module to run campaign actions.')
