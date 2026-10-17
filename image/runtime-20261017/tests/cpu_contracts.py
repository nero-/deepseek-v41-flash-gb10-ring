"""Check source/import contracts before allowing candidate GPU qualification."""
import ast
import hashlib
import importlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys
import tempfile

site = Path('/usr/local/lib/python3.12/dist-packages')
sys.path.insert(0, '/opt/sparkring/transports')
import sparkring_transport_selector as selector
import os

bundle = selector.verify_bundle(os.environ['SPARKRING_TRANSPORT_PROFILE'],
                                os.environ['SPARKRING_TRANSPORT_MANIFEST_SHA256'])
import b12x
from b12x.comm import roce
from b12x.comm.roce import _preparation
from b12x.preparation import Plan, PreparedCall
assert Path(roce.__file__).is_relative_to(bundle)
assert Path(b12x.__file__).is_relative_to(site / 'flashinfer/experimental/b12x')
assert importlib.import_module('flashinfer.experimental.b12x.preparation') is importlib.import_module('b12x.preparation')
assert roce.API_VERSION == 1
assert hasattr(_preparation.compile_roce, 'cache_info')
assert 'b12x_loader' not in {e.name for e in metadata.entry_points(group='vllm.general_plugins')}
assert 'sparkring_status' in {e.name for e in metadata.entry_points(group='vllm.general_plugins')}

def source(relative):
    return (site / relative).read_text()

def methods(relative, cls):
    node = next(n for n in ast.parse(source(relative)).body if isinstance(n, ast.ClassDef) and n.name == cls)
    return {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

assert {'schedule','_has_pending_local_prefill','_request_is_runnable_decode'} <= methods('vllm/v1/core/sched/scheduler.py','Scheduler')
assert 'add_requests' in methods('vllm/v1/worker/gpu/model_runner.py','GPUModelRunner')
assert 'compile_or_warm_up_model' in methods('vllm/v1/worker/gpu_worker.py','Worker')
assert 'slot_mapping_circular' in source('vllm/v1/worker/gpu/model_runner.py')
assert 'mapping_enabled & ~circular' in source('vllm/v1/worker/gpu/block_table.py')
assert 'retain_cuda_graph_capture_resource(arena)' in source('vllm/models/deepseek_v4_1/attention.py')
assert hashlib.sha256((site / 'vllm/tokenizers/deepseek_v41_encoding.py').read_bytes()).hexdigest() == '975347b83ee68f06027893d2a8bcd248323186fe2f778a039cb5c639f85afd51'

# A damaged copied bundle must fail closed before any GPU runtime is constructed.
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    copied = root / os.environ['SPARKRING_TRANSPORT_PROFILE']
    shutil.copytree(bundle.parent, copied, ignore=shutil.ignore_patterns('__pycache__'))
    p = copied / 'roce/_path_config.py'
    p.write_text(p.read_text() + '\n# altered\n')
    try:
        selector.verify_bundle(os.environ['SPARKRING_TRANSPORT_PROFILE'],
                               os.environ['SPARKRING_TRANSPORT_MANIFEST_SHA256'], root)
    except ValueError as e:
        assert 'SHA-256 differs' in str(e)
    else:
        raise AssertionError('Corrupt transport accepted')
print(json.dumps({'passed':True,'transport':str(bundle),'b12x_provider':str(b12x.__file__)}))
