"""Run a diagnostic under the same verified CUDA/NCCL environment as serving."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

path = Path('/opt/sparkring/toolchain/toolchain.py')
spec = importlib.util.spec_from_file_location('toolchain', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
lock = json.loads(path.with_name('toolchain.json').read_text())
environment = module.configure_environment(lock, os.environ)
if any(os.environ.get(k) != v for k, v in environment.items()):
    os.execve(sys.executable, [sys.executable, __file__, *sys.argv[1:]], environment)
subprocess.run([sys.executable, str(path), 'verify'], check=True)
assert len(sys.argv) > 1
os.execvpe(sys.argv[1], sys.argv[1:], environment)
