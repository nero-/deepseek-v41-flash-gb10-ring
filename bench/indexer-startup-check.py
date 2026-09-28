#!/usr/bin/env python3
"""CPU regression check: synthetic warmup requests must not arm indexer TP."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
for plugin in ('dsv41_indexer_tp', 'dsv41_context_indexer'):
    names = ('torch', 'b12x', 'b12x.attention', 'b12x.attention.dsa_indexer',
             'vllm', 'vllm.distributed', 'vllm.v1', 'vllm.v1.worker',
             'vllm.v1.worker.gpu', 'vllm.v1.worker.gpu.model_runner',
             'vllm.v1.worker.gpu_worker')
    previous = {name: sys.modules.get(name) for name in names}
    old_env = os.environ.get('DSV41_INDEXER_ARM_ON_REQUEST')
    try:
        for name in names:
            module = types.ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module
        dsa = sys.modules['b12x.attention.dsa_indexer']
        sys.modules['b12x.attention'].dsa_indexer = dsa
        dsa.bind = dsa.score = dsa.select = lambda *a, **kw: None
        sys.modules['vllm.distributed'].get_tp_group = lambda: None
        calls = []
        class GPUModelRunner:
            def add_requests(self, output):
                calls.extend(output.scheduled_new_reqs)
                return 'added'
        runner = GPUModelRunner()
        class Worker:
            def compile_or_warm_up_model(self):
                runner.add_requests(types.SimpleNamespace(scheduled_new_reqs=['synthetic-warmup']))
                return 'compiled'
        sys.modules['vllm.v1.worker.gpu.model_runner'].GPUModelRunner = GPUModelRunner
        sys.modules['vllm.v1.worker.gpu_worker'].Worker = Worker
        os.environ['DSV41_INDEXER_ARM_ON_REQUEST'] = '1'
        spec = importlib.util.spec_from_file_location(plugin, ROOT / 'image/vllm-local-plugins' / (plugin + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            module.register()
            worker = Worker()
            for cycle in range(2):
                before = log.getvalue().count('first real request observed')
                assert worker.compile_or_warm_up_model() == 'compiled'
                assert log.getvalue().count('first real request observed') == before
                assert runner.add_requests(types.SimpleNamespace(scheduled_new_reqs=[])) == 'added'
                assert log.getvalue().count('first real request observed') == before
                assert runner.add_requests(types.SimpleNamespace(scheduled_new_reqs=['real'])) == 'added'
                assert log.getvalue().count('first real request observed') == before + 1
                runner.add_requests(types.SimpleNamespace(scheduled_new_reqs=['another-real']))
                assert log.getvalue().count('first real request observed') == before + 1
        events = [line for line in log.getvalue().splitlines() if 'startup complete' in line or 'first real request' in line]
        assert len(events) == 4
        assert all('startup complete' in events[i] and 'first real request' in events[i + 1] for i in (0, 2))
        assert calls == ['synthetic-warmup', 'real', 'another-real'] * 2
        print('PASS', plugin, 'warmup exclusion, original call/return preservation, real activation, recapture reset')
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
        if old_env is None:
            os.environ.pop('DSV41_INDEXER_ARM_ON_REQUEST', None)
        else:
            os.environ['DSV41_INDEXER_ARM_ON_REQUEST'] = old_env
