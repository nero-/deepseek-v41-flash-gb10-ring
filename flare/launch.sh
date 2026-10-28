#!/usr/bin/env bash
# (Re)create the persistent FLARE group. Run on the controller (rank 0):
#
#   ssh spark-r0 'bash -s' < flare/launch.sh               # newest downloaded package
#   ssh spark-r0 'bash -s' -- /path/model.safetensors < flare/launch.sh
#
# The defaults are this fleet's. Another cluster overrides them in the
# environment (see flare/INSTALL.md), for example:
#
#   ssh spark1 'FLARE_HEAD=spark1 FLARE_CLUSTER=sparks FLARE_GROUP=deepseek bash -s' < flare/launch.sh
#
# Only needed for a new package or a changed flag. A plain restart of the saved
# group is `flare orbit run --name ds41-flare --cluster ds41 --detach`
# (./cluster.sh up). The first launch of a package copies each peer's 264 GiB
# share over the fabric and verifies it (about 15 minutes); later starts reuse it.
set -euo pipefail

head=${FLARE_HEAD:-spark-r0}                          # this host's name in orbit.toml
cluster=${FLARE_CLUSTER:-ds41}                        # [cluster.NAME] in orbit.toml
group=${FLARE_GROUP:-ds41-flare}
models=${FLARE_MODELS:-$HOME/flare-models}            # the --model-cache used for flare download
port=${FLARE_PORT:-8015}
model_name=${FLARE_MODEL_NAME:-DeepSeek-V4.1-Flash-TP4}
memory_limit=${FLARE_MEMORY_LIMIT:--2G}

package=${1:-}
if [[ -z $package ]]; then
    version=$(ls -d "$models"/models/checkpoint-expanded-scales/gb10-tp4-*/ | sort | tail -1)
    package=${version}model.safetensors
fi
[[ -f $package ]] || { echo "no package primary at $package" >&2; exit 2; }

flare orbit stop "$group" --cluster "$cluster" 2>/dev/null || true
flare orbit rm "$group" 2>/dev/null || true

# Publisher recipe (TP4 README) plus site settings: port 8015 and the historical
# model name for existing clients, and a 2 GiB reserve instead of the package
# default, which gives 16.6 GiB KV per GPU (19.3M tokens) at about 111 GiB used.
exec flare orbit run "$head:$package" \
    --cluster "$cluster" --name "$group" --persistent --detach \
    --max-concurrency 32 --mtp-draft-tokens 5 --mtp-adaptive-verification \
    --embedding-table-storage disk --embedding-table-resident-scales \
    --embedding-table-cache-size 1GiB \
    --memory-limit="$memory_limit" \
    --host 0.0.0.0 --port "$port" --served-model-name "$model_name"
