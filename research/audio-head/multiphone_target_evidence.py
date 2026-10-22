"""Describe child rating support using the completed, pinned development study.

No inference, selection, human relabeling, or model fitting is performed.
Five ratings at a target position are never counted as five children.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE / 'outputs/multiphone-20260926'
INPUTS = {
    'cohort': (BASE / 'cohort.json', '33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805'),
    'comparison': (BASE / 'outer-comparison-v1/report.json', 'c12a0562ffec6f9783c231950a7099dee3a0b0e196cf0a2bc0c7ae810077c542'),
}
MODELS = ('scalar-full13', 'phonetic-target-scalars-all-age')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def support(rows):
    require(all(len(r['raterCounts']) == 3 and sum(r['raterCounts']) == 5
                and all(type(c) is int and c >= 0 for c in r['raterCounts']) for r in rows),
            'Expected five integer ratings per position')
    result = {'positions': len(rows), 'clips': len({r['clipId'] for r in rows}),
              'speakers': len({r['speakerId'] for r in rows}),
              'observedRaterCounts': [sum(r['raterCounts'][i] for r in rows) for i in range(3)],
              'mixedRaterPositions': sum(sum(c > 0 for c in r['raterCounts']) > 1 for r in rows)}
    for name, classes in (('rating0', (0,)), ('rating1', (1,)), ('ratingBelow2', (0, 1))):
        positive = [r for r in rows if sum(r['raterCounts'][i] for i in classes) > 0]
        result[name] = {'raterVotes': sum(sum(r['raterCounts'][i] for i in classes) for r in rows),
                        'positionsWithAnyVote': len(positive),
                        'clipsWithAnyVote': len({r['clipId'] for r in positive}),
                        'speakersWithAnyVote': len({r['speakerId'] for r in positive})}
    return result


def build():
    initial_source = digest(Path(__file__))
    documents, pins = {}, {}
    for name, (path, expected) in INPUTS.items():
        payload = path.read_bytes()
        require(hashlib.sha256(payload).hexdigest() == expected, 'Pinned input changed')
        documents[name] = json.loads(payload)
        pins[name] = {'path': str(path), 'sha256': expected}
    cohort, comparison = documents['cohort'], documents['comparison']
    require(cohort['authorPartition'] == 'train' and comparison['complete'] is True
            and comparison['winnerSelectionPerformed'] is False
            and comparison['authorTestInferencePerformed'] is False, 'Study scope changed')
    children = [r for r in cohort['rows'] if 6 <= r['age'] <= 12]
    eligible = [r for r in children if r['trainingEligible']]
    reference = comparison['statistics']['slices']['ages6to12']
    require(len(eligible) == 5654 and len({r['speakerId'] for r in eligible}) == 52,
            'Expected unique full child development population')
    results = []
    for target in cohort['targets']:
        rows = [r for r in children if r['targetId'] == target['id']]
        evidence = support(rows)
        item = {'targetId': target['id'], 'phone': target['phone'], 'symbol': target['symbol'],
                'trainingEligible': target['trainingEligible'], 'support': evidence,
                'sourceExclusionReason': target['exclusionReason'], 'metrics': None}
        if target['trainingEligible']:
            saved = reference['perPhoneSupport'][target['phone']]
            require(all(evidence[k] == v for k, v in saved.items()), 'Published child support differs')
            item['metrics'] = {name: reference['models'][name]['perPhone'][target['phone']] for name in MODELS}
            for metrics in item['metrics'].values():
                for event in ('rating0', 'ratingBelow2'):
                    require(metrics[event]['positiveRaterWeight'] == evidence[event]['raterVotes']
                            and metrics[event]['negativeRaterWeight'] == 5 * len(rows) - evidence[event]['raterVotes'],
                            'Published ranking denominator differs')
            item['phoneticMinusScalarNLL'] = (item['metrics'][MODELS[1]]['perRaterLogLoss']
                                              - item['metrics'][MODELS[0]]['perRaterLogLoss'])
        results.append(item)
    require([r['targetId'] for r in results] == list(range(24))
            and sum(r['trainingEligible'] for r in results) == 23, 'Target inventory differs')
    result = {'complete': True, 'inputFiles': pins, 'sourceSha256': initial_source,
        'ageMinimum': 6, 'ageMaximum': 12, 'eligibleChildSupport': support(eligible), 'targets': results,
        'interpretation': 'Descriptive development support and already-published point metrics; no adequacy threshold or target selection.',
        'inferencePerformed': False, 'trainingPerformed': False, 'newHumanLabels': False,
        'learnerFeedbackEligible': False, 'clinicalUseEligible': False}
    require(digest(Path(__file__)) == initial_source
            and all(digest(Path(v['path'])) == v['sha256'] for v in pins.values()), 'Input changed during audit')
    return result


def markdown(report):
    lines = ['# Child target evidence audit', '',
        'This describes the existing public-corpus development evidence for ages 6–12. '
        'It does not certify any sound for learner feedback. No new inference, training, '
        'threshold selection or human labeling was performed.', '',
        'The 23 fitted targets together have 5,654 positions from 52 children. '
        'Each position has five corpus ratings; neither votes nor positions are independent children. '
        'Rows with any lower vote can also contain higher votes. Age 2–5 and verified SSD coverage remain absent.', '',
        '## Where the lower-rating evidence comes from', '',
        '“0 children” and “<2 children” count distinct children with at least one corresponding vote. '
        'These are corpus rating events, not qualified substitution/distortion diagnoses. '
        'Children recur across different target rows, so do not sum the table’s child counts.', '',
        '| Target | Positions | Children | Votes 0 / 1 / 2 | 0 positions | 0 children | <2 positions | <2 children |',
        '| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |']
    for target in report['targets']:
        s = target['support']; zero, lower = s['rating0'], s['ratingBelow2']
        name = target['phone'] + ('' if target['trainingEligible'] else ' (excluded)')
        votes = ' / '.join(map(str, s['observedRaterCounts']))
        lines.append(f"| {name} | {s['positions']} | {s['speakers']} | {votes} | {zero['positionsWithAnyVote']} | {zero['speakersWithAnyVote']} | {lower['positionsWithAnyVote']} | {lower['speakersWithAnyVote']} |")
    lines += ['', '## Already-published per-target comparison', '',
        'The two fixed all-age fitting pipelines are scalar-only and phonetic target-window plus scalars. '
        'Each prediction excludes its own speaker from fitting, but development choices used overlapping inner outcomes. '
        'These descriptive point estimates have no per-target confidence intervals here. '
        'NLL is lower when the rating probabilities fit better; rating-0 AUROC measures ranking, not an operating threshold or accuracy.', '',
        '| Target | Scalar NLL | Phonetic + scalar NLL | NLL difference | Scalar rating-0 AUROC | Phonetic + scalar rating-0 AUROC |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for target in report['targets']:
        if not target['trainingEligible']:
            continue
        a, b = (target['metrics'][name] for name in MODELS)
        lines.append(f"| {target['phone']} | {a['perRaterLogLoss']:.5f} | {b['perRaterLogLoss']:.5f} | {target['phoneticMinusScalarNLL']:+.5f} | {a['rating0']['auroc']:.3f} | {b['rating0']['auroc']:.3f} |")
    lines += ['', '## Implication for the next labels', '',
        'A trained output ID is not evidence that its errors can be detected reliably. '
        'Use these denominators to discuss missing examples with the SLP, while preserving the existing blinded audit. '
        'Any new independent evaluation needs its own permissioned speakers, prompts and qualified judgments. '
        'Do not set a minimum clinical sample size from this table or relabel corpus ratings as produced-phone errors. '
        'ZH remains excluded from model output despite being present in the practice content.', '',
        'Machine-readable support, full published per-phone metrics (including average precision and event prevalence), '
        'and exact source/input identities are retained in the adjacent JSON.']
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists() and args.output.resolve().is_relative_to(HERE / 'outputs'),
            'Choose a fresh ignored output directory')
    result = build()
    args.output.mkdir(parents=True)
    (args.output / 'report.json').write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    (args.output / 'report.md').write_text(markdown(result))
    print(json.dumps({'complete': True, 'targets': len(result['targets']),
                      'reportSha256': digest(args.output / 'report.json')}))
