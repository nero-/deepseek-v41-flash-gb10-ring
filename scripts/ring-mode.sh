#!/usr/bin/env bash
# Compatibility wrapper for the historical command names; use ../cluster.sh.
#
#   scripts/ring-mode.sh ds            # start DeepSeek (FLARE group ds41-flare)
#   scripts/ring-mode.sh recover-ds    # after a reboot: stop leftovers, check the fabric, start
#   scripts/ring-mode.sh stop          # stop DeepSeek
#   scripts/ring-mode.sh status        # node and workload status
#
# All of these run the actions in config/cluster.toml (flare orbit on spark-r0)
# without asking for confirmation.
set -euo pipefail
cluster="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/cluster.sh"
case "${1:-status}" in
    ds|ds-flare) exec "$cluster" run deepseek start --yes ;;
    recover-ds)  exec "$cluster" run deepseek recover --yes ;;
    stop)        exec "$cluster" run deepseek stop --yes ;;
    status)      exec "$cluster" status ;;
    qwen|ds-vllm|ds-vllm-stock)
        echo "$1 is retired (vLLM and Qwen serving were retired; FLARE serves DeepSeek)." >&2
        exit 2 ;;
    *) sed -n 2,10p "$0"; exit 2 ;;
esac
