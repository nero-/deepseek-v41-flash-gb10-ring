"""Create a new composition receipt from the verified October 17 parent."""
import csv
import base64
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
CONTEXT = ROOT / "switched-20261020"
SITE = Path("/usr/local/lib/python3.12/dist-packages")
RECEIPT = ROOT / "receipts/external-base-installed.json"
assert platform.machine() == "aarch64"
subprocess.run([sys.executable, str(ROOT / "toolchain/toolchain.py"), "verify"], check=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


spec = importlib.util.spec_from_file_location("external", ROOT / "bin/external-base.py")
external = importlib.util.module_from_spec(spec)
spec.loader.exec_module(external)
parent_bytes = RECEIPT.read_bytes()
record = json.loads(parent_bytes)
assert record["sources"]["vllm"]["commit"] == "8244d1c44348ae8a5bbfc9f1b607021652283ed4"
assert record["sources"]["b12x"]["commit"] == "91271757f7746f3dfb58f7c2aeb44a663389de9e"
assert record["capabilities"]["transport_profile"] == "tp2-rocenante-adaptive-prepared"
manifest = json.loads((CONTEXT / "staged/manifest.json").read_text())
assert manifest["transport_fix"] == "f3bbd1ce79cb9a62afb88b367580b0583db167ee"
assert len(manifest["files"]) == 4
for name, hashes in manifest["files"].items():
    path = Path(name)
    assert not path.is_absolute() and ".." not in path.parts
    target = SITE / path
    assert not target.is_symlink()
    assert sha(target) == hashes["before"], name
    assert sha(CONTEXT / "staged/site" / path) == hashes["after"], name

# Save the genuine parent receipts before creating the new, distinct receipt.
(CONTEXT / "parent-external-receipt.json").write_bytes(parent_bytes)
shutil.copyfile(ROOT / "toolchain/installed.json", CONTEXT / "parent-toolchain-receipt.json")
for name, hashes in manifest["files"].items():
    target = SITE / name
    shutil.copyfile(CONTEXT / "staged/site" / name, target)
    for bytecode in target.parent.glob("__pycache__/" + target.stem + ".*.pyc"):
        bytecode.unlink()
    record["files"][str(target)] = hashes["after"]

# The former bundle stays as inert parent history; its import hook is removed.
old_hook = SITE / "sparkring_transport.pth"
assert str(old_hook) in record["files"]
old_hook.unlink()
record["files"].pop(str(old_hook))
record["removed_files"].append(str(old_hook))
new_hook = SITE / "ds41_switched_transport.pth"
assert not new_hook.exists()
new_hook.write_text(
    str(CONTEXT) + "\nimport ds41_switch_guard; ds41_switch_guard.install()\n"
)

# Update only the changed distribution records, using actual installed paths.
for distribution_name in ("vllm", "flashinfer-python"):
    distribution = metadata.distribution(distribution_name)
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
    expected = {name for name in manifest["files"]
                if name.startswith("vllm/" if distribution_name == "vllm" else "flashinfer/")}
    assert matched == expected, (distribution_name, matched, expected)
    with record_path.open("w", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerows(rows)
    record["distribution_records"][str(record_path)] = sha(record_path)
    if str(record_path) in record["files"]:
        record["files"][str(record_path)] = sha(record_path)

provider = SITE / "flashinfer/experimental/b12x/comm/roce"
transport_files = {str(p): sha(p) for p in sorted(provider.rglob("*"))
                   if p.is_file() and p.suffix != ".pyc"}
adapter = SITE / "vllm/distributed/device_communicators/b12x_roce_all_reduce.py"
transport_files[str(adapter)] = sha(adapter)
transport_manifest = {
    "schema": "ds41-switched-provider/v1",
    "profile": "flashinfer-abi8-switched",
    "base_commit": manifest["flashinfer_base"],
    "fix_commit": manifest["transport_fix"],
    "proxy_abi": 8, "files": transport_files,
}
(CONTEXT / "transport-manifest.json").write_text(json.dumps(transport_manifest, indent=2) + "\n")
record["parent_composition_receipt_sha256"] = hashlib.sha256(parent_bytes).hexdigest()
record["composition_sha256"] = sha(CONTEXT / "staged/manifest.json")
record["capabilities"].update(
    transport_profile="flashinfer-abi8-switched",
    transport_manifest_sha256=sha(CONTEXT / "transport-manifest.json"),
)
record["sources"]["rocenante_transport"] = {
    "base_commit": manifest["flashinfer_base"], "fix_commit": manifest["transport_fix"],
    "adapter": "local two-shot capacity, agreement, preparation and dispatch integration",
}
record["local_corrections"] += [
    "Unshadow FlashInfer switched RoCEnante provider",
    "ABI-8 two-shot send-buffer lifetime fix",
    "Explicit vLLM two-shot integration",
]
record["serving_qualified"] = False
for p in CONTEXT.rglob("*"):
    if p.is_file() and p.suffix != ".pyc":
        record["files"][str(p)] = sha(p)
record["files"][str(new_hook)] = sha(new_hook)
RECEIPT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
# Re-seal against this composition; retain the old seal in the context above.
(ROOT / "toolchain/installed.json").unlink()
print(json.dumps(external.verify()), flush=True)
