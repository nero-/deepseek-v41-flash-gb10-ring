#!/usr/bin/env python3
"""CPU-only parity/timing probe of the actual DeepSeek V4.1 tokenizer mode."""
import argparse,hashlib,json,os,random,statistics,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--enabled',type=int,choices=[0,1],required=True);p.add_argument('--output',required=True);a=p.parse_args()
os.environ['VLLM_USE_FASTOKENS']=str(a.enabled)
from vllm.tokenizers.registry import get_tokenizer
tok=get_tokenizer('/models/target',tokenizer_mode='deepseek_v41',local_files_only=True)
from tokenizers.decoders import DecodeStream
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def timing(fn,repeats=5):
 value=fn();times=[]
 for _ in range(repeats):
  t=time.perf_counter();value=fn();times.append(time.perf_counter()-t)
 return value,{'median_seconds':statistics.median(times),'samples_seconds':times}
texts=['Hello, world!','你好，世界。こんにちは世界。안녕하세요. مرحبا بالعالم.','café cafe\u0301 👩🏽‍💻 🧪\n\t  spaces\r\n','def f(x):\n    return x ** 2\n```json\n{"x": 1}\n```','<｜begin▁of▁sentence｜><｜User｜>test<｜Assistant｜>','abc '*4096,'x'*8192]
rows=[]
for text in texts:
 ids=tok.encode(text,add_special_tokens=False);decoded=tok.decode(ids,skip_special_tokens=False)
 for skip in [False,True]:
  stream=DecodeStream(skip_special_tokens=skip);chunks=[stream.step(tok.backend_tokenizer,i) or '' for i in ids]
  rows.append({'kind':'text','text_sha256':digest(text),'skip_special_tokens':skip,'ids_sha256':digest(ids),'tokens':len(ids),'decoded_sha256':digest(decoded),'stream_sha256':digest(''.join(chunks))})
tools=[{'type':'function','function':{'name':'get_weather','description':'Current weather','parameters':{'type':'object','properties':{'city':{'type':'string'}},'required':['city']}}}]
messages=[{'role':'user','content':'What is the weather in Paris?'}]
for thinking in [False,True]:
 ids=tok.apply_chat_template(messages,tools=tools,thinking=thinking,tokenize=True)
 rows.append({'kind':'tools-template','thinking':thinking,'ids_sha256':digest(ids),'tokens':len(ids)})
image_messages=[{'role':'user','content':[{'type':'text','text':'Describe this image.'},{'type':'image_url','image_url':{'url':'data:image/png;base64,placeholder'}}]}]
ids=tok.apply_chat_template(image_messages,thinking=False,tokenize=True)
rows.append({'kind':'image-placeholder-template','ids_sha256':digest(ids),'tokens':len(ids)})
rng=random.Random(7);words='harbour lantern meadow copper violin orchard compass thistle ember granite'.split();records=[f'Record {i}: the {rng.choice(words)} keeper counted {rng.randint(1,999)} {rng.choice(words)} crates. ' for i in range(65536)]
bench=[]
for label,count in [('8k',512),('128k',8192),('1m',65536)]:
 text=''.join(records[:count]);ids,encode=timing(lambda:tok.encode(text,add_special_tokens=False),3)
 decoded,decode=timing(lambda:tok.decode(ids,skip_special_tokens=False),3)
 bench.append({'label':label,'bytes':len(text.encode()),'tokens':len(ids),'ids_sha256':digest(ids),'decoded_sha256':digest(decoded),'encode':encode,'decode':decode})
ids=tok.encode(('Hello, world! 你好 👩🏽‍💻 café.\n'*600),add_special_tokens=False)[:8192]
def stream_all():
 stream=DecodeStream(skip_special_tokens=True)
 return ''.join(stream.step(tok.backend_tokenizer,i) or '' for i in ids)
decoded,stream_time=timing(stream_all,3)
result={'enabled':bool(a.enabled),'backend_type':str(type(tok.backend_tokenizer)),'cpu_limit':2,'rayon_threads':os.environ.get('RAYON_NUM_THREADS'),'parity':rows,'timings':bench,'stream':{'tokens':len(ids),'output_sha256':digest(decoded),**stream_time}}
Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
