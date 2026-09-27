#!/usr/bin/env bash
# Replicate the checkpoint from this node to ring neighbours over the CX7 fabric.
#
#   scripts/dist_model.sh <src-dir> <dest-dir> <fabric-ip>...
#
# Copies completed files only (hf download stages partials under .cache/), four files
# in flight per target, then verifies sizes. Safe to re-run: rsync skips finished files.
set -euo pipefail
SRC=${1%/}; DEST=${2%/}; shift 2
SSH="ssh -i $HOME/.ssh/id_ed25519_ring -o StrictHostKeyChecking=accept-new -o BatchMode=yes -c aes128-gcm@openssh.com"
copy_to() {
  local ip=$1
  $SSH nero@"$ip" "mkdir -p '$DEST'"
  (cd "$SRC" && find . -path ./.cache -prune -o -type f -print) |
    xargs -P4 -I{} rsync -aR --partial --inplace -e "$SSH" "$SRC/./{}" "nero@$ip:$DEST/"
  local want got
  want=$(cd "$SRC" && find . -path ./.cache -prune -o -type f -printf '%P %s\n' | sort | md5sum)
  got=$($SSH nero@"$ip" "cd '$DEST' && find . -path ./.cache -prune -o -type f -printf '%P %s\n' | sort | md5sum")
  [[ $want == "$got" ]] && echo "$ip: $(cd "$SRC" && find . -path ./.cache -prune -o -type f -print | wc -l) files match" || echo "$ip: MISMATCH" >&2
}
for ip in "$@"; do copy_to "$ip" & done
wait
