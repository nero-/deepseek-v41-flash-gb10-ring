"""Apply the full KK #926 fix and record an explicit verified derived layer."""
import hashlib,importlib.util,json,py_compile,shutil
from pathlib import Path
ctx=Path('/opt/kk926');site=Path('/usr/local/lib/python3.12/dist-packages')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((ctx/'manifest.json').read_text())
receipt=Path('/opt/sparkring/receipts/external-base-installed.json')
toolchain=Path('/opt/sparkring/toolchain/installed.json')
before=receipt.read_bytes();tc_before=toolchain.read_bytes();record=json.loads(before);tc=json.loads(tc_before)
assert tc['parent_receipt_sha256']==sha(receipt)
for name,pins in m['files'].items():
 p=site/name;assert sha(p)==pins['before'],name
 assert record['files'][str(p)]==pins['before'],name
 assert sha(ctx/'source'/name)==pins['after'],name
backup=ctx/'parent';backup.mkdir()
(backup/'external-base-installed.json').write_bytes(before)
(backup/'toolchain-installed.json').write_bytes(tc_before)
for name,pins in m['files'].items():
 p=site/name;saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,saved)
 shutil.copyfile(ctx/'source'/name,p);p.chmod(0o644);py_compile.compile(str(p),doraise=True)
 record['files'][str(p)]=sha(p)
spec=importlib.util.spec_from_file_location('external','/opt/sparkring/bin/external-base.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
record_path,digest=mod.record_distribution('vllm',site/'vllm')
assert record_path in record['distribution_records'];record['distribution_records'][record_path]=digest
record.setdefault('local_corrections',[]).append({'name':'deepseek-compressor-ring-kk926','upstream_head':m['upstream_head'],'receipt':'/opt/sparkring/receipts/derived-vllm-kk926.json'})
receipt.write_text(json.dumps(record,indent=2)+'\n')
tc['parent_receipt_sha256']=sha(receipt);toolchain.write_text(json.dumps(tc,indent=2)+'\n')
Path('/opt/sparkring/receipts/derived-vllm-kk926.json').write_text(json.dumps({**m,'parent_external_receipt_sha256':hashlib.sha256(before).hexdigest(),'external_receipt_sha256':sha(receipt),'parent_toolchain_receipt_sha256':hashlib.sha256(tc_before).hexdigest(),'toolchain_receipt_sha256':sha(toolchain),'native_libraries_changed':False,'serving_qualified':False},indent=2)+'\n')
print(json.dumps(mod.verify()))
