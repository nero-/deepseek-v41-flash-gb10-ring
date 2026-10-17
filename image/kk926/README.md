# Selected compressor-state correction

The selected GPU base layers the complete KK vLLM #926 correction at
`7b935cb78a3f1f256b04006e82504a651685f72d` onto the pinned SparkRing/eugr
nightly parent. Both circular slot mapping and enabled ring writes are needed.
The exact three-file source replacement and preimage/postimage SHA-256 values
are in [manifest.json](manifest.json); the upstream patch and license are kept.

The parent image ID is
`sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf`.
`install.py` checks parent sources and composition/toolchain receipts, backs
up the replaced files inside the image, updates the distribution RECORD and
receipts, and runs the parent verifier. CUDA, NCCL, B12x, RoCEnante and the
checkpoint remain inherited. Local plugins are a separate read-only mount.

## Rebuilding on an existing node

Copy this repository's image context to the node first. From its repository
root, with the exact parent already present:

```bash
docker image inspect sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf
docker tag sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf dsv41-pinned-base:kk926
docker build --network none --pull=false -t dsv41-sparkring:kk926-rebuild image/kk926
docker run --rm --network none --entrypoint python3 \
  dsv41-sparkring:kk926-rebuild /opt/sparkring/toolchain/toolchain.py verify
```

A rebuild can have a different image ID. It does not replace the selected
root-owned configuration or live containers. Qualification and explicit
selection are required before serving a rebuilt image. The historical
September 29 promotion/rollback scripts were campaign-specific and are archived.

The image construction receipt deliberately retains `serving_qualified: false`;
actual deployment qualification is separate. See
[the selected image identities](../../results/20260929-kk926/images.json) and
[retained qualification status](../../results/20260929-kk926/qualification-statuses.json).

The active 1017 images add the two Python frontend corrections described in
[image/1017](../1017/README.md). September image IDs here identify the retained
GPU parent; current per-rank identities are in `results/deployment.json`.
