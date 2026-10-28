**Title:** Orbit agent eviction removes `flare download`'s default model store in `~/.cache/flare/packages`

## Summary

`flare download` and the Orbit agent default to the same directory. The download root is
`~/.cache/flare/packages` (`flare/src/cache_support.rs:34`, `flare/src/config.rs:116`). The
agent's cache root is `~/.cache/flare` (`flare/src/package_cache.rs:68`), and its `packages`
kind directory is that same `~/.cache/flare/packages`.

After a transfer, the agent evicts every unpinned unit in its kind directory:

```rust
// flare/src/orbit/agent.rs:985, transfer(); put() evicts the stored unit's parent at :856
for removed in cache::evict(&agent.cache.join("packages"), &agent.pins)? {
    eprintln!("removed superseded {}", removed.display());
}
```

`cache::evict` (`flare/src/package_cache.rs:237`) removes every non-hidden child it can take
an eviction lease on. That includes the download store's top-level directories, so a completed
download on the same host is deleted. The code path is unchanged on `main` (`312ae0e2`).

## Evidence

- Host: rank 0 and controller of a TP4 Orbit cluster (DGX Spark).
- Download: `local-inference-lab/DeepSeek-V4.1-Flash-1017-FLARE@gb10`, TP4, made with
  `b697d3b8` using the default root. It finished at 17:20 UTC (490 GiB).
- Agent: `ec0a3126`. Two minutes into the first `flare orbit push`, the rank-0 agent logged:

```
removed superseded /home/nero/.cache/flare/packages/blobs
removed superseded /home/nero/.cache/flare/packages/locks
removed superseded /home/nero/.cache/flare/packages/models
removed superseded /home/nero/.cache/flare/packages/origins
removed superseded /home/nero/.cache/flare/packages/refs
removed superseded /home/nero/.cache/flare/packages/sources
removed superseded /home/nero/.cache/flare/packages/staging
```

  The download was gone afterwards, and fetching it again from Hugging Face took two hours.
- The repeat download with `--model-cache /home/nero/flare-models` has survived later pushes
  and `orbit run` launches on `7c22369f`.

## Minimal reproduction

1. On a host with a paired agent, run
   `flare download REPO --revision REV --filename model.safetensors --tensor-parallel N`
   without `--model-cache` or `paths.package_cache`.
2. Start an Orbit operation that makes that host's agent run `transfer` or `put`. We ran
   `flare orbit push` of that package from the same host.
3. The agent logs `removed superseded …/packages/{blobs,models,refs,…}`, and
   `flare models list` no longer shows the download.

## Possible direction (needs maintainer input)

Either change would keep the agent's units and the download store apart:

- Default the download root and the agent's `packages` kind directory to different paths.
- Restrict `cache::evict` to agent units, so it skips the `package::cache::Root` layout
  (`blobs`, `models`, `refs`, …).

We have not checked whether the documented `paths.package_cache` setting can point both at
the same directory on purpose.
