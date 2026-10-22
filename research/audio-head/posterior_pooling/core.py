"""Pure canonical-conditioned CTC state occupancy and acoustic pooling.

canonical_index indexes the complete mapped prompt sequence, including vowels.
Equal tokens are distinct occurrences. Occupancy is conditioned on that complete
sequence; it is not produced-phone, insertion/deletion, boundary or quality truth.
No input is renormalized over a token subset, and no failed row is replaced.
"""
from __future__ import annotations

import numpy as np

POLICY = {
    'version': 'canonical-posterior-expectation-pooling-v1',
    'input': 'finite full-vocabulary float32 log-softmax, unchanged quantized CTC source',
    'fullVocabularyLogNormalizationAtol': 3e-5,
    'canonicalIndex': 'zero-based occurrence in full mapped prompt tokens including vowels',
    'state': '2*canonicalIndex+1; original CTC repeat/skip restrictions',
    'tables': 'float64 log domain; A[t+1,s]+B[t+1,s]-logZ',
    'emptyCanonicalSequence': 'all-blank graph; no token occurrence to pool',
    'invariantTolerance': 'max(1e-10,64*float64eps*max(T,abs(logZ))), capped at 1e-6',
    'tokenOccupancyLowerBound': 1.,
    'q': 'log-sum-exp normalization of token-state occupancy over frames',
    'contextFrames': 2,
    'kernel': 'per-source-normalized box over valid neighbors; no global renormalization',
    'meaning': 'posterior expectation of historical one-frame padded-window mean',
    'accumulation': 'float64', 'persisted': 'float32',
    'historicalControl': 'unchanged original pooled_vectors mean path; new weighted sums do not certify bit parity',
    'targetsAccessed': False, 'producedPhoneTruth': False, 'deletionTruth': False,
    'replacement': False, 'clinicalUseEligible': False,
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def box_weights(q):
    """u[t]=sum_k q[k]*1(abs(t-k)<=2)/validNeighborCount(k)."""
    _require(isinstance(q, np.ndarray) and q.dtype == np.dtype('<f8') and q.ndim == 1 and q.size > 0
             and np.isfinite(q).all() and (q >= 0).all()
             and np.isclose(q.sum(dtype=np.float64), 1., rtol=0, atol=1e-10),
             'Finite normalized float64 frame weights required')
    frames = q.size
    indices = np.arange(frames)
    counts = np.minimum(frames, indices+3) - np.maximum(0, indices-2)
    scaled = q / counts
    u = np.zeros(frames, dtype=np.float64)
    for offset in range(-2, 3):
        start, end = max(0, -offset), min(frames, frames-offset)
        if start < end:
            u[start+offset:end+offset] += scaled[start:end]
    _require(np.isfinite(u).all() and (u >= 0).all() and u.sum() > 0
             and np.isclose(u.sum(dtype=np.float64), 1., rtol=0, atol=1e-10),
             'Invalid posterior-expectation kernel mass')
    return u


def pool_hidden(hidden, u):
    """Weighted float64 accumulation, then float32; no historical bit-parity claim."""
    _require(isinstance(hidden, np.ndarray) and hidden.dtype == np.dtype('<f4') and hidden.ndim == 2
             and hidden.shape[0] > 0 and hidden.shape[1] > 0 and np.isfinite(hidden).all(),
             'Finite float32 [frame, feature] hidden grid required')
    _require(isinstance(u, np.ndarray) and u.dtype == np.dtype('<f8') and u.shape == (len(hidden),)
             and np.isfinite(u).all() and (u >= 0).all()
             and np.isclose(u.sum(dtype=np.float64), 1., rtol=0, atol=1e-10),
             'Finite normalized weights matching hidden frames required')
    vector64 = (hidden.astype(np.float64) * u[:, None]).sum(axis=0, dtype=np.float64)
    vector = vector64.astype(np.float32)
    _require(np.isfinite(vector64).all() and np.isfinite(vector).all(), 'Nonfinite pooled vector')
    return vector


def vector_distance(candidate, control):
    """Rating-free L2 and cosine distance; zero-norm cosine remains undefined."""
    _require(isinstance(candidate, np.ndarray) and isinstance(control, np.ndarray)
             and candidate.dtype == control.dtype == np.dtype('<f4')
             and candidate.ndim == 1 and candidate.size > 0 and candidate.shape == control.shape
             and np.isfinite(candidate).all() and np.isfinite(control).all(), 'Invalid vectors for descriptive distance')
    a, b = candidate.astype(np.float64), control.astype(np.float64)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    cosine = None if na == 0 or nb == 0 else float(1. - np.clip(np.dot(a/na, b/nb), -1., 1.))
    return dict(l2=float(np.linalg.norm(a-b)), cosineDistance=cosine, targetsAccessed=False)


class CTCPosterior:
    """Same A/B table convention as frozen SequenceCTC, with explicit guards.

    Finite emissions make every topologically reachable prefix/suffix cell finite.
    Structural negative infinity in unreachable cells is necessary and permitted.
    Empty target is valid (all blank), but has no token state for token_weights.
    """
    def __init__(self, log_probabilities, target, blank=0):
        _require(isinstance(log_probabilities, np.ndarray) and log_probabilities.dtype == np.dtype('<f4')
                 and log_probabilities.ndim == 2 and log_probabilities.shape[0] > 0
                 and log_probabilities.shape[1] > 1 and np.isfinite(log_probabilities).all(),
                 'Finite nonempty full-vocabulary float32 log probabilities required')
        logp = np.array(log_probabilities, dtype=np.float64, copy=True)
        _require((logp <= 1e-6).all(), 'Positive log probability')
        normalizers = np.logaddexp.reduce(logp, axis=1)
        _require(np.allclose(normalizers, 0., rtol=0, atol=POLICY['fullVocabularyLogNormalizationAtol']),
                 'Invalid full-vocabulary normalization; do not normalize a token subset')
        _require(type(blank) is int and 0 <= blank < logp.shape[1], 'Invalid blank token')
        _require(isinstance(target, (list, tuple)) and all(type(token) is int and 0 <= token < logp.shape[1]
                 and token != blank for token in target), 'Invalid full canonical token sequence')
        self.logp, self.target, self.blank = logp, tuple(target), blank
        self.states = np.full(2*len(target)+1, blank, dtype=np.int64)
        self.states[1::2] = target
        self.forward, self.backward, forward_reachable, backward_reachable = self._tables()
        self.log_probability = float(np.logaddexp(self.forward[-1, -1], self.forward[-1, -2])
                                     if target else self.forward[-1, 0])
        _require(np.isfinite(self.log_probability), 'Impossible or nonfinite canonical CTC path')
        self.tolerance = float(min(1e-6, max(1e-10, 64*np.finfo(np.float64).eps*max(len(logp), abs(self.log_probability)))))
        _require(np.isfinite(self.forward[forward_reachable]).all() and np.isfinite(self.backward[backward_reachable]).all(),
                 'Nonfinite reachable CTC table cell')
        _require(np.isneginf(self.forward[~forward_reachable]).all() and np.isneginf(self.backward[~backward_reachable]).all(),
                 'Invalid unreachable CTC table cell')
        agreement = float(abs(self.log_probability - self.backward[0, 0]))
        _require(np.isfinite(agreement) and agreement <= self.tolerance, 'Forward/backward CTC likelihoods differ')
        self.log_gamma = self.forward[1:] + self.backward[1:] - self.log_probability
        used = forward_reachable[1:] & backward_reachable[1:]
        _require(np.isfinite(self.log_gamma[used]).all() and np.isneginf(self.log_gamma[~used]).all(),
                 'Invalid used CTC posterior cell')
        self.gamma = np.exp(self.log_gamma)
        frame_mass = self.gamma.sum(axis=1, dtype=np.float64)
        token_mass = self.gamma[:, 1::2].sum(axis=0, dtype=np.float64)
        _require(np.isfinite(self.gamma).all() and np.allclose(frame_mass, 1., rtol=0, atol=self.tolerance),
                 'Per-frame CTC state occupancy mass differs from one')
        _require(np.isfinite(token_mass).all() and (token_mass >= 1.-self.tolerance).all(),
                 'Canonical token occupancy below one')
        self.audit = dict(frames=len(logp), vocabulary=logp.shape[1], tokens=len(target), states=len(self.states),
            logProbability=self.log_probability, forwardBackwardAbs=agreement,
            frameMassMaxAbs=float(np.max(np.abs(frame_mass-1))), tokenOccupancies=token_mass.tolist(),
            logNormalizationMaxAbs=float(np.max(np.abs(normalizers))), invariantAtol=self.tolerance,
            conditioning='complete canonical transcript, not produced-phone or deletion truth', targetsAccessed=False)
        for array in (self.logp, self.states, self.forward, self.backward, self.log_gamma, self.gamma):
            array.flags.writeable = False

    def _tables(self):
        frames, states = len(self.logp), len(self.states)
        skip = np.zeros(states, dtype=bool)
        skip[2:] = (self.states[2:] != self.blank) & (self.states[2:] != self.states[:-2])
        a = np.full((frames+1, states), -np.inf, dtype=np.float64)
        ar = np.zeros(a.shape, dtype=bool)
        a[0, 0], ar[0, 0] = 0., True
        for t in range(frames):
            incoming, reachable = a[t].copy(), ar[t].copy()
            incoming[1:] = np.logaddexp(incoming[1:], a[t, :-1])
            reachable[1:] |= ar[t, :-1]
            incoming[2:] = np.logaddexp(incoming[2:], np.where(skip[2:], a[t, :-2], -np.inf))
            reachable[2:] |= skip[2:] & ar[t, :-2]
            a[t+1], ar[t+1] = incoming + self.logp[t, self.states], reachable
        b = np.full_like(a, -np.inf)
        br = np.zeros(a.shape, dtype=bool)
        b[-1, -1], br[-1, -1] = 0., True
        if self.target:
            b[-1, -2], br[-1, -2] = 0., True
        for t in range(frames-1, -1, -1):
            outgoing = self.logp[t, self.states] + b[t+1]
            b[t], br[t] = outgoing, br[t+1]
            b[t, :-1] = np.logaddexp(b[t, :-1], outgoing[1:])
            br[t, :-1] |= br[t+1, 1:]
            b[t, :-2] = np.logaddexp(b[t, :-2], np.where(skip[2:], outgoing[2:], -np.inf))
            br[t, :-2] |= skip[2:] & br[t+1, 2:]
        return a, b, ar, br

    def token_weights(self, canonical_index):
        _require(type(canonical_index) is int and 0 <= canonical_index < len(self.target),
                 'canonical_index must index full mapped prompt tokens including vowels')
        state = 2*canonical_index+1
        log_gamma = self.log_gamma[:, state]
        log_duration = float(np.logaddexp.reduce(log_gamma))
        _require(np.isfinite(log_duration), 'Zero or nonfinite token occupancy mass')
        q = np.exp(log_gamma-log_duration)
        _require(np.isfinite(q).all() and q.sum() > 0 and np.isclose(q.sum(), 1., rtol=0, atol=1e-10),
                 'Invalid log-normalized token frame mass')
        u = box_weights(q)
        frames = np.arange(len(q), dtype=np.float64)
        metadata = dict(canonicalIndex=canonical_index, tokenId=self.target[canonical_index], state=state,
            expectedOccupancy=float(np.exp(log_duration)), qMass=float(q.sum()), uMass=float(u.sum()),
            qEffectiveFrames=float(1./np.dot(q, q)), uEffectiveFrames=float(1./np.dot(u, u)),
            qCentroidFrame=float(np.dot(q, frames)), uCentroidFrame=float(np.dot(u, frames)),
            conditioning='complete canonical transcript, not produced-phone or deletion truth', targetsAccessed=False)
        return dict(gamma=self.gamma[:, state].copy(), q=q, u=u, metadata=metadata)

    def pool(self, hidden, canonical_index):
        _require(isinstance(hidden, np.ndarray) and hidden.ndim == 2 and len(hidden) == len(self.logp),
                 'CTC and hidden frame counts differ')
        result = self.token_weights(canonical_index)
        return dict(vector=pool_hidden(hidden, result['u']), **result)
