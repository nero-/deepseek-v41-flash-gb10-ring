"""CPU-only advisory Engram read-ahead for known prompt tokens.

Requires buffered native disk reads; O_DIRECT cannot benefit from page-cache
warming. Does not change hash/lookup outputs or GPU synchronization. A bounded
single CPU job may advise the next chunk; consumption stays on the native path.
"""
def hash_prompt_rows(compressed, begin, end, geometry, index, pad_id):
    import numpy as np
    positions = np.arange(begin, end)
    rolling = np.zeros(end - begin, dtype=np.int64)
    blocked = np.zeros(end - begin, dtype=bool)
    columns = []
    for lag in range(4):
        source = positions - lag
        blocked |= source < 0
        values = np.where(blocked, pad_id, compressed[np.maximum(source, 0)])
        rolling ^= values * geometry.multipliers[index][lag]
        if lag:
            for head in range((lag - 1) * 8, lag * 8):
                columns.append(rolling % geometry.primes[index][head] + geometry.offsets[index][head])
    return np.stack(columns, axis=1)


def register():
    import concurrent.futures
    import os
    import numpy as np
    from vllm.v1.worker.gpu.model_runner import GPUModelRunner
    from vllm.models.deepseek_v4_1.common.engram import _token_map

    if getattr(GPUModelRunner, "_engram_readahead_trial", False):
        return
    if os.environ.get("B12X_DISK_TABLE_BUFFERED_IO") != "1":
        raise RuntimeError("Engram read-ahead requires buffered I/O")
    original_load, original_execute = GPUModelRunner.load_model, GPUModelRunner.execute_model

    def load(self, *args, **kwargs):
        result = original_load(self, *args, **kwargs)
        mc = self.vllm_config.model_config
        tokens, _ = _token_map(mc.tokenizer, mc.revision, mc.trust_remote_code)
        self._ra_token_map = np.asarray(tokens, dtype=np.int64)
        self._ra_prompts = {}
        self._ra_pool = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="engram-advice")
        self._ra_future = None
        self._ra_files = {}
        self._ra_jobs = 0
        return result

    def advise(self, compressed, begin, end):
        import time
        started = time.perf_counter()
        language_model = getattr(self.model, "language_model", self.model)
        model = language_model.model
        geometry = model.engram_layout.geometry
        pages_issued = 0
        for layer in model.layers:
            engram = getattr(layer, "engram", None)
            if engram is None:
                continue
            table = engram.embed_tokens
            index = engram.layer_hash_index
            hashed = hash_prompt_rows(compressed, begin, end, geometry, index, self._ra_token_map[2])
            ids = np.unique(hashed[(hashed >= table.shard_start) & (hashed < table.shard_start + table.shard_rows)])
            for path, offset, scale in table._disk_sources:
                if scale:
                    continue
                if path not in self._ra_files:
                    self._ra_files[path] = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
                pages = np.unique((offset + ids * 256) // 4096)[:8192]
                if not pages.size:
                    continue
                cuts = np.flatnonzero(np.diff(pages) != 1) + 1
                for run in np.split(pages, cuts):
                    os.posix_fadvise(self._ra_files[path], int(run[0]) * 4096, len(run) * 4096, os.POSIX_FADV_WILLNEED)
                pages_issued += len(pages)
        self._ra_jobs += 1
        if self._ra_jobs <= 3 or self._ra_jobs % 100 == 0:
            print(f"[engram-advice] tokens={end-begin} pages={pages_issued} cpu_ms={(time.perf_counter()-started)*1000:.1f}", flush=True)

    def execute(self, scheduler_output, *args, **kwargs):
        real = not kwargs.get("dummy_run", False)
        if real and hasattr(self, "_ra_prompts"):
            for rid in scheduler_output.finished_req_ids:
                self._ra_prompts.pop(rid, None)
            for req in scheduler_output.scheduled_new_reqs:
                tokens = req.prefill_token_ids
                if tokens and not getattr(req, "mm_features", None):
                    self._ra_prompts[req.req_id] = self._ra_token_map[np.asarray(tokens, dtype=np.int64)]
        result = original_execute(self, scheduler_output, *args, **kwargs)
        if real and hasattr(self, "_ra_prompts"):
            future = self._ra_future
            if future is not None and future.done():
                future.result()
                self._ra_future = None
            if self._ra_future is None:
                for rid, count in scheduler_output.num_scheduled_tokens.items():
                    prompt = self._ra_prompts.get(rid)
                    slot = self.req_states.req_id_to_index.get(rid)
                    if prompt is None or slot is None:
                        continue
                    begin = int(self.req_states.num_computed_tokens_np[slot]) + count
                    end = min(len(prompt), begin + 8192)
                    if end - begin >= 512:
                        self._ra_future = self._ra_pool.submit(advise, self, prompt, begin, end)
                        break
        return result

    GPUModelRunner.load_model, GPUModelRunner.execute_model = load, execute
    GPUModelRunner._engram_readahead_trial = True
    print("[engram-advice] armed buffered prompt lookahead <=8192 tokens, <=8192 pages/layer", flush=True)
