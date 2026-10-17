#!/usr/bin/env bash
# Operate DeepSeek-V4.1-Flash TP4 on the four-node ring.
#
#   scripts/ring-mode.sh ds                 # serve the selected SparkRing vLLM configuration
#   scripts/ring-mode.sh recover-ds         # stop workloads, reset all mesh services, start selected vLLM
#   scripts/ring-mode.sh ds-vllm-stock       # serve the official installer defaults
#   scripts/ring-mode.sh qwen               # reports retired; leaves DeepSeek running
#   scripts/ring-mode.sh stop               # stop everything (mesh left as is)
#   scripts/ring-mode.sh status
#
# Runs from any host that can SSH to spark-r0 / gx10-r0 (the Mac or a node).
# The DeepSeek head is spark-r0.
# ds/ds-vllm select the qualified local SparkRing configuration; ds-vllm-stock
# selects the unchanged official installer deployment.
# Retired Qwen pair stop entry points remain compatible with DeepSeek recovery.
# The root-owned helper coordinates the mesh lifecycle with DeepSeek.
set -euo pipefail
RANKS=(spark-r0 spark-r1 gx10-r1 gx10-r0)
DS_HEAD=spark-r0
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o ProxyCommand=none)
ssh_node() {
    local host=$1 ip
    shift
    case "$host" in
        spark-r0) ip=192.168.50.219 ;;
        spark-r1) ip=192.168.50.129 ;;
        gx10-r1) ip=192.168.50.192 ;;
        gx10-r0) ip=192.168.50.23 ;;
        *) echo "Unknown ring node: $host" >&2; return 2 ;;
    esac
    "${SSH[@]}" -o "HostName=$ip" "$host" "$@"
}

control()   { ssh_node "$DS_HEAD" "sudo -n /usr/local/sbin/deepseek-ring-control $1"; }
ds_stop()   { control down; }
qwen_head() { case $1 in spark) echo spark-r0 ;; gx10) echo gx10-r0 ;; esac; }  # bash 3.2 (macOS): no assoc arrays
qwen()      { ssh_node "$(qwen_head "$1")" "bash ~/builds/qwen-tp2/cluster.sh $2"; }
case "${1:-status}" in
  ds|ds-vllm|ds-vllm-stock|recover-ds)
    for p in spark gx10; do qwen "$p" stop; done
    if [[ $1 == recover-ds ]]; then
      ds_stop
      control mesh-off
    fi
    if [[ $1 == ds-vllm-stock ]]; then control stock-up; else control up; fi
    ;;
  qwen)
    echo 'Qwen serving was retired from this ring to reserve storage for GLM. See ../GLM/HANDOFF.md.' >&2
    exit 2
    ;;
  stop)
    ds_stop
    for p in spark gx10; do qwen $p stop >/dev/null 2>&1 || true; done
    ;;
  status)
    control status
    for h in "${RANKS[@]}"; do
      printf '%-9s mesh=%-8s %s\n' "$h" "$(ssh_node "$h" 'systemctl is-active sparkring-sparkring-deepseek-v41-flash-adaefa-mesh.service 2>/dev/null || true')" \
        "$(ssh_node "$h" "docker ps --format '{{.Names}}' | tr '\n' ' '")"
    done
    ;;
  *) sed -n 2,12p "$0"; exit 2 ;;
esac
