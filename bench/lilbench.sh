#!/usr/bin/env bash
# Run local-inference-lab/llm-inference-bench v0.6.2 (ccd9ad8) against the DeepSeek head, with the
# same case definitions as the Qwen TP2 campaign so results compare directly.
#
#   bench/lilbench.sh TAG case[,case...]      (run on gx10-r0, a worker; results in ~/bench/results)
#
# Cases: quick (A/B screening), matrix, c16, coding, prose, hiconc (C1/C16/C32 at 8k/32k),
#        full (8k-128k x C1-C16 + prefill to 128k).
set -euo pipefail
TAG=$1; CASES=$2
HOST=${HOST:-192.168.50.219} PORT=${PORT:-8888} MODEL=${MODEL:-deepseek-v4.1-flash}
B=$HOME/bench; OUT=$B/results; mkdir -p "$OUT"
common=("$B/.venv/bin/python" -u "$B/llm-inference-bench/llm_decode_bench.py"
        --host "$HOST" --port "$PORT" --model "$MODEL" --no-hw-monitor --display-mode plain --no-resume)
prose="Write a detailed step-by-step explanation of how a hash map works, including collision handling, resizing, and time complexity. Be thorough."
for c in ${CASES//,/ }; do
  case $c in
    quick)  o=(--contexts 8192 --concurrency 1,8 --duration 20 --max-tokens 2048 --standalone-prefill --prefill-contexts 8k,64k) ;;
    matrix) o=(--contexts 8192,32768,65536 --concurrency 1,8 --duration 30 --max-tokens 2048 --standalone-prefill --prefill-contexts 8k,32k,64k) ;;
    c16)    o=(--skip-prefill --contexts 8192,32768 --concurrency 16 --duration 30 --max-tokens 2048) ;;
    coding) o=(--skip-prefill --contexts 8192 --concurrency 1 --duration 15 --max-tokens 2048 --coding-peak --coding-peak-runs 3 --coding-peak-max-tokens 2000) ;;
    prose)  o=(--completion-stats --prompt "$prose" --profile-concurrency 1 --profile-runs 5 --max-tokens 600
               --completion-stats-temperature 0 --completion-stats-top-p 1 --reasoning-effort none
               --completion-stats-seed 42 --completion-stats-correct-regex "" --completion-stats-no-prefill-scout) ;;
    hiconc) o=(--skip-prefill --contexts 8192,32768 --concurrency 1,16,32 --duration 30 --max-tokens 2048) ;;
    full)   o=(--contexts 8192,32768,65536,131072 --concurrency 1,2,4,8,16 --duration 30 --max-tokens 2048
               --standalone-prefill --prefill-contexts 8k,32k,64k,128k) ;;
    *) echo "unknown case $c" >&2; exit 2 ;;
  esac
  prefix=$OUT/$TAG-$c
  printf '%s\n' "${common[@]}" "${o[@]}" --output "$prefix.json" > "$prefix-command.txt"
  "${common[@]}" "${o[@]}" --output "$prefix.json" > "$prefix.log" 2>&1 || { echo "$c FAILED (see $prefix.log)"; tail -5 "$prefix.log"; }
  echo "$c done: $prefix.json"
done
