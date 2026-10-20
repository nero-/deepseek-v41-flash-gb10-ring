#!/usr/bin/env python3
"""Stage a pinned, coherent MoE backport from locally audited source snapshots."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil

COMMIT = "a6b096f7b34dd0266af382a4ece59682676f6ece"
BASE_IMAGE = "sha256:9f26f0b3718ccca889cfd93cb72e2165b6d4c11dd9dc93fe65f585883537f2db"
EXTRA = {
    "_lib/quant/csf_blocks_tuning.py", "_lib/quant/nvfp4_csf.py",
    "_lib/quant/csf_encode.py", "_lib/quant/csf_inline.py",
    "preparation/_cache.py",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--installed", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--source-receipt", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    receipt = json.loads(a.source_receipt.read_text())
    assert receipt["commit"] == COMMIT
    assert not a.output.exists()
    before = {str(f.relative_to(a.installed)): f for f in a.installed.rglob("*") if f.is_file()}
    after = {str(f.relative_to(a.candidate)): f for f in a.candidate.rglob("*") if f.is_file()}
    selected = sorted(f for f in after if f.startswith("moe/") or f in EXTRA)
    assert not [f for f in before if (f.startswith("moe/") or f in EXTRA) and f not in after]
    manifest = {"schema": "ds41-moe-backport/v1", "base_image": BASE_IMAGE,
                "upstream_commit": COMMIT, "upstream_archive_sha256": receipt["archive_sha256"],
                "online_csf": False, "preparation_cache_schema": 23, "files": {}}
    for name in selected:
        source = after[name]
        assert not source.is_symlink() and ".." not in Path(name).parts
        old = digest(before[name]) if name in before else None
        new = digest(source)
        if old == new:
            continue
        if source.suffix == ".py":
            ast.parse(source.read_text(), filename=name)
        relative = "flashinfer/experimental/b12x/" + name
        target = a.output / "site" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest["files"][relative] = {"before": old, "after": new}
    assert len(manifest["files"]) == 29, len(manifest["files"])
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"files": len(manifest["files"]), "manifest_sha256": digest(a.output / "manifest.json")}))


if __name__ == "__main__":
    main()
