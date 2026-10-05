#!/usr/bin/env python3
"""Temporary checkpoint distributor, bound only to the existing fabric addresses."""
import functools,http.server,json,socket,threading,sys
from pathlib import Path
ROOT=Path('/srv/sparkring/sparkring/checkpoints/local-inference-lab--DeepSeek-V4.1-Flash-lossless-CSF/c5c41fe301c4c1d24fc09376883d9168e521dc66')
allowed={x['rfilename'] for x in json.loads((ROOT/'hub-file-manifest.json').read_text())['siblings']}|{'hub-file-manifest.json','verified-shards.json'}
allowed|={'serving/'+x.name for x in (ROOT/'metadata').iterdir()}
class Handler(http.server.SimpleHTTPRequestHandler):
 def send_head(self):
  rel=self.path.lstrip('/')
  if rel not in allowed or not (ROOT/rel).is_file():self.send_error(404);return None
  p=ROOT/rel;f=p.open('rb');size=p.stat().st_size;offset=0
  r=self.headers.get('Range')
  if r:
   if not r.startswith('bytes=') or not r.endswith('-'):self.send_error(416);f.close();return None
   offset=int(r[6:-1])
   if offset>=size:self.send_error(416);f.close();return None
  self.send_response(206 if r else 200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(size-offset));self.send_header('Accept-Ranges','bytes')
  if r:self.send_header('Content-Range',f'bytes {offset}-{size-1}/{size}')
  self.end_headers();f.seek(offset);return f
 def copyfile(self,source,outputfile):self.connection.sendfile(source,offset=source.tell())
 def log_message(self,fmt,*args):pass
servers=[http.server.ThreadingHTTPServer((ip,8984),functools.partial(Handler,directory=str(ROOT))) for ip in (sys.argv[1:] or ['10.10.0.10','10.11.3.11'])]
for s in servers:threading.Thread(target=s.serve_forever,daemon=True).start()
threading.Event().wait()
