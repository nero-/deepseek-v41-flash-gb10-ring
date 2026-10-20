#!/usr/bin/env python3
"""Stage pinned source changes for a switched RoCEnante candidate, without installing.

Writes four replacement source files, their before/after hashes and unified
diffs to a new output directory. This does not build an image or touch the fleet.
"""

from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import difflib
import hashlib
import json
from pathlib import Path
import urllib.request

VLLM = "8244d1c44348ae8a5bbfc9f1b607021652283ed4"
FI = "91271757f7746f3dfb58f7c2aeb44a663389de9e"
FIX = "f3bbd1ce79cb9a62afb88b367580b0583db167ee"
ADAPTER = "vllm/distributed/device_communicators/b12x_roce_all_reduce.py"
TRANSPORT = "flashinfer/experimental/b12x/comm/roce/"
ADAPTER_SHA = "cca86b8c97d96b3647e4ef3f90f9638ebc4d8b5dfc1673abc2e5a7750bed9018"
FIX_HASHES = {
    "_proxy.py": (
        "ae1ba421414272302a501f7d2f070b46bce742884d798f0afe9bc5e82c02cfc0",
        "e1cf801788d1bf5e73ef42f416da854923cc844df1792b79af020dee587c9680",
    ),
    "_roce_proxy.c": (
        "7d5e2f1c719275c230725a4353ca1b47ce38a7266d9eefa24074def21fe9900a",
        "d60adff67f215e313db5760450d947d1d173be4b230273269b27d7341ba1a046",
    ),
    "_twoshot_cute.py": (
        "4319525816ad8e5a92db370a7f9ee4322612f01920ba74d0d9c3747d3156ae97",
        "bd064a007f9ef4100afcd99a6140c9790c78e02a79dcf9eab1dd59ec2ec404b9",
    ),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(repo: str, commit: str, path: str, expected: str) -> bytes:
    url = f"https://raw.githubusercontent.com/local-inference-lab/{repo}/{commit}/{path}"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read()
    if sha(data) != expected:
        raise ValueError(f"Upstream preimage differs: {url}")
    return data


def patch_adapter(before: bytes) -> bytes:
    if sha(before) != ADAPTER_SHA:
        raise ValueError("Unsupported vLLM adapter preimage")
    source = before.decode()

    def replace(old: str, new: str, count: int = 1) -> None:
        nonlocal source
        if source.count(old) != count:
            raise ValueError(f"Unexpected adapter match count: {old!r}")
        source = source.replace(old, new)

    replace("from collections.abc import Sequence\n", "import os\nfrom collections.abc import Sequence\n")
    replace(
        "REQUIRED_B12X_ROCE_API_VERSION = 1\n",
        '''REQUIRED_B12X_ROCE_API_VERSION = 1


def _two_shot_limits(world_size: int) -> tuple[int, int]:
    """Local experimental knobs; not upstream vLLM environment variables."""
    capacity = _parse_byte_size(os.getenv("DS41_ROCE_PIPE_BYTES", "0"))
    default_threshold = "2MiB" if world_size == 2 else "1MiB"
    threshold = _parse_byte_size(
        os.getenv("DS41_ROCE_PIPE_THRESHOLD", default_threshold)
    )
    if capacity < 0 or capacity % 16:
        raise ValueError("DS41_ROCE_PIPE_BYTES must be a non-negative multiple of 16")
    if threshold < 16 or threshold % 16:
        raise ValueError("DS41_ROCE_PIPE_THRESHOLD must be a positive multiple of 16")
    if capacity and threshold > capacity:
        raise ValueError("DS41_ROCE_PIPE_THRESHOLD exceeds the pipe capacity")
    return capacity, threshold
''',
    )
    replace("self._announced = False", "self._announced_routes: set[str] = set()")
    replace("max_size, max_gather = limits", "max_size, max_gather, pipe_bytes, pipe_threshold = limits")
    # The compatibility classmethod discards pipe_* in **_ignored. Use the
    # constructor used by upstream's two-shot tests, still with the Gloo group.
    replace("roce.AllReduce.from_exchange_group(", "roce.AllReduce(")
    replace(
        "                max_gather_bytes=max_gather,\n",
        "                max_gather_bytes=max_gather,\n"
        "                pipe_bytes=pipe_bytes,\n"
        "                pipe_threshold=pipe_threshold,\n",
    )
    replace(
        '"Using RoCEnante (b12x one-shot RoCE collectives): world=%d, hcas=%s, "\n'
        '                "all-reduce max=%d bytes, all-gather shard max=%d bytes.",',
        '"Using RoCEnante: world=%d, hcas=%s, one-shot max=%d bytes, "\n'
        '                "all-gather shard max=%d bytes, two-shot capacity=%d bytes, "\n'
        '                "two-shot threshold=%d bytes.",',
    )
    replace(
        "                max_gather,\n            )",
        "                max_gather,\n                pipe_bytes,\n"
        "                pipe_threshold,\n            )",
    )
    replace("tuple[int, int] | None", "tuple[int, int, int, int] | None", count=3)
    replace(
        "_parse_byte_size(envs.VLLM_ROCE_ALLGATHER_MAX_SIZE),\n            )",
        "_parse_byte_size(envs.VLLM_ROCE_ALLGATHER_MAX_SIZE),\n"
        "                *_two_shot_limits(self.world_size),\n"
        "            )\n"
        "            if limits[2]:\n"
        "                from b12x.comm.roce import _proxy\n\n"
        "                if _proxy.ABI_VERSION != 8:\n"
        '                    raise ValueError("Two-shot candidate requires fixed proxy ABI 8")',
    )
    replace(
        '            calls = [\n                _preparation.prepared_call(state, inp=buffer)',
        '            if self._runtime.pipe_bytes:\n'
        '                # Execute each two-shot dtype before graph capture, not only\n'
        '                # its tiny one-shot counterpart. The plan compiles both.\n'
        '                prime_bytes = self._runtime.pipe_threshold\n'
        '                buffers.extend(\n'
        '                    torch.zeros(prime_bytes // dtype.itemsize, dtype=dtype,\n'
        '                                device=self.device)\n'
        '                    for dtype in (torch.float16, torch.bfloat16, torch.float32)\n'
        '                )\n'
        '            calls = [\n                _preparation.prepared_call(state, inp=buffer)',
    )
    replace(
        "        if not self._announced:\n            self._announced = True",
        '        nbytes = inp.numel() * inp.element_size()\n'
        '        route = "two-shot" if self._runtime._uses_pipe(nbytes) else "one-shot"\n'
        '        if route not in self._announced_routes:\n'
        '            self._announced_routes.add(route)',
    )
    replace(
        '"RoCEnante all-reduce is live: first routed all-reduce is %d bytes "\n'
        '                "(%s); NCCL remains the fallback above %s.",\n'
        '                inp.numel() * inp.element_size(),\n'
        '                str(inp.dtype).replace("torch.", ""),\n'
        '                envs.VLLM_ROCE_ALLREDUCE_MAX_SIZE,',
        '"RoCEnante %s is live: first routed all-reduce is %d bytes "\n'
        '                "(%s); NCCL fallback above %d bytes or for unsupported inputs.",\n'
        '                route,\n'
        '                nbytes,\n'
        '                str(inp.dtype).replace("torch.", ""),\n'
        '                max(self._runtime.max_size, self._runtime.pipe_bytes),',
    )
    source = source.replace(
        "``(max_size, max_gather)``",
        "``(max_size, max_gather, pipe_bytes, pipe_threshold)``",
    )
    ast.parse(source)
    return source.encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new staging directory")

    before = fetch("vllm", VLLM, ADAPTER, ADAPTER_SHA)
    changes = [(ADAPTER, before, patch_adapter(before))]

    def fixed_file(item):
        name, (before_sha, after_sha) = item
        path = TRANSPORT + name
        return (
            path,
            fetch("flashinfer", FI, path, before_sha),
            fetch("flashinfer", FIX, path, after_sha),
        )

    with ThreadPoolExecutor(3) as pool:
        changes.extend(pool.map(fixed_file, FIX_HASHES.items()))
    # Fetch/validate everything before creating the staging artifact.
    args.output.mkdir(parents=True)
    manifest = {
        "schema": "ds41-rocenante-switch-source-candidate/v1",
        "vllm": VLLM, "flashinfer_base": FI, "transport_fix": FIX,
        "stage_script_sha256": sha(Path(__file__).read_bytes()),
        "installed": False, "gpu_qualified": False,
        "requires": [
            "Unshadow FlashInfer RoCEnante with a new verified image composition",
            "Keep all remaining base transport files and preparation APIs together",
            "Rebuild proxy/CuTe caches and verify imports in spawned workers",
            "Run four-rank eager/graph/numerical/timeout tests before model use",
        ],
        "files": {},
    }
    patches = []
    for path, old, new in changes:
        if path.endswith(".py"):
            ast.parse(new)
        dest = args.output / "site" / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(new)
        manifest["files"][path] = {"before": sha(old), "after": sha(new)}
        patches.extend(difflib.unified_diff(
            old.decode().splitlines(keepends=True),
            new.decode().splitlines(keepends=True),
            fromfile="a/" + path, tofile="b/" + path,
        ))
    (args.output / "candidate.patch").write_text("".join(patches))
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"staged": str(args.output), "files": len(changes),
                      "installed": False, "gpu_qualified": False}))


if __name__ == "__main__":
    main()
