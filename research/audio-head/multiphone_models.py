"""Acoustic heads for three-class expert-rating distributions, not phone decoding.

Each active phone ID represents one canonical occurrence in its clip. Attention
weights pool contextual encoder states; they are not observed phone boundaries.
The caller supplies the target inventory and masks any ineligible target types.
"""
from __future__ import annotations

import math

import torch
from torch import nn


class _PhoneRatingHead(nn.Module):
    def __init__(self, feature_dim: int = 768, num_phones: int = 24,
                 hidden_dim: int = 128, dropout: float = 0.1):
        super().__init__()
        if any(type(value) is not int or value < 1
               for value in (feature_dim, num_phones, hidden_dim)):
            raise ValueError("Model dimensions must be positive integers")
        if type(dropout) not in (int, float) or not 0 <= dropout < 1:
            raise ValueError("Dropout must be finite and in [0, 1)")
        self.feature_dim = feature_dim
        self.num_phones = num_phones
        self.hidden_dim = hidden_dim
        self.phone_embedding = nn.Embedding(num_phones, hidden_dim)
        self.acoustic_projection = nn.Sequential(nn.Linear(feature_dim, hidden_dim), nn.GELU())
        self.classifier = nn.Sequential(
            nn.Linear(2 * hidden_dim, hidden_dim), nn.GELU(),
            nn.Dropout(float(dropout)), nn.Linear(hidden_dim, 3),
        )

    def _inputs(self, features: torch.Tensor, frame_mask: torch.Tensor,
                phone_ids: torch.Tensor, target_mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if not all(isinstance(value, torch.Tensor)
                   for value in (features, frame_mask, phone_ids, target_mask)):
            raise ValueError("Model inputs must be tensors")
        if (features.ndim != 3 or features.shape[2] != self.feature_dim
                or features.shape[0] < 1 or features.shape[1] < 1
                or not features.is_floating_point()):
            raise ValueError("Expected floating features with shape [batch, frames, feature_dim]")
        if (frame_mask.dtype != torch.bool or frame_mask.shape != features.shape[:2]
                or phone_ids.ndim != 2 or phone_ids.shape[0] != features.shape[0]
                or phone_ids.shape[1] < 1 or phone_ids.dtype != torch.long
                or target_mask.dtype != torch.bool or target_mask.shape != phone_ids.shape):
            raise ValueError("Invalid frame mask, phone IDs, or target mask shape/dtype")
        if any(value.device != features.device for value in (frame_mask, phone_ids, target_mask)):
            raise ValueError("All model inputs must use the same device")
        if not frame_mask.any(dim=1).all() or not target_mask.any(dim=1).all():
            raise ValueError("Every clip requires a valid frame and target")
        active_ids = phone_ids[target_mask]
        if ((active_ids < 0) | (active_ids >= self.num_phones)).any():
            raise ValueError("Active phone ID is outside the target inventory")
        duplicate = ((phone_ids.unsqueeze(2) == phone_ids.unsqueeze(1))
                     & target_mask.unsqueeze(2) & target_mask.unsqueeze(1))
        if duplicate.triu(diagonal=1).any():
            raise ValueError("Active phone IDs must be unique within each clip")
        if not torch.isfinite(features[frame_mask]).all():
            raise ValueError("Nonfinite valid acoustic features")
        # Replace padding before arithmetic: multiplying NaN padding by zero
        # would still poison pooled vectors and encoder gradients.
        clean_features = features.masked_fill(~frame_mask.unsqueeze(-1), 0)
        safe_ids = phone_ids.masked_fill(~target_mask, 0)
        return clean_features, self.phone_embedding(safe_ids)

    def _pool(self, features: torch.Tensor, frame_mask: torch.Tensor,
              queries: torch.Tensor) -> torch.Tensor:
        raise NotImplementedError

    def forward(self, features: torch.Tensor, frame_mask: torch.Tensor,
                phone_ids: torch.Tensor, target_mask: torch.Tensor, *,
                return_attention: bool = False) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        """Return [B,K,3] logits, optionally with [B,K,T] pooling weights.

        True mask entries are valid. Padding phone IDs may be arbitrary integers,
        including -1. Masked targets return exact-zero logits and weights; the
        training loss must also exclude them. No softmax is applied to logits.
        """
        clean_features, queries = self._inputs(features, frame_mask, phone_ids, target_mask)
        attention = self._pool(clean_features, frame_mask, queries)
        pooled = torch.einsum("bkt,btf->bkf", attention, clean_features)
        acoustic = self.acoustic_projection(pooled)
        logits = self.classifier(torch.cat((acoustic, queries), dim=-1))
        logits = logits.masked_fill(~target_mask.unsqueeze(-1), 0)
        attention = attention.masked_fill(~target_mask.unsqueeze(-1), 0)
        if not torch.isfinite(logits).all() or not torch.isfinite(attention).all():
            raise ValueError("Nonfinite model output")
        return (logits, attention) if return_attention else logits


class MeanPoolPhoneRatingHead(_PhoneRatingHead):
    """Masked whole-clip mean followed by a phone-conditioned shared MLP."""

    def _pool(self, features: torch.Tensor, frame_mask: torch.Tensor,
              queries: torch.Tensor) -> torch.Tensor:
        weights = frame_mask.to(features.dtype) / frame_mask.sum(dim=1, keepdim=True)
        return weights.unsqueeze(1).expand(-1, queries.shape[1], -1)


class AttentionPhoneRatingHead(_PhoneRatingHead):
    """A phone-type query pools full-clip contextual frames for a shared MLP.

    The query cannot identify distinct occurrences of one phone in a clip, hence
    the enforced unique-target contract. It has no word, age, or timing inputs.
    """

    def __init__(self, feature_dim: int = 768, num_phones: int = 24,
                 hidden_dim: int = 128, dropout: float = 0.1):
        super().__init__(feature_dim, num_phones, hidden_dim, dropout)
        self.key_projection = nn.Linear(feature_dim, hidden_dim, bias=False)

    def _pool(self, features: torch.Tensor, frame_mask: torch.Tensor,
              queries: torch.Tensor) -> torch.Tensor:
        keys = self.key_projection(features)
        scores = torch.einsum("bkh,bth->bkt", queries, keys) / math.sqrt(self.hidden_dim)
        scores = scores.masked_fill(~frame_mask.unsqueeze(1), -torch.inf)
        return scores.softmax(dim=-1)
