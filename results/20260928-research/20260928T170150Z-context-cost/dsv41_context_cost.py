"""Experimental context-conditioned native DSpark verification costs.

Uses the native cost builder, confidence estimator and rejection sampler.
Additional startup measurements retain graph shape/request-count accounting.
No per-step CUDA synchronization or independent rank-local timing decisions.
"""
import math


def context_key(contexts, available):
    length = max(1.0, sum(contexts) / max(1, len(contexts)))
    return min(available, key=lambda value: abs(math.log(max(1, value) / length)))


def register():
    import os
    from vllm import envs
    from vllm.distributed import get_tp_group
    from vllm.v1.worker.gpu.spec_decode.adaptive_verification import AdaptiveVerificationManager as Manager

    if getattr(Manager, "_local_context_cost", False):
        return
    original_profile = Manager.profile_costs
    original_get = Manager.get_num_tokens
    extra_contexts = tuple(int(x) for x in os.environ.get("DSV41_COST_CONTEXTS", "8192,65536,262144").split(","))
    if any(x < 1 or x > 262144 for x in extra_contexts):
        raise ValueError("Invalid context cost profile lengths")

    def profile(self, run_dummy, step_timing, capture_sizes, full_batch_shapes):
        original_profile(self, run_dummy, step_timing, capture_sizes, full_batch_shapes)
        base_context = int(envs.VLLM_ADAPTIVE_VERIFICATION_PROFILE_CONTEXT_LEN)
        base = (self.cost_tables, self.verify_cost_tables_by_num_reqs)
        tables = {base_context: base}
        for length in extra_contexts:
            if length == base_context:
                continue
            batches = [dict(batch, context_len=length) for batch in self.batches_to_profile(
                capture_sizes, full_batch_shapes, replays=1) if "profile_num_reqs" in batch]
            if not batches:
                raise RuntimeError("Context costs require native full graph profile shapes")
            for batch in batches:
                run_dummy(**batch)
            with step_timing.collect() as timings:
                for _ in range(3):
                    for batch in batches:
                        run_dummy(**batch)
            self.set_initial_cost_curves(timings)
            # Extra samples cover decode graphs only. Keep native eager costs.
            self.cost_tables[1][self._cudagraph_limit + 1:] = base[0][1][self._cudagraph_limit + 1:]
            for table in self.verify_cost_tables_by_num_reqs.values():
                table[self._cudagraph_limit + 1:] = base[0][1][self._cudagraph_limit + 1:]
            tables[length] = (self.cost_tables, self.verify_cost_tables_by_num_reqs)
            if get_tp_group().rank_in_group == 0:
                print(f"[context-cost] measured context={length} samples={len(timings)}", flush=True)
        self._local_context_tables = tables
        self.cost_tables, self.verify_cost_tables_by_num_reqs = base

    def get_num_tokens(self, num_tokens_per_req, draft_tokens):
        tables = getattr(self, "_local_context_tables", None)
        if not tables or not draft_tokens:
            return original_get(self, num_tokens_per_req, draft_tokens)
        contexts = [int(self.req_states.num_computed_tokens_np[self.req_states.req_id_to_index[rid]])
                    for rid in num_tokens_per_req]
        key = context_key(contexts, tables)
        saved = (self.cost_tables, self.verify_cost_tables_by_num_reqs)
        self.cost_tables, self.verify_cost_tables_by_num_reqs = tables[key]
        try:
            return original_get(self, num_tokens_per_req, draft_tokens)
        finally:
            self.cost_tables, self.verify_cost_tables_by_num_reqs = saved

    Manager.profile_costs = profile
    Manager.get_num_tokens = get_num_tokens
    Manager._local_context_cost = True
    print(f"[context-cost] armed contexts={extra_contexts}", flush=True)
