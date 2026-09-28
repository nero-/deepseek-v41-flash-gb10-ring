"""Exactness gate for prefill mHC row ownership using native prepared kernels.

Compares each rank's partial result with its own original full-row result;
original replicas can differ numerically. The default stage reconstructs
outputs at each mHC boundary. An explicit research-only flag retains owned
residual rows between blocks and materializes at Engram, CED and final consumers.
A failed row-slice gate falls back to the original full-row operation.
"""
def register():
    import dataclasses
    import os
    import torch
    from b12x.norm import mhc
    from vllm.distributed import get_tp_group

    if getattr(mhc, "_owned_row_trial", False):
        return
    decisions = {}
    armed = False
    fields = ("out", "post_buffer", "comb_buffer", "y", "pre_out")
    retain = os.environ.get("DSV41_RETAIN_OWNED_RESIDUALS", "0") == "1"

    def region_for(tensor, group):
        count = tensor.shape[0] // 4
        start = group.rank_in_group * count
        return slice(start, start + count)

    def materialize(tensor, group):
        return group.all_gather(tensor[region_for(tensor, group)].contiguous(), dim=0)

    def full_inputs(args, kwargs, positional_rows, group):
        full_args = list(args)
        for index in positional_rows:
            full_args[index] = materialize(args[index], group)
        full_kwargs = dict(kwargs)
        if full_kwargs.get("pre_mix") is not None:
            full_kwargs["pre_mix"] = materialize(full_kwargs["pre_mix"], group)
        return full_args, full_kwargs

    def wrap(original, positional_rows):
        def run(*args, **kwargs):
            nonlocal armed
            binding = kwargs.get("binding")
            rows = args[0].shape[0]
            if binding is None or rows < 512 or rows % 4 or torch.cuda.is_current_stream_capturing():
                return original(*args, **kwargs)
            group = get_tp_group()
            if group.world_size != 4:
                return original(*args, **kwargs)
            if not armed:
                flag = torch.tensor([int(os.path.isfile("/opt/dsv41-local-plugins/owned-mhc.enabled"))], device=args[0].device, dtype=torch.int32)
                torch.distributed.all_reduce(flag, op=torch.distributed.ReduceOp.MIN, group=group.device_group)
                if not flag.item():
                    return original(*args, **kwargs)
                armed = True
            key = (id(binding.state), original.__name__, rows)
            if decisions.get(key) is False:
                if retain:
                    full_args, full_kwargs = full_inputs(args, kwargs, positional_rows, group)
                    return original(*full_args, **full_kwargs)
                return original(*args, **kwargs)
            reference = None
            timing = None
            if key not in decisions:
                timing = [torch.cuda.Event(enable_timing=True) for _ in range(4)]
                oracle_args, oracle_kwargs = full_inputs(args, kwargs, positional_rows, group) if retain else (args, kwargs)
                timing[0].record()
                original(*oracle_args, **oracle_kwargs)
                timing[1].record()
                reference = [getattr(binding, f).clone() if getattr(binding, f) is not None else None for f in fields]
            count = rows // 4
            start = group.rank_in_group * count
            region = slice(start, start + count)
            local_args = list(args)
            for index in positional_rows:
                local_args[index] = args[index][region]
            local_kwargs = dict(kwargs)
            for name in ("pre_mix", "pre_out"):
                if local_kwargs.get(name) is not None:
                    local_kwargs[name] = local_kwargs[name][region]
            replacements = {f: getattr(binding, f)[region] if getattr(binding, f) is not None else None for f in fields}
            replacements["partials"] = binding.partials[:count] if binding.partials is not None else None
            replacements["expected_m"] = None
            local_binding = dataclasses.replace(binding, **replacements)
            local_kwargs["binding"] = local_binding
            if timing:
                timing[2].record()
            original(*local_args, **local_kwargs)
            gather_all = not retain or reference is not None
            gathered = [group.all_gather(getattr(local_binding, f).contiguous(), dim=0)
                        if getattr(local_binding, f) is not None and (gather_all or f == "y") else None for f in fields]
            if timing:
                timing[3].record()
            if reference is not None:
                exact_fields = {f: a is None or torch.equal(a[region], getattr(local_binding, f))
                                for a, f in zip(reference, fields)}
                same = all(exact_fields.values())
                flag = torch.tensor([int(same)], device=args[0].device, dtype=torch.int32)
                torch.distributed.all_reduce(flag, op=torch.distributed.ReduceOp.MIN, group=group.device_group)
                decisions[key] = bool(flag.item())
                if group.rank_in_group == 0:
                    print(f"[owned-mhc] operation={original.__name__} rows={rows} guard=local-mhc-rows exact={'ON' if decisions[key] else 'OFF'} rank0_fields={exact_fields} native_ms={timing[0].elapsed_time(timing[1]):.3f} owned_gather_ms={timing[2].elapsed_time(timing[3]):.3f}", flush=True)
                if not decisions[key]:
                    gathered = reference
            for f, value in zip(fields, gathered):
                if value is not None and (not retain or not decisions[key] or f == "y"):
                    getattr(binding, f).copy_(value)
            return binding.out, binding.post_buffer, binding.comb_buffer, binding.y
        return run

    mhc.run_pre = wrap(mhc.run_pre, (0,))
    mhc.run_post_pre = wrap(mhc.run_post_pre, (0, 1, 2, 3))
    if retain:
        # Keep row ownership through consecutive mHC blocks. Materialize the
        # full residual only at explicit consumers: Engram/aux/final post,
        # CED row compaction, and weighted final collapse's small pre-mix.
        original_post, original_collapse = mhc.run_post, mhc.run_collapse
        from vllm.models.deepseek_v4_1.ced import gather_rows
        original_gather = gather_rows._init_fn

        def active(tensor):
            return (armed and tensor.shape[0] >= 512 and tensor.shape[0] % 4 == 0
                    and not torch.cuda.is_current_stream_capturing())

        def post(x, residual, previous_post, previous_comb, **kwargs):
            out = kwargs.get("out")
            if out is None or not active(residual):
                return original_post(x, residual, previous_post, previous_comb, **kwargs)
            group = get_tp_group()
            region = region_for(residual, group)
            key = ("post", id(kwargs["plan"]), residual.shape[0])
            reference = None
            if key not in decisions or not decisions[key]:
                full = [materialize(t, group) for t in (x, residual, previous_post, previous_comb)]
                original_post(*full, **kwargs)
                if decisions.get(key) is False:
                    return out
                reference = out.clone()
            local_kwargs = dict(kwargs, out=out[region])
            original_post(x[region], residual[region], previous_post[region], previous_comb[region], **local_kwargs)
            if reference is not None:
                flag = torch.tensor([int(torch.equal(reference[region], out[region]))], device=x.device, dtype=torch.int32)
                torch.distributed.all_reduce(flag, op=torch.distributed.ReduceOp.MIN, group=group.device_group)
                decisions[key] = bool(flag.item())
                if group.rank_in_group == 0:
                    print(f"[owned-mhc] operation=post rows={residual.shape[0]} guard=local-mhc-rows exact={'ON' if decisions[key] else 'OFF'}", flush=True)
                if not decisions[key]:
                    out.copy_(reference)
                    return out
            out.copy_(materialize(out, group))
            return out

        def collapse(state, pre_mix, **kwargs):
            if pre_mix is not None and active(state):
                pre_mix = materialize(pre_mix, get_tp_group())
            return original_collapse(state, pre_mix, **kwargs)

        def gather(source, indices):
            if source.ndim >= 2 and active(source):
                source = materialize(source, get_tp_group())
            return original_gather(source, indices)

        mhc.run_post, mhc.run_collapse = post, collapse
        gather_rows.register_kernel("cuda")(gather)
    mhc._owned_row_trial = True
    print(f"[owned-mhc] armed guarded native prefill row slices retain_residuals={retain}", flush=True)
