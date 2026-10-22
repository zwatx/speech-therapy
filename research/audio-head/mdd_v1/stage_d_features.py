"""Frozen-C canonical phone features; no scores or reference timings enter x."""
import numpy as np
import torch

from .evaluate import anchored
from .gop import ctc_log_likelihoods, labels
from .inventory import PHONES, PHONE_TO_ID, ID_TO_PHONE
from .runtime import collapse

SCHEMA = 'full-ctc-vector-v1'
NUMERIC_NAMES = ([f'log_ratio_{phone}' for phone in PHONES] +
                 ['log_ratio_deletion', 'span_mean_posterior', 'span_max_posterior',
                  'span_seconds', 'utterance_position', 'word_phone_position',
                  'word_position', 'word_metadata_present', 'blind_disagreement'])
FEATURE_NAMES = NUMERIC_NAMES + [f'{context}_{phone}' for context in ('phone', 'previous', 'next')
                                for phone in ['<boundary>'] + PHONES]


def gop_vector(log_probs, canonical):
    """Fixed global replacement columns; canonical column=0, deletion last."""
    if not canonical:
        raise ValueError('Empty canonical prompt')
    alternatives = [list(canonical)]
    columns = []
    for i, phone in enumerate(canonical):
        for replacement in range(1, len(PHONES) + 1):
            if replacement != phone:
                alternatives.append(canonical[:i] + [replacement] + canonical[i+1:])
                columns.append((i, replacement-1))
        alternatives.append(canonical[:i] + canonical[i+1:])
        columns.append((i, len(PHONES)))
    values = ctc_log_likelihoods(log_probs, alternatives)
    if not np.isfinite(values[0]):
        raise ValueError('Canonical sequence has no finite CTC alignment')
    if np.isnan(values).any() or np.isposinf(values).any():
        raise ValueError('Invalid competitor CTC likelihood')
    ratios = np.zeros((len(canonical), len(PHONES)+1))
    raw = values[1:] - values[0]
    for (i, column), value in zip(columns, np.clip(raw, -100., 100.)):
        ratios[i, column] = value
    return ratios, int(((raw < -100) | (raw > 100)).sum())


def forced_spans(log_probs, canonical):
    """Viterbi CTC canonical-state occupancy; ties prefer stay, step, skip."""
    values = np.asarray(log_probs, dtype=np.float64)
    if (values.ndim != 2 or not len(values) or not np.isfinite(values).all()
            or not canonical or any(p <= 0 or p >= values.shape[1] for p in canonical)):
        raise ValueError('Invalid forced alignment inputs')
    minimum = len(canonical) + sum(a == b for a, b in zip(canonical, canonical[1:]))
    if len(values) < minimum:
        raise ValueError('Insufficient CTC frames')
    states = np.zeros(2*len(canonical)+1, dtype=int)
    states[1::2] = canonical
    skip = np.zeros(len(states), dtype=bool)
    skip[2:] = (states[2:] != 0) & (states[2:] != states[:-2])
    previous = np.full(len(states), -np.inf)
    previous[:2] = values[0, states[:2]]
    back = np.zeros((len(values), len(states)), dtype=np.int8)
    for frame in range(1, len(values)):
        step = np.r_[-np.inf, previous[:-1]]
        jump = np.r_[-np.inf, -np.inf, previous[:-2]]
        jump[~skip] = -np.inf
        choices = np.stack([previous, step, jump])
        winner = choices.argmax(0)
        previous = choices[winner, np.arange(len(states))] + values[frame, states]
        back[frame] = winner
    end = len(states)-2 if previous[-2] >= previous[-1] else len(states)-1
    if not np.isfinite(previous[end]):
        raise ValueError('No finite forced alignment')
    path = np.empty(len(values), dtype=int)
    path[-1] = end
    for frame in range(len(values)-1, 0, -1):
        path[frame-1] = path[frame] - back[frame, path[frame]]
    spans = []
    for i in range(len(canonical)):
        occupied = np.flatnonzero(path == 2*i+1)
        if not len(occupied):
            raise ValueError('Missing canonical CTC state')
        spans.append((int(occupied[0]), int(occupied[-1])+1))
    return spans


def word_positions(canonical, words):
    """Independent prompt grouping only. Missing word metadata is explicit."""
    if words is None:
        return [(-1., -1., 0.)] * len(canonical)
    flattened = [phone for word in words for phone in word]
    if flattened != canonical or any(not word for word in words):
        raise ValueError('Canonical word grouping mismatch')
    return [(i/max(1, len(word)-1), wi/max(1, len(words)-1), 1.)
            for wi, word in enumerate(words) for i in range(len(word))]


def extract(row, log_probs, words=None):
    """Return all canonical slots; label masking happens after feature creation."""
    canonical = row['canonical']
    target = [PHONE_TO_ID[p] for p in canonical]
    log_probs = log_probs.detach().float().cpu()
    ratios, clipped = gop_vector(log_probs, target)
    spans = forced_spans(log_probs.numpy(), target)
    words_at = word_positions(canonical, words)
    hypothesis = collapse(log_probs.argmax(-1).tolist(), ID_TO_PHONE)
    slots, _ = anchored(canonical, hypothesis)
    probabilities = log_probs.exp().numpy()
    x = []
    for i, (phone, (left, right), position) in enumerate(zip(target, spans, words_at)):
        posterior = probabilities[left:right, phone]
        numeric = list(ratios[i]) + [float(posterior.mean()), float(posterior.max()),
                   (right-left)*.02, i/max(1, len(target)-1), *position,
                   float(slots[i] != canonical[i])]
        identities = [phone, target[i-1] if i else 0, target[i+1] if i+1 < len(target) else 0]
        one_hot = np.zeros((3, len(PHONES)+1))
        one_hot[np.arange(3), identities] = 1.
        x.append(numeric + one_hot.ravel().tolist())
    x = np.asarray(x, dtype=np.float32)
    if x.shape != (len(target), len(FEATURE_NAMES)) or not np.isfinite(x).all():
        raise ValueError('Nonfinite or incorrect feature matrix')
    truth = labels(row)
    records = [dict(id=row['id'], speaker=row['speaker'], index=i, phone=p,
                    error=truth.get(i), span=list(spans[i])) for i, p in enumerate(canonical)]
    return x, records, clipped
