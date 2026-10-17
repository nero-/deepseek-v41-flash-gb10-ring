"""Bounded source/control-flow checks; no vLLM imports, GPU work or mutation."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent


def indexer_publication(revision):
    source = (ROOT / 'upstream' / revision / 'inference/model.py').read_text()
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'Indexer')
    forward = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'forward')
    blocks = [n for n in forward.body if isinstance(n, ast.If) and 'self.owns_k' in ast.unparse(n.test)]
    shared = NS(index_k='decoder-cache-left-from-previous-step')
    env = dict(self=NS(owns_k=True, k_cache='encoder-cache'), latent=None, shared_attn=shared)
    exec(compile(ast.fix_missing_locations(ast.Module(body=blocks, type_ignores=[])), '<publication>', 'exec'), env)
    return shared.index_k


old = indexer_publication('dba1be0a40aa45a94ad051997016db3960a90277')
new = indexer_publication('5254448103b6254fc646dacbca1cbbf20e9216c1')
assert old == 'decoder-cache-left-from-previous-step' and new == 'encoder-cache'
source = (ROOT / 'runtime/deepseek_v4_1/attention.py').read_text()
tree = ast.parse(source)
bindings = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) == 'dsa_indexer.bind']
assert bindings
expressions = [ast.unparse(k.value) for call in bindings for k in call.keywords if k.arg == 'index_k_cache']
assert 'self.indexer.k_cache.kv_cache' in expressions
assert 'shared_attn.index_k' not in source
assert 'self.prefix, self.owns_k, self.k_cache = prefix, owns_k, k_cache' in source
assert 'f"{prefix}.indexer.k_cache"' in source
assert 'f"{_source(prefix, self.kv_source_layer_id)}.indexer.k_cache"' in source

# Execute the installed WO orchestration with recording tensor/kernel stand-ins.
# This proves quantized activation payloads feed WO-A on both WO-B dispatch paths;
# it does not test kernel arithmetic or establish bitwise equality to TileLang.
prep = ast.parse((ROOT / 'runtime/b12x/gemm/wo_projection/_preparation.py').read_text())
method = next(n for n in ast.walk(prep) if isinstance(n, ast.FunctionDef) and n.name == 'run_inv_rope')
env = {}
exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), '<installed-WO>', 'exec'), env)

class Tensor:
    def __init__(self, label, ndim=3):
        self.label, self.ndim, self.shape = label, ndim, (6, 4096, 2)
    def view(self, *args): return self
    def reshape(self, *args): return self
    def unsqueeze(self, *args): return self
    def __getitem__(self, key): return self

events = []
def quantize(*args, **kwargs):
    events.append('inverse_rope_then_quantize')
def run_a(lhs, rhs, **kwargs):
    assert events == ['inverse_rope_then_quantize']
    assert lhs[0].label == 'quantized_A'
    events.append('WO_A_consumes_quantized_input')
def quant_b(*args): events.append('quantize_B')
def run_b(*args, **kwargs): events.append('WO_B')
quant = NS(values=Tensor('quantized_A'), scale_mma=Tensor('scale_A'))
weights = NS(groups=2, rank=1024, hidden=5120,
             wo_a=NS(values=Tensor('weight_A'), scale_mma=Tensor('wa_scale'), values_tiled=None),
             wo_b=NS(values=Tensor('weight_B'), scale_mma=Tensor('wb_scale'), values_tiled=None))
binding = NS(o=Tensor('raw'), positions=None, cos_sin_cache=None, x_q=quant, weights=weights,
             heads_per_group=8, nope_dim=448, rope_dim=64, tmp=Tensor('tmp'),
             tmp_q=NS(values=Tensor('quant_B'), scale_mma=Tensor('qb_scale')),
             output=Tensor('result'), return_3d=True)
traces = []
for fused in (False, True):
    events.clear()
    state = NS(quantizers=NS(quantize_a_inv_rope=quantize, quantize_b=quant_b),
               query=NS(group_width=4096, groups=2, wo_b_tiled=False),
               ordinary_a=NS(run=run_a, lowering=NS(b_tile_major=False)),
               ordinary_b=NS(run=run_b), fused_b=NS(run=run_b) if fused else None)
    assert env['run_inv_rope'](state, binding) is binding.output
    traces.append({'fused_B': fused, 'events': list(events)})
report = {'status': 'PASS', 'upstream_incomplete_group_old': old,
          'upstream_incomplete_group_fixed': new,
          'native_cache_selection': 'source-bound cache; no shared_attn.index_k slot',
          'native_score_cache_arguments': expressions, 'native_WO_control_flow': traces,
          'limits': 'Static and mocked control-flow checks only; not a GPU numerical proof.'}
(ROOT / 'source-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
