#!/usr/bin/env python3
"""Compare generated-token distributions with prefill of the exact same sequence.

Coarsened KL uses the intersection of reported top-20 tokens plus one other-mass
bucket, so it is a lower bound, not full-vocabulary KL or the upstream metric.
Each build generates its own continuations. Raw distributions are retained.
"""
import argparse,gzip,json,math,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--tokens',type=int,default=2048);p.add_argument('--limit',type=int,default=8);a=p.parse_args()
base='http://127.0.0.1:8015';model='DeepSeek-V4.1-Flash-TP4'
prompts=[
 'Write a detailed textbook chapter on photosynthesis, covering molecular mechanisms, plant adaptations, experiments and ecological consequences. Aim for at least 3000 words.',
 'Write a thorough history of mathematics, from ancient counting systems through calculus and modern abstract algebra. Include worked examples and aim for 3000 words.',
 'Write a detailed tutorial on building a reliable distributed key-value store. Discuss consensus, replication, recovery, consistency and tests. Aim for 3000 words.',
 'Explain European architecture from classical antiquity to modernism in a detailed 3000-word essay, with examples and comparisons.',
 'Derive and explain the central limit theorem, including assumptions, examples, counterexamples and practical uses. Provide a lengthy, careful answer.',
 'Design a Python library for a persistent job queue with retries, idempotency and crash recovery. Explain the design and provide substantial tested code.',
 'Explain how to plan a scientific experiment distinguishing competing hypotheses about plant growth. Discuss controls, measurements, statistics and limitations in depth.',
 'Solve and generalize this problem carefully: count the ways to tile a 2 by n rectangle with dominoes. Then discuss extensions, algorithms and proofs in detail.'
]
def post(path,body):
 q=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(q,timeout=1200) as r:return json.load(r)
def probs(top):return {int(k.removeprefix('token_id:')):math.exp(v if isinstance(v,(float,int)) else v['logprob']) for k,v in top.items()}
def measure(dec,pre):
 keys=set(dec)&set(pre); pp=[pre[k] for k in keys];qq=[dec[k] for k in keys]
 pm,qm=sum(pp),sum(qq);pp.append(max(0,1-pm));qq.append(max(0,1-qm))
 kl=sum(x*math.log(x/max(y,1e-30)) for x,y in zip(pp,qq) if x>0)
 return {'coarsened_kl':kl,'top1_agreement':int(max(pre,key=pre.get)==max(dec,key=dec.get)), 'prefill_mass':pm,'decode_mass':qm,'intersection_tokens':len(keys)}
rows=[];out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
for i,prompt in enumerate(prompts[:a.limit]):
 thinking=i>=4
 tok=post('/tokenize',{'model':model,'messages':[{'role':'user','content':prompt}],'add_generation_prompt':True,'chat_template_kwargs':{'thinking':thinking}})['tokens']
 t=time.monotonic();d=post('/v1/completions',{'model':model,'prompt':tok,'temperature':0,'max_tokens':a.tokens,'ignore_eos':True,'logprobs':20,'return_token_ids':True,'return_tokens_as_token_ids':True});elapsed=time.monotonic()-t
 choice=d['choices'][0];ids=choice['token_ids'];assert len(ids)==a.tokens
 replay=post('/v1/completions',{'model':model,'prompt':tok+ids,'temperature':0,'max_tokens':1,'prompt_logprobs':20,'return_token_ids':True,'return_tokens_as_token_ids':True})
 cached=(replay['usage'].get('prompt_tokens_details') or {}).get('cached_tokens');assert cached==0,('Replay must be fresh',cached)
 pref=replay['choices'][0]['prompt_logprobs'];tops=choice['logprobs']['top_logprobs'];assert len(tops)==len(ids) and len(pref)==len(tok)+len(ids)
 measures=[measure(probs(tops[j]),probs(pref[len(tok)+j])) for j in range(len(ids))]
 raw=out.with_name(out.stem+f'-prompt{i}.json.gz')
 with gzip.open(raw,'wt') as f:json.dump({'prompt':prompt,'thinking':thinking,'prompt_ids':tok,'decode':d,'prefill':replay},f,ensure_ascii=False)
 rows.append({'prompt_index':i,'thinking':thinking,'output_tokens':len(ids),'elapsed_seconds':elapsed,'replay_cached_tokens':cached,'positions':measures,'raw':raw.name})
 report={'method':'top-20 intersection plus other-mass bucket KL(prefill||decode)','args':vars(a),'requests':rows,'bins':[]}
 for lo,hi in [(0,256),(256,512),(512,1024),(1024,1536),(1536,2048)]:
  vals=[x for r in rows for x in r['positions'][lo:hi]]
  if vals:report['bins'].append({'start':lo,'end':hi,'count':len(vals),**{k:sum(x[k] for x in vals)/len(vals) for k in vals[0]}})
 out.write_text(json.dumps(report,indent=2)+'\n')
 print('PROMPT',i,'thinking',thinking,'seconds',round(elapsed,2),'bins',[(r['start'],round(r['coarsened_kl'],4),round(r['top1_agreement'],4)) for r in report['bins']],flush=True)
