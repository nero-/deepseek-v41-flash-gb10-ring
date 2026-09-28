"""DeepSeek adapter for native shortlist-only DSpark Markov projection.

Retains packed NVFP4 rows for the native gathered kernel and uses the native
truncated-proposal sampler/cache path. Full target logits are unchanged.
"""
def register():
    import os
    from vllm.model_executor.models.qwen3_dspark import DSparkMarkovHead
    from vllm.model_executor.kernels.linear.nvfp4.b12x import B12xNvFp4LinearKernel
    from vllm.models.deepseek_v4_1.nvidia.dspark import DSparkDeepseekV4ForCausalLM
    from vllm.v1.worker.gpu.spec_decode.dspark.speculator import DSparkSpeculator

    if getattr(DSparkSpeculator, "_local_markov_shortlist", False):
        return
    k = int(os.environ.get("DSV41_MARKOV_SHORTLIST", "20"))
    if not 8 <= k <= 128:
        raise ValueError("Invalid draft shortlist")
    original_init = DSparkMarkovHead.__init__
    original_load = DSparkSpeculator.load_model
    original_pack = B12xNvFp4LinearKernel.process_weights_after_loading

    def init(self, *args, **kwargs):
        kwargs["retain_weight_for_gather"] = True
        return original_init(self, *args, **kwargs)

    def pack(self, layer):
        retain = getattr(layer, "_retain_weight_for_gather", False)
        if retain:
            # The online DeepSeek quantizer supplies ordinary row-major packed
            # bytes and group-16 scales here. B12x then swizzles the scales for
            # its full projection. Retain those exact quantized values rather
            # than quantizing the checkpoint again or indexing swizzled scales.
            layer._nvfp4_weight_for_gather = layer.weight.detach().clone()
            layer._nvfp4_weight_scale_for_gather = layer.weight_scale.detach().clone()
            layer._nvfp4_weight_global_scale_for_gather = layer.weight_global_scale.detach().clone()
            layer._nvfp4_group_size_for_gather = 16
        result = original_pack(self, layer)
        if retain:
            if layer.b12x_activation_mode != "a16":
                raise RuntimeError("Shortlist requires the original BF16 activation mode")
            layer.is_w4a16_nvfp4 = True
        return result

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
    B12xNvFp4LinearKernel.process_weights_after_loading = pack
    DSparkDeepseekV4ForCausalLM.apply_markov_bias_gathered = apply
    DSparkSpeculator.load_model = load
    DSparkSpeculator._local_markov_shortlist = True
