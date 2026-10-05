# Rejected CSF image overlay

This retained experimental recipe was rejected for slower prefill and concurrent
decode. The previous KK926-corrected runtime remains selected. See
[the campaign report](../../CSF-UPGRADE-20261004.md).

This campaign rebases the selected SparkRing Python changes onto vLLM beta
`00a33e23142097f99fef95b1ecab6da4ea271e2e` and B12x
`4bc601a42d9938fc1b33392b5e69b2f2485b4872` (the merged inline-CSF work).
The CUTLASS DSL packages advance to 4.7.1. The parent ARM64 vLLM extensions,
CUDA 13.4.2, NCCL 2.32.3 and PyTorch binaries are retained and hash checked.
There is no upstream C/CMake/setup difference between the parent native build
revision and the selected vLLM revision.

Prepare a new context from immutable source revisions:

```bash
python3 image/csf/prepare-context.py /path/to/new/context
```

On each ARM64 node, tag that node's recorded parent image from
`results/20261004-csf/images-before-sparkring-update.json` as `ds41:csf-parent`, transfer the generated
context, and build:

```bash
docker build --progress plain -t ds41:csf-20261004 /path/to/new/context
docker run --rm ds41:csf-20261004 verify
```

Then apply the [current SparkRing reliability layer](sparkring-update/README.md).
The final candidate image IDs are in `results/20261004-csf/images.json`; the
initial-stage record above retains its KK926 parents and CSF image IDs.

The patches and `local/` files preserve the rebased integration changes;
`prepare-context.py` rejects a different native ABI and refuses to overwrite
an existing context. The campaign's reproduced context matches all 3,736
original file hashes. Conflict decisions are recorded in the campaign results.
Unrelated models carried by the recipe are not qualified by this DeepSeek test.

`rebind-transport.py` copies the parent prepared transport into a distinct CSF
profile. Its wire/proxy files remain byte-identical. The binding records the
new B12x preimages; the old transport profile remains immutable. The selection
cache correction is incorporated into its new source owner. Transport and
serving qualification are recorded outside the sealed image rather than
fabricating inherited qualification.
The existing SparkRing dashboard's installed-source receipt describes the
parent image. Use `/opt/dsv41-csf/manifest.json` and this campaign's deployment
receipt for the derived revisions and qualification.

The checkpoint is pinned to
`local-inference-lab/DeepSeek-V4.1-Flash-lossless-CSF` revision
`c5c41fe301c4c1d24fc09376883d9168e521dc66`. Mount its root read-only at
`/models/csf`, prepare its metadata in `serving/`, and use
`--load-format mxfp4_csf --quantization mxfp4_csf`. The generated serving config
sets `checkpoint_root` to `/models/csf`; retained source metadata stays intact.

`stage-checkpoint.py` resumes downloads and verifies every shard against its
published LFS SHA-256. Eight shards have unchanged tensor payloads; these can
be copied from the original local checkpoint behind the official new header
only if tensor names, types, shapes and offsets match. The resulting whole
file must still match the official hash. `replicate-checkpoint.py --delete-old`
deletes an old shard only after its replacement is verified. The artifact
server binds explicitly selected fabric addresses and publishes only the
checkpoint's allowlisted files.

Use distinct compiler/tuning caches for the new code and checkpoint. Preserve
the site's four-node transport environment, plugin mounts, scheduler settings
and GPU clock service. The site's private launch documents are excluded from
Git; this is a recipe overlay, not a universal installer.

## Recovery and cleanup

This campaign never promoted its candidate. The retained permanent selection
still names the corrected original images and original checkpoint.
[scripts/csf-rollback.py](../../scripts/csf-rollback.py) checks that selection,
stops the candidate, verifies the retained Spark originals and reconstructs
missing GX10 shards with [restore-original.py](restore-original.py).

The recovery codec works on integer scale bytes and copies unchanged tensor
bytes; it does not requantize. Original padded headers come from published CSF
receipts. Every reconstructed scale matrix and complete original shard must
match its published source SHA-256. A shard is atomically published and fsynced
before its compressed source can be removed on a constrained GX10.

The CPU fixture checks exact complete-file reconstruction, byte value 255,
reuse of verified originals and rejection of corrupt receipts. The cleanup
fixtures check live mounts, symlink escapes, external hard links, internal
hard links and preservation of the neighboring original tree. Actual recovery
receipts belong to [the campaign record](../../CSF-UPGRADE-20261004.md).

[scripts/csf-cleanup-candidate.py](../../scripts/csf-cleanup-candidate.py) is
gated on restored original serving. It removes only stopped campaign containers
and the exact rejected CSF revision after mount/link checks. It leaves original
weights, images, configuration, compiler caches, Qwen and the stock fallback
available. These scripts require private fleet receipts and are not general
checkpoint maintenance tools. Do not rerun a completed campaign blindly.

During recovery the user selected a faster remaining-shard transfer from the
verified original Spark copies.
[scripts/csf-rollback-fabric.py](../../scripts/csf-rollback-fabric.py) resumes
that specific interrupted campaign. The two
[original artifact servers](original-artifact-server.py) bind only direct
fabric addresses and allowlist the original weight filenames. The
[fabric client](restore-original-fabric.py) retains the already verified
originals, copies missing files with two workers and checks their original
SHA-256 before atomic publication. On GX10s the remaining rejected CSF tree
was removed before transfer because complete verified originals remained on
both Sparks. No network reconfiguration or repeat benchmark is involved.
