"""Retain the qualified toolchain verifier and require the switched provider."""
import os
import sys

if len(sys.argv) > 1 and sys.argv[1] == "serve":
    from ds41_switch_guard import require_active
    require_active()
argv = [sys.executable, "/opt/sparkring/toolchain/toolchain.py", *sys.argv[1:]]
os.execve(argv[0], argv, os.environ)
