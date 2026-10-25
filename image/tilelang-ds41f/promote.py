#!/usr/bin/env python3
"""Install, or roll back, the TileLang selection under the root controller.

install   requires the trial interlock and a stopped fleet apart from the
          ds41f-tilelang-rN trial containers. Renames the previous canonical
          containers to ds41-before-tilelang-rN, backs up the installed
          selection as optimized-specs.pre-tilelang-20261024.json, installs the
          new root-owned selection, archives the interlock and runs the normal
          fixed-action `deepseek-ring-control up`.
rollback  the exact reverse: controller down, new containers renamed to
          ds41-tilelang-rN, previous containers and selection restored, up.
reselect  after a rollback, swap back: the TileLang containers and selection
          return as ds41-optimized-rN and the B12X ones as ds41-before-tilelang-rN.

Root writes run in a network-less container with /etc/deepseek-ring mounted,
as earlier campaigns did; nothing else on the hosts is changed.
"""
import argparse
import datetime
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import fleet  # noqa: E402

FALLBACK_IMAGE = "sha256:9f26f0b3718ccca889cfd93cb72e2165b6d4c11dd9dc93fe65f585883537f2db"
PREVIOUS_SHA256 = "c87a397ccc4614c6f3fee59e566bb7599e7165c80e858bb12c84d78ef5e27775"
BACKUP = "optimized-specs.pre-tilelang-20261024.json"
STAGE = "/home/nero/ds41f-tilelang-20261024"
MARKER_ARCHIVE = "DS41F_TILELANG_20261024.finished.json"
TRIAL = "ds41f-tilelang-r{rank}"
CANONICAL = "ds41-optimized-r{rank}"
PREVIOUS = "ds41-before-tilelang-r{rank}"
RETIRED = "ds41-tilelang-r{rank}"
STAGED_SECCOMP = f"{STAGE}/seccomp.json"
SECCOMP = ("/srv/sparkring/sparkring/deepseek-v41-flash-tp4-iba1b36389e5d/source-8b152d65c701/"
           "runtime/common/loader-seccomp.json")


def log(*parts):
    print(datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%SZ"), *parts, flush=True)


def save(directory: Path, name: str, value: dict):
    with (directory / name).open("x") as f:
        json.dump({"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), **value}, f, indent=2)
        f.write("\n")


def running(rank):
    return fleet.remote(rank, ["docker", "ps", "--format", "{{.Names}}"]).stdout.split()


def names(rank):
    return fleet.remote(rank, ["docker", "ps", "-a", "--format", "{{.Names}}"]).stdout.split()


def root(code: str, timeout=120):
    """Python as root on spark-r0 with /etc/deepseek-ring at /control and the stage read-only."""
    r = fleet.remote(0, ["docker", "run", "--rm", "--network", "none", "--entrypoint", "python3",
                         "-v", "/etc/deepseek-ring:/control", "-v", f"{STAGE}:/stage:ro",
                         "-v", f"{SECCOMP}:/seccomp/production.json:ro", FALLBACK_IMAGE, "-c", code],
                     check=False)
    if r.returncode:
        raise SystemExit(f"root step failed: {r.stderr[-3000:]}")
    return r.stdout


def health():
    try:
        with urllib.request.urlopen("http://192.168.50.219:8015/health", timeout=5) as response:
            return response.status
    except OSError:
        return None


def controller(action, timeout=2500):
    r = fleet.remote(0, ["sudo", "-n", "/usr/local/sbin/deepseek-ring-control", action], check=False)
    return r


def identities(prefix):
    def one(rank):
        info = json.loads(fleet.remote(rank, ["docker", "inspect", prefix.format(rank=rank)]).stdout)[0]
        return {"rank": rank, "id": info["Id"], "image": info["Image"], "running": info["State"]["Running"]}
    return fleet.parallel(one)


def install(args):
    out = args.receipts
    out.mkdir(parents=True, exist_ok=True)
    selection = Path(args.selection).read_bytes()
    digest = hashlib.sha256(selection).hexdigest()
    document = json.loads(selection)
    image = document["specs"][0]["image_id"]
    assert fleet.remote(0, ["test", "-e", "/etc/deepseek-ring/FLARE_STAGING.json"], check=False).returncode == 0, \
        "the trial interlock must own the fleet"
    for rank in range(4):
        assert set(running(rank)) <= {TRIAL.format(rank=rank)}, (rank, running(rank))
        assert PREVIOUS.format(rank=rank) not in names(rank), f"rank {rank}: {PREVIOUS} already exists"
        fleet.remote(rank, ["docker", "image", "inspect", image])
    fleet.remote(0, ["bash", "-c", f"cat > {STAGE}/optimized-specs.json"], data=selection.decode())
    # Read-only checks first, so a mismatch leaves every container and file untouched.
    print(root(f'''
import hashlib, json
from pathlib import Path
assert hashlib.sha256(Path("/control/optimized-specs.json").read_bytes()).hexdigest() == {PREVIOUS_SHA256!r}
assert hashlib.sha256(Path("/stage/optimized-specs.json").read_bytes()).hexdigest() == {digest!r}
assert json.loads(Path("/stage/seccomp.json").read_text()) == json.loads(Path("/seccomp/production.json").read_text())
assert not Path("/control/{BACKUP}").exists() and not Path("/control/{MARKER_ARCHIVE}").exists()
print("preconditions verified")
'''))
    log("STOPPING_TRIAL_CONTAINERS")
    fleet.parallel(lambda rank: fleet.remote(rank, ["docker", "stop", "--time", "30", TRIAL.format(rank=rank)],
                                             check=False))
    assert not any(fleet.parallel(running)), "containers still running"
    previous = identities(CANONICAL)
    assert all(p["image"] == FALLBACK_IMAGE and not p["running"] for p in previous), previous
    fleet.parallel(lambda rank: fleet.remote(rank, ["docker", "rename", CANONICAL.format(rank=rank),
                                                    PREVIOUS.format(rank=rank)]))
    log("PREVIOUS_CONTAINERS_RENAMED", PREVIOUS)
    print(root(f'''
import hashlib, json, os, datetime
from pathlib import Path
control = Path("/control")
current = (control / "optimized-specs.json").read_bytes()
assert hashlib.sha256(current).hexdigest() == {PREVIOUS_SHA256!r}, "installed selection changed"
staged = Path("/stage/optimized-specs.json").read_bytes()
assert hashlib.sha256(staged).hexdigest() == {digest!r}
assert json.loads(Path("/stage/seccomp.json").read_text()) == json.loads(Path("/seccomp/production.json").read_text()), \
    "the trial seccomp copy differs from the production profile"
backup = control / {BACKUP!r}
with backup.open("xb") as f:
    f.write(current)
os.chmod(backup, 0o644)
temporary = control / ".optimized-specs.json.new"
temporary.write_bytes(staged)
os.chown(temporary, 0, 0); os.chmod(temporary, 0o644)
os.replace(temporary, control / "optimized-specs.json")
marker = control / "FLARE_STAGING.json"
record = json.loads(marker.read_text())
assert record["owner"].startswith("DS41-ds41f-tilelang"), record
record.update(finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              outcome="promoted: TileLang selection installed as the controller default",
              selection_sha256={digest!r})
archive = control / {MARKER_ARCHIVE!r}
with archive.open("x") as f:
    json.dump(record, f, indent=2); f.write("\\n")
os.chmod(archive, 0o644)
marker.unlink()
print("selection installed; interlock archived")
'''))
    save(out, "install.json", {"selection_sha256": digest, "previous_selection_sha256": PREVIOUS_SHA256,
                               "backup": f"/etc/deepseek-ring/{BACKUP}", "previous_containers": previous,
                               "archived_interlock": f"/etc/deepseek-ring/{MARKER_ARCHIVE}"})
    log("CONTROLLER_UP")
    started = time.time()
    up = controller("up")
    save(out, "controller-up.json", {"returncode": up.returncode, "elapsed_seconds": time.time() - started,
                                     "stdout": up.stdout[-4000:], "stderr": up.stderr[-4000:]})
    if up.returncode:
        raise SystemExit(f"controller up failed; inspect logs, then `promote.py rollback`: {up.stderr[-1500:]}")
    new = identities(CANONICAL)
    assert all(n["image"] == image and n["running"] for n in new) and health() == 200, new
    installed = hashlib.sha256(fleet.remote(0, ["cat", "/etc/deepseek-ring/optimized-specs.json"]).stdout.encode())
    assert installed.hexdigest() == digest
    save(out, "promoted.json", {"selection_sha256": digest, "containers": new, "api_health": 200})
    log("TILELANG_SELECTION_SERVING", digest)


def rollback(args):
    out = args.receipts
    out.mkdir(parents=True, exist_ok=True)
    for rank in range(4):
        assert PREVIOUS.format(rank=rank) in names(rank), f"rank {rank}: no {PREVIOUS} to restore"
        assert RETIRED.format(rank=rank) not in names(rank), f"rank {rank}: {RETIRED} already exists"
    down = controller("down")
    assert down.returncode == 0, down.stderr
    assert not any(fleet.parallel(running)), "containers still running"
    fleet.parallel(lambda rank: fleet.remote(rank, ["docker", "rename", CANONICAL.format(rank=rank),
                                                    RETIRED.format(rank=rank)]))
    fleet.parallel(lambda rank: fleet.remote(rank, ["docker", "rename", PREVIOUS.format(rank=rank),
                                                    CANONICAL.format(rank=rank)]))
    print(root(f'''
import hashlib, os
from pathlib import Path
control = Path("/control")
backup = (control / {BACKUP!r}).read_bytes()
assert hashlib.sha256(backup).hexdigest() == {PREVIOUS_SHA256!r}
temporary = control / ".optimized-specs.json.old"
temporary.write_bytes(backup)
os.chown(temporary, 0, 0); os.chmod(temporary, 0o644)
os.replace(temporary, control / "optimized-specs.json")
print("previous selection restored")
'''))
    up = controller("up")
    save(out, "rollback.json", {"returncode": up.returncode, "stdout": up.stdout[-4000:],
                                "stderr": up.stderr[-4000:]})
    assert up.returncode == 0 and health() == 200, up.stderr[-1500:]
    log("PREVIOUS_SELECTION_SERVING", PREVIOUS_SHA256)


def reselect(args):
    """Return to the TileLang selection after a rollback: the reverse of rollback."""
    out = args.receipts
    out.mkdir(parents=True, exist_ok=True)
    selection = Path(args.selection).read_bytes()
    digest = hashlib.sha256(selection).hexdigest()
    installed = hashlib.sha256(fleet.remote(0, ["cat", "/etc/deepseek-ring/optimized-specs.json"]).stdout.encode())
    assert installed.hexdigest() == PREVIOUS_SHA256, "the B12X selection is not the installed one"
    for rank in range(4):
        assert RETIRED.format(rank=rank) in names(rank), f"rank {rank}: no {RETIRED} to reselect"
        assert PREVIOUS.format(rank=rank) not in names(rank), f"rank {rank}: {PREVIOUS} already exists"
    fleet.remote(0, ["bash", "-c", f"cat > {STAGE}/optimized-specs.json"], data=selection.decode())
    print(root(f'''
import hashlib
from pathlib import Path
assert hashlib.sha256(Path("/stage/optimized-specs.json").read_bytes()).hexdigest() == {digest!r}
print("staged TileLang selection verified")
'''))
    down = controller("down")
    assert down.returncode == 0, down.stderr
    assert not any(fleet.parallel(running)), "containers still running"
    fleet.parallel(lambda rank: fleet.remote(rank, ["docker", "rename", CANONICAL.format(rank=rank),
                                                    PREVIOUS.format(rank=rank)]))
    fleet.parallel(lambda rank: fleet.remote(rank, ["docker", "rename", RETIRED.format(rank=rank),
                                                    CANONICAL.format(rank=rank)]))
    print(root(f'''
import os
from pathlib import Path
control = Path("/control")
temporary = control / ".optimized-specs.json.new"
temporary.write_bytes(Path("/stage/optimized-specs.json").read_bytes())
os.chown(temporary, 0, 0); os.chmod(temporary, 0o644)
os.replace(temporary, control / "optimized-specs.json")
print("TileLang selection reinstalled")
'''))
    started = time.time()
    up = controller("up")
    save(out, "reselect.json", {"returncode": up.returncode, "elapsed_seconds": time.time() - started,
                                "selection_sha256": digest, "stdout": up.stdout[-4000:], "stderr": up.stderr[-4000:]})
    assert up.returncode == 0 and health() == 200, up.stderr[-1500:]
    log("TILELANG_SELECTION_SERVING", digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    one = sub.add_parser("install")
    one.add_argument("--selection", required=True, help="output of selection.py")
    one.add_argument("--receipts", type=Path, required=True)
    two = sub.add_parser("rollback")
    two.add_argument("--receipts", type=Path, required=True)
    three = sub.add_parser("reselect")
    three.add_argument("--selection", required=True, help="the TileLang selection (sha 4d2bc32e...)")
    three.add_argument("--receipts", type=Path, required=True)
    args = parser.parse_args()
    {"install": install, "rollback": rollback, "reselect": reselect}[args.action](args)


if __name__ == "__main__":
    main()
