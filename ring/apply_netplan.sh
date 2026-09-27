#!/bin/bash
# Usage (root): apply_netplan.sh <new-yaml> <old fabric yaml>...
set -euo pipefail
new=$1; shift
bk=/etc/netplan/backup-dsv41-$(date +%Y%m%dT%H%M%S)
mkdir -p "$bk"
cp -a /etc/netplan/*.yaml "$bk/"       # full snapshot for rollback
for f in "$@"; do [ -f "/etc/netplan/$f" ] && mv "/etc/netplan/$f" "$bk/moved-$f"; done
install -m 600 "$new" /etc/netplan/41-dsv41-ring.yaml
netplan generate
netplan apply
echo "backup: $bk"
