"""Exercise the image boundary, distinct images, chat history and streaming."""
import base64,json,re,struct,time,urllib.error,urllib.request,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
URL='http://192.168.50.219:8015'
MODEL='DeepSeek-V4.1-Flash-TP4'
results=[]
def png(color,tag,width=64,height=64):
 def chunk(k,d):return struct.pack('>I',len(d))+k+d+struct.pack('>I',zlib.crc32(k+d)&0xffffffff)
 pixels=bytearray(bytes(color)*width*height)
 # A distinct four-pixel identifier forces distinct content hashes per image.
 for i in range(4):pixels[i*3:i*3+3]=bytes([(tag>>(8*i))&255,0,0])
 rows=b''.join(b'\x00'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')
def image(color,tag,size=64):
 return {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(png(color,tag,size,size)).decode()}}
def images(n,offset,size=64):
 palette=[(0,180,0),(255,255,0),(255,0,255),(0,255,255)]
 return [image((255,0,0) if i==0 else ((0,0,255) if i==n-1 else palette[i%len(palette)]),offset+i,size) for i in range(n)]
def request(name,messages,stream=False,expected=('red','blue'),max_tokens=100):
 body={'model':MODEL,'messages':messages,'max_tokens':max_tokens,'temperature':0,'chat_template_kwargs':{'thinking':False},'stream':stream}
 if stream:body['stream_options']={'include_usage':True}
 started=time.monotonic();row={'name':name,'stream':stream}
 try:
  req=urllib.request.Request(URL+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=600) as r:
   row['status']=r.status
   if not stream:
    data=json.load(r);row['response']=data;reply=data['choices'][0]['message']['content'] or ''
   else:
    reply='';chunks=0;done=False
    for line in r:
     if not line.startswith(b'data: '):continue
     raw=line[6:].strip()
     if raw==b'[DONE]':done=True;break
     part=json.loads(raw)
     if 'error' in part:row['stream_error']=part['error'];break
     if part.get('usage'):row['usage']=part['usage']
     for choice in part.get('choices',[]):reply+=choice.get('delta',{}).get('content') or ''
     chunks+=1
    row.update(done=done,chunks=chunks)
   row['reply']=reply
   row['pass']=all(re.search(r'\b'+re.escape(x)+r'\b',reply,re.I) for x in expected) and (not stream or row.get('done',False))
 except urllib.error.HTTPError as e:
  row.update(status=e.code,error=e.read().decode());row['pass']=False
 except Exception as e:row.update(error=repr(e));row['pass']=False
 row['elapsed_s']=round(time.monotonic()-started,3)
 row['health_after']=urllib.request.urlopen(URL+'/health',timeout=10).status
 results.append(row);(ROOT/'multi-image-checks.json').write_text(json.dumps(results,indent=2)+'\n')
 print(json.dumps({k:v for k,v in row.items() if k!='response'}),flush=True)
 return row
question={'type':'text','text':'Name the dominant color of the FIRST image and the LAST image, in that order. Reply briefly.'}
for n,size in [(5,1024),(16,64),(64,64)]:
 row=request(f'{n}-distinct-images-{size}px',[{'role':'user','content':images(n,n*1000,size)+[question]}],stream=(n==16))
 if not row['pass']:raise SystemExit('Image qualification failed')
# The first turn already contains four images. A later turn adds two more.
messages=[{'role':'user','content':images(4,100000)+[{'type':'text','text':'Remember these pictures.'}]},{'role':'assistant','content':'I have noted them.'},{'role':'user','content':[image((255,0,0),100010),image((0,0,255),100011),{'type':'text','text':'Name the dominant colors of the two NEW images in this last message, in order.'}]}]
row=request('six-images-across-chat-history',messages,stream=True)
if not row['pass']:raise SystemExit('History qualification failed')
messages.extend([{'role':'assistant','content':row['reply']},{'role':'user','content':'Now compute 17 times 23. Reply with the number only.'}])
row=request('text-followup-with-image-history',messages,stream=True,expected=('391',),max_tokens=32)
if not row['pass']:raise SystemExit('Continuation failed')
# Reject above the configured cap before processing, then prove the API is usable.
boundary=request('1000-images-rejected',[{'role':'user','content':[image((255,0,0),200000)]*1000+[question]}],expected=())
boundary['pass']=boundary.get('status')==400 and 'At most 999 image' in boundary.get('error','')
(ROOT/'multi-image-checks.json').write_text(json.dumps(results,indent=2)+'\n')
row=request('text-after-rejection',[{'role':'user','content':'What is 17 times 23? Reply with the number only.'}],stream=True,expected=('391',),max_tokens=32)
if not row['pass'] or not boundary['pass']:raise SystemExit('Boundary/recovery check failed')
print('All multi-image checks passed',flush=True)
