"""Fixed descriptive corpus-vote reliability; no fitting or model inference."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE / 'outputs/multiphone-20260926'
PROTOCOL = HERE / '../../docs/model/multiphone-rating-reliability-protocol.md'
PROTOCOL_SHA = '0e6de8ab2b07dcff436c0aebd4cbef022a30ed8425b2e4a4f9966c6990955462'
LOADER_SHA = '38cbd74b7c7980f4e4e84da6bc5a8892d75bf65eef5cc96cadd80d001acdebed'
REPORT_SHA = 'c12a0562ffec6f9783c231950a7099dee3a0b0e196cf0a2bc0c7ae810077c542'
MODELS = ('phonetic-target-scalars-all-age', 'phonetic-target-scalars-child-only',
          'scalar-full13', 'child-only-phone-prior')
EVENTS = {'rating0': (0,), 'ratingBelow2': (0, 1)}
EDGES = np.asarray([i / 10 for i in range(11)], dtype=np.float64)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def votes(rows):
    require(all(len(r['raterCounts']) == 3 and sum(r['raterCounts']) == 5
                and all(type(c) is int and c >= 0 for c in r['raterCounts']) for r in rows),
            'Expected five nonnegative integer corpus votes per target')
    return np.asarray([r['raterCounts'] for r in rows], dtype=np.int64).reshape(-1, 3)


def checked_probabilities(values, count):
    p = np.asarray(values, dtype=np.float64)
    require(p.shape == (count, 3) and np.isfinite(p).all() and (p >= 0).all()
            and (p <= 1).all() and np.allclose(p.sum(1), 1, rtol=0, atol=1e-6),
            'Expected finite complete rating probabilities')
    return p


def support(rows, positive):
    observed = [r for r, c in zip(rows, positive, strict=True) if c > 0]
    total = int(sum(positive))
    return {'positions': len(rows), 'clips': len({r['clipId'] for r in rows}),
            'speakers': len({r['speakerId'] for r in rows}),
            'phones': len({r['targetPhone'] for r in rows}),
            'positiveVotes': total, 'negativeVotes': 5 * len(rows) - total,
            'positionsWithAnyPositiveVote': len(observed),
            'speakersWithAnyPositiveVote': len({r['speakerId'] for r in observed})}


def reliability(probabilities, rows, classes):
    p = checked_probabilities(probabilities, len(rows))[:, classes].sum(1)
    positive = votes(rows)[:, classes].sum(1)
    require(np.isfinite(p).all() and (p >= 0).all() and (p <= 1).all(),
            'Event probability lies outside zero to one')
    assignments = np.minimum(np.searchsorted(EDGES, p, side='right') - 1, 9)
    bins = []
    for index in range(10):
        mask = assignments == index
        selected = [r for r, keep in zip(rows, mask, strict=True) if keep]
        item = {'index': index, 'lowerInclusive': float(EDGES[index]),
                'upper': float(EDGES[index + 1]), 'upperInclusive': index == 9,
                'support': support(selected, positive[mask]), 'meanPredicted': None,
                'observedVoteFraction': None, 'predictionMinusObservation': None}
        if selected:
            item['meanPredicted'] = float(p[mask].mean())
            item['observedVoteFraction'] = int(positive[mask].sum()) / (5 * len(selected))
            item['predictionMinusObservation'] = item['meanPredicted'] - item['observedVoteFraction']
        bins.append(item)
    require(sum(b['support']['positions'] for b in bins) == len(rows), 'Bin partition lost rows')
    result = {'support': support(rows, positive), 'bins': bins, 'meanPredicted': None,
              'observedVoteFraction': None, 'predictionMinusObservation': None,
              'positionWeightedAbsoluteBinnedResidual': None}
    if rows:
        result['meanPredicted'] = float(p.mean())
        result['observedVoteFraction'] = int(positive.sum()) / (5 * len(rows))
        result['predictionMinusObservation'] = result['meanPredicted'] - result['observedVoteFraction']
        result['positionWeightedAbsoluteBinnedResidual'] = sum(
            b['support']['positions'] * abs(b['predictionMinusObservation'])
            for b in bins if b['support']['positions']) / len(rows)
    return result


def summarize(models, rows, row_folds):
    require(tuple(models) == MODELS and len(rows) == len(row_folds), 'Fixed model or row inventory differs')
    votes(rows)
    phones = sorted({r['targetPhone'] for r in rows})
    folds = np.asarray(row_folds)
    require(set(folds.tolist()) == set(range(5)), 'Expected all five outer folds')
    output = {}
    for name, values in models.items():
        p = checked_probabilities(values, len(rows))
        output[name] = {}
        for event, classes in EVENTS.items():
            by_phone, by_fold = {}, {}
            for phone in phones:
                mask = np.asarray([r['targetPhone'] == phone for r in rows])
                by_phone[phone] = reliability(p[mask], [r for r, keep in zip(rows, mask) if keep], classes)
            for fold in range(5):
                mask = folds == fold
                by_fold[str(fold)] = reliability(p[mask], [r for r, keep in zip(rows, mask) if keep], classes)
            output[name][event] = {'pooled': reliability(p, rows, classes), 'perPhone': by_phone,
                'perFold': by_fold, 'equalPhoneMeanAbsoluteBinnedResidual': float(np.mean([
                    v['positionWeightedAbsoluteBinnedResidual'] for v in by_phone.values()]))}
    return output


def markdown(value):
    lines = ['# Child corpus-rating reliability', '',
        'Exploratory development diagnostic of saved out-of-speaker predictions for 5,654 positions '
        'from 52 children aged 6–12. The measured events are corpus votes, not pronunciation correctness. '
        'No model was fitted, corrected or selected.', '',
        '| Pipeline | Event | Mean predicted | Observed vote fraction | Prediction − observation | Pooled absolute binned residual | Equal-phone residual |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for name in MODELS:
        for event in EVENTS:
            cell = value['models'][name][event]; p = cell['pooled']
            values = [p[k] for k in ('meanPredicted', 'observedVoteFraction', 'predictionMinusObservation',
                                    'positionWeightedAbsoluteBinnedResidual')]
            values.append(cell['equalPhoneMeanAbsoluteBinnedResidual'])
            lines.append('| ' + name + ' | ' + event + ' | ' + ' | '.join(f'{v:.6f}' for v in values) + ' |')
    lines += ['', 'Ten fixed equal-width bins retain all empty cells. Every bin records position, clip, phone, '
        'child and vote support. Full pooled, 23-phone and five-fold bin tables are in the JSON. '
        'The pooled statistic weights positions; the equal-phone statistic weights the 23 phones equally. '
        'These are bin-dependent descriptive residuals, not calibrated-accuracy scores.', '',
        'Different models assign different recordings to bins, so within-bin comparisons are not paired. '
        'Pooling can hide opposite phone/fold errors; small occupied bins remain sparse, and empty bins '
        'do not mean agreement. Five votes, many positions or several sounds from a child do not create '
        'independent participants. No uncertainty interval, temperature, threshold, winner or learner policy is produced.', '',
        'The four full-data exports are unchanged. This used development corpus has no ages 2–5 or verified '
        'SSD cohort and cannot establish reliability on new children, natural app recordings, or produced-phone errors.']
    return '\n'.join(lines) + '\n'


def build(output):
    import multiphone_outer_report as loader
    require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Choose fresh ignored output')
    report_path = BASE / 'outer-comparison-v1/report.json'
    pins = {str(Path(__file__).resolve()): digest(Path(__file__)), str(PROTOCOL.resolve()): PROTOCOL_SHA,
            str(Path(loader.__file__).resolve()): LOADER_SHA, str(report_path): REPORT_SHA}
    require(all(digest(Path(p)) == h for p, h in pins.items()), 'Reviewed source or protocol changed')
    published = json.loads(report_path.read_text())
    require(published['complete'] and not published['authorTestInferencePerformed']
            and not published['winnerSelectionPerformed'], 'Published study scope differs')
    bundle = loader.load_predictions(Path(published['releasePath']), published['releaseSha256'],
                                     Path(published['evaluationLedgerPath']), published['evaluationLedgerSha256'])
    require(bundle['rowIndices'] == published['alignedRowIndices'], 'Published row identity differs')
    mask = np.asarray([6 <= r['age'] <= 12 for r in bundle['rows']])
    rows = [r for r, keep in zip(bundle['rows'], mask, strict=True) if keep]
    indices = [i for i, keep in zip(bundle['rowIndices'], mask, strict=True) if keep]
    row_folds = np.asarray(bundle['rowFolds'])[mask].tolist()
    require(len(rows) == 5654 and len(set(indices)) == 5654 and len({r['speakerId'] for r in rows}) == 52
            and len({r['targetPhone'] for r in rows}) == 23, 'Child population changed')
    models = {name: bundle['models'][name][mask] for name in MODELS}
    value = {'complete': True, 'childRowIndices': indices, 'rowFolds': row_folds,
        'models': summarize(models, rows, row_folds), 'sourceAndInputSha256': pins,
        'releaseArtifactSha256': bundle['artifactSha256'], 'loaderSourceSha256': bundle['sourceSha256'],
        'inferencePerformed': False, 'trainingPerformed': False, 'calibrationCorrectionPerformed': False,
        'thresholdSelected': False, 'winnerSelected': False, 'authorTestInferencePerformed': False,
        'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    content = markdown(value)
    loader.guard_bundle(bundle)
    require(all(digest(Path(p)) == h for p, h in pins.items()), 'Source or input changed during diagnostic')
    output.mkdir(parents=True, mode=0o700)
    (output / 'report.md').write_text(content)
    value['markdownSha256'] = digest(output / 'report.md')
    (output / 'report.json').write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.output)
    print(json.dumps({'complete': result['complete'], 'models': len(result['models']),
                      'reportSha256': digest(args.output / 'report.json')}))
