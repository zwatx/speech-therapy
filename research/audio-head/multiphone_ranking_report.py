"""Five fixed auxiliary-ranking arms and retained NLL controls; no new inference."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

import multiphone_consistency_replication_report as controls
from multiphone_cache import atomic_json, digest

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / '../../docs/model/multiphone-ranking-objective-protocol.md'
PROTOCOL_SHA = 'dc94968abf6497516e67cea3df764fe5d0c47c40c9005345336765dba8aad2ac'
CONTROL_READER_SHA = '296819b87f7bbc33b4dd77f322c32b8c2fc3eb7b54d9e72d84937e0bc37a4b4b'
SUPPORT = HERE / 'outputs/multiphone-20260926/pairwise-sampling-support-assessment-v1.json'
SUPPORT_SHA = 'cefb950e7cfddc80ca3de7bbbc1775240f3fbd31c199085668545cfbc60c7d92'
AGES = ('allAges', 'ages6to12', 'ages13plus')
require, read_json = controls.require, controls.read_json


def confidence(probabilities, rows):
    ages = np.asarray([row['age'] for row in rows])
    masks = {'allAges': np.ones(len(rows), bool), 'ages6to12': (ages >= 6) & (ages <= 12), 'ages13plus': ages >= 13}
    require(all(mask.any() for mask in masks.values()), 'Expected all three observed age slices')
    return {age: controls.profile(probabilities[mask]) for age, mask in masks.items()}


def checked_probabilities(values, count):
    p = np.asarray(values, dtype=np.float64)
    require(p.shape == (count, 3) and np.isfinite(p).all() and (p >= 0).all() and (p <= 1).all()
            and np.allclose(p.sum(1), 1, rtol=0, atol=1e-6), 'Invalid complete rating probabilities')
    return p


def metrics(evaluation, profile, age):
    value = evaluation[age]
    ranking = value['targetDiscrimination']['macroTarget']
    return {'macroNLL': value['macroTargetLogLoss'], 'perRaterNLL': value['perRaterLogLoss'],
        'perRaterBrier': value['perRaterBrier'], 'rating0AUROC': ranking['rating0']['auroc'],
        'rating0AP': ranking['rating0']['averagePrecision'], 'below2AUROC': ranking['ratingBelow2']['auroc'],
        'below2AP': ranking['ratingBelow2']['averagePrecision'],
        'meanClass0Probability': profile[age]['meanClassProbabilities'][0],
        'meanClass1Probability': profile[age]['meanClassProbabilities'][1],
        'meanClass2Probability': profile[age]['meanClassProbabilities'][2],
        'meanMaximumProbability': profile[age]['meanMaximumProbability'], 'meanEntropy': profile[age]['meanEntropy']}


def describe(arms):
    require([arm['fold'] for arm in arms] == list(range(5)), 'Exactly five ordered folds are required')
    summaries = {}
    for age in AGES:
        values = {name: [metrics(arm[name]['evaluation'], arm[name]['confidence'], age) for arm in arms]
                  for name in ('selected', 'control', 'original')}
        for arm in arms:
            a, b, c = (arm[name]['evaluation'][age] for name in ('selected', 'control', 'original'))
            require(all(a[k] == b[k] == c[k] for k in ('examples', 'speakers', 'observedRaterCounts', 'macroTargetPhones')),
                    'Comparison label or phone support differs')
            for event in ('rating0', 'ratingBelow2'):
                ranks = [v['targetDiscrimination']['macroTarget'][event] for v in (a, b, c)]
                require(all(ranks[0][k] == ranks[1][k] == ranks[2][k] for k in
                            ('definedTargets', 'undefinedTargets', 'excludedPhones')), 'Comparison ranking support differs')
        summaries[age] = {}
        for key in values['selected'][0]:
            cell = {name: controls.describe([v[key] for v in entries]) for name, entries in values.items()}
            for name in ('control', 'original'):
                cell['differenceVs' + name.title()] = controls.signed_difference(
                    [v[key] for v in values['selected']], [v[key] for v in values[name]])
            summaries[age][key] = cell
    return summaries


def control_record(record, pins):
    directory = Path(record['reportPath']).parent
    config, report = read_json(directory / 'config.json'), read_json(directory / 'report.json')
    predictions = read_json(directory / 'predictions.json')
    require(config['regime'] == 'child-only' and config['coefficient'] == 0
            and predictions['rowIndices'] == config['validationRows'], 'Retained control identity differs')
    for name in ('config.json', 'report.json', 'predictions.json', 'best.pt', 'replay.json'):
        pins[str((directory / name).resolve())] = digest(directory / name)
    return config, report, predictions


def checked_ranking(queue, ledger_path, expected_sha, retained, cohort, splits, pins):
    require(digest(ledger_path) == expected_sha, 'Caller-pinned ranking ledger differs')
    ledger = read_json(ledger_path)
    plan_path = Path(ledger['planPath']); plan = read_json(plan_path)
    require(ledger['complete'] is True and not ledger.get('failure') and ledger['contract'] == plan['contract'],
            'Ranking queue incomplete or changed')
    training = queue.guard_plan(plan, plan_path, ledger['planSha256'])
    require([(j['fold'], j['coefficient']) for j in ledger['jobs']] == [(f, .1) for f in range(5)]
            and [{k: j[k] for k in ('fold', 'coefficient', 'output')} for j in ledger['jobs']] ==
                [{k: j[k] for k in ('fold', 'coefficient', 'output')} for j in plan['jobs']], 'Ranking inventory differs')
    pins[str(ledger_path.resolve())] = expected_sha
    pins[str(plan_path.resolve())] = ledger['planSha256']
    arms = []
    for job in ledger['jobs']:
        queue.guard_outputs(job)
        require(queue.verify_fitted(job, plan, training) == job['verified']
                and queue.verify_replay(job) == job['replaySha256'], 'Ranking checkpoint or replay differs')
        directory = Path(job['output'])
        config, report, predictions = (read_json(directory / name) for name in ('config.json', 'report.json', 'predictions.json'))
        fold = job['fold']; control = retained[fold]
        control_config, control_report, control_predictions = control_record(control, pins)
        require(config['fold'] == report['fold'] == fold and config['coefficient'] == report['coefficient'] == .1
                and config['validationRows'] == splits['folds'][fold]['innerValidationRows']
                and all(config[k] == control_config[k] for k in ('fitRows', 'validationRows', 'selectionRows')),
                'Ranking and retained control populations differ')
        warm_pins = lambda c: {(str(Path(v['path']).resolve()), v['sha256'])
                              for k, v in c['inputFiles'].items() if k.startswith('warm/')}
        require(warm_pins(config) and warm_pins(config) == warm_pins(control_config)
                and {k: v for k, v in config['inputFiles'].items() if k.startswith('clean/')} ==
                    {k: v for k, v in control_config['inputFiles'].items() if k.startswith('clean/')},
                'Ranking and control warm-head or clean feature bindings differ')
        selected_checkpoint = torch.load(directory / 'best.pt', map_location='cpu', weights_only=True)
        control_checkpoint = torch.load(Path(control['reportPath']).parent / 'best.pt', map_location='cpu', weights_only=True)
        require(all(torch.equal(selected_checkpoint[k], control_checkpoint[k]) for k in ('mean', 'std')),
                'Ranking and control normalization differs')
        for name in ('cohort', 'splits'):
            a, b = config['inputFiles']['clean/' + name], control_config['inputFiles']['clean/' + name]
            require(a == b and digest(Path(a['path'])) == a['sha256'], 'Ranking cohort or split differs')
            pins[str(Path(a['path']).resolve())] = a['sha256']
        indices = config['validationRows']; rows = [cohort['rows'][i] for i in indices]
        require(predictions['rowIndices'] == indices, 'Ranking probability row identity differs')
        selected = checked_probabilities(predictions['probabilities'], len(rows))
        warm = checked_probabilities(predictions['warmProbabilities'], len(rows))
        control_p = checked_probabilities(control_predictions['cleanProbabilities'], len(rows))
        require(np.array_equal(warm, control_predictions['warmCleanProbabilities']), 'Original warm probabilities differ')
        evaluated = {name: controls.first_report.score_predictions(p, rows)
                     for name, p in (('selected', selected), ('control', control_p), ('original', warm))}
        require(evaluated['selected'] == report['evaluation'] and evaluated['original'] == report['warmEvaluation']
                and evaluated['control'] == control_report['cleanEvaluation']
                and evaluated['original'] == control_report['warmCleanEvaluation'], 'Ranking/control metrics differ from probabilities')
        profiles = {name: confidence(p, rows) for name, p in (('selected', selected), ('control', control_p), ('original', warm))}
        require(profiles['selected'] == report['confidence'] and profiles['original'] == report['warmConfidence'],
                'Ranking confidence diagnostics differ from saved probabilities')
        record = {'fold': fold, 'coefficient': .1,
            **{name: {'evaluation': evaluated[name], 'confidence': profiles[name]} for name in evaluated},
            'reportPath': str(directory / 'report.json'), 'reportSha256': job['verified']['files']['report.json'],
            'checkpointSha256': job['verified']['files']['best.pt'], 'replaySha256': job['replaySha256'],
            'bestEpoch': report['bestEpoch'], 'epochsRun': report['epochsRun'], 'exactReplayVerified': True,
            'controlReportPath': control['reportPath'], 'controlReportSha256': control['reportSha256'],
            'controlCheckpointSha256': control['checkpointSha256'], 'controlReplaySha256': control['replaySha256'],
            'controlBestEpoch': control['bestEpoch'], 'controlEpochsRun': control['epochsRun'],
            'historyPath': str(directory / 'history.json'), 'historySha256': job['verified']['files']['history.json']}
        arms.append(record)
    return arms, (queue, plan, plan_path, ledger)


def markdown(value):
    child = value['support']['ages6to12']; metrics_child = value['descriptiveSummaries']['ages6to12']
    lines = ['# Fixed child rating-ranking objective comparison', '',
        'Five new auxiliary-objective fits are compared with five retained ordinary-NLL continuation controls '
        'and their original warm heads. The architecture, warm model, supervised row order and stopping rule '
        'are matched; the pairwise objective and its fixed sampling distribution are the added treatment. '
        'No coefficient or ranking-best checkpoint is selected.', '',
        f"These overlapping inner folds contain {child['deduplicated']['speakers']} distinct children in "
        f"{child['foldMembershipSums']['speakers']} fold memberships. There are "
        f"{child['deduplicated']['targets']} unique target rows and {child['foldMembershipSums']['targets']} row memberships. "
        'Means below weight folds equally and have no independent-fold confidence interval.', '',
        '| Metric, clean child ratings | Original | NLL continuation | NLL + .1 ranking |',
        '| --- | ---: | ---: | ---: |']
    for key in metrics_child:
        fmt = lambda v: 'undefined' if v is None else f'{v:.6f}'
        cell = metrics_child[key]
        lines.append('| ' + key + ' | ' + ' | '.join(fmt(cell[name]['equalFoldMean']) for name in ('original', 'control', 'selected')) + ' |')
    lines += ['', '## Every fold retained', '',
        '| Fold | New selected / run epochs | Control selected / run epochs | Child NLL difference | Rating-0 AUROC difference | Below-2 AUROC difference |',
        '| ---: | --- | --- | ---: | ---: | ---: |']
    for arm in value['arms']:
        f = arm['fold']
        changes = [metrics_child[k]['differenceVsControl']['perFold'][f] for k in ('macroNLL', 'rating0AUROC', 'below2AUROC')]
        lines.append(f"| {f} | {arm['bestEpoch']} / {arm['epochsRun']} | {arm['controlBestEpoch']} / {arm['controlEpochsRun']} | "
                     + ' | '.join('undefined' if v is None else f'{v:+.6f}' for v in changes) + ' |')
    lines += ['', 'Differences are selected auxiliary model minus its same-fold NLL control. '
        'All phone-level proper/ranking metrics, undefined-event support, confidence profiles, selected '
        'checkpoint identities and diagnostic history paths remain in the JSON.', '',
        'The paired samples do not create independent speakers: 16 fitting phone/event cells have one '
        'positive child, and two have zero pair mass. A probability or ranking gain here would concern '
        'corpus ratings within used development data. It would not establish pronunciation correctness, '
        'calibration, clinical error recognition, thresholds, device robustness or suitability for ages 2–5. '
        'No final research bundle or learner feedback policy is changed.']
    return '\n'.join(lines) + '\n'


def build(first_ledger, replication_ledger, replication_sha, ranking_ledger, ranking_sha, output):
    import multiphone_consistency_replication_queue as replication_queue
    import multiphone_ranking_queue as ranking_queue
    require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Choose fresh ignored output')
    pins = {str(Path(__file__).resolve()): digest(Path(__file__)), str(PROTOCOL.resolve()): PROTOCOL_SHA,
            str(SUPPORT.resolve()): SUPPORT_SHA, str(Path(controls.__file__).resolve()): CONTROL_READER_SHA,
            str(Path(controls.first_report.__file__).resolve()): controls.FIRST_REPORT_SOURCE_SHA}
    require(all(digest(Path(p)) == h for p, h in pins.items()), 'Reviewed reporting input or helper changed')
    first, first_context, cohort, splits = controls.checked_queue(controls.first_report.queue,
        first_ledger, controls.FIRST_LEDGER_SHA, [0], pins)
    extra, extra_context, cohort2, splits2 = controls.checked_queue(replication_queue,
        replication_ledger, replication_sha, [1, 2, 3, 4], pins)
    require(cohort == cohort2 and splits == splits2, 'Control study populations differ')
    retained = {a['fold']: a for a in first + extra if a['regime'] == 'child-only' and a['coefficient'] == 0}
    require(sorted(retained) == list(range(5)), 'Exactly five retained child controls required')
    arms, ranking_context = checked_ranking(ranking_queue, ranking_ledger, ranking_sha, retained, cohort, splits, pins)
    value = {'complete': True, 'arms': arms, 'descriptiveSummaries': describe(arms),
        'support': controls.memberships(cohort, splits), 'pairSamplingSupport': read_json(SUPPORT),
        'sourceAndInputSha256': pins, 'inferencePerformed': False, 'trainingPerformed': False,
        'coefficientSelected': False, 'independentFoldConfidenceIntervalsComputed': False,
        'authorTestInferencePerformed': False, 'outerPerformanceEvaluationPerformed': False,
        'noisyAccuracyMeasured': False, 'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    require(value['support']['ages6to12']['deduplicated']['speakers'] == 27
            and value['support']['ages6to12']['foldMembershipSums']['speakers'] == 39, 'Child memberships changed')
    content = markdown(value)
    for module, plan, plan_path, ledger in (first_context, extra_context, ranking_context):
        module.guard_plan(plan, plan_path, ledger['planSha256'])
        require(ledger['contract'] == module.contract(), 'Queue contract changed during report')
        for job in ledger['jobs']:
            module.guard_outputs(job)
    require(all(digest(Path(p)) == h for p, h in pins.items()), 'Captured artifact or source changed during report')
    output.mkdir(parents=True, mode=0o700)
    (output / 'report.md').write_text(content)
    value['markdownSha256'] = digest(output / 'report.md')
    atomic_json(output / 'report.json', value)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('first-ledger', 'replication-ledger', 'ranking-ledger', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('replication-sha256', 'ranking-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    value = build(args.first_ledger, args.replication_ledger, args.replication_sha256,
                  args.ranking_ledger, args.ranking_sha256, args.output)
    print(json.dumps({'complete': value['complete'], 'newArms': len(value['arms'])}))
