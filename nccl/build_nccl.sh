#!/usr/bin/env bash
# Build SparkRing's patched NCCL 2.30.7 (switchless ring + dual PCI domain) for GB10.
#
#   nccl/build_nccl.sh <sparkring-checkout> <output-dir>
#
# Compiles inside the pinned SGLang serving image so the CUDA toolkit matches the runtime.
# The patch is cumulative against the pinned NCCL revision: it already contains the
# switchless-cycle change, so no other sparkring NCCL patch is applied on top.
set -euo pipefail
SPARKRING=$(readlink -f "$1"); OUT=$(readlink -f "$2")
IMAGE=${IMAGE:-lmsysorg/sglang:dev-dsv41@sha256:3dbc313030a6ef2c5d7de8ecf48e9aece722694a82182cb618cc82b588816349}
NCCL_REV=73cf112295c33aee2b895f329f592f2a9b4b0f97
PATCH=spark_transport/nccl/nccl-2.30.7-dual-pci-domain.patch
PATCH_BLOB=f4853e84334eaa3f980dce69a12660d8f1774d7c

got=$(git -C "$SPARKRING" hash-object "$PATCH")
[[ $got == "$PATCH_BLOB" ]] || { echo "patch blob $got != $PATCH_BLOB" >&2; exit 1; }
mkdir -p "$OUT"
docker run --rm --network host -v "$SPARKRING/$PATCH:/patch:ro" -v "$OUT:/out" "$IMAGE" bash -euc "
  git clone -q https://github.com/NVIDIA/nccl.git /src && cd /src && git checkout -q $NCCL_REV
  git apply /patch
  nvcc --version | tail -2
  make -j\$(nproc) src.build CUDA_HOME=/usr/local/cuda BUILDDIR=/build \
    NVCC_GENCODE='-gencode=arch=compute_121,code=sm_121' > /out/build.log 2>&1
  cp -L /build/lib/libnccl.so.2 /out/libnccl.so.2.30.7
  chown $(id -u):$(id -g) /out/libnccl.so.2.30.7 /out/build.log"
grep -qa SWITCHLESS_RING_ONLY "$OUT/libnccl.so.2.30.7"
grep -qa NCCL_IB_EXTENDED_IPV4_GIDS "$OUT/libnccl.so.2.30.7" || grep -qa EXTENDED_IPV4_GIDS "$OUT/libnccl.so.2.30.7"
sha256sum "$OUT/libnccl.so.2.30.7"
