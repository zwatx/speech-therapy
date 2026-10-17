"""Marginal correspondence choices across ALL minimum-cost edit alignments.

Additive research diagnostic: existing deterministic alignment and reports are
unchanged. Match costs zero; substitution, deletion and insertion cost one.
No probabilities, path weighting, calibration or clinical meaning are implied.
"""
from collections.abc import Sequence
from dataclasses import dataclass

# Two quadratic distance grids plus marginal outputs; reject excessive work
# before allocating them. This is a resource limit, not a phonetic constraint.
MAX_DP_CELLS = 250_000


@dataclass(frozen=True)
class ReferenceChoices:
    reference_index: int
    reference_phone: str
    hypothesis_indices: tuple[int | None, ...]
    hypothesis_phones: tuple[str | None, ...]
    agreement: str

    @property
    def correspondence_ambiguous(self):
        """More than one possible index/deletion correspondence."""
        return len(self.hypothesis_indices) > 1

    @property
    def identity_ambiguous(self):
        """More than one possible phone identity/deletion outcome."""
        return len(self.hypothesis_phones) > 1


@dataclass(frozen=True)
class AlignmentAmbiguity:
    """Choices are marginals, not independently selectable alignment steps.

    An index is zero-based into the original hypothesis. None represents a
    deletion, distinct from every phone string. Options use increasing indices
    or lexical phone order, with None last. A caller cannot arbitrarily combine
    choices from different positions into a single globally legal optimal path.
    """
    distance: int
    positions: tuple[ReferenceChoices, ...]


def _sequence(values, name):
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise ValueError(f'{name} must be a finite sequence of phone tokens')
    if len(values) + 1 > MAX_DP_CELLS:
        raise ValueError('alignment exceeds MAX_DP_CELLS')
    result = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError(f'{name} must contain nonblank string phone tokens')
    return result


def analyze_alignment(reference, hypothesis):
    """Return exact edit distance and all optimal per-reference choices.

    Inputs are finite sequences of nonblank string tokens, compared exactly
    without normalization. Empty sequences are supported. The grid size
    (len(reference)+1)*(len(hypothesis)+1) must not exceed MAX_DP_CELLS.
    Distance work and memory are O((n+1)*(m+1)); sorting identity options adds
    O(n*m*log(m+1)) worst-case work. No paths are enumerated or counted.
    Output size is O(n*(m+1)) in the worst case.

    agreement is 'match' when every optimal path matches this reference phone,
    'mismatch' when every path substitutes/deletes it, and 'ambiguous' when both
    occur. Multiple indices can still imply the same identity and agreement.
    """
    reference = _sequence(reference, 'reference')
    hypothesis = _sequence(hypothesis, 'hypothesis')
    n, m = len(reference), len(hypothesis)
    if (n + 1) * (m + 1) > MAX_DP_CELLS:
        raise ValueError('alignment exceeds MAX_DP_CELLS')
    forward = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        forward[i][0] = i
    for j in range(m + 1):
        forward[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            forward[i][j] = min(forward[i - 1][j] + 1, forward[i][j - 1] + 1,
                                forward[i - 1][j - 1] + (reference[i - 1] != hypothesis[j - 1]))
    backward = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        backward[i][m] = n - i
    for j in range(m + 1):
        backward[n][j] = m - j
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            backward[i][j] = min(backward[i + 1][j] + 1, backward[i][j + 1] + 1,
                                 backward[i + 1][j + 1] + (reference[i] != hypothesis[j]))
    distance = forward[n][m]
    positions = []
    for i, phone in enumerate(reference):
        indices, deleted = [], False
        for j in range(m + 1):
            # An edge is on some optimal path exactly when its best prefix,
            # edge cost and best suffix sum to the globally optimal distance.
            if forward[i][j] + 1 + backward[i + 1][j] == distance:
                deleted = True
            if (j < m and forward[i][j] + (phone != hypothesis[j])
                    + backward[i + 1][j + 1] == distance):
                indices.append(j)
        identities = sorted({hypothesis[j] for j in indices})
        if deleted:
            identities.append(None)
        matching = phone in identities
        mismatching = any(value != phone for value in identities)
        agreement = 'ambiguous' if matching and mismatching else 'match' if matching else 'mismatch'
        positions.append(ReferenceChoices(i, phone, tuple(indices) + ((None,) if deleted else ()),
                                          tuple(identities), agreement))
    return AlignmentAmbiguity(distance, tuple(positions))
