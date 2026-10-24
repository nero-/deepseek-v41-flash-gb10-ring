#!/usr/bin/env python3
"""Short diagnostic generation with clocks/fabric/memory, outside timed LIL."""
import argparse
import concurrent.futures
import json
import time
import urllib.request
import uuid
from common import remote, parallel, save

p=argparse.ArgumentParser();p.add_argument('label');a=p.parse_args()
assert a.label.replace('-','').isalnum()
READ=r'''import json,pathlib,subprocess
out={}
for h in ('rocep1s0f1','roceP2p1s0f1'):
 root=pathlib.Path('/sys/class/infiniband')/h/'ports/1'
 out[h]={}
 for name in ('port_xmit_data','port_rcv_data','port_xmit_packets','port_rcv_packets','port_xmit_discards','port_rcv_errors'):
  f=root/'counters'/name
  if f.exists():out[h][name]=int(f.read_text())
mem=pathlib.Path('/proc/meminfo').read_text();m={l.split()[0].rstrip(':'):int(l.split()[1]) for l in mem.splitlines()}
out['memory']={'used_gib':(m['MemTotal']-m['MemAvailable'])/1024**2,'available_gib':m['MemAvailable']/1024**2,'swap_used_gib':(m['SwapTotal']-m['SwapFree'])/1024**2}
out['gpu']=subprocess.check_output(['nvidia-smi','--query-gpu=clocks.sm,utilization.gpu,power.draw,temperature.gpu','--format=csv,noheader,nounits'],text=True).strip()
out['clock_service']=subprocess.check_output(['systemctl','is-active','gb10-gpu-clock-cap.service'],text=True).strip()
print(json.dumps(out))
'''
def observe():
    return parallel(lambda rank:{'rank':rank,**json.loads(remote(rank,['python3','-c',READ]).stdout)})

def generate():
    payload={'model':'DeepSeek-V4.1-Flash-TP4','messages':[{'role':'user','content':uuid.uuid4().hex+'\nWrite a detailed Python HTTP server tutorial with request parsing, error handling, tests and deployment. Explain each part.'}],
             'temperature':1,'top_p':1,'max_tokens':512,'ignore_eos':True,
             'chat_template_kwargs':{'thinking':False},'stream':True,'stream_options':{'include_usage':True}}
    req=urllib.request.Request('http://192.168.50.219:8015/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    started=time.monotonic();chunks=[];first=None
    with urllib.request.urlopen(req,timeout=300) as response:
        for line in response:
            if line.startswith(b'data: ') and line[6:].strip()!=b'[DONE]':
                d=json.loads(line[6:]);chunks.append(d)
                if first is None and any(c.get('delta',{}).get('content') for c in d.get('choices',[])):first=time.monotonic()-started
    return {'request':payload,'ttft_seconds':first,'elapsed_seconds':time.monotonic()-started,'chunks':chunks}

before=observe()
with concurrent.futures.ThreadPoolExecutor(1) as pool:
    work=pool.submit(generate)
    time.sleep(2)
    during=observe()
    result=work.result()
after=observe()
save(a.label+'-load-observation.json',{'before':before,'during':during,'after':after,'generation':result,'not_a_benchmark':True})
print('GENERATION_CLOCKS',[r['gpu'] for r in during],flush=True)
print('MEMORY_USED_GIB',[round(r['memory']['used_gib'],3) for r in after],flush=True)
assert result['ttft_seconds'] is not None
assert all(row['clock_service']=='active' for row in during)
assert all(2300<=float(row['gpu'].split(',')[0])<=2350 for row in during),during
