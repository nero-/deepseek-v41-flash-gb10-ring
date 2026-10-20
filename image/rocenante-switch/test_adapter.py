#!/usr/bin/env python3
"""CPU contract tests for a staged adapter; not GPU/transport qualification."""

import ast
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

STAGE = Path(sys.argv.pop(1))
SOURCE = STAGE / "site/vllm/distributed/device_communicators/b12x_roce_all_reduce.py"


def parse_size(value):
    # Upstream's parser is unchanged; this stub isolates adapter contract tests.
    match = re.fullmatch(r"(-?\d+)(MiB)?", value)
    if match is None:
        raise ValueError(value)
    return int(match[1]) * ((1 << 20) if match[2] else 1)


def module(name, **attrs):
    result = ModuleType(name)
    result.__dict__.update(attrs)
    return result


@dataclass
class Call:
    run: object
    output: object = None


class AdapterContracts(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.proxy = module("b12x.comm.roce._proxy", ABI_VERSION=8)
        self.runtime = NS(
            pipe_bytes=64 << 20, pipe_threshold=1 << 20,
            max_size=2 << 20, hca_names=("railA", "railB"),
        )
        self.factory = Mock(return_value=self.runtime)
        self.factory.from_exchange_group = Mock(
            side_effect=AssertionError("Compatibility wrapper ignores pipe settings")
        )
        self.roce = module(
            "b12x.comm.roce", API_VERSION=1, _proxy=self.proxy,
            is_supported=lambda device: True,
            AllReduce=self.factory,
            query_from_runtime=lambda *a, **k: None,
            plan=lambda *a, **k: NS(request=lambda **k: NS(**k)),
        )
        self.preparation = module("b12x.comm.roce._preparation")
        self.roce._preparation = self.preparation
        self.modules = patch.dict(sys.modules, {
            "b12x": module("b12x"),
            "b12x.comm": module("b12x.comm", roce=self.roce),
            "b12x.comm.roce": self.roce,
            "b12x.comm.roce._proxy": self.proxy,
            "b12x.comm.roce._preparation": self.preparation,
            "b12x.preparation": module("b12x.preparation", CollectiveRequirement=NS),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.dist = NS(
            get_rank=lambda group=None: 0,
            get_world_size=lambda group=None: 4,
            all_gather_object=lambda output, vote, **kw: output.__setitem__(
                slice(None), [vote] * 4
            ),
        )
        self.torch = NS(
            float16=NS(itemsize=2), bfloat16=NS(itemsize=2),
            float32=NS(itemsize=4),
            zeros=lambda count, dtype, device: NS(
                nbytes=count * dtype.itemsize, dtype=dtype, device=device
            ),
        )
        namespace = {
            "os": os, "_parse_byte_size": parse_size, "dist": self.dist,
            "torch": self.torch, "contextmanager": contextmanager,
            "envs": NS(VLLM_ROCE_ALLREDUCE_MAX_SIZE="2MiB",
                       VLLM_ROCE_ALLGATHER_MAX_SIZE="16MiB"),
            "in_the_same_node_as": lambda *a, **k: [False] * 4,
            "register_b12x_unit_provider": Mock(), "logger": Mock(),
            "B12xPreparationUnit": NS, "PreparationResourceUnavailableError": RuntimeError,
        }
        tree = ast.parse(SOURCE.read_text())
        # Execute the actual staged definitions with controlled transport/GPU
        # dependencies; do not import CUDA libraries on the workstation.
        tree.body = [
            item for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.ClassDef, ast.Assign))
            and not (isinstance(item, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "logger"
                             for t in item.targets))
        ]
        tree.body.insert(0, ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations")], level=0
        ))
        exec(compile(ast.fix_missing_locations(tree), str(SOURCE), "exec"), namespace)
        self.limits = namespace["_two_shot_limits"]
        self.cls = namespace["B12xRoceAllReduce"]
        self.adapter = self.cls.__new__(self.cls)
        self.adapter.world_size = 4
        self.adapter.rank = 0
        self.adapter.device = "cuda:0"
        self.adapter.group = "gloo"

    def test_disabled_default_and_world_thresholds(self):
        self.assertEqual(self.limits(4), (0, 1 << 20))
        self.assertEqual(self.limits(2), (0, 2 << 20))

    def test_invalid_sizes_rejected_before_constructor(self):
        for capacity, threshold in [
            ("-16", "16"), ("17", "16"), ("1024", "0"),
            ("1024", "17"), ("1024", "2048"),
        ]:
            with self.subTest(capacity=capacity, threshold=threshold):
                os.environ.update(DS41_ROCE_PIPE_BYTES=capacity,
                                  DS41_ROCE_PIPE_THRESHOLD=threshold)
                reason, limits = self.adapter._local_capability()
                self.assertIsNotNone(reason)
                self.assertIsNone(limits)
        self.factory.assert_not_called()

    def test_old_proxy_is_rejected_when_two_shot_enabled(self):
        os.environ["DS41_ROCE_PIPE_BYTES"] = "64MiB"
        self.proxy.ABI_VERSION = 7
        reason, limits = self.adapter._local_capability()
        self.assertIn("ABI 8", reason)
        self.assertIsNone(limits)

    def test_rank_capacity_and_threshold_must_agree(self):
        reference = (2 << 20, 16 << 20, 64 << 20, 1 << 20)
        for index in (2, 3):
            different = list(reference)
            different[index] *= 2
            self.dist.all_gather_object = lambda output, vote, **kw: output.__setitem__(
                slice(None), [vote, (None, tuple(different)), vote, vote]
            )
            self.assertIn("differ across ranks", self.adapter._exchange_vote(None, reference))

    def test_constructor_receives_pipe_settings(self):
        os.environ["DS41_ROCE_PIPE_BYTES"] = "64MiB"
        self.cls("gloo", "cuda-group", "cuda:0")
        kwargs = self.factory.call_args.kwargs
        self.factory.from_exchange_group.assert_not_called()
        self.assertEqual(kwargs["exchange_group"], "gloo")
        self.assertEqual(kwargs["pipe_bytes"], 64 << 20)
        self.assertEqual(kwargs["pipe_threshold"], 1 << 20)
        self.assertEqual(kwargs["max_size"], 2 << 20)
        self.assertEqual(kwargs["max_gather_bytes"], 16 << 20)

    def test_mismatched_rank_does_not_construct_transport(self):
        self.dist.all_gather_object = lambda output, vote, **kw: output.__setitem__(
            slice(None), [vote, ("bad pipe setting", None), vote, vote]
        )
        adapter = self.cls("gloo", "cuda-group", "cuda:0")
        self.assertTrue(adapter.disabled)
        self.factory.assert_not_called()

    def test_preparation_runs_one_shot_and_two_shot_for_each_dtype(self):
        adapter = self.adapter
        adapter.disabled = False
        adapter._runtime = self.runtime
        adapter.global_ranks = (0, 1, 2, 3)
        ran = []
        self.preparation.prepared_call = lambda state, inp: Call(
            run=lambda: ran.append(("reduce", inp.nbytes)), output=inp
        )
        self.preparation.prepared_gather_call = lambda state, inp: Call(
            run=lambda: ran.append(("gather", inp.nbytes))
        )
        units = adapter.get_b12x_preparation_units(adapter, NS(stage="weights"))
        prepared = units[0].requests[0].prepare_call(object())
        prepared.run()
        self.assertEqual(ran, [
            ("reduce", 16), ("reduce", 16), ("reduce", 16),
            ("reduce", 1 << 20), ("reduce", 1 << 20), ("reduce", 1 << 20),
            ("gather", 16),
        ])


if __name__ == "__main__":
    unittest.main()
