# spark-ds41f TileLang selection

**The stopped alternative since 2026-10-25.** It was selected on 2026-10-24
and stood down the same day: the user re-selected the five-draft B12X build
for GPQA Diamond accuracy ([comparison](../../results/20261024-b12x-comparison/REPORT.md)).
Its containers are kept as `ds41-tilelang-rN` with selection
`4d2bc32eb4f2e9a2540ee18ca2eafbe2c7da95c4ec7f4c7e2ac8c3052fc54dfc`.
Qualification: [results/20261024-tilelang](../../results/20261024-tilelang/REPORT.md).

The image is spark-ds41f's promoted **spark-ds41f-1022** release, built
unchanged from [christopherowen/spark-ds41f](https://github.com/christopherowen/spark-ds41f)
at `9f1565f060ad84a6f06a745a9b7b4191393cc842`:

| Source | Revision | Patched tree |
|---|---|---|
| LIL vLLM `integration/karmic-kraken-beta` + 186 patches | `19f2c20e` | `e68aa19c` |
| LIL b12x (vision tower, loader) | `236ddff0` | `1a647a31` |
| NCCL 2.30.7 + AArch64 IB fence | `73cf1122` | `6af10aa7` |
| TileLang 0.1.15 + 3 SM12x block-scaled MMA patches | `b95ee4ff` | `222b895d` |
| DeepSeek TileKernels 2.0.0 | `66258df6` | `cb2fa41c` |
| sparknet 0.5.0 | `ed6af327` | `f997a594` |
| Base image | vLLM nightly `af1c0149` | `sha256:3cf14c52…` |

Built image: `sha256:2fc5565e9c15b005f3297a552131b8973a2f19fb811868a8358a3e99b33491d0`
(611 s on spark-r1; GPU, TileLang and sparknet import smokes passed).

## Rebuild

```bash
git clone https://github.com/christopherowen/spark-ds41f ~/Agent/Builds/DS41-ds41f-tilelang/build/spark-ds41f
cd ~/Agent/Builds/DS41-ds41f-tilelang/build/spark-ds41f && git checkout 9f1565f060ad84a6f06a745a9b7b4191393cc842
# git-ignored; lets bin/spark resolve tp4-ring (see DS41-ds41f-tilelang for the file used)
cp <site node map> config/nodes-ring4.local.json
./bin/spark --cluster-config config/cluster.json --shape tp4-ring build prepare     # any host
# then, on an idle node with >= 64 GiB available (serving stopped):
./bin/spark --cluster-config config/cluster.json --shape tp4-ring build image --apply --tag ds41f-tilelang:19f2c20ed4d6-1022-sparkring
```

`prepare` must report the build directory
`vllm-19f2c20ed4d6-b12x-236ddff04a5f-99695427`. Copy the image to the other
ranks with `docker save | ssh <peer> docker load` over rail A and compare
`RootFS.Layers` on all four.

## Render, select, install

```bash
python3 render.py --image sha256:2fc5565e… --output <new-dir>/launch
python3 selection.py --launch <new-dir>/launch --current <copy of installed selection> --output <new-dir>/optimized-specs.json
python3 promote.py install --selection <new-dir>/optimized-specs.json --receipts <new-dir>/receipts
```

`render.py` loads the pinned `bin/spark`, resolves its `tp4-ring` recipe and
applies only these recorded site changes. spark-ds41f's own launcher refuses
four-node switched fabrics, which is why this step exists.

- sparknet's switched clique: `SPARKNET_ROCE_TOPOLOGY=direct`, both port-1
  rails, no peer map; sparknet's `switched` NCCL profile replaces the ring-only
  policy; `NCCL_CROSS_NIC=0`; no traffic class (CRS812 QoS is not configured).
- Bootstrap on rail A (`10.10.10.1`), sockets on `enp1s0f1np1`.
- Port 8015 and model name `DeepSeek-V4.1-Flash-TP4`.
- **20 GiB KV per rank** and **999 images per request** (SparkRing policy; the
  recipe has 10.5 GiB and 4).
- `PYTHONPATH=/opt/spark-ds41f/candidate/...`: the pinned recipe still names
  the pre-rename `/opt/spark3`, which silently loads stock vLLM.
- The local 1017 checkpoint (read-only) and a fresh cache under
  `/srv/sparkring/sparkring/cache/ds41f-tilelang-20261024`.
- The production SparkRing loader seccomp profile instead of `unconfined`.

Kernels, arithmetic, speculation (DSpark 5, greedy drafts, block rejection,
rule-based budget), scheduler, late admission, sink rejection and sampling
defaults are the recipe's.

`selection.py` maps every docker-run flag into the controller's
`ContainerSpec` and fails on an unknown flag. The stack (64 MiB) and core (0)
limits the controller cannot express are set by a `bash` wrapper before
`exec vllm serve`. The DRM card becomes a device entry (carve-out is off at TP4).

`promote.py install` renames the previous canonical containers to
`ds41-before-tilelang-rN`, backs up the old selection as
`/etc/deepseek-ring/optimized-specs.pre-tilelang-20261024.json`, installs the
new root-owned selection and runs the fixed-action controller `up`.

## Switching

```bash
python3 promote.py reselect --selection ../../../DS41-ds41f-tilelang/results/20261024-promotion/optimized-specs.json --receipts <new-dir>
python3 promote.py rollback --receipts <new-dir>
```

`reselect` serves TileLang again: the B12X containers become
`ds41-before-tilelang-rN` and `ds41-tilelang-rN` returns as `ds41-optimized-rN`.
`rollback` is the reverse: it stops the TileLang containers (renamed
`ds41-tilelang-rN`), restores the five-draft B12X selection `c87a397c…` and its
containers, and starts them. Both are `./cluster.sh` actions (*switch to
TileLang selection*, *switch back to B12X selection*). The B12X image `9f26f0b3718c…` stays on every rank, and its
recipe chain remains in `image/rocenante-switch`, `image/runtime-20261017`,
`image/1017`, `image/kk926` and `image/vllm-local-plugins`.

## Known behaviour

- Greedy drafts with sink rejection: a single request's first token waits one
  extra decode step (about 0.1 s at C1).
- Usage omits `prompt_tokens_details.cached_tokens`, so `bench/cold-needle.py`
  exits 1 even when the answer is correct; read `needle_pass`.
- At four ranks the Engram/reduce-scatter row exchange relays the opposite
  rank through a neighbour (ring logic); on the switch this is correct but
  costs some prefill.
