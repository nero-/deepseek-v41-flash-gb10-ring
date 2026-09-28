# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
# Helpers retained from the Qwen optimization GPU rejection-sampler tests.
import math
import torch
from vllm.v1.worker.gpu.sample.gumbel import gumbel_sample
from vllm.v1.worker.gpu.spec_decode.rejection_sampler_utils import rejection_sample
NARROW_NUM_TRIALS = 200_000

def _build_rejection_sample_inputs(
    target_logits_1d: torch.Tensor,
    draft_logits_1d: torch.Tensor,
    num_speculative_steps: int,
    temperature: float,
    num_trials: int,
) -> dict:
    """Build rejection_sample kwargs from a fixed target and draft distribution.

    target_logits_1d must already have temperature applied (the sampler applies
    sampling params before verification), whereas draft_logits_1d must not:
    rejection_sample divides the draft logits by the temperature on load.
    """
    device = target_logits_1d.device
    vocab_size = target_logits_1d.shape[0]
    K = num_speculative_steps
    num_logits = num_trials * (K + 1)

    target_logits = target_logits_1d.unsqueeze(0).expand(num_logits, -1).contiguous()
    draft_logits = (
        draft_logits_1d.view(1, 1, vocab_size).expand(num_trials, K, -1).contiguous()
    )

    scaled_draft_logits_1d = draft_logits_1d.float()
    if temperature > 0:
        scaled_draft_logits_1d = scaled_draft_logits_1d / temperature
    draft_probs = torch.softmax(scaled_draft_logits_1d, dim=0)
    draft_tokens = torch.multinomial(
        draft_probs.expand(num_trials, -1), K, replacement=True
    )
    draft_sampled_2d = torch.zeros(num_trials, K + 1, dtype=torch.int64, device=device)
    draft_sampled_2d[:, 1:] = draft_tokens
    draft_sampled = draft_sampled_2d.reshape(-1)

    cu_num_logits = torch.arange(num_trials + 1, dtype=torch.int32, device=device) * (
        K + 1
    )
    pos = torch.arange(num_logits, dtype=torch.int32, device=device)
    idx_mapping = torch.arange(num_trials, dtype=torch.int32, device=device)
    expanded_idx_mapping = torch.arange(
        num_trials, dtype=torch.int32, device=device
    ).repeat_interleave(K + 1)
    expanded_local_pos = torch.arange(K + 1, dtype=torch.int32, device=device).repeat(
        num_trials
    )
    temp_tensor = torch.full(
        (num_trials,), temperature, dtype=torch.float32, device=device
    )
    seed = torch.arange(num_trials, dtype=torch.int64, device=device)

    return dict(
        target_logits=target_logits,
        draft_logits=draft_logits,
        draft_sampled=draft_sampled,
        cu_num_logits=cu_num_logits,
        pos=pos,
        idx_mapping=idx_mapping,
        expanded_idx_mapping=expanded_idx_mapping,
        expanded_local_pos=expanded_local_pos,
        temperature=temp_tensor,
        seed=seed,
    )

def _assert_distribution_match(
    sampled_tokens: torch.Tensor,
    target_probs: torch.Tensor,
    device: str,
    label: str = "",
    min_expected: float = 5.0,
):
    """
    Assert sampled tokens match the target distribution via a
    chi-squared goodness-of-fit test. This is done by computing
    observed vs expected token counts (target_probs * num_samples),
    then checking that the chi-squared statistic is below a conservative
    threshold. The threshold is set at df + 10*sqrt(2*df), which
    corresponds to ~10 sigma under the chi-squared distribution's
    normal approximation, effectively disallowing false positives.

    NOTE: Tokens with expected count < min_expected are merged into
    a single "other" bin to minimize chi-squared noise.
    """
    num_samples = sampled_tokens.shape[0]
    vocab_size = target_probs.shape[0]

    observed = torch.zeros(vocab_size, device=device, dtype=torch.float32)
    observed.scatter_add_(0, sampled_tokens, torch.ones(num_samples, device=device))
    expected = target_probs * num_samples

    sufficient = expected >= min_expected
    obs_main = observed[sufficient]
    exp_main = expected[sufficient]

    obs_other = observed[~sufficient].sum().unsqueeze(0)
    exp_other = expected[~sufficient].sum().unsqueeze(0)

    if exp_other.item() >= min_expected:
        obs_all = torch.cat([obs_main, obs_other])
        exp_all = torch.cat([exp_main, exp_other])
    else:
        obs_all = obs_main
        exp_all = exp_main

    chi2 = ((obs_all - exp_all) ** 2 / exp_all).sum().item()
    df = obs_all.shape[0] - 1
    if df < 1:
        # All samples were merged into < 2 bins, which is too
        # few to evaluate.
        return

    threshold = df + 10 * math.sqrt(2 * df)
    prefix = f"[{label}] " if label else ""
    assert chi2 < threshold, (
        f"{prefix}Chi-squared test failed: chi2={chi2:.1f}, "
        f"df={df}, threshold={threshold:.1f}. "
        f"Output distribution does not match target distribution."
    )

def _gumbel_drafted_tokens(
    inputs: dict,
    draft_logits_1d: torch.Tensor,
    num_trials: int,
    num_speculative_steps: int,
) -> torch.Tensor:
    """Proposals drawn with gumbel_sample, shaped like inputs["draft_sampled"].

    _build_rejection_sample_inputs draws them with torch.multinomial, which is
    independent of the resample noise by construction. Production drafts come
    from gumbel_sample keyed by pos[t * (K + 1) + i] for step i of trial t --
    the same entry _rejection_kernel and _resample_kernel read for that token --
    so the draft and the residual compete for one noise stream.
    """
    k = num_speculative_steps
    vocab_size = draft_logits_1d.shape[0]
    device = draft_logits_1d.device
    draft_tokens = gumbel_sample(
        draft_logits_1d.unsqueeze(0).expand(num_trials * k, vocab_size).float(),
        inputs["expanded_idx_mapping"]
        .view(num_trials, k + 1)[:, :k]
        .reshape(-1)
        .contiguous(),
        inputs["temperature"],
        inputs["seed"],
        inputs["pos"].view(num_trials, k + 1)[:, :k].reshape(-1).contiguous(),
        apply_temperature=True,
        is_drafting=True,
    )
    draft_sampled = torch.zeros(num_trials * (k + 1), dtype=torch.int64, device=device)
    draft_sampled.view(num_trials, k + 1)[:, 1:] = draft_tokens.view(num_trials, k)
    return draft_sampled
