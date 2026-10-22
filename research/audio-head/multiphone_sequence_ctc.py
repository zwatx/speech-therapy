"""Exact single-slot CTC substitution/deletion likelihoods, without segmentation.

The candidate labels are decoder tokens, not diagnosed produced phones. Shared
canonical prefix/suffix sums avoid recomputing a complete CTC graph per token.
No external implementation is imported or copied.
"""
from __future__ import annotations

import numpy as np


def require(condition, message):
    if not condition:
        raise ValueError(message)


class SequenceCTC:
    def __init__(self, log_probabilities, target, blank=0):
        logp = np.array(log_probabilities, dtype=np.float64, copy=True)
        require(logp.ndim == 2 and logp.shape[0] > 0 and logp.shape[1] > 1,
                'Nonempty [frame, vocabulary] probabilities required')
        require(type(blank) is int and 0 <= blank < logp.shape[1], 'Invalid blank token')
        require(not np.isnan(logp).any() and not np.isposinf(logp).any() and (logp <= 1e-6).all()
                and np.allclose(np.exp(logp).sum(1), 1., rtol=0, atol=3e-5),
                'Invalid full-vocabulary log probabilities; do not renormalize a token subset')
        target = tuple(target)
        require(all(type(token) is int and 0 <= token < logp.shape[1] and token != blank for token in target),
                'Invalid canonical token sequence')
        self.logp, self.target, self.blank = logp, target, blank
        self.states = np.full(2*len(target)+1, blank, dtype=np.int64)
        self.states[1::2] = target
        self._forward, self._backward = self._tables()
        self.log_probability = float(np.logaddexp(self._forward[-1, -1], self._forward[-1, -2])
                                     if target else self._forward[-1, 0])
        require(np.isclose(self.log_probability, self._backward[0, 0], rtol=0, atol=1e-8),
                'Forward and backward likelihoods differ')
        for value in (self.logp, self.states, self._forward, self._backward):
            value.flags.writeable = False

    def _tables(self):
        frames, state_count = len(self.logp), len(self.states)
        # a[t,s] has consumed t frames. The initial blank is a virtual state.
        a = np.full((frames+1, state_count), -np.inf)
        a[0, 0] = 0.
        skip = np.zeros(state_count, dtype=bool)
        skip[2:] = (self.states[2:] != self.blank) & (self.states[2:] != self.states[:-2])
        for t in range(frames):
            incoming = a[t].copy()
            incoming[1:] = np.logaddexp(incoming[1:], a[t, :-1])
            incoming[2:] = np.logaddexp(incoming[2:], np.where(skip[2:], a[t, :-2], -np.inf))
            a[t+1] = incoming + self.logp[t, self.states]
        # b[t,s] includes only frames t onward, given state s after t frames.
        b = np.full_like(a, -np.inf)
        b[-1, -1] = 0.
        if self.target:
            b[-1, -2] = 0.
        for t in range(frames-1, -1, -1):
            outgoing = self.logp[t, self.states] + b[t+1]
            b[t] = outgoing
            b[t, :-1] = np.logaddexp(b[t, :-1], outgoing[1:])
            b[t, :-2] = np.logaddexp(b[t, :-2], np.where(skip[2:], outgoing[2:], -np.inf))
        return a, b

    def slot_likelihoods(self, position, candidates):
        require(type(position) is int and 0 <= position < len(self.target), 'Invalid target slot')
        candidates = tuple(candidates)
        require(candidates and len(candidates) == len(set(candidates))
                and all(type(q) is int and 0 <= q < self.logp.shape[1] and q != self.blank for q in candidates)
                and self.target[position] in candidates, 'Distinct nonblank candidates must include the canonical token')
        q = np.array(candidates, dtype=np.int64)
        s, frames = 2*position+1, len(self.logp)
        last_slot = position == len(self.target)-1
        running = np.full(len(q), -np.inf)
        total = np.full(len(q), -np.inf)
        for t in range(frames):
            incoming = np.logaddexp(running, self._forward[t, s-1])
            if position:
                incoming = np.logaddexp(incoming, np.where(q != self.target[position-1], self._forward[t, s-2], -np.inf))
            running = self.logp[t, q] + incoming
            # Partition paths by their unique LAST frame occupying the new token.
            if t+1 < frames:
                exit_mass = np.full(len(q), self.logp[t+1, self.blank] + self._backward[t+2, s+1])
                if not last_slot:
                    next_token = self.target[position+1]
                    skip_mass = self.logp[t+1, next_token] + self._backward[t+2, s+2]
                    exit_mass = np.logaddexp(exit_mass, np.where(q != next_token, skip_mass, -np.inf))
                total = np.logaddexp(total, running + exit_mass)
            elif last_slot:
                total = np.logaddexp(total, running)
        if last_slot:
            deletion = self._forward[frames, s-1]
            if position:
                deletion = np.logaddexp(deletion, self._forward[frames, s-2])
        else:
            # Partition deleted-target paths by their FIRST next-token frame.
            incoming = self._forward[:-1, s-1].copy()
            if position and self.target[position-1] != self.target[position+1]:
                incoming = np.logaddexp(incoming, self._forward[:-1, s-2])
            deletion = np.logaddexp.reduce(incoming + self.logp[:, self.target[position+1]] + self._backward[1:, s+2])
        canonical = total[candidates.index(self.target[position])]
        require(np.isclose(canonical, self.log_probability, rtol=0, atol=1e-8),
                'Canonical slot splice does not recover original likelihood')
        return {'position': position, 'canonicalToken': self.target[position], 'candidateTokenIds': list(candidates),
                'replacementLogLikelihoods': total.tolist(), 'canonicalLogLikelihood': self.log_probability,
                'deletionLogLikelihood': float(deletion)}


def summarize_slot(result):
    """Restricted-hypothesis log shares; these are not correctness probabilities."""
    candidates = result['candidateTokenIds']
    values = np.asarray(result['replacementLogLikelihoods'], dtype=np.float64)
    deletion, canonical = result['deletionLogLikelihood'], result['canonicalLogLikelihood']
    require(values.shape == (len(candidates),) and len(set(candidates)) == len(candidates)
            and result['canonicalToken'] in candidates and np.isfinite(canonical)
            and not np.isnan(values).any() and not np.isposinf(values).any()
            and (np.isfinite(deletion) or deletion == -np.inf), 'Undefined slot likelihoods')
    index = candidates.index(result['canonicalToken'])
    require(np.isclose(values[index], canonical, rtol=0, atol=1e-8), 'Canonical likelihood differs')
    denominator = float(np.logaddexp(np.logaddexp.reduce(values), deletion))
    require(np.isfinite(denominator) and canonical <= denominator+1e-8, 'Undefined alternative denominator')
    others = values.copy()
    others[index] = -np.inf
    best = float(others.max())
    return {'denominatorLogLikelihood': denominator, 'canonicalVsAlternativesLogRatio': canonical-denominator,
            'canonicalVsDeletionLogRatio': canonical-deletion if np.isfinite(deletion) else None,
            'canonicalVsBestOtherTokenLogRatio': canonical-best if np.isfinite(best) else None,
            'bestOtherToken': candidates[int(others.argmax())] if np.isfinite(best) else None,
            'deletionLogShare': deletion-denominator if np.isfinite(deletion) else None}
