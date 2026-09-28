#!/usr/bin/env python3
"""Serial screening for one isolated research variant; persist exact commands."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

spec = importlib.util.spec_from_file_location("trial", Path(__file__).with_name("research-trial.py"))
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("variant", choices=trial.VARIANTS)
    p.add_argument("--ready", action="store_true")
    args = p.parse_args()
    if not args.ready:
        trial.start(args.variant)
    active = json.loads((trial.RESULTS / "active.json").read_text())
    assert active["variant"] == args.variant
    folder = Path(active["folder"])
    statuses = {}

    def run(name, rank, command, required=True):
        (folder / (name + "-command.json")).write_text(json.dumps({"rank": rank, "argv": command}, indent=2))
        result = trial.remote(rank, command, check=False)
        (folder / (name + ".log")).write_text(result.stdout + result.stderr)
        statuses[name] = result.returncode
        (folder / "statuses.json").write_text(json.dumps(statuses, indent=2))
        print(args.variant, name, result.returncode, flush=True)
        if required and result.returncode:
            raise RuntimeError(f"{name} failed: inspect {folder}")
        return result

    root = "/home/nero/sparkring-migration-20260927"
    run("functional", 0, ["python3", root + "/probes/functional.py", "http://127.0.0.1:8015/v1"])
    indexer = "indexer" in args.variant
    owned = args.variant.startswith("owned-")
    if indexer or owned or args.variant == "engram-readahead":
        smoke = run("needle", 0, ["python3", root + "/smoke.py", "--url", "http://127.0.0.1:8015", "--needle", "128000"], required=False)
        import re
        if not re.search(r"needle \d+ tokens: PASS", smoke.stdout):
            raise RuntimeError("Long-context retrieval did not pass")
        if indexer or owned:
            result = run("guards", 0, ["docker", "logs", active["names"][0]])
            marker = "context-indexer" if args.variant.startswith("context-indexer") else args.variant
            if args.variant.startswith("query-indexer-"):
                marker = "local-indexer-tp"
            if owned:
                marker = "owned-mhc"
            lines = [line for line in (result.stdout + result.stderr).splitlines() if "[" + marker + "]" in line]
            counts = {"enabled": sum("exact=ON" in line for line in lines), "disabled": sum("exact=OFF" in line for line in lines)}
            (folder / "guards.json").write_text(json.dumps({**counts, "lines": lines}, indent=2))
            if not counts["enabled"]:
                (folder / "decision.json").write_text(json.dumps({"decision": "not selected", "reason": "no real-input geometry passed exactness guard", **counts}, indent=2))
                print("REJECTED", args.variant, "no exact geometry", flush=True)
                return
            if indexer or args.variant == "owned-residual":
                source = (trial.ROOT / "bench/cold-needle.py").read_text()
                dest = trial.REMOTE + "/cold-needle.py"
                trial.remote(0, ["python3", "-c", "import sys;from pathlib import Path;Path(sys.argv[1]).write_text(sys.stdin.read())", dest], source)
                for size in ([256000, 1048576] if indexer else [256000]):
                    label = "cold-256k" if size == 256000 else "cold-1m"
                    output = trial.REMOTE + "/" + args.variant + "-" + label + ".json"
                    run(label, 0, ["python3", dest, "--tokens", str(size), "--output", output])
                    (folder / (label + ".json")).write_text(trial.remote(0, ["cat", output]).stdout)
    if args.variant == "timed-prefill":
        output = trial.REMOTE + "/mixed-timed-prefill.json"
        run("mixed", 0, ["python3", root + "/mixed_traffic.py", "research-timed-prefill", "--output", output])
        (folder / "mixed.json").write_text(trial.remote(0, ["cat", output]).stdout)
        run("mixed-integrity", 0, ["python3", root + "/mixed_traffic.py", "research-timed-prefill-integrity", "--rounds", "1", "--integrity", "--output", output + ".integrity"])
        (folder / "mixed-integrity.json").write_text(trial.remote(0, ["cat", output + ".integrity"]).stdout)
    if args.variant == "owned-residual":
        output = trial.REMOTE + "/owned-residual-mixed-integrity.json"
        run("mixed-integrity", 0, ["python3", root + "/mixed_traffic.py", "research-owned-residual-integrity", "--rounds", "1", "--integrity", "--output", output])
        (folder / "mixed-integrity.json").write_text(trial.remote(0, ["cat", output]).stdout)
    if args.variant.endswith("-auto"):
        source = (trial.ROOT / "bench/long-functional.py").read_text()
        dest = trial.REMOTE + "/long-functional.py"
        trial.remote(0, ["python3", "-c", "import sys;from pathlib import Path;Path(sys.argv[1]).write_text(sys.stdin.read())", dest], source)
        (folder / "long-functional.py").write_text(source)
        output = trial.REMOTE + "/" + args.variant + "-long-functional.json"
        run("long-functional", 0, ["python3", dest, "--suite", root + "/probes/functional.py", "--output", output])
        (folder / "long-functional.json").write_text(trial.remote(0, ["cat", output]).stdout)
        output = trial.REMOTE + "/" + args.variant + "-mixed.json"
        run("mixed", 0, ["python3", root + "/mixed_traffic.py", "research-" + args.variant, "--output", output])
        (folder / "mixed.json").write_text(trial.remote(0, ["cat", output]).stdout)
        # Exercise the optimized path under contention, beyond its 8K
        # compressed-position threshold. Keep the ordinary three-round latency
        # workload unchanged for its baseline comparison.
        mixed_source = (trial.ROOT / "bench/mixed_traffic.py").read_text()
        mixed_dest = trial.REMOTE + "/mixed_traffic.py"
        trial.remote(0, ["python3", "-c", "import sys;from pathlib import Path;Path(sys.argv[1]).write_text(sys.stdin.read())", mixed_dest], mixed_source)
        (folder / "mixed_traffic.py").write_text(mixed_source)
        run("mixed-integrity", 0, ["python3", mixed_dest, "research-" + args.variant + "-integrity", "--rounds", "1", "--integrity", "--prefill-records", "6144", "--min-uncached-tokens", "65536", "--output", output + ".integrity"])
        (folder / "mixed-integrity.json").write_text(trial.remote(0, ["cat", output + ".integrity"]).stdout)
    tag = "research-" + args.variant + "-20260928"
    run("tune", 3, ["env", "MATCHED=1", "bash", "/home/nero/bench/lilbench.sh", tag, "tune"])
    for suffix in (".json", ".matched-request.json", "-command.txt"):
        data = trial.remote(3, ["cat", "/home/nero/bench/results/" + tag + "-tune" + suffix]).stdout
        (folder / ("tune" + suffix)).write_text(data)
    if args.variant.startswith("markov-shortlist"):
        quality_tag = "research-" + args.variant
        run("quality", 0, ["env", "PYTHONPATH=" + root + "/baseline", "python3", root + "/baseline/qeval.py", "run", quality_tag, "--url", "http://127.0.0.1:8015/v1/chat/completions"])
        (folder / "quality.json").write_text(trial.remote(0, ["cat", "/home/nero/qeval-" + quality_tag + ".json"]).stdout)
    if indexer or owned:
        result = run("guards-final", 0, ["docker", "logs", active["names"][0]])
        lines = [line for line in (result.stdout + result.stderr).splitlines() if "[" + marker + "]" in line]
        (folder / "guards-final.json").write_text(json.dumps({
            "enabled": sum("exact=ON" in line for line in lines),
            "disabled": sum("exact=OFF" in line for line in lines), "lines": lines}, indent=2))
        if args.variant.endswith("-auto"):
            startup = next((i for i, line in enumerate(lines) if "worker startup complete" in line), None)
            first_real = next((i for i, line in enumerate(lines) if "first real request observed" in line), None)
            first_guard = next((i for i, line in enumerate(lines) if "exact=" in line), None)
            gated = startup is not None and first_real is not None and first_guard is not None and startup < first_real < first_guard
            (folder / "startup-gate.json").write_text(json.dumps({
                "startup_complete_line": startup, "first_real_line": first_real, "first_guard_line": first_guard,
                "startup_complete_before_real_request": gated,
                "real_request_before_guards": gated}, indent=2))
            if not gated:
                raise RuntimeError("Request-based startup gate was not observed before numerical guards")
    print("SCREEN COMPLETE", args.variant, folder, flush=True)


if __name__ == "__main__":
    main()
