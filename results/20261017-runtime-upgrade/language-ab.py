"""Paired English-only language-drift screen; not a broad quality evaluation."""
import concurrent.futures,json,re,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'language-ab'
OUT.mkdir(exist_ok=False)
BASE='http://192.168.50.219:8015/v1/chat/completions'
CJK=re.compile('[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ebef\U00030000-\U000323af]')
assert len(CJK.findall('English 中文 123'))==2
cases=[
 ('distributed',True,'Design a reliable distributed task queue. Explain leases, retries, idempotence, backpressure, crash recovery and observability. Give a detailed technical design with examples.'),
 ('mathematics',True,'Derive the expected number of draws required to collect all n equally likely coupons. Explain the proof, variance intuition, approximations, and a Python simulation.'),
 ('debugging',True,'A Python service occasionally processes the same payment event twice after a network timeout. Reason through the failure modes and design an idempotent PostgreSQL transaction, including tests.'),
 ('tutorial',False,'Write an extensive English tutorial on cache invalidation for a web application. Cover expiration, versioning, event-driven invalidation, stampedes, consistency and failure recovery.'),
 ('physics',False,'Explain in detail why seasons happen, why tides happen, and how these mechanisms differ. Give intuitive examples and correct common misconceptions.'),
 ('writing',False,'Write a long, original English science-fiction story about an engineer repairing a remote weather station. Use a coherent plot, natural dialogue and a thoughtful ending.'),
]
jobs=[]
for seed in [17,29]:
 for index,(name,thinking,prompt) in enumerate(cases):
  order=[1.0,0.95] if (index+seed)%2 else [0.95,1.0]
  for top_p in order:jobs.append((name,thinking,prompt,seed,top_p))

def run(job):
 name,thinking,prompt,seed,top_p=job
 identity=f'{name}-seed{seed}-p{top_p}'
 messages=[{'role':'user','content':prompt}]
 if seed==29:messages.insert(0,{'role':'system','content':'Use English for the entire response, including any reasoning. Do not translate into another language.'})
 body={'model':'DeepSeek-V4.1-Flash-TP4','messages':messages,
       'temperature':1.0,'top_p':top_p,'top_k':-1,'min_p':0.0,'repetition_penalty':1.0,'seed':seed,'max_tokens':3072 if thinking else 1536,'chat_template_kwargs':{'thinking':thinking}}
 request=urllib.request.Request(BASE,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 started=time.monotonic()
 with urllib.request.urlopen(request,timeout=900) as response:result=json.load(response)
 choice=result['choices'][0];message=choice['message']
 channels={'content':message.get('content') or '', 'reasoning':message.get('reasoning_content') or message.get('reasoning') or ''}
 assert all(isinstance(v,str) for v in channels.values())
 assert any(channels.values()),result
 counts={k:len(CJK.findall(v)) for k,v in channels.items()}
 excerpts={k:[v[max(0,m.start()-40):m.end()+40] for m in list(CJK.finditer(v))[:3]] for k,v in channels.items()}
 row={'id':identity,'top_p':top_p,'thinking':thinking,'seed':seed,'case':name,'english_system_instruction':seed==29,'cjk_characters':counts,'cjk_any':any(counts.values()),'generated_characters':{k:len(v) for k,v in channels.items()},'completion_tokens':result['usage']['completion_tokens'],'finish_reason':choice['finish_reason'],'elapsed_seconds':time.monotonic()-started,'excerpts':excerpts}
 (OUT/(identity+'.json')).write_text(json.dumps({'request':body,'response':result,'score':row},ensure_ascii=False,indent=2)+'\n')
 print(identity,'tokens',row['completion_tokens'],'CJK',counts,flush=True)
 return row

with concurrent.futures.ThreadPoolExecutor(4) as pool:rows=list(pool.map(run,jobs))
summary={'purpose':'Unexpected CJK script in English-only prompts, separated by visible answer and reasoning','limits':'Bounded purposive screen, not proof of language-drift equivalence or a throughput benchmark. Mixed-arm requests run at concurrency four. Half use ordinary English user prompts without a system instruction; half explicitly ask for English. Max output 3072 thinking / 1536 non-thinking; length-limited replies are included.','rows':rows,'arms':{}}
for top_p in [1.0,0.95]:
 selected=[r for r in rows if r['top_p']==top_p]
 summary['arms'][str(top_p)]={'requests':len(selected),'completion_tokens':sum(r['completion_tokens'] for r in selected),'requests_with_cjk':sum(r['cjk_any'] for r in selected),'content_cjk':sum(r['cjk_characters']['content'] for r in selected),'reasoning_cjk':sum(r['cjk_characters']['reasoning'] for r in selected),'length_limited':sum(r['finish_reason']=='length' for r in selected)}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary['arms'],indent=2),flush=True)
