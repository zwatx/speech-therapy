"""Independent supplied-report audit; grouped ranking and scalar numeric replay.

No evaluator, fitter, model, corpus or stage imports. No scientific pass/fail rule.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ARMS = ('candidate', 'retained', 'calibration')
METRICS = ('auroc', 'logLoss', 'brier')
TOLERANCE = 1e-10


def _require(condition, message):
    if not condition: raise ValueError(message)


def _finite(value):
    try: return type(value) in (int, float) and math.isfinite(value)
    except OverflowError: return False


def _json(value):
    if value is None or type(value) in (str, bool, int): return True
    if type(value) is float: return math.isfinite(value)
    if type(value) is list: return all(_json(item) for item in value)
    if type(value) is dict: return all(type(key) is str and _json(item) for key, item in value.items())
    return False


def _identity(value):
    return type(value) is str and bool(value.strip())


def _key(row): return row['childId'], row['tokenId']


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _input(payload):
    _require(type(payload) is dict and _json(payload)
             and set(payload) == {'children', 'selectedTokens', 'arms', 'ratings'}, 'Invalid audit payload')
    _require(type(payload['children']) is list, 'Missing complete child roster')
    ids = set()
    for child in payload['children']:
        _require(type(child) is dict and _identity(child.get('childId')) and set(child) <= {'childId', 'descriptors'},
                 'Invalid child record')
        _require(child['childId'] not in ids and ('descriptors' not in child or type(child['descriptors']) is dict),
                 'Duplicate child or invalid descriptors')
        ids.add(child['childId'])
    def roster(rows):
        _require(type(rows) is list, 'Invalid terminal roster')
        keys = []
        for row in rows:
            _require(type(row) is dict and _identity(row.get('childId')) and _identity(row.get('tokenId'))
                     and row['childId'] in ids, 'Invalid terminal identity')
            keys.append(_key(row))
        _require(len(keys) == len(set(keys)), 'Duplicate terminal row')
        return set(keys)
    selected = roster(payload['selectedTokens'])
    _require(all(set(row) == {'childId', 'tokenId'} for row in payload['selectedTokens']), 'Unknown selected fields')
    _require(type(payload['arms']) is dict and set(payload['arms']) == set(ARMS), 'Invalid arms')
    for arm in ARMS:
        _require(roster(payload['arms'][arm]) == selected, 'Incomplete arm roster')
        for row in payload['arms'][arm]:
            if row.get('status') == 'processed':
                _require(set(row) == {'childId', 'tokenId', 'status', 'probability'}
                         and _finite(row['probability']) and 0 <= row['probability'] <= 1, 'Invalid probability')
            else:
                _require(set(row) == {'childId', 'tokenId', 'status', 'reason'}
                         and row['status'] in ('failed', 'unavailable') and _identity(row['reason']), 'Invalid arm failure')
    _require(roster(payload['ratings']) == selected, 'Incomplete rating roster')
    for row in payload['ratings']:
        if row.get('status') == 'available':
            _require(set(row) == {'childId', 'tokenId', 'status', 'positiveVotes', 'negativeVotes'}
                     and all(type(row[key]) is int and row[key] >= 0 for key in ('positiveVotes', 'negativeVotes'))
                     and row['positiveVotes'] + row['negativeVotes'] > 0, 'Invalid vote counts')
        else:
            _require(set(row) == {'childId', 'tokenId', 'status', 'reason'}
                     and row['status'] == 'unavailable' and _identity(row['reason']), 'Invalid rating failure')
    value = copy.deepcopy(payload)
    value['children'].sort(key=lambda row: row['childId'])
    for rows in (value['selectedTokens'], value['ratings'], *value['arms'].values()): rows.sort(key=_key)
    return value


def _numeric(rows):
    positive = sum(pos for _, pos, _ in rows)
    negative = sum(neg for _, _, neg in rows)
    groups = {}
    for probability, pos, neg in rows:
        totals = groups.setdefault(probability, [0, 0]); totals[0] += pos; totals[1] += neg
    negative_below = credit_twice = 0
    # Integer doubled credit counts all within-score ties, including self pairs.
    for probability in sorted(groups):
        pos, neg = groups[probability]
        credit_twice += pos * (2 * negative_below + neg)
        negative_below += neg
    auroc = credit_twice / (2 * positive * negative) if positive and negative else None
    votes = positive + negative
    losses, briers = [], []
    for probability, pos, neg in rows:
        probability = min(max(probability, 1e-6), 1 - 1e-6)
        # Normalize integer listener masses before multiplication by floating logs.
        losses.append(-(pos / votes) * math.log(probability) - (neg / votes) * math.log1p(-probability))
        briers.append((pos / votes) * (1 - probability) ** 2 + (neg / votes) * probability ** 2)
    return {'auroc': auroc, 'logLoss': math.fsum(losses) if votes else None,
            'brier': math.fsum(briers) if votes else None}


def _arm(keys, predictions, ratings):
    statuses = dict.fromkeys(('processed', 'unavailable', 'failed'), 0)
    exclusions, rows = [], []
    rated = 0
    for key in keys:
        prediction, rating = predictions[key], ratings[key]
        statuses[prediction['status']] += 1; rated += rating['status'] == 'available'
        reasons = []
        if prediction['status'] != 'processed': reasons.append(f"prediction:{prediction['status']}:{prediction['reason']}")
        if rating['status'] != 'available': reasons.append(f"rating:unavailable:{rating['reason']}")
        if reasons: exclusions.append({'tokenId': key[1], 'reasons': reasons})
        else: rows.append((prediction['probability'], rating['positiveVotes'], rating['negativeVotes']))
    positive = sum(pos for _, pos, _ in rows); negative = sum(neg for _, _, neg in rows)
    reason = 'no_selected_tokens' if not keys else 'no_processed_rated_tokens' if not rows else None
    ranking_reason = reason or ('no_positive_votes' if not positive else 'no_negative_votes' if not negative else None)
    return {**_numeric(rows), 'coverage': {'selected': len(keys), **statuses, 'ratingAvailable': rated,
            'processedAndRated': len(rows), 'positiveVotes': positive, 'negativeVotes': negative},
            'exclusions': exclusions, 'metricReasons': {'auroc': ranking_reason, 'logLoss': reason, 'brier': reason}}


def _pair(keys, candidate, comparator, ratings):
    shared = [key for key in keys if candidate[key]['status'] == comparator[key]['status'] == 'processed'
              and ratings[key]['status'] == 'available']
    left, right = _arm(shared, candidate, ratings), _arm(shared, comparator, ratings)
    if not shared and keys:
        for side in (left, right): side['metricReasons'] = dict.fromkeys(METRICS, 'no_shared_processed_rated_tokens')
    exclusions = []
    for key in keys:
        if key in shared: continue
        reasons = []
        if candidate[key]['status'] != 'processed': reasons.append(f"candidate:{candidate[key]['status']}:{candidate[key]['reason']}")
        if comparator[key]['status'] != 'processed': reasons.append(f"comparator:{comparator[key]['status']}:{comparator[key]['reason']}")
        if ratings[key]['status'] != 'available': reasons.append(f"rating:unavailable:{ratings[key]['reason']}")
        exclusions.append({'tokenId': key[1], 'reasons': reasons})
    gains = {metric + 'Gain': None if left[metric] is None or right[metric] is None else
             (left[metric] - right[metric]) * (1 if metric == 'auroc' else -1) for metric in METRICS}
    return {'tokenIds': [key[1] for key in shared], 'selectedTokens': len(keys),
            'sharedProcessedRatedTokens': len(shared), 'excludedTokens': exclusions,
            'candidate': left, 'comparator': right, **gains}


def _mean(values): return math.fsum(values) / len(values) if values else None


def _median(values):
    values = sorted(values)
    if not values: return None
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def _summary(children, arm, metric):
    defined = [child for child in children if child['arms'][arm][metric] is not None]
    values = [child['arms'][arm][metric] for child in defined]
    return {'fullChildDenominator': len(children), 'definedChildIds': [child['childId'] for child in defined],
            'excludedChildren': [{'childId': child['childId'], 'reason': child['arms'][arm]['metricReasons'][metric]}
                                 for child in children if child not in defined],
            'mean': _mean(values), 'median': _median(values)}


def _paired_summary(children, name, metric):
    defined, excluded, gains = [], [], []
    for child in children:
        pair = child['paired'][name]; gain = pair[metric + 'Gain']
        if gain is None:
            excluded.append({'childId': child['childId'], 'reasons': {
                side: pair[side]['metricReasons'][metric] for side in ('candidate', 'comparator')}})
        else: defined.append(child['childId']); gains.append(gain)
    bootstrap = {'population': 'defined_paired_children_only', 'seed': 20261002,
                 'generator': 'numpy.default_rng/PCG64', 'requestedReplicates': 2000,
                 'quantileMethod': 'linear', 'confidenceLevel': .95, 'generatedReplicates': 0,
                 'undefinedReplicates': 0, 'skippedReplicates': 2000, 'interval95': None, 'degenerate': len(gains) == 1}
    if gains:
        rng = np.random.default_rng(20261002)
        indices = rng.integers(0, len(gains), size=(2000, len(gains)))
        sampled = sorted(math.fsum(gains[index] for index in row) / len(row) for row in indices)
        def quantile(fraction):
            position = (len(sampled) - 1) * fraction; below = math.floor(position); above = math.ceil(position)
            return sampled[below] + (sampled[above] - sampled[below]) * (position - below)
        bootstrap.update(generatedReplicates=2000, skippedReplicates=0, interval95=[quantile(.025), quantile(.975)])
    return {'fullChildDenominator': len(children), 'definedChildIds': defined, 'excludedChildren': excluded,
            'gains': [{'childId': child, 'gain': gain} for child, gain in zip(defined, gains)],
            'gainDirection': 'candidate_minus_comparator' if metric == 'auroc' else 'comparator_minus_candidate',
            'meanGain': _mean(gains), 'medianGain': _median(gains), 'improvedChildren': sum(value > 0 for value in gains),
            'worsenedChildren': sum(value < 0 for value in gains), 'tiedChildren': sum(value == 0 for value in gains),
            'fractionImproved': sum(value > 0 for value in gains) / len(gains) if gains else None,
            'fractionWorsened': sum(value < 0 for value in gains) / len(gains) if gains else None, 'bootstrap': bootstrap}


def _compare(actual, expected, path='report'):
    if type(expected) is dict:
        _require(type(actual) is dict and set(actual) == set(expected), 'Audit fields differ: ' + path)
        for key, value in expected.items(): _compare(actual[key], value, path + '.' + key)
    elif type(expected) is list:
        _require(type(actual) is list and len(actual) == len(expected), 'Audit rows differ: ' + path)
        for index, value in enumerate(expected): _compare(actual[index], value, f'{path}[{index}]')
    elif type(expected) is float:
        _require(_finite(actual) and math.isclose(actual, expected, abs_tol=TOLERANCE, rel_tol=TOLERANCE),
                 'Audit numeric replay differs: ' + path)
    else:
        _require(type(actual) is type(expected) and actual == expected, 'Audit value differs: ' + path)


def audit_evaluation(payload, report):
    """Audit all reported rows, metrics, coverage and conditional uncertainty.

    This proves supplied-artifact consistency only, not original ratings, model
    execution, chronology, independence, clinical truth or scientific acceptance.
    """
    canonical = _input(payload)
    ratings = {_key(row): row for row in canonical['ratings']}
    predictions = {arm: {_key(row): row for row in canonical['arms'][arm]} for arm in ARMS}
    children = []
    for child in canonical['children']:
        keys = [_key(row) for row in canonical['selectedTokens'] if row['childId'] == child['childId']]
        arms = {name: _arm(keys, predictions[name], ratings) for name in ARMS}
        pairs = {'candidateVsRetained': _pair(keys, predictions['candidate'], predictions['retained'], ratings),
                 'candidateVsCalibration': _pair(keys, predictions['candidate'], predictions['calibration'], ratings)}
        children.append({'childId': child['childId'], 'descriptors': copy.deepcopy(child.get('descriptors', {})),
                         'arms': arms, 'paired': pairs})
    expected = {'schemaVersion': 1, 'researchOnly': True, 'clinicalUseEligible': False,
                'learnerFeedbackEligible': False, 'productionUseEligible': False, 'fullChildDenominator': len(children),
                'selectedTokenDenominator': len(canonical['selectedTokens']), 'children': children,
                'armSummary': {arm: {metric: _summary(children, arm, metric) for metric in METRICS} for arm in ARMS},
                'pairedSummary': {'candidateVsRetained': {'auroc': _paired_summary(children, 'candidateVsRetained', 'auroc')},
                                  'candidateVsCalibration': {metric: _paired_summary(children, 'candidateVsCalibration', metric)
                                                             for metric in ('logLoss', 'brier')}},
                'terminalOutcomes': {key: canonical[key] for key in ('selectedTokens', 'arms', 'ratings')}}
    _require(type(report) is dict and set(report) == set(expected) and _json(report), 'Malformed evaluation report')
    # First independently verify all child metrics and coverage. Tiny gain signs
    # depend on IEEE rounding: verify saved subtraction exactly, then resample the
    # independently checked saved gains rather than a differently rounded replay.
    _compare(report['children'], children)
    _require(_digest(report['terminalOutcomes']) == _digest(expected['terminalOutcomes']), 'Changed terminal input bytes')
    for actual, original in zip(report['children'], canonical['children']):
        _require(_digest(actual['descriptors']) == _digest(original.get('descriptors', {})), 'Changed metadata descriptors')
        for pair in actual['paired'].values():
            for metric in METRICS:
                left, right = pair['candidate'][metric], pair['comparator'][metric]
                saved_gain = pair[metric + 'Gain']
                subtraction = None if left is None or right is None else (left - right) * (1 if metric == 'auroc' else -1)
                _require(type(saved_gain) is type(subtraction) and saved_gain == subtraction, 'Inconsistent saved gain arithmetic')
    checked_children = report['children']
    expected['armSummary'] = {arm: {metric: _summary(checked_children, arm, metric) for metric in METRICS} for arm in ARMS}
    expected['pairedSummary'] = {
        'candidateVsRetained': {'auroc': _paired_summary(checked_children, 'candidateVsRetained', 'auroc')},
        'candidateVsCalibration': {metric: _paired_summary(checked_children, 'candidateVsCalibration', metric)
                                  for metric in ('logLoss', 'brier')}}
    _compare(report, expected)
    return {'schemaVersion' : 1, 'outcome': 'verified', 'researchOnly': True, 'clinicalUseEligible': False,
            'learnerFeedbackEligible': False, 'productionUseEligible': False,
            'fullChildDenominator': len(children), 'selectedTokenDenominator': len(canonical['selectedTokens']),
            'inputSha256': _digest(canonical), 'reportSha256': _digest(report),
            'auditorSourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'method': 'grouped_integer_rank_credit_scalar_proper_scores_numpy_indices_scalar_quantiles',
            'numericTolerance': {'absolute': TOLERANCE, 'relative': TOLERANCE},
            'numpyVersion': np.__version__, 'limitations': [
                'Same declared PCG64 generator; independent indices and scalar quantiles on independently checked saved gains.',
                'Saved gain arithmetic/sign counts are exact; numerical metric replay uses the declared tolerance.',
                'Supplied-artifact audit cannot establish original ratings, execution, provenance or outcome chronology.',
                'Not a qualified statistical signoff, scientific pass/fail decision or learner finding.']}
