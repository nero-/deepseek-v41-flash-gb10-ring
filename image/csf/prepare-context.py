#!/usr/bin/env python3
"""Reproduce the pinned, patched Python overlay without rebuilding native ABI."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        raise SystemExit("Destination must be new; refusing to overlay another build")
    destination.mkdir(parents=True)
    manifest = json.loads((HERE / "manifest.json").read_text())
    for package in ("b12x", "vllm"):
        checkout = destination / ("checkout-" + package)
        run("git", "clone", "--filter=blob:none", "--no-checkout",
            "https://github.com/local-inference-lab/" + package + ".git", str(checkout))
        run("git", "checkout", manifest[package], cwd=checkout)
        patch = HERE / (package + "-sparkring.patch")
        assert hashlib.sha256(patch.read_bytes()).hexdigest() == manifest[package + "_patch_sha256"]
        run("git", "apply", "--check", str(patch), cwd=checkout)
        run("git", "apply", str(patch), cwd=checkout)
        if package == "vllm":
            native = run("git", "diff", manifest["native_vllm_abi"]["baseline"],
                         manifest[package], "--", "csrc", "CMakeLists.txt", "cmake", "setup.py", cwd=checkout)
            assert not native, "Native ABI changed; compile a matching ARM64 wheel instead"
        paths = run("git", "ls-files", package, cwd=checkout).splitlines()
        if package == "b12x":
            paths += ["pyproject.toml", "README.md", "LICENSE"]
        for name in paths:
            source = checkout / name
            if source.is_file():
                target = destination / "src" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        shutil.rmtree(checkout)
    shutil.copytree(HERE / "local", destination / "src", dirs_exist_ok=True)
    for name in ("Dockerfile", "runtime.py", "manifest.json", "rebind-transport.py"):
        shutil.copyfile(HERE / name, destination / name)
    hashes = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in destination.rglob("*") if p.is_file()}
    (destination / "context-sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    print(destination)


if __name__ == "__main__":
    main()
