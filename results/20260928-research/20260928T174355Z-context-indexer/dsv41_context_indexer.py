"""Guarded context-axis TP prototype for candidate-free prefill indexing.

Each rank scores a disjoint page range, then merges bounded top-k candidates.
Original target scoring/selection is the exactness oracle. Failed geometries
fall back permanently; this module is research-only and off by default.
"""
def register():
    import os
    import torch
    from b12x.attention import dsa_indexer as dsa
    from vllm.distributed import get_tp_group

    if getattr(dsa, "_context_tp_trial", False):
        return
    original_bind, original_score, original_select = dsa.bind, dsa.score, dsa.select
    pending, decisions = {}, {}
    armed = False

    def bind(plan, **kw):
        nonlocal armed
        full = original_bind(plan, **kw)
        q, width = kw.get("q_mxfp4"), kw.get("score_width")
        if (q is None or q.shape[0] < 128 or width is None or width < 8192
                or kw.get("candidate_indices") is not None or kw.get("candidate_output") is not None
                or kw.get("output_scores") is not None or getattr(plan.query, "mode", None) != "prefill"
                or torch.cuda.is_current_stream_capturing()):
            return full
        group = get_tp_group()
        if group.world_size != 4:
            return full
        if not armed:
            flag = torch.tensor([int(os.path.isfile("/opt/dsv41-local-plugins/context-indexer.enabled"))], device=q.device, dtype=torch.int32)
            torch.distributed.all_reduce(flag, op=torch.distributed.ReduceOp.MIN, group=group.device_group)
            if not flag.item():
                return full
            armed = True
        key = (id(plan), kw["index_k_cache"].data_ptr(), q.shape[0], (width - 1).bit_length())
        if decisions.get(key) is False:
            return full
        caps = full.runtime.plan.caps
        span = ((width + 4 * 256 - 1) // (4 * 256)) * 256
        offset = group.rank_in_group * span
        page = caps.page_size
        table = kw["page_table"][:, offset // page:(offset + span) // page]
        if table.shape[1] == 0:
            return full
        local = dict(kw)
        local.update(page_table=table, score_width=span,
                     cache_lengths=(kw["cache_lengths"] - offset).clamp(0, span),
                     active_width=(kw["active_width"] - offset).clamp(0, span),
                     output_indices=torch.empty_like(kw["output_indices"]),
                     output_scores=torch.empty_like(kw["output_indices"], dtype=torch.float32))
        partial = original_bind(plan, **local)
        pending[id(full)] = (partial, key, group, offset, width)
        return full

    def score(binding):
        state = pending.get(id(binding))
        return original_score(state[0] if state is not None and decisions.get(state[1]) else binding)

    def select(binding):
        state = pending.pop(id(binding), None)
        if state is None:
            return original_select(binding)
        partial, key, group, offset, width = state
        reference = None
        if key not in decisions:
            original_select(binding)
            reference = binding.output_indices.clone()
            original_score(partial)
        original_select(partial)
        local_ids = torch.where(partial.output_indices >= 0, partial.output_indices + offset, 2147483647)
        ids = group.all_gather(local_ids.contiguous(), dim=1)
        values = group.all_gather(partial.output_scores.contiguous(), dim=1)
        # Shards and their native outputs are in ascending global index order.
        # Stable score ordering therefore chooses smaller indices on ties.
        order = torch.argsort(values, dim=1, descending=True, stable=True)[:, :binding.output_indices.shape[1]]
        merged = ids.gather(1, order).sort(dim=1).values
        merged = torch.where(merged == 2147483647, -1, merged)
        if reference is not None:
            consensus = reference.clone()
            group.broadcast(consensus, src=0)
            flag = torch.tensor([int(torch.equal(reference, merged)), int(torch.equal(reference, consensus))], device=merged.device, dtype=torch.int32)
            torch.distributed.all_reduce(flag, op=torch.distributed.ReduceOp.MIN, group=group.device_group)
            decisions[key] = bool(flag[0].item())
            if group.rank_in_group == 0:
                ordered = torch.where(reference >= 0, reference, 2147483647)
                positions = torch.searchsorted(ordered, merged.clamp_min(0)).clamp_max(ordered.shape[1] - 1)
                valid = merged >= 0
                hits = (ordered.gather(1, positions) == merged) & valid
                overlap = (hits.sum().float() / valid.sum().clamp_min(1)).item()
                print(f"[context-indexer] rows={merged.shape[0]} width={width} exact={'ON' if decisions[key] else 'OFF'} overlap={overlap:.6f} original_replicas_exact={flag[1].item()}", flush=True)
            if not decisions[key]:
                binding.output_indices.copy_(reference)
                return binding.output_indices
        binding.output_indices.copy_(merged)
        return binding.output_indices

    dsa.bind, dsa.score, dsa.select = bind, score, select
    dsa._context_tp_trial = True
    print("[context-indexer] armed: candidate-free prefill >=8192 compressed positions", flush=True)
