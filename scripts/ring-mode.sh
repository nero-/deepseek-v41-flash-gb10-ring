#!/usr/bin/env bash
# Compatibility wrapper for the historical command names; use ../cluster.sh.
#
#   scripts/ring-mode.sh ds            # start the selected DeepSeek configuration
#   scripts/ring-mode.sh recover-ds    # after a reboot: stop, keep the old mesh off, start
#   scripts/ring-mode.sh stop          # stop DeepSeek
#   scripts/ring-mode.sh status        # node and workload status
#
# All of these run the fixed-action root controller on spark-r0 through the
# actions in config/cluster.toml, without asking for confirmation.
set -euo pipefail
cluster="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/cluster.sh"
case "${1:-status}" in
    ds|ds-vllm)  exec "$cluster" run deepseek start --yes ;;
    recover-ds)  exec "$cluster" run deepseek recover --yes ;;
    stop)        exec "$cluster" run deepseek stop --yes ;;
    status)      exec "$cluster" status ;;
    qwen|ds-vllm-stock)
        echo "$1 is retired (Qwen storage was released; the stock installer needs the old physical ring)." >&2
        exit 2 ;;
    *) sed -n 2,10p "$0"; exit 2 ;;
esac
