#!/usr/bin/env python3
"""Repeat the two C8 cells without changing the active tokenizer or settings."""
import argparse,importlib.util,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('f',root/'scripts/fastokens-serving.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
parser=argparse.ArgumentParser();parser.add_argument('--label',choices=['fastokens','hf'],default='fastokens');args=parser.parse_args()
name=args.label+'-c8-repeat';out=f.R+'/'+name+'.json'
argv=f.read('fastokens-screen-argv.json');argv[argv.index('--concurrency')+1]='8';argv[argv.index('--output')+1]=out
argv.remove('--standalone-prefill');i=argv.index('--prefill-contexts');del argv[i:i+2];argv.append('--skip-prefill')
(f.F/(name+'-argv.json')).write_text(json.dumps(argv,indent=2))
launcher="import json,subprocess,sys\na=json.load(sys.stdin)\nwith open(sys.argv[1],'w') as out:r=subprocess.run(a,input='n'+chr(10),text=True,stdout=out,stderr=subprocess.STDOUT)\nraise SystemExit(r.returncode)"
f.k.run(name,3,['python3','-c',launcher,out+'.log'],json.dumps(argv))
for remote,local in [(out,name+'.json'),(out.replace('.json','.matched-request.json'),name+'.matched-request.json'),(out+'.log',name+'.txt')]:
 (f.F/local).write_text(f.k.t.remote(3,['cat',remote]).stdout)
