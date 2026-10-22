"""Deterministic Levenshtein PER and canonical-position MDD, with explicit gaps."""
from collections import Counter


def align(reference, hypothesis):
    """Return (reference index or None, hypothesis index or None) pairs.

    Unit costs; ties prefer diagonal, deletion, insertion in that order.
    """
    n, m = len(reference), len(hypothesis)
    costs = [[0]*(m+1) for _ in range(n+1)]
    for i in range(n+1):
        costs[i][0] = i
    for j in range(m+1):
        costs[0][j] = j
    for i in range(1, n+1):
        for j in range(1, m+1):
            costs[i][j] = min(costs[i-1][j-1]+(reference[i-1] != hypothesis[j-1]),
                              costs[i-1][j]+1, costs[i][j-1]+1)
    pairs, i, j = [], n, m
    while i or j:
        if i and j and costs[i][j] == costs[i-1][j-1]+(reference[i-1] != hypothesis[j-1]):
            pairs.append((i-1, j-1)); i -= 1; j -= 1
        elif i and costs[i][j] == costs[i-1][j]+1:
            pairs.append((i-1, None)); i -= 1
        else:
            pairs.append((None, j-1)); j -= 1
    return list(reversed(pairs))


def per_counts(reference, hypothesis):
    counts = Counter(N=len(reference), S=0, D=0, I=0)
    confusions = Counter()
    for i, j in align(reference, hypothesis):
        if i is None:
            counts['I'] += 1; confusions[f'∅ → {hypothesis[j]}'] += 1
        elif j is None:
            counts['D'] += 1; confusions[f'{reference[i]} → ∅'] += 1
        elif reference[i] != hypothesis[j]:
            counts['S'] += 1; confusions[f'{reference[i]} → {hypothesis[j]}'] += 1
    return counts, confusions


def anchored(canonical, hypothesis):
    slots, gaps, cursor = [None]*len(canonical), {}, 0
    for i, j in align(canonical, hypothesis):
        if i is None:
            gaps.setdefault(cursor, []).append(hypothesis[j])
        else:
            slots[i] = hypothesis[j] if j is not None else None
            cursor = i+1
    return slots, gaps


def mdd_counts(record, hypothesis):
    canonical = record['canonical']
    slots, gaps = anchored(canonical, hypothesis)
    counts = Counter(TA=0, FR=0, FA=0, TR=0, CD=0, diagnosis_eligible_TR=0,
                     reference_insertions=0, predicted_insertions=0, correct_insertion_phones=0,
                     same_broad_identity_reference_errors=0, same_broad_identity_TR=0, same_broad_identity_FA=0)
    expected_gaps = {}
    for event in record['events']:
        index, expected = event['canonical_index'], event['perceived']
        if event['event'] == 'insertion':
            expected_gaps.setdefault(index, []).append(expected)
            continue
        actual = slots[index]
        reference_error = event['event'] != 'unchanged'
        rejected = actual != canonical[index]
        counts[('TR' if rejected else 'FA') if reference_error else ('FR' if rejected else 'TA')] += 1
        if reference_error and expected == canonical[index]:
            counts['same_broad_identity_reference_errors'] += 1
            counts['same_broad_identity_TR' if rejected else 'same_broad_identity_FA'] += 1
        known = event['event'] == 'deletion' or expected is not None
        if reference_error and rejected and known:
            counts['diagnosis_eligible_TR'] += 1
            if actual == expected:
                counts['CD'] += 1
    counts['reference_insertions'] = sum(map(len, expected_gaps.values()))
    counts['predicted_insertions'] = sum(map(len, gaps.values()))
    for index, reference in expected_gaps.items():
        for i, j in align(reference, gaps.get(index, [])):
            if i is not None and j is not None and reference[i] is not None and reference[i] == gaps[index][j]:
                counts['correct_insertion_phones'] += 1
    return counts


def ratio(a, b):
    return a/b if b else None


def evaluate(records, predictions):
    per, mdd, confusions = Counter(N=0, S=0, D=0, I=0), Counter(), Counter()
    included, unknown = 0, 0
    for row in records:
        hypothesis = predictions[row['id']]
        if all(p is not None for p in row['perceived']):
            c, errors = per_counts(row['perceived'], hypothesis)
            per.update(c); confusions.update(errors); included += 1
        else:
            unknown += 1
        if row['source'] == 'l2-arctic':
            mdd.update(mdd_counts(row, hypothesis))
    result = dict(utterances=len(records), per_utterances=included, unknown_reference_utterances=unknown,
                  per=dict(per), PER=ratio(per['S']+per['D']+per['I'], per['N']),
                  top_confusions=confusions.most_common(20))
    if mdd:
        precision = ratio(mdd['TR'], mdd['TR']+mdd['FR'])
        recall = ratio(mdd['TR'], mdd['TR']+mdd['FA'])
        result.update(mdd=dict(mdd), precision=precision, recall=recall,
                      F1=ratio(2*mdd['TR'], 2*mdd['TR']+mdd['FR']+mdd['FA']),
                      diagnosis_accuracy=ratio(mdd['CD'], mdd['diagnosis_eligible_TR']),
                      descriptive_diagnosis_excluding_same_broad=ratio(
                          mdd['CD'], mdd['diagnosis_eligible_TR']-mdd['same_broad_identity_TR']),
                      descriptive_recall_excluding_same_broad=ratio(
                          mdd['TR']-mdd['same_broad_identity_TR'],
                          mdd['TR']+mdd['FA']-mdd['same_broad_identity_reference_errors']))
    return result
