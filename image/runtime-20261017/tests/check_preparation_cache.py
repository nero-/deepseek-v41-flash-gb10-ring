"""Regression: materializing a transport plan must not consume cached programs."""
import ast
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / 'transports/tp2-rocenante-adaptive-prepared/roce/_preparation.py'
tree = ast.parse(source.read_text())
plan = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'plan')
materialize = next(n for n in plan.body if isinstance(n, ast.FunctionDef) and n.name == 'materialize')
cached = {'bf16': object(), 'gather': object()}
calls = []
scope = {
    'compile_roce': lambda payload, ordinal: cached,
    'payload': object(), 'query': object(),
    '_dtypes': lambda query: ('bf16',),
    'runtime': SimpleNamespace(_prepare_resources=lambda *a, **k: calls.append((a, k))),
    '_PreparedRoce': lambda runtime, programs, gather: (programs, gather),
}
exec(compile(ast.Module(body=[materialize], type_ignores=[]), str(source), 'exec'), scope)
first = scope['materialize'](None, SimpleNamespace(ordinal=0))
second = scope['materialize'](None, SimpleNamespace(ordinal=0))
assert first == second
assert set(cached) == {'bf16', 'gather'}
assert set(first[0]) == {'bf16'} and first[0] is not cached
assert len(calls) == 2
print('Prepared transport cache reuse passed')
