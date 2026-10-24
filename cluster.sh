#!/usr/bin/env bash
# Cluster control entry point. With no arguments it opens the TUI.
#
#   ./cluster.sh                    interactive TUI (nodes, workloads, actions, output)
#   ./cluster.sh status             one-shot node and workload health
#   ./cluster.sh list               workloads and their actions
#   ./cluster.sh up|down|recover    start / stop / post-reboot recovery of the default workload
#   ./cluster.sh run WORKLOAD ACTION [--yes]
#
# The cluster is defined in config/cluster.toml (override with CLUSTER_CONFIG=path
# or --config path). Needs Python 3.11+ for tomllib; the newest python3.x on PATH is used.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

python=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        python=$candidate
        break
    fi
done
[[ -n $python ]] || { echo "cluster.sh needs Python 3.11 or newer" >&2; exit 2; }

cli=("$python" "$here/scripts/cluster.py")
default_workload() {
    "$python" - "${CLUSTER_CONFIG:-$here/config/cluster.toml}" <<'PY'
import sys, tomllib
workloads = tomllib.load(open(sys.argv[1], "rb")).get("workloads", [])
print(next((w["name"] for w in workloads if w.get("default")), workloads[0]["name"] if workloads else ""))
PY
}

case "${1:-tui}" in
    tui|status|list|run) exec "${cli[@]}" "$@" ;;
    up|start)            exec "${cli[@]}" run "$(default_workload)" start "${@:2}" ;;
    down|stop)           exec "${cli[@]}" run "$(default_workload)" stop "${@:2}" ;;
    recover)             exec "${cli[@]}" run "$(default_workload)" recover "${@:2}" ;;
    --config)            exec "${cli[@]}" "$@" ;;
    -h|--help|help)      sed -n 2,12p "$0" ;;
    *)                   echo "unknown command: $1" >&2; sed -n 2,12p "$0" >&2; exit 2 ;;
esac
