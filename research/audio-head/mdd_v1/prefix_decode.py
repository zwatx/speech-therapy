"""Research-only, prompt-blind CTC prefix beam search, without a language model.

Recurrence: https://distill.pub/2017/ctc/ (Inference). Vocabulary IDs are
preserved, and every token is considered at each frame. No token pruning or
renormalization is applied. This module has no model/runtime dependencies.
"""
from dataclasses import dataclass
import math
import operator

_NEG_INF = -math.inf


@dataclass(frozen=True)
class Hypothesis:
    """A collapsed token sequence and its retained alignment log mass.

    log_probability is a lower bound on the full sequence log probability when
    prefixes were pruned. It is neither an exact CTC score nor normalized over
    the returned beam; a wide enough beam recovers exact CTC probabilities.
    """
    tokens: tuple[int, ...]
    log_probability: float


def _add(a, b):
    if a == _NEG_INF:
        return b
    if b == _NEG_INF:
        return a
    high, low = max(a, b), min(a, b)
    return high + math.log1p(math.exp(low - high))


def _integer(value, name):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be an integer')
    try:
        return operator.index(value)
    except TypeError as error:
        raise ValueError(f'{name} must be an integer') from error


def _validated(log_probs, blank_id, normalization_tolerance):
    blank_id = _integer(blank_id, 'blank_id')
    if blank_id < 0:
        raise ValueError('blank_id must be nonnegative')
    tolerance = float(normalization_tolerance)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError('normalization_tolerance must be finite and nonnegative')
    shape = getattr(log_probs, 'shape', None)
    if shape is not None and len(shape) != 2:
        raise ValueError('log_probs must be a two-dimensional matrix')
    rows = []
    width = shape[1] if shape is not None else None
    try:
        for row in log_probs:
            values = tuple(float(value) for value in row)
            if width is None:
                width = len(values)
            if not values or len(values) != width:
                raise ValueError('log_probs must have nonempty, equal-width rows')
            total = _NEG_INF
            for value in values:
                if math.isnan(value) or value == math.inf:
                    raise ValueError('log_probs may contain only finite values or -infinity')
                total = _add(total, value)
            if not math.isfinite(total) or abs(total) > tolerance:
                raise ValueError('each log_probs row must be normalized within tolerance')
            rows.append(values)
    except (TypeError, OverflowError) as error:
        raise ValueError('log_probs must be a two-dimensional numeric matrix') from error
    if width is not None and (width < 1 or blank_id >= width):
        raise ValueError('blank_id must index the vocabulary')
    return rows, blank_id


def prefix_beam_decode(log_probs, *, blank_id, beam_width=32,
                       normalization_tolerance=1e-5):
    """Return up to beam_width hypotheses, best first, from T-by-V log probs.

    beam_width is a positive integer. T=0 returns the empty sequence at log mass
    zero; an empty Python sequence has no known vocabulary width, so any
    nonnegative blank_id is accepted there. For a shaped empty matrix, its
    vocabulary width is checked. Ties are ordered lexicographically by IDs.
    Runtime is O(T * beam_width * V) apart from sorting and tuple handling;
    callers must choose a beam and input length suitable for their budget.
    """
    beam_width = _integer(beam_width, 'beam_width')
    if beam_width < 1:
        raise ValueError('beam_width must be positive')
    rows, blank_id = _validated(log_probs, blank_id, normalization_tolerance)
    beam = {(): (0.0, _NEG_INF)}
    for row in rows:
        following = {}

        def accumulate(prefix, blank=_NEG_INF, nonblank=_NEG_INF):
            if blank == _NEG_INF and nonblank == _NEG_INF:
                return
            old_blank, old_nonblank = following.get(prefix, (_NEG_INF, _NEG_INF))
            following[prefix] = (_add(old_blank, blank), _add(old_nonblank, nonblank))

        for prefix, (blank, nonblank) in beam.items():
            total = _add(blank, nonblank)
            accumulate(prefix, blank=total + row[blank_id])
            for token, probability in enumerate(row):
                if token == blank_id or probability == _NEG_INF:
                    continue
                if prefix and token == prefix[-1]:
                    # An adjacent repeat stays collapsed; a blank separates it.
                    accumulate(prefix, nonblank=nonblank + probability)
                    accumulate(prefix + (token,), nonblank=blank + probability)
                else:
                    accumulate(prefix + (token,), nonblank=total + probability)
        ranked = sorted(following.items(), key=lambda item: (-_add(*item[1]), item[0]))
        beam = dict(ranked[:beam_width])
    return [Hypothesis(prefix, _add(*masses)) for prefix, masses in beam.items()]


def greedy_decode(log_probs, *, blank_id, normalization_tolerance=1e-5):
    """Collapse the best individual alignment; this need not win CTC search."""
    rows, blank_id = _validated(log_probs, blank_id, normalization_tolerance)
    tokens, previous = [], None
    for row in rows:
        token = max(range(len(row)), key=row.__getitem__)
        if token != blank_id and token != previous:
            tokens.append(token)
        previous = token
    return tuple(tokens)


def sequence_log_probability(log_probs, tokens, *, blank_id,
                             normalization_tolerance=1e-5):
    """Sum all CTC alignments for exactly tokens, without beam truncation.

    Returns a natural-log probability, or -infinity for impossible alignments.
    Targets contain integer vocabulary IDs excluding blank. An unshaped empty
    input has no known vocabulary width, so only nonnegativity and blank
    exclusion can be checked there. Empty targets require all frames blank.
    Uses O(T * (len(tokens) + 1)) time and O(len(tokens) + 1) state memory, plus
    the validated input matrix. No length reward or renormalization is applied.
    """
    rows, blank_id = _validated(log_probs, blank_id, normalization_tolerance)
    shape = getattr(log_probs, 'shape', None)
    width = len(rows[0]) if rows else (shape[1] if shape is not None else None)
    try:
        target = tuple(_integer(token, 'target token') for token in tokens)
    except TypeError as error:
        raise ValueError('tokens must be an iterable of integer vocabulary IDs') from error
    for token in target:
        if token < 0 or token == blank_id or (width is not None and token >= width):
            raise ValueError('target tokens must index the vocabulary and exclude blank')
    if not target:
        return sum((row[blank_id] for row in rows), 0.0)
    minimum_frames = len(target) + sum(a == b for a, b in zip(target, target[1:]))
    if len(rows) < minimum_frames:
        return _NEG_INF

    # Expanded states alternate blank and target IDs. Before frame zero, only
    # the initial blank state is reachable; transitions emit their destination.
    states = [blank_id]
    for token in target:
        states.extend((token, blank_id))
    forward = [0.0] + [_NEG_INF] * (len(states) - 1)
    for row in rows:
        following = [_NEG_INF] * len(states)
        for index, token in enumerate(states):
            mass = forward[index]
            if index:
                mass = _add(mass, forward[index - 1])
            if index > 1 and token != blank_id and token != states[index - 2]:
                mass = _add(mass, forward[index - 2])
            following[index] = mass + row[token]
        forward = following
    return _add(forward[-1], forward[-2])
