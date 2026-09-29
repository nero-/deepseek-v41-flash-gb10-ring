#!/usr/bin/env python3
"""Matched uncached and KV-cached chat TTFT using fixed prompts and usage checks."""
import argparse,hashlib,json,random,statistics,time,urllib.request,uuid
import concurrent.futures as cf
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--label',required=True);p.add_argument('--nonce');p.add_argument('--prompt-label');a=p.parse_args()
url='http://127.0.0.1:8015/v1/chat/completions';model='DeepSeek-V4.1-Flash-TP4'
def request(prompt):
 body={'model':model,'messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':16,'chat_template_kwargs':{'thinking':False},'stream':True,'stream_options':{'include_usage':True}}
 req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 start=time.perf_counter();ttft=None;parts=[];usage=None
 with urllib.request.urlopen(req,timeout=1800) as response:
  for line in response:
   if not line.startswith(b'data: ') or line[6:].strip()==b'[DONE]':continue
   item=json.loads(line[6:]);usage=item.get('usage') or usage
   for c in item.get('choices',[]):
    content=c.get('delta',{}).get('content')
    if content:
     if ttft is None:ttft=time.perf_counter()-start
     parts.append(content)
 answer=''.join(parts);assert 'RING-7825-COBALT' in answer,answer
 return {'ttft_seconds':ttft,'elapsed_seconds':time.perf_counter()-start,'usage':usage,'answer':answer}
rng=random.Random(7);words='harbour lantern meadow copper violin orchard compass thistle ember granite'.split()
records=[f'Record {i}: the {rng.choice(words)} keeper counted {rng.randint(1,999)} {rng.choice(words)} crates. ' for i in range(65536)]
nonce=a.nonce or uuid.uuid4().hex;prompt_label=a.prompt_label or a.label
report={'label':a.label,'nonce':nonce,'prompt_label':prompt_label,'method':'first content SSE; pinned corpus/prefix across backends after restart; 16 output tokens max','cases':[]}
out=Path(a.output)
for label,count in [('8k',512),('128k',8192),('1m',65536)]:
 chunks=records[:count];mid=len(chunks)//2
 prompt=f'{nonce}-{prompt_label}-{label}-fresh\n'+''.join(chunks[:mid])+'\nThe access code is RING-7825-COBALT.\n'+''.join(chunks[mid:])+'\nWhat is the access code? Reply with the code only.'
 cold=request(prompt);assert cold['usage']['prompt_tokens_details']['cached_tokens']==0,cold
 # Warm repeated prompt before the timed samples. Require actual KV reuse.
 warm=request(prompt)
 cached=[request(prompt) for _ in range(5)]
 with cf.ThreadPoolExecutor(8) as pool:concurrent=list(pool.map(lambda _:request(prompt),range(8)))
 for q in cached+concurrent:
  assert q['usage']['prompt_tokens_details']['cached_tokens']>=q['usage']['prompt_tokens']*.95,q
 case={'label':label,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'cold':cold,'warmup':warm,'cached_c1':cached,'cached_c8':concurrent,'cached_c1_median_ttft':statistics.median(q['ttft_seconds'] for q in cached),'cached_c8_median_ttft':statistics.median(q['ttft_seconds'] for q in concurrent)}
 report['cases'].append(case);out.write_text(json.dumps(report,indent=2)+'\n');print(label,'cold',cold['ttft_seconds'],'cached C1',case['cached_c1_median_ttft'],'cached C8',case['cached_c8_median_ttft'],flush=True)
