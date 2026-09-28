"""Experimental SGLang-style decode-only replicated projection split.

Local general plugin for the pinned native DeepSeek V4.1 vLLM implementation.
Checkpoint precision and the large-row prefill path are unchanged. Each rank
computes contiguous output rows of fused_wqa_wkv for batches <= 96, then gathers.
The full replicated weights are retained for fallback and prefill. No upstream
source or installer receipt is modified. Requires B12x preparation of both paths.
"""
import copy
import os


def register():
    import torch
    from torch import nn
    from vllm.distributed import get_tp_group
    from vllm.models.deepseek_v4_1 import attention, b12x_layers as native
    from vllm.utils.b12x import set_b12x_preparation_provider

    if getattr(attention, "_local_decode_split_installed", False):
        return
    max_rows = int(os.environ.get("DSV41_VLLM_SPLIT_MAX_ROWS", "96"))
    if not 1 <= max_rows <= 96:
        raise ValueError("Local decode split requires 1 <= max rows <= 96")
    layers = native._LINEARS
    base = native.B12xFP8LinearMethod

    @torch.library.custom_op("dsv41_local::decode_split", mutates_args=())
    def split(x: torch.Tensor, key: int) -> torch.Tensor:
        layer = layers[key]
        proxy = layer._local_split_proxy
        rows = x.numel() // x.shape[-1]
        if rows > max_rows or layer._local_split_enabled is False:
            return base.apply(layer.quant_method, layer, x)
        group = get_tp_group()
        if layer._local_split_enabled is None:
            if torch.cuda.is_current_stream_capturing():
                raise RuntimeError("Decode split exactness must be decided before graph capture")
            start, end = layer._local_split_range
            generator = torch.Generator(device=x.device).manual_seed(4321)
            checks = [x] + [torch.randn((m, x.shape[-1]), generator=generator,
                       device=x.device, dtype=x.dtype) for m in (1, 6, 16)]
            exact = True
            for sample in checks:
                full = base.apply(layer.quant_method, layer, sample)
                part = base.apply(layer.quant_method, proxy, sample)
                exact = exact and torch.equal(full[..., start:end], part[..., :end-start])
            flag = torch.tensor([int(exact)], dtype=torch.int32, device=x.device)
            torch.distributed.all_reduce(flag, op=torch.distributed.ReduceOp.MIN, group=group.device_group)
            layer._local_split_enabled = bool(flag.item())
            if group.rank_in_group == 0:
                print(f"[local-decode-split] {layer.prefix}: bit-exact={'ON' if layer._local_split_enabled else 'OFF'}", flush=True)
            if not layer._local_split_enabled:
                return base.apply(layer.quant_method, layer, x)
        output = base.apply(layer.quant_method, proxy, x)
        width = layer._local_split_width
        if output.shape[-1] < width:
            output = torch.nn.functional.pad(output, (0, width - output.shape[-1]))
        gathered = group.all_gather(output.contiguous(), dim=-1)
        return torch.cat([gathered[..., rank * width:rank * width + count]
                          for rank, count in enumerate(layer._local_split_counts)], dim=-1)

    @split.register_fake
    def split_fake(x, key):
        layer = layers[key]
        return torch.empty((*x.shape[:-1], layer.weight.shape[0]), device=x.device, dtype=torch.bfloat16)

    class DecodeSplitMethod(base):
        def process_weights_after_loading(self, layer):
            super().process_weights_after_loading(layer)
            group = get_tp_group()
            n, k = layer.weight.shape
            if group.world_size != 4 or n % 128 or n // 128 < group.world_size:
                raise ValueError(f"Unsupported decode-split geometry: TP{group.world_size} {n}x{k}")
            tiles, extra = divmod(n // 128, group.world_size)
            counts = [(tiles + int(rank < extra)) * 128 for rank in range(group.world_size)]
            start = sum(counts[:group.rank_in_group])
            end = start + counts[group.rank_in_group]
            proxy = nn.Module()
            # Native B12x prepares kernels collectively: all ranks must declare
            # the same plan geometries, even when their useful slices differ.
            width = max(counts)
            weight = torch.zeros((width, k), device=layer.weight.device, dtype=layer.weight.dtype)
            weight[:end-start].copy_(layer.weight[start:end])
            scale = torch.ones((width // 32, k // 32), device=layer.weight.device,
                               dtype=torch.float32).to(layer.weight_scale_inv.dtype)
            scale[:(end-start)//32].copy_(layer.weight_scale_inv[start // 32:end // 32])
            proxy.weight = nn.Parameter(weight, requires_grad=False)
            proxy.weight_scale_inv = nn.Parameter(scale, requires_grad=False)
            base.process_weights_after_loading(self, proxy)
            selected = [(m, p) for m, p in zip(proxy.b12x_capacities, proxy.b12x_plans) if m <= max_rows]
            if not selected or selected[-1][0] != max_rows:
                raise ValueError("Decode split max rows must be a prepared execution capacity")
            proxy.b12x_capacities, proxy.b12x_plans = zip(*selected)
            # Keep proxy alive without registering a second model submodule/provider.
            object.__setattr__(layer, "_local_split_proxy", proxy)
            layer._local_split_range = (start, end)
            layer._local_split_counts = counts
            layer._local_split_width = max(counts)
            layer._local_split_enabled = None
            set_b12x_preparation_provider(layer, self)

        def get_b12x_preparation_units(self, layer, workload):
            return (base.get_b12x_preparation_units(self, layer, workload) +
                    base.get_b12x_preparation_units(self, layer._local_split_proxy, workload))

        def get_workspace_size(self, layer, num_tokens):
            full = base.get_workspace_size(self, layer, num_tokens)
            return max(full, base.get_workspace_size(self, layer._local_split_proxy, num_tokens)) if num_tokens <= max_rows else full

        def apply(self, layer, x, bias=None):
            if bias is not None:
                raise ValueError("Decode split requires bias-free projections")
            return split(x, layer.b12x_key)

    original = attention.MergedColumnParallelLinear

    class SplitMergedColumnParallelLinear(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if kwargs.get("prefix", "").endswith(".fused_wqa_wkv"):
                if not isinstance(self.quant_method, base) or not kwargs.get("disable_tp"):
                    raise RuntimeError("Pinned replicated FP8 Q/KV projection contract changed")
                method = copy.copy(self.quant_method)
                method.__class__ = DecodeSplitMethod
                self.quant_method = method

    attention.MergedColumnParallelLinear = SplitMergedColumnParallelLinear
    attention._local_decode_split_installed = True
    print(f"[local-decode-split] armed for fused_wqa_wkv, rows <= {max_rows}", flush=True)
