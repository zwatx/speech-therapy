"""Pure additive phone/class/child descriptions of a fixed paired NLL contrast."""
import numpy as np

PHONES = tuple('B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG'.split())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _indices(values, size, name):
    array = np.asarray(values)
    require(array.shape == (size,) and array.dtype.kind in 'iu'
            and (array >= 0).all() and (array < 5).all(), name + ' must be integer indices in 0..4')
    # Reject mixed bool/int Python sequences before NumPy silently coerces them.
    require(all(not isinstance(v, (bool, np.bool_)) for v in values), name + ' must not contain booleans')
    return array


def _logs(values, size):
    array = np.asarray(values)
    require(array.shape == (size, 3) and array.dtype.kind in 'fiu', 'Expected numeric N by 3 log probabilities')
    array = array.astype(np.float64, copy=False)
    require(np.isfinite(array).all() and (array <= 0).all()
            and np.allclose(np.exp(array).sum(1), 1., rtol=0, atol=1e-12),
            'Expected finite normalized nonpositive stable logs')
    return array


def _same_sum(parts, expected, name):
    require(np.isclose(sum(parts), expected, rtol=2e-11, atol=2e-12), name + ' additive identity differs')


def analyze(rows, folds, groups, candidateLogs, referenceLogs):
    """Describe candidate-minus-reference NLL without fitting, selection, or ranks.

    Every phone includes all five speaker folds, 25 speaker/word cells, and every
    child in the supplied population. Subcell contributions use that phone's
    position count; explicit pooled contributions use the whole population.
    The caller validates original-child population and model artifact lineage.
    """
    size = len(rows)
    require(size > 0, 'Nonempty matched rows required')
    fields = ('id', 'clipId', 'speakerId', 'targetPhone', 'raterCounts')
    require(all(isinstance(row, dict) and all(key in row for key in fields) for row in rows), 'Missing row identity or labels')
    require(all(isinstance(row[key], str) and row[key] for row in rows for key in ('id', 'clipId', 'speakerId')),
            'Row, clip, and speaker IDs must be nonempty strings')
    require(len({row['id'] for row in rows}) == size, 'Duplicate row identity')
    require(all(row['targetPhone'] in PHONES for row in rows), 'Unknown target phone')
    require(all(np.asarray(row['raterCounts']).shape == (3,)
                and all(isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_)) and 0 <= v <= 5
                        for v in row['raterCounts']) and sum(row['raterCounts']) == 5 for row in rows),
            'Expected five nonnegative integer, nonboolean votes')
    counts = np.asarray([row['raterCounts'] for row in rows], dtype=np.int64)
    folds, groups = _indices(folds, size, 'folds'), _indices(groups, size, 'groups')
    speakers = np.asarray([row['speakerId'] for row in rows])
    children = sorted(set(speakers.tolist()))
    require(all(len(np.unique(folds[speakers == child])) == 1 for child in children), 'One child belongs to multiple folds')
    candidate, reference = _logs(candidateLogs, size), _logs(referenceLogs, size)
    class_delta = -counts * (candidate - reference) / 5
    delta = class_delta.sum(1)
    require(np.isfinite(class_delta).all() and np.isfinite(delta).all(), 'Nonfinite loss contrast')
    phones = np.asarray([row['targetPhone'] for row in rows])

    def support(mask):
        selected = np.flatnonzero(mask)
        return dict(positions=len(selected), children=len({rows[i]['speakerId'] for i in selected}),
                    recordings=len({rows[i]['clipId'] for i in selected}), raterVotes=counts[mask].sum(0).tolist())

    def cell(mask, phone_count):
        positions = int(mask.sum())
        total = float(delta[mask].sum())
        return dict(support=support(mask), meanNLLDelta=total / positions if positions else None,
                    phoneNLLContribution=total / phone_count if phone_count else 0.)

    per_phone = {}
    for phone in PHONES:
        mask = phones == phone
        phone_count = int(mask.sum())
        value = cell(mask, phone_count)
        value['pooledNLLContribution'] = float(delta[mask].sum() / size)
        classes = {}
        for rating in range(3):
            votes = int(counts[mask, rating].sum())
            total = float(class_delta[mask, rating].sum())
            classes[str(rating)] = dict(votes=votes,
                conditionalNLLDelta=float((-counts[mask, rating] * (candidate[mask, rating] - reference[mask, rating])).sum() / votes)
                    if votes else None,
                phoneNLLContribution=total / phone_count if phone_count else 0., pooledNLLContribution=total / size)
        value['ratingClasses'] = classes
        value['speakerFolds'] = {str(fold): cell(mask & (folds == fold), phone_count) for fold in range(5)}
        value['wordCells'] = {f's{fold}-w{group}': cell(mask & (folds == fold) & (groups == group), phone_count)
                              for fold in range(5) for group in range(5)}
        value['children'] = {child: cell(mask & (speakers == child), phone_count) for child in children}
        expected = value['phoneNLLContribution']
        for name in ('ratingClasses', 'speakerFolds', 'wordCells', 'children'):
            _same_sum((part['phoneNLLContribution'] for part in value[name].values()), expected, phone + '/' + name)
        _same_sum((part['pooledNLLContribution'] for part in classes.values()), value['pooledNLLContribution'], phone + '/pooled classes')
        per_phone[phone] = value
    pooled = dict(support=support(np.ones(size, dtype=bool)), meanNLLDelta=float(delta.mean()))
    _same_sum((value['pooledNLLContribution'] for value in per_phone.values()), pooled['meanNLLDelta'], 'Pooled phones')
    return dict(rowLossDelta=delta.tolist(), rowClassLossDelta=class_delta.tolist(), pooled=pooled, perPhone=per_phone)
