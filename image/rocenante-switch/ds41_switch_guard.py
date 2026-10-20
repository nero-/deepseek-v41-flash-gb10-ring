"""Select the verified FlashInfer RoCEnante provider in every Python worker."""
from __future__ import annotations

import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
MODE = "flashinfer-abi8-switched"
PACKAGE = "b12x.comm.roce"
PROVIDER = Path("/usr/local/lib/python3.12/dist-packages/flashinfer/experimental/b12x/comm/roce")


def check_files():
    data = json.loads((ROOT / "transport-manifest.json").read_text())
    for name, expected in data["files"].items():
        path = Path(name)
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Switched transport source differs: " + name)


class SourceLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        return self.source_to_code(self.get_data(self.path), self.path)


class ProviderFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != PACKAGE and not fullname.startswith(PACKAGE + "."):
            return None
        relative = fullname[len(PACKAGE):].lstrip(".").split(".")
        candidate = PROVIDER.joinpath(*relative) if relative != [""] else PROVIDER
        is_package = candidate.is_dir()
        source = candidate / "__init__.py" if is_package else candidate.with_suffix(".py")
        if not source.is_file():
            raise ImportError("Missing selected RoCEnante module: " + fullname)
        return importlib.util.spec_from_file_location(
            fullname, source, loader=SourceLoader(fullname, str(source)),
            submodule_search_locations=[str(candidate)] if is_package else None,
        )


def install():
    mode = os.getenv("DS41_ROCE_TRANSPORT", "")
    if not mode:  # Build-time verification needs no GPU/provider import.
        return
    try:
        if mode != MODE:
            raise RuntimeError("Unknown switched transport selection")
        for name in ("SPARKRING_TRANSPORT_PROFILE", "SPARKRING_TRANSPORT_MANIFEST_SHA256",
                     "B12X_ROCE_PEER_HCA_MAP", "B12X_ROCE_OPPOSITE_PATHS",
                     "NCCL_SWITCHLESS_RING_ONLY"):
            if os.getenv(name):
                raise RuntimeError("Remove ring-only environment setting: " + name)
        check_files()
        if any(isinstance(item, ProviderFinder) for item in sys.meta_path):
            return
        if any(key == PACKAGE or key.startswith(PACKAGE + ".") for key in sys.modules):
            raise RuntimeError("RoCEnante imported before selecting the switched provider")
        sys.meta_path.insert(0, ProviderFinder())
    except Exception as error:
        # Exceptions in .pth files are otherwise ignored by Python.
        raise SystemExit("Switched transport activation failed: " + str(error)) from error


def require_active():
    if os.getenv("DS41_ROCE_TRANSPORT") != MODE:
        raise RuntimeError("Serving requires explicit switched transport selection")
    if not sys.meta_path or not isinstance(sys.meta_path[0], ProviderFinder):
        raise RuntimeError("Switched transport finder is not active")
    check_files()
