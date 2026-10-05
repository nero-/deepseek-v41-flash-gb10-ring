#!/usr/bin/env python3
"""Exercise retained SparkRing fixed regimes against beta's execution API."""
import json
import sys
import torch
sys.path.insert(0, '/tests/b12x')
from tests.gemm.test_blockscaled import _quantize_mxfp4_rows, _dequantize_mxfp4_rows
from b12x._lib.intrinsics import swizzle_block_scale
from b12x.gemm import blockscaled
from b12x.preparation import PreparationSession, PreparedCall

torch.manual_seed(104)
n, k, capacity = 128, 256, 16
b, bs = _quantize_mxfp4_rows(torch.randn(n, k, device='cuda') * .3)
bscale = swizzle_block_scale(bs)
cases = {}
for rows in (1, 6, 7, capacity):
    a, sa = _quantize_mxfp4_rows(torch.randn(rows, k, device='cuda') * .3)
    expected = (_dequantize_mxfp4_rows(a, sa).bfloat16()
                @ _dequantize_mxfp4_rows(b, bs).bfloat16().T).bfloat16()
    cases[rows] = (a, swizzle_block_scale(sa), expected)
query = blockscaled.FixedBlockscaledQuery(
    recipe='mxfp4', call_kind='serialized', max_rows=capacity,
    in_features=k, padded_in_features=k, out_features=n,
    input_dtype='uint8', output_dtype='bfloat16', expected_m=None)
plan = blockscaled.plan_regimes(query, exact_m=(1, 6))
def prepare_call(state):
    a, sa, _ = cases[state.query.max_rows]
    return PreparedCall(run=lambda: state.run_serialized(
        a, sa, b, bscale, None, ab_dtype='float4_e2m1fn',
        sf_dtype='float8_e8m0fnu', c_dtype='bfloat16', sf_vec_size=32,
        block_fp8=False, stream=None))
with PreparationSession(device='cuda', autotune=False, compile_workers=2) as session:
    session.prepare((plan.request(name='fixed-regime-parity',
                                 prepare_calls={rows: prepare_call for rows in plan.token_counts}),))
    session.freeze()
    for rows, (a, sa, expected) in cases.items():
        launch = torch.compile(lambda x, sx: blockscaled.mm_mxfp4(
            x, sx, b, bscale, plan=plan), fullgraph=True)
        actual = launch(a, sa)
        torch.testing.assert_close(actual, expected, rtol=0, atol=0)
        graph = torch.cuda.CUDAGraph()
        try:
            with torch.cuda.graph(graph):
                replayed = launch(a, sa)
            pointer, allocated = replayed.data_ptr(), torch.cuda.memory_allocated()
            for _ in range(3):
                replayed.fill_(float('nan'))
                graph.replay()
            torch.cuda.synchronize()
            torch.testing.assert_close(replayed, expected, rtol=0, atol=0)
            assert replayed.data_ptr() == pointer
            assert torch.cuda.memory_allocated() == allocated
        finally:
            graph.reset()
print(json.dumps({'passed': True, 'rows': list(cases), 'exact_rows': [1, 6],
                  'capacity': capacity, 'graph_replays': 3}), flush=True)
