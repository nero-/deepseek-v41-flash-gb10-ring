"""Experimental integer-only TP gather for replicated long-prefill index scoring.

Pinned native DeepSeek V4.1 call boundary only. Leaves Q/K generation, candidate
source/consumer passes, decode, and short contexts unchanged. Existing prepared
DSA kernels support fewer live rows; no new kernel geometry is introduced.
"""
def register():
    import os
    import torch
    from b12x.attention import dsa_indexer as dsa
    from vllm.distributed import get_tp_group

    if getattr(dsa, "_local_indexer_tp_installed", False):
        return
    original_bind, original_score, original_select = dsa.bind, dsa.score, dsa.select
    pending, decisions = {}, {}
    armed = False
    local_guard = os.environ.get("DSV41_QUERY_LOCAL_GUARD", "0") == "1"
    value_guard = os.environ.get("DSV41_QUERY_VALUE_GUARD", "0") == "1"
    min_rows = int(os.environ.get("DSV41_QUERY_MIN_ROWS", "256"))
    if min_rows < 128 or min_rows % 4:
        raise ValueError("Query partition requires a >=128-row, four-aligned threshold")
    arm_on_request = os.environ.get("DSV41_INDEXER_ARM_ON_REQUEST", "0") == "1"
    real_input_seen = False
    startup_complete = False
    if arm_on_request:
        from vllm.v1.worker.gpu.model_runner import GPUModelRunner
        from vllm.v1.worker.gpu_worker import Worker
        original_add = GPUModelRunner.add_requests
        original_warmup = Worker.compile_or_warm_up_model

        def compile_or_warm_up_model(self, *args, **kwargs):
            nonlocal startup_complete, real_input_seen, armed
            startup_complete = real_input_seen = armed = False
            decisions.clear()
            pending.clear()
            result = original_warmup(self, *args, **kwargs)
            startup_complete = True
            print("[local-indexer-tp] worker startup complete; awaiting real request", flush=True)
            return result

        def add_requests(self, scheduler_output):
            nonlocal real_input_seen
            result = original_add(self, scheduler_output)
            if startup_complete and scheduler_output.scheduled_new_reqs and not real_input_seen:
                real_input_seen = True
                print("[local-indexer-tp] first real request observed; numerical guards pending", flush=True)
            return result

        # Warmup sends synthetic requests through add_requests too. Require
        # completion of the entire worker warmup before observing real input.
        Worker.compile_or_warm_up_model = compile_or_warm_up_model
        GPUModelRunner.add_requests = add_requests

    row_fields = ("q_mxfp4", "q_scales", "query_weights", "page_table", "cache_lengths", "output_indices")

    def bind(plan, **kwargs):
        nonlocal armed
        full = original_bind(plan, **kwargs)
        q = kwargs.get("q_mxfp4")
        width = kwargs.get("score_width")
        if (q is None or q.shape[0] < min_rows or q.shape[0] % 4 or width is None or width < 8192
                or kwargs.get("candidate_indices") is not None
                or kwargs.get("candidate_output") is not None
                or kwargs.get("output_scores") is not None
                or getattr(plan.query, "mode", None) != "prefill"
                or torch.cuda.is_current_stream_capturing()):
            return full
        group = get_tp_group()
        if group.world_size != 4:
            return full
        if not armed:
            # The trial controller activates only after API readiness. Empty
            # startup/profile inputs must not satisfy the real-input guard.
            ready = real_input_seen if arm_on_request else os.path.isfile("/opt/dsv41-local-plugins/indexer-tp.enabled")
            flag = torch.tensor([int(ready)],
                                device=q.device, dtype=torch.int32)
            torch.distributed.all_reduce(flag, op=torch.distributed.ReduceOp.MIN, group=group.device_group)
            if not flag.item():
                return full
            armed = True
        rows = q.shape[0]
        key = (id(plan), kwargs["index_k_cache"].data_ptr(), rows, (width - 1).bit_length())
        if decisions.get(key) is False:
            return full
        chunk = rows // 4
        start = group.rank_in_group * chunk
        local = dict(kwargs)
        for name in row_fields:
            if name == "page_table" and kwargs[name].shape[0] == 1:
                continue
            local[name] = kwargs[name][start:start + chunk]
        partial = original_bind(plan, **local)
        pending[id(full)] = (partial, key, group, width)
        return full

    def score(binding):
        state = pending.get(id(binding))
        if state is None or state[1] not in decisions:
            return original_score(binding)
        # The pinned attention caller ignores this return value, consuming only
        # the full output_indices buffer after select().
        return original_score(state[0])

    def select(binding):
        state = pending.pop(id(binding), None)
        if state is None:
            return original_select(binding)
        partial, key, group, width = state
        reference = None
        reference_scores = None
        start = group.rank_in_group * partial.output_indices.shape[0]
        count = partial.output_indices.shape[0]
        if key not in decisions:
            original_select(binding)
            reference = binding.output_indices.clone()
            if value_guard:
                reference_scores = binding.runtime.runtime.scratch["scores"][start:start + count].clone()
            original_score(partial)
        original_select(partial)
        gathered = group.all_gather(partial.output_indices.contiguous(), dim=0)
        if reference is not None:
            comparison = reference[start:start + partial.output_indices.shape[0]] if local_guard else reference
            actual = partial.output_indices if local_guard else gathered
            indices_exact = torch.equal(comparison, actual)
            values_exact = False
            same_scores = selected_values_equal = valid_layout = False
            if reference_scores is not None:
                # Native top-k uses atomic candidate insertion and can choose
                # different keys tied at the cutoff. Require identical raw
                # scores and selected score multisets, plus valid distinct IDs;
                # no tolerance or "close enough" index overlap is accepted.
                rt = partial.runtime.runtime
                scores = rt.scratch["scores"][:count]
                visible = torch.minimum(rt.cache_lengths, rt.active_width).clamp(0, scores.shape[1])
                live = torch.arange(scores.shape[1], device=scores.device)[None, :] < visible[:, None]
                same_scores = bool(((scores == reference_scores) | ~live).all().item())
                ids = partial.output_indices
                ref_ids = reference[start:start + count]
                valid = ids >= 0
                bounds = bool((((ids < visible[:, None]) | ~valid) & (ids >= -1)).all().item())
                counts = bool((valid.sum(1) == visible.clamp_max(ids.shape[1])).all().item())
                distinct = bool(((ids[:, 1:] != ids[:, :-1]) | ~valid[:, 1:]).all().item())
                def ranked_values(indices):
                    values = reference_scores.gather(1, indices.clamp(0, scores.shape[1] - 1).long())
                    return values.masked_fill(indices < 0, -float("inf")).sort(dim=1).values
                selected_values_equal = torch.equal(ranked_values(ids), ranked_values(ref_ids))
                valid_layout = bounds and counts and distinct
                values_exact = same_scores and valid_layout and selected_values_equal
            flag = torch.tensor([int(indices_exact), int(values_exact), int(same_scores), int(selected_values_equal), int(valid_layout)], device=gathered.device, dtype=torch.int32)
            torch.distributed.all_reduce(flag, op=torch.distributed.ReduceOp.MIN, group=group.device_group)
            decisions[key] = bool(flag[1 if value_guard else 0].item())
            if group.rank_in_group == 0:
                guard = "local-scores-and-topk-values" if value_guard else "local-query-selection" if local_guard else "replica-selection"
                label = "score-exact" if value_guard else "bit-exact"
                detail = f" raw_scores_exact={flag[2].item()} topk_values_exact={flag[3].item()} valid_ids={flag[4].item()}" if value_guard else ""
                print(f"[local-indexer-tp] rows={gathered.shape[0]} width={width} guard={guard} {label}={'ON' if decisions[key] else 'OFF'} indices_exact={flag[0].item()}{detail}", flush=True)
            if not decisions[key]:
                binding.output_indices.copy_(reference)
                return binding.output_indices
        binding.output_indices.copy_(gathered)
        return binding.output_indices

    dsa.bind, dsa.score, dsa.select = bind, score, select
    dsa._local_indexer_tp_installed = True
    print(f"[local-indexer-tp] armed: >={min_rows} rows, >=8192 compressed positions, candidate-free prefill only", flush=True)
