import csv,datetime,json,re,statistics
from pathlib import Path
F=Path('/Users/jg/Agent/Builds/deepseek-v41-flash-ring/results/20260930-maintenance')
def phase(name):
 j=json.loads((F/(name+'-screen.json')).read_text());day=j['metadata']['timestamp'][:10];ready={};windows={}
 def epoch(s):return datetime.datetime.fromisoformat(day+'T'+s).replace(tzinfo=datetime.timezone.utc).timestamp()
 for line in j['event_log']:
  r=re.match(r'(\d\d:\d\d:\d\d) ready C=(\d+) ctx=(\d+)k',line)
  if r:ready[(int(r[2]),int(r[3])*1024)]=epoch(r[1])
  r=re.match(r'(\d\d:\d\d:\d\d) cell done C=(\d+) ctx=(\d+)k',line)
  if r:
   key=(int(r[2]),int(r[3])*1024);end=epoch(r[1]);start=ready.get(key)
   if start and end-start>=20:windows[key]=(start,end)
 samples=[]
 for rank in range(4):
  rows=[]
  for r in csv.reader((F/f'{name}-telemetry-r{rank}.csv').read_text().splitlines()):
   try:
    stamp=datetime.datetime.strptime(r[0].strip(),'%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=datetime.timezone.utc).timestamp()
    rows.append({'time':stamp,'mhz':float(r[1].split()[0]),'watts':float(r[2].split()[0]),'celsius':float(r[3]),'util':float(r[4].split()[0])})
   except (ValueError,IndexError):continue
  assert rows,rank;samples.append(rows)
 result=[]
 for r in j['results']:
  key=(r['concurrency'],r['context_tokens']);start,end=windows[key];ranks=[]
  for rank,rows in enumerate(samples):
   window=[x for x in rows if start<=x['time']<end];assert len(window)>=20,(rank,key,len(window))
   ranks.append({'rank':rank,'samples':len(window),'mean_watts':statistics.mean(x['watts'] for x in window),'peak_celsius':max(x['celsius'] for x in window),'mean_mhz':statistics.mean(x['mhz'] for x in window)})
  result.append({'context':r['context_tokens'],'concurrency':r['concurrency'],'tps':r['aggregate_tps'],'acceptance':r['server_accept_len_effective'],'steps_per_second':r['server_steps_per_s'],'ranks':ranks,'fleet_gpu_watts':sum(x['mean_watts'] for x in ranks),'peak_gpu_celsius':max(x['peak_celsius'] for x in ranks),'valid':not any(r.get(x) for x in ['loop_detected','capacity_limited','failure_reason','num_errors','warmup_timed_out'])})
 return {'prefill':j['prefill'],'decode':result}
report={name:phase(name) for name in ['stock','2300','stock-repeat']}
(F/'clock-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
for a,b in zip(report['stock']['decode'],report['2300']['decode']):print(a['context'],a['concurrency'],round(a['tps'],2),round(b['tps'],2),'pct',round(100*(b['tps']/a['tps']-1),2),'watts',round(a['fleet_gpu_watts'],1),round(b['fleet_gpu_watts'],1),'peakC',a['peak_gpu_celsius'],b['peak_gpu_celsius'])
for key,a in report['stock']['prefill'].items():
 b=report['2300']['prefill'][key];print('prefill',key,a['tok_per_sec'],b['tok_per_sec'],round(100*(b['tok_per_sec']/a['tok_per_sec']-1),2))
