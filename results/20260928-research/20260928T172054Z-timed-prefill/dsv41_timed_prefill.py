"""Experimental bounded prefill quantum from observed scheduler turnaround.

Measures schedule-to-output wall time (including queueing), not GPU kernel time.
The controller acts only with >=4 runnable decoders and pending prefill.
"""
import math


def choose_budget(seconds_per_token, target_seconds, maximum=8192):
    desired = target_seconds / seconds_per_token if seconds_per_token > 0 else 4096
    choices = [x for x in (1024, 2048, 3072, 4096, 6144, 8192) if x <= maximum]
    return max((x for x in choices if x <= desired), default=min(choices))


def register():
    import os
    import time
    from vllm.v1.core.sched.scheduler import Scheduler

    if getattr(Scheduler, "_local_timed_prefill", False):
        return
    if getattr(Scheduler, "_local_adaptive_prefill_installed", False):
        raise RuntimeError("Timed and fixed adaptive prefill plugins must not be combined")
    original_schedule = Scheduler.schedule
    original_update = Scheduler.update_from_output
    target = float(os.environ.get("DSV41_PREFILL_TARGET_SECONDS", "0.8"))
    if not 0.2 <= target <= 2:
        raise ValueError("Invalid prefill time target")

    def schedule(self, *args, **kwargs):
        if self.compute_share_controller is not None:
            raise RuntimeError("Timed prefill requires native compute sharing disabled")
        ceiling = self.max_num_scheduled_tokens
        pending = self._has_pending_local_prefill()
        decoders = sum(self._request_is_runnable_decode(r, scheduling_step=self.current_step + 1)
                       for r in self.running) if pending else 0
        requests = self.requests
        lengths = [r.num_computed_tokens for r in self.running if r.num_computed_tokens < r.num_prompt_tokens]
        bucket = int(math.log2(max(8192, max(lengths, default=8192))))
        costs = getattr(self, "_local_prefill_costs", {})
        active = pending and decoders >= 4
        budget = choose_budget(costs.get(bucket, target / 4096), target, ceiling) if active else ceiling
        before = {rid: max(0, r.num_prompt_tokens - r.num_computed_tokens) for rid, r in requests.items()}
        start = time.monotonic()
        self.max_num_scheduled_tokens = budget
        try:
            output = original_schedule(self, *args, **kwargs)
        finally:
            self.max_num_scheduled_tokens = ceiling
        if active:
            count = sum(min(n, before.get(rid, 0)) for rid, n in output.num_scheduled_tokens.items())
            records = getattr(self, "_local_prefill_records", {})
            if count >= 512:
                records[id(output)] = (start, count, bucket)
                while len(records) > 16:
                    records.pop(next(iter(records)))
            self._local_prefill_records = records
            if budget != getattr(self, "_local_last_budget", None):
                print(f"[timed-prefill] budget={budget} context_bucket={bucket} decoders={decoders}", flush=True)
                self._local_last_budget = budget
        return output

    def update(self, scheduler_output, model_runner_output):
        record = getattr(self, "_local_prefill_records", {}).pop(id(scheduler_output), None)
        if record:
            start, count, bucket = record
            elapsed = time.monotonic() - start
            if 0.01 <= elapsed <= 10:
                costs = getattr(self, "_local_prefill_costs", {})
                observed = elapsed / count
                costs[bucket] = 0.75 * costs.get(bucket, observed) + 0.25 * observed
                self._local_prefill_costs = costs
        return original_update(self, scheduler_output, model_runner_output)

    Scheduler.schedule = schedule
    Scheduler.update_from_output = update
    Scheduler._local_timed_prefill = True
    print(f"[timed-prefill] armed target_seconds={target}", flush=True)
