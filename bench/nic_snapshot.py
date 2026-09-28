#!/usr/bin/env python3
"""Read four-node RDMA error counters; compare snapshots without resetting them."""
import concurrent.futures
import json
import shlex
import subprocess
import time

CODE = """import json
from pathlib import Path
data={}
for h in Path('/sys/class/infiniband').iterdir():
 values={}
 for p in (h/'ports/1/hw_counters').glob('*'):
  if any(s in p.name for s in ('err','discard','out_of','timeout','retry')):
   try: values[p.name]=int(p.read_text())
   except (ValueError,OSError): pass
 data[h.name]=values
print(json.dumps(data))
"""


def read(host):
    output = subprocess.check_output(["ssh", "-o", "BatchMode=yes", host,
                                      "python3 -c " + shlex.quote(CODE)], text=True)
    return host, json.loads(output)


with concurrent.futures.ThreadPoolExecutor(4) as pool:
    nodes = dict(pool.map(read, ("spark-r0", "spark-r1", "gx10-r1", "gx10-r0")))
print(json.dumps({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "nodes": nodes}, indent=2))
