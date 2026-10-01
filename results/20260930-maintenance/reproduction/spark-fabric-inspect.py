import importlib.util,json
s=importlib.util.spec_from_file_location('m','/tmp/spark-maintenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
code="""import sys,json
sys.path.insert(0,'/usr/lib/sparkring')
from scripts.deploy_inventory import _collect_local,_request
c=json.load(open('/etc/sparkring/fabric.json'));v=c['management']
f=_collect_local(_request(c['rank'],c['ssh_target'],v['address'],(),v['witness']))
print(json.dumps({'expected':v,'observed':f['management']}))
"""
for rank in range(4):
 r=m.record(rank,'fabric-observe',['python3','-c',code],True);print(rank,r.returncode,r.stdout[-2000:])
