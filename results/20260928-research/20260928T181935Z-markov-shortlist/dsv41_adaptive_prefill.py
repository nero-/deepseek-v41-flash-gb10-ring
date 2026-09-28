"""Keep the ordinary mixed scheduler, with a smaller budget under contention.

The native compute-share controller changes service allocation; this experiment
changes only the token quantum. Decode requests still participate in ordinary
mixed batches. Engine allocation/capture capacity stays at the configured 8K.
"""
def register():
    import os
    from vllm.v1.core.sched.scheduler import Scheduler

    if getattr(Scheduler, "_local_adaptive_prefill_installed", False):
        return
    limit = int(os.environ.get("DSV41_CONTENDED_PREFILL_TOKENS", "4096"))
    minimum_decoders = int(os.environ.get("DSV41_CONTENDED_MIN_DECODERS", "4"))
    if not 512 <= limit <= 8192 or not 1 <= minimum_decoders <= 16:
        raise ValueError("Invalid local adaptive prefill bounds")
    original = Scheduler.schedule

    def schedule(self, *args, **kwargs):
        if self.compute_share_controller is not None:
            raise RuntimeError("Local adaptive token budget requires native compute sharing to be disabled")
        configured = self.max_num_scheduled_tokens
        decoders = 0
        if self._has_pending_local_prefill():
            decoders = sum(self._request_is_runnable_decode(r, scheduling_step=self.current_step + 1)
                           for r in self.running)
        active = decoders >= minimum_decoders and configured > limit
        if active != getattr(self, "_local_budget_active", False):
            print(f"[local-prefill-budget] active={active} runnable_decoders={decoders} budget={limit if active else configured}", flush=True)
            self._local_budget_active = active
        if active:
            self.max_num_scheduled_tokens = limit
        try:
            return original(self, *args, **kwargs)
        finally:
            self.max_num_scheduled_tokens = configured

    Scheduler.schedule = schedule
    Scheduler._local_adaptive_prefill_installed = True
    print(f"[local-prefill-budget] armed: {limit} tokens when >= {minimum_decoders} decoders contend with prefill", flush=True)
