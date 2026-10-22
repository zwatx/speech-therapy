"""Warm-preserving sequence evidence branch for fixed one-frame target features."""
from __future__ import annotations

import torch
from torch import nn
from multiphone_models import MeanPoolPhoneRatingHead


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fitting_moments(values, fit_positions):
    """Population moments of only the explicitly supplied fitting positions."""
    require(isinstance(values, torch.Tensor) and values.dtype == torch.float32
            and values.ndim == 2 and values.shape[1] == 4 and torch.isfinite(values).all(),
            'Finite float32 four-column sequence matrix required')
    positions = list(fit_positions)
    require(positions and len(positions) == len(set(positions))
            and all(type(i) is int and 0 <= i < len(values) for i in positions),
            'Distinct valid fitting positions required')
    selected = values[positions]
    mean, std = selected.mean(0), selected.std(0, unbiased=False).clamp_min(1e-6)
    require(torch.isfinite(mean).all() and torch.isfinite(std).all(), 'Nonfinite fitting moments')
    return mean, std


class SequenceEvidenceHead(MeanPoolPhoneRatingHead):
    """Append four normalized columns; preserve the original acoustic operation.

    The study uses one frame and one target per row. The disabled branch exists
    only for control equivalence verification; no fitted candidate disables it.
    """

    def __init__(self, feature_dim=1037, num_phones=24, hidden_dim=128,
                 dropout=.1, *, enabled=True):
        super().__init__(feature_dim, num_phones, hidden_dim, dropout)
        require(type(enabled) is bool, 'Branch enabled flag must be boolean')
        self.enabled = enabled
        self.sequence_projection = nn.Linear(4, hidden_dim, bias=False)
        nn.init.zeros_(self.sequence_projection.weight)
        self.sequence_projection.requires_grad_(enabled)

    def load_warm(self, state):
        expected = set(self.state_dict()) - {'sequence_projection.weight'}
        require(set(state) == expected, 'Warm state must contain exactly original head parameters')
        result = self.load_state_dict(state, strict=False)
        require(result.missing_keys == ['sequence_projection.weight'] and not result.unexpected_keys,
                'Warm state mismatch')
        nn.init.zeros_(self.sequence_projection.weight)

    def forward(self, features, frame_mask, phone_ids, target_mask, *, return_attention=False):
        require(isinstance(features, torch.Tensor) and features.ndim == 3
                and features.shape[1:] == (1, self.feature_dim + 4)
                and isinstance(phone_ids, torch.Tensor) and phone_ids.ndim == 2
                and phone_ids.shape[1] == 1,
                'Sequence head requires one frame, one target and four appended columns')
        # Contiguous original-width matrix preserves the retained head GEMM.
        original, sequence = features[..., :self.feature_dim].contiguous(), features[..., self.feature_dim:]
        clean, queries = self._inputs(original, frame_mask, phone_ids, target_mask)
        require(torch.isfinite(sequence[frame_mask]).all(), 'Nonfinite sequence evidence')
        if not self.enabled:
            return super().forward(original, frame_mask, phone_ids, target_mask,
                                   return_attention=return_attention)
        attention = self._pool(clean, frame_mask, queries)
        pooled = torch.einsum('bkt,btf->bkf', attention, clean)
        auxiliary = torch.einsum('bkt,btf->bkf', attention, sequence)
        preactivation = self.acoustic_projection[0](pooled) + self.sequence_projection(auxiliary)
        acoustic = self.acoustic_projection[1](preactivation)
        logits = self.classifier(torch.cat((acoustic, queries), dim=-1))
        logits = logits.masked_fill(~target_mask.unsqueeze(-1), 0)
        attention = attention.masked_fill(~target_mask.unsqueeze(-1), 0)
        require(torch.isfinite(logits).all() and torch.isfinite(attention).all(), 'Nonfinite sequence head output')
        return (logits, attention) if return_attention else logits
