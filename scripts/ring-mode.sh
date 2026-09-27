#!/usr/bin/env bash
# Switch the four-node ring between DeepSeek-V4.1-Flash TP4 and the Qwen TP2 pairs.
#
#   scripts/ring-mode.sh ds                 # stop Qwen on both pairs, mesh up, serve DeepSeek TP4
#   scripts/ring-mode.sh qwen [spark|gx10|both]   # stop DeepSeek, mesh down, start Qwen pair(s)
#   scripts/ring-mode.sh stop               # stop everything (mesh left as is)
#   scripts/ring-mode.sh status
#
# Runs from any host that can SSH to spark-r0 / gx10-r0 (the Mac or a node).
# The DeepSeek head is spark-r0 (~/NewModels/DS4.1, Mia's launcher with .env.tp4).
# Qwen pairs are driven by each pair's own ~/builds/qwen-tp2/cluster.sh.
# dsv41-mesh (hardware-forwarded opposite-node paths) is only needed by DeepSeek; it is
# stopped in Qwen mode so its UDP-65535 RDMA marker can never touch a Qwen queue pair.
set -euo pipefail
RANKS=(spark-r0 spark-r1 gx10-r1 gx10-r0)
DS_HEAD=spark-r0 DS_DIR='~/NewModels/DS4.1'
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10)

ds_stop()   { "${SSH[@]}" $DS_HEAD "cd $DS_DIR && ./start-tp4.sh stop" || true; }
qwen_head() { case $1 in spark) echo spark-r0 ;; gx10) echo gx10-r0 ;; esac; }  # bash 3.2 (macOS): no assoc arrays
qwen()      { "${SSH[@]}" "$(qwen_head "$1")" "bash ~/builds/qwen-tp2/cluster.sh $2"; }
# Needs passwordless sudo for these unit verbs on every node (the Sparks get it from
# ring/sudoers-dsv41-mesh; the GX10s already have NOPASSWD sudo).
mesh()      { for h in "$@"; do "${SSH[@]}" "$h" "sudo -n systemctl $MESH_ACTION dsv41-mesh" & done; wait; }

case "${1:-status}" in
  ds)
    for p in spark gx10; do qwen $p stop >/dev/null 2>&1 || true; done
    MESH_ACTION=start mesh "${RANKS[@]}"
    "${SSH[@]}" $DS_HEAD "cd $DS_DIR && ./start-tp4.sh serve"
    ;;
  qwen)
    pairs=${2:-both}; [[ $pairs == both ]] && pairs="spark gx10"
    ds_stop
    for p in $pairs; do
      [[ $p == spark ]] && MESH_ACTION=stop mesh spark-r0 spark-r1
      [[ $p == gx10 ]] && MESH_ACTION=stop mesh gx10-r0 gx10-r1
      qwen $p start && qwen $p wait
    done
    ;;
  stop)
    ds_stop
    for p in spark gx10; do qwen $p stop >/dev/null 2>&1 || true; done
    ;;
  status)
    for h in "${RANKS[@]}"; do
      printf '%-9s mesh=%-8s %s\n' "$h" "$("${SSH[@]}" $h 'systemctl is-active dsv41-mesh 2>/dev/null || true')" \
        "$("${SSH[@]}" $h "docker ps --format '{{.Names}}' | tr '\n' ' '")"
    done
    ;;
  *) sed -n 2,12p "$0"; exit 2 ;;
esac
