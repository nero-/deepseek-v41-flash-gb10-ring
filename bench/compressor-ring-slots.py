#!/usr/bin/env python3
"""Probe the real worker's per-spec ring mapping, on old and corrected builds."""
import inspect,json
import torch
from vllm.v1.kv_cache_interface import CircularBufferSpec,FullAttentionSpec
from vllm.v1.worker.gpu import block_table as bt
specs=[FullAttentionSpec(block_size=16,num_kv_heads=1,head_size=64,dtype=torch.bfloat16),CircularBufferSpec(block_size=8,num_kv_heads=1,head_size=1024,head_size_v=0,dtype=torch.float32)]
mode=getattr(bt,'slot_mapping_mode',lambda s:(s.uses_slot_mapping,isinstance(s,CircularBufferSpec)))
enabled,circular=zip(*(mode(s) for s in specs))
kw=dict(block_sizes=[16,8],max_num_reqs=2,max_num_batched_tokens=64,max_num_blocks_per_group=[4,1],device=torch.device('cuda'),kernel_block_sizes=[16,8],slot_mapping_enabled=list(enabled))
if 'slot_mapping_circular' in inspect.signature(bt.BlockTables).parameters:kw['slot_mapping_circular']=list(circular)
t=bt.BlockTables(**kw);t.append_block_ids(req_index=0,new_block_ids=([3,4,5],[9]),overwrite=True);t.append_block_ids(req_index=1,new_block_ids=([6],[]),overwrite=True);t.apply_staged_writes()
pos=list(range(3,40))+[5,6]
slots=t.compute_slot_mappings(torch.tensor([0,1],device='cuda',dtype=torch.int32),torch.tensor([0,37,39],device='cuda',dtype=torch.int32),torch.tensor(pos+[0,0],device='cuda',dtype=torch.int64),num_tokens_padded=41)
actual=slots[1].tolist();expected=[9*8+p%8 for p in pos[:37]]+[-1]*4
paged=[[3,4,5][p//16]*16+p%16 for p in pos[:37]]+[101,102,-1,-1]
passed=actual==expected and slots[0].tolist()==paged
print(json.dumps({'mapping_enabled':enabled,'mapping_circular':circular,'ring_actual':actual,'ring_expected':expected,'paged_correct':slots[0].tolist()==paged,'passed':passed}),flush=True)
raise SystemExit(0 if passed else 1)
