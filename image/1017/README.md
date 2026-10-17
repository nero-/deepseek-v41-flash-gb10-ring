# Selected 1017 frontend corrections

These two sequential layers preserve the corrected September GPU stack,
including KK #926/#943, and adapt the frontend for the official 1017 checkpoint.

1. `prompt/` replaces only the tool-result user-turn boundary logic with the
   official pinned 1017 implementation, keeping vLLM's surrounding adaptations.
2. `parser/` installs the exact Python files from KK #921 at
   `eba11af7a0502738e67f98cb547494978e84cb14`, preserving DSML parameters when
   `string=` is absent. The Rust frontend is disabled in this recipe.

Both installers enforce preimage/postimage hashes, preserve backups inside the
image and update distribution/source/toolchain receipts. Native libraries do
not change. The parser build runs 128 upstream CPU tests with isolated offline
test dependencies; no serving Python package is upgraded for those tests.

Use the rank's `original_image_id` in
`../../results/20261017-checkpoint-upgrade/candidate-images.json` as the prompt
layer base (`--build-arg BASE=...`). Then build the parser layer from that result
(`--build-arg BASE_IMAGE=...`). Both builds use `--network none --pull=false`.
The complete existing-node build launchers and original logs are retained in
`~/Agent/Diagnostics/deepseek-v41-flash-ring/upgrade-1017-20261017/` as
`build_images.py` and `build_parser_images.py`.

Each build runs `/opt/sparkring/toolchain/toolchain.py verify`. A rebuild may have
a different image ID and does not automatically replace the selected config.
Its image receipt retains `serving_qualified: false`; serving qualification is
recorded separately in the deployment manifest and upgrade report.

[Selected identities and qualification](../../results/20261017-checkpoint-upgrade/REPORT.md).
