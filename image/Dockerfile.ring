# Thin layer over Mia's production image (Dockerfile.canary-roce) for this mixed fleet.
#
# SGLang aborts the boot when one TP rank finishes loading more than 480 s before another
# (dist_barrier_after_load, UNBALANCED_MODEL_LOADING_TIMEOUT_S). The GX10s' 1 TB drives load
# the checkpoint several times slower than the Sparks' 4 TB drives, so allow 30 minutes.
ARG BASE=dsv41-4x-spark:canary-roce
FROM ${BASE}
RUN f=/sgl-workspace/sglang/python/sglang/srt/model_executor/model_runner_components/load_model_utils.py \
 && sed -i 's/^UNBALANCED_MODEL_LOADING_TIMEOUT_S = 480\b/UNBALANCED_MODEL_LOADING_TIMEOUT_S = 1800/' "$f" \
 && grep -q '^UNBALANCED_MODEL_LOADING_TIMEOUT_S = 1800' "$f"
