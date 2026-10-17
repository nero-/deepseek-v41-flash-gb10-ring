"""Stopped-fleet eager/CUDA-graph checks of the selected ring transport.

Launch one process per node with RANK/WORLD_SIZE/MASTER_ADDR/MASTER_PORT set.
No model loads or serving configuration edits are made by this test.
"""
import datetime
import json
import os
from pathlib import Path
import time

import torch
import torch.distributed as dist

dist.init_process_group('gloo', timeout=datetime.timedelta(seconds=240))
rank, world = dist.get_rank(), dist.get_world_size()
assert world == 4
torch.cuda.set_device(0)
device = torch.device('cuda', 0)
from b12x.comm import roce
from b12x.comm.roce import _preparation
from b12x.preparation import CollectiveRequirement, PreparationSession, PreparedCall

runtime = roce.AllReduce.from_exchange_group(
    exchange_group=dist.group.WORLD, device=device,
    max_size=2 << 20, max_gather_bytes=16 << 20,
)
query = roce.query_from_runtime(runtime, surface='AllReduce.all_reduce',
    call={'dtypes': ('float16', 'bfloat16', 'float32')}, topology='roce_rdma',
    peer_hosts=tuple(f'rank:{r}' for r in range(world)))
plan = roce.plan(query, runtime=runtime)
seeds = [torch.zeros(16 // d.itemsize, dtype=d, device=device)
         for d in (torch.float16, torch.bfloat16, torch.float32)]

def prepare(state):
    calls = [_preparation.prepared_call(state, inp=x) for x in seeds]
    calls.append(_preparation.prepared_gather_call(state, inp=seeds[1]))
    return PreparedCall(run=lambda: [c.run() for c in calls], output=tuple(c.output for c in calls))

session = PreparationSession(device=device, autotune=False, compile_workers=2)

def coordinate(progress):
    assert progress.ready_cache is None and not progress.ready_tuning
    ready = tuple(item.key for item in progress.ready_collectives)
    peers = [None] * world
    dist.all_gather_object(peers, ready)
    common = set.intersection(*(set(keys) for keys in peers))
    return sorted(common)[0] if common else None

session.prepare((plan.request(name='ring-collectives', prepare_call=prepare,
    collective=CollectiveRequirement(key='ring-collectives', ranks=tuple(range(world)))),),
    coordinator=coordinate)
session.freeze()
results = []
for dtype in (torch.bfloat16, torch.float16, torch.float32):
    for size in (16, 10240, 65536, 262144, 524288, 983040, 1048576, 1769472, 2097152):
        count = size // dtype.itemsize
        # Exactly representable values give an independent, exact four-rank oracle.
        x = ((torch.arange(count, device=device) % 17) - 8).to(dtype) + rank
        expected = (x.float() - rank) * world + sum(range(world))
        expected = expected.to(dtype)
        out = torch.empty_like(x)
        runtime.all_reduce(x, out=out, plan=plan)
        torch.cuda.synchronize()
        runtime.check_health()
        assert torch.equal(out, expected), ('eager reduce', rank, dtype, size)
        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            graph = torch.cuda.CUDAGraph()
            with runtime.capture(stream=stream):
                with torch.cuda.graph(graph, stream=stream):
                    for _ in range(20):
                        runtime.all_reduce(x, out=out, plan=plan)
            for _ in range(10):
                out.fill_(float('nan'))
                graph.replay()
                stream.synchronize()
                runtime.check_health()
                assert torch.equal(out, expected), ('graph reduce', rank, dtype, size)
        torch.cuda.current_stream().wait_stream(stream)
        results.append({'operation':'all_reduce','dtype':str(dtype),'bytes':size,'graph_replays':10,'ops_per_graph':20})

for dtype in (torch.bfloat16, torch.int32):
    for size in (16, 10240, 262144, 1048576, 4194304, 16777216):
        count = size // dtype.itemsize
        x = torch.full((count,), rank + 1, dtype=dtype, device=device)
        expected = torch.cat([torch.full_like(x, r + 1) for r in range(world)])
        out = runtime.all_gather(x, dim=0, plan=plan)
        torch.cuda.synchronize()
        runtime.check_health()
        assert torch.equal(out, expected), ('eager gather', rank, dtype, size)
        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            graph = torch.cuda.CUDAGraph()
            with runtime.capture(stream=stream):
                with torch.cuda.graph(graph, stream=stream):
                    output = runtime.all_gather(x, dim=0, plan=plan)
            for _ in range(10):
                output.fill_(0)
                graph.replay()
                stream.synchronize()
                runtime.check_health()
                assert torch.equal(output, expected), ('graph gather', rank, dtype, size)
        torch.cuda.current_stream().wait_stream(stream)
        results.append({'operation':'all_gather','dtype':str(dtype),'shard_bytes':size,'graph_replays':10})

# Verify that a large message takes the preserved patched-NCCL path successfully.
oversize = torch.ones((4 << 20) // 2, dtype=torch.bfloat16, device=device)
assert not runtime.should_allreduce(oversize)
nccl = dist.new_group(backend='nccl', timeout=datetime.timedelta(seconds=180))
dist.all_reduce(oversize, group=nccl)
torch.cuda.synchronize()
assert torch.equal(oversize, torch.full_like(oversize, world))
results.append({'operation':'nccl_fallback','bytes':4 << 20})
dist.barrier()
report = {'rank':rank, 'passed':True, 'cases':results, 'runtime_stats':runtime.stats(),
          'completed_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
Path(f'/receipts/collectives-r{rank}.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
print(json.dumps({'rank':rank, 'passed':True, 'cases':len(results)}), flush=True)
runtime.close()
session.close() if hasattr(session, 'close') else None
dist.destroy_process_group()
