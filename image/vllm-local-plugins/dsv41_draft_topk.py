# SPDX-License-Identifier: Apache-2.0
"""Qwen-derived proposal filtering at the native DSpark sampling boundary.

Filter after the full base + Markov logits are computed, before both draft
sampling and its verification cache. Target sampling/vocabulary are unchanged.
This does not claim to save the already completed draft-head matrix multiply.
"""
def limit_draft_logits(logits, top_k=20):
    import torch
    if not 1 <= top_k <= logits.shape[-1]:
        raise ValueError("Draft top-k exceeds the vocabulary")
    threshold = torch.topk(logits, top_k, dim=-1).values[..., -1:]
    return logits.masked_fill(logits < threshold, float("-inf"))


def register():
    from vllm.v1.worker.gpu.spec_decode.dspark.speculator import DSparkSpeculator
    if getattr(DSparkSpeculator, "_local_top20_installed", False):
        return
    original = DSparkSpeculator._sample_logits

    def sample(self, logits, idx_map, sample_pos, step):
        if self.draft_logits is None or self._draft_topk is not None:
            raise RuntimeError("Local top-20 requires probabilistic DSpark without base-logit top-k")
        return original(self, limit_draft_logits(logits), idx_map, sample_pos, step)

    DSparkSpeculator._sample_logits = sample
    DSparkSpeculator._local_top20_installed = True
    print("[local-draft-top20] full Markov logits filtered before sampling and verification cache", flush=True)
