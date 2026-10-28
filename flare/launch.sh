#!/usr/bin/env bash
# (Re)create the persistent FLARE group ds41-flare. Run on spark-r0 as nero:
#
#   ssh spark-r0 'bash -s' < flare/launch.sh               # newest downloaded package
#   ssh spark-r0 'bash -s' -- /path/model.safetensors < flare/launch.sh
#
# Only needed for a new package or a changed flag. A plain restart of the saved
# group is `flare orbit run --name ds41-flare --cluster ds41 --detach`
# (./cluster.sh up). The first launch of a package copies each peer's 264 GiB
# share over the fabric and verifies it (about 15 minutes); later starts reuse it.
set -euo pipefail

package=${1:-}
if [[ -z $package ]]; then
    version=$(ls -d "$HOME"/flare-models/models/checkpoint-expanded-scales/gb10-tp4-*/ | sort | tail -1)
    package=${version}model.safetensors
fi
[[ -f $package ]] || { echo "no package primary at $package" >&2; exit 2; }

flare orbit stop ds41-flare --cluster ds41 2>/dev/null || true
flare orbit rm ds41-flare 2>/dev/null || true

# Publisher recipe (TP4 README) plus site settings: port 8015 and the historical
# model name for existing clients, and a 2 GiB reserve instead of the package
# default, which gives 16.6 GiB KV per GPU (19.3M tokens) at about 111 GiB used.
exec flare orbit run "spark-r0:$package" \
    --cluster ds41 --name ds41-flare --persistent --detach \
    --max-concurrency 32 --mtp-draft-tokens 5 --mtp-adaptive-verification \
    --embedding-table-storage disk --embedding-table-resident-scales \
    --embedding-table-cache-size 1GiB \
    --memory-limit=-2G \
    --host 0.0.0.0 --port 8015 --served-model-name DeepSeek-V4.1-Flash-TP4
