#!/usr/bin/env bash
# One measured configuration: quality gate (Mia's qeval, 75 tasks, c1, greedy) then LIL cases.
#   bench/evalrun.sh TAG [lil-cases]      (on gx10-r0; default cases: quick)
set -uo pipefail
TAG=$1; CASES=${2:-quick}
R=$HOME/bench/results; mkdir -p "$R"
Q=$HOME/dsv41-4x-spark/scripts
( cd "$R" && python3 "$Q/qeval.py" run "$TAG" --url http://192.168.50.219:8888/v1/chat/completions ) > "$R/$TAG-qeval.log" 2>&1
tail -3 "$R/$TAG-qeval.log"
if [[ $CASES == ring ]]; then
  python3 "$HOME/bench/ringbench.py" "$R/$TAG-ring.json" ${RING_ARGS:-} > "$R/$TAG-ring.log" 2>&1; echo "ring done: $R/$TAG-ring.json"
else
  bash "$HOME/bench/lilbench.sh" "$TAG" "$CASES"
fi
