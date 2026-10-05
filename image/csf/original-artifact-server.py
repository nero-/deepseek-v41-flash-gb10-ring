#!/usr/bin/env python3
"""Serve only verified original shards, on an explicitly selected fabric IP."""
import argparse,http.server,json,threading
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--bind',required=True);p.add_argument('--manifest',required=True);a=p.parse_args()
ROOT=Path('/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash/dba1be0a40aa45a94ad051997016db3960a90277')
manifest=Path(a.manifest);api=json.loads(manifest.read_text());assert api['sha']==ROOT.name
allowed={x['rfilename'] for x in api['siblings'] if x['rfilename'].endswith('.safetensors')};assert len(allowed)==48
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  name=self.path.lstrip('/')
  if name=='manifest.json':path=manifest
  elif name in allowed:path=ROOT/name
  else:self.send_error(404);return
  assert path.is_file() and not path.is_symlink()
  with path.open('rb') as source:
   size=path.stat().st_size;offset=0;r=self.headers.get('Range')
   if r:
    if not r.startswith('bytes=') or not r.endswith('-'):self.send_error(416);return
    offset=int(r[6:-1])
    if not 0<=offset<size:self.send_error(416);return
   self.send_response(206 if r else 200);self.send_header('Content-Length',str(size-offset));self.send_header('Accept-Ranges','bytes')
   if r:self.send_header('Content-Range',f'bytes {offset}-{size-1}/{size}')
   self.end_headers();self.connection.sendfile(source,offset=offset)
 def log_message(self,*args):pass
http.server.ThreadingHTTPServer((a.bind,8985),Handler).serve_forever()
