"""DeepSeek adapter for native shortlist-only DSpark Markov projection.

Retains packed NVFP4 rows for the native gathered kernel and uses the native
truncated-proposal sampler/cache path. Full target logits are unchanged.
"""
def register():
    import os
    from vllm.model_executor.models.qwen3_dspark import DSparkMarkovHead
    from vllm.models.deepseek_v4_1.nvidia.dspark import DSparkDeepseekV4ForCausalLM
    from vllm.v1.worker.gpu.spec_decode.dspark.speculator import DSparkSpeculator

    if getattr(DSparkSpeculator, "_local_markov_shortlist", False):
        return
    k = int(os.environ.get("DSV41_MARKOV_SHORTLIST", "20"))
    if not 8 <= k <= 128:
        raise ValueError("Invalid draft shortlist")
    original_init = DSparkMarkovHead.__init__
    original_load = DSparkSpeculator.load_model

    def init(self, *args, **kwargs):
        kwargs["retain_weight_for_gather"] = True
        return original_init(self, *args, **kwargs)

    def apply(self, markov_embed, logits, values, index):
        return self.model.markov_head.apply_bias_gathered(
            markov_embed, logits, values, index, self.logits_processor.scale)

    def load(self, *args, **kwargs):
        result = original_load(self, *args, **kwargs)
        if not isinstance(self.model, DSparkDeepseekV4ForCausalLM):
            raise RuntimeError("Shortlist adapter requires pinned DeepSeek DSpark")
        head = self.model.model.markov_head.markov_w2
        if not head.is_w4a16_nvfp4 or not hasattr(head, "_nvfp4_weight_for_gather"):
            raise RuntimeError("Shortlist requires retained original NVFP4 head rows")
        self._draft_topk = k
        print(f"[markov-shortlist] enabled k={k}; native proposal cache/rejection retained", flush=True)
        return result

    DSparkMarkovHead.__init__ = init
    DSparkDeepseekV4ForCausalLM.apply_markov_bias_gathered = apply
    DSparkSpeculator.load_model = load
    DSparkSpeculator._local_markov_shortlist = True
