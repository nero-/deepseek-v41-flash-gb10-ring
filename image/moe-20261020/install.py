"""Apply an audited MoE source boundary and seal a distinct image composition."""
import base64
import csv
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path("/opt/sparkring")
CONTEXT = ROOT / "moe-20261020"
SITE = Path("/usr/local/lib/python3.12/dist-packages")
RECEIPT = ROOT / "receipts/external-base-installed.json"
assert platform.machine() == "aarch64"
subprocess.run([sys.executable, str(ROOT / "toolchain/toolchain.py"), "verify"], check=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


parent = RECEIPT.read_bytes()
record = json.loads(parent)
assert record["sources"]["vllm"]["commit"] == "8244d1c44348ae8a5bbfc9f1b607021652283ed4"
assert record["sources"]["b12x"]["commit"] == "91271757f7746f3dfb58f7c2aeb44a663389de9e"
assert record["capabilities"]["transport_profile"] == "flashinfer-abi8-switched"
manifest = json.loads((CONTEXT / "staged/manifest.json").read_text())
assert manifest["upstream_commit"] == "a6b096f7b34dd0266af382a4ece59682676f6ece"
assert len(manifest["files"]) == 29 and manifest["online_csf"] is False
transport_path = ROOT / "switched-20261020/transport-manifest.json"
transport_sha = sha(transport_path)
transport = json.loads(transport_path.read_text())
for name, expected in transport["files"].items():
    assert sha(name) == expected, name
for name, hashes in manifest["files"].items():
    relative = Path(name)
    assert not relative.is_absolute() and ".." not in relative.parts
    assert name.startswith("flashinfer/experimental/b12x/")
    target = SITE / relative
    assert not target.is_symlink()
    if hashes["before"] is None:
        assert not target.exists(), name
    else:
        assert sha(target) == hashes["before"], name
    assert sha(CONTEXT / "staged/site" / relative) == hashes["after"], name

(CONTEXT / "parent-external-receipt.json").write_bytes(parent)
shutil.copyfile(ROOT / "toolchain/installed.json", CONTEXT / "parent-toolchain-receipt.json")
for name, hashes in manifest["files"].items():
    target = SITE / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTEXT / "staged/site" / name, target)
    for pyc in target.parent.glob("__pycache__/" + target.stem + ".*.pyc"):
        pyc.unlink()
    record["files"][str(target)] = hashes["after"]

distribution = metadata.distribution("flashinfer-python")
records = [x for x in distribution.files if str(x).endswith(".dist-info/RECORD")]
assert len(records) == 1
record_path = Path(distribution.locate_file(records[0]))
with record_path.open(newline="") as stream:
    rows = list(csv.reader(stream))
matched = set()
for row in rows:
    target = Path(distribution.locate_file(row[0]))
    relative = str(target.relative_to(SITE)) if target.is_relative_to(SITE) else ""
    if relative in manifest["files"]:
        digest = base64.urlsafe_b64encode(bytes.fromhex(sha(target))).rstrip(b"=").decode()
        row[1:] = ["sha256=" + digest, str(target.stat().st_size)]
        matched.add(relative)
for name in sorted(set(manifest["files"]) - matched):
    assert manifest["files"][name]["before"] is None, name
    target = SITE / name
    digest = base64.urlsafe_b64encode(bytes.fromhex(sha(target))).rstrip(b"=").decode()
    rows.append([name, "sha256=" + digest, str(target.stat().st_size)])
with record_path.open("w", newline="") as stream:
    csv.writer(stream, lineterminator="\n").writerows(rows)
record["distribution_records"][str(record_path)] = sha(record_path)
if str(record_path) in record["files"]:
    record["files"][str(record_path)] = sha(record_path)

assert sha(transport_path) == transport_sha
for name, expected in transport["files"].items():
    assert sha(name) == expected, name
record["parent_composition_receipt_sha256"] = hashlib.sha256(parent).hexdigest()
record["composition_sha256"] = sha(CONTEXT / "staged/manifest.json")
record["sources"]["b12x_moe_backport"] = {
    "commit": manifest["upstream_commit"],
    "scope": "complete changed MoE implementation, quantization dependencies and preparation cache schema",
    "manifest_sha256": sha(CONTEXT / "staged/manifest.json"),
    "online_csf": False,
}
record["local_corrections"] += ["Coherent compact MXFP4 MoE backport, fresh schema-23 tuning required"]
record["serving_qualified"] = False
for path in CONTEXT.rglob("*"):
    if path.is_file() and path.suffix != ".pyc":
        record["files"][str(path)] = sha(path)
RECEIPT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

spec = importlib.util.spec_from_file_location("external", ROOT / "bin/external-base.py")
external = importlib.util.module_from_spec(spec)
spec.loader.exec_module(external)
(ROOT / "toolchain/installed.json").unlink()
print(json.dumps(external.verify()), flush=True)
