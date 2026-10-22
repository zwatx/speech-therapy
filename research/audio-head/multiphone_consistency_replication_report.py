"""Thirty fixed arms: descriptive per-fold replication, no coefficient selection."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

import multiphone_consistency_report as first_report
from multiphone_cache import atomic_json, digest

trainer = first_report.trainer
require, read_json = trainer.require, trainer.read_json
FIRST_LEDGER_SHA = '727e071a5276b7f0c6ab045ce4d92c349f95474ac48f742a387ba6c12b546000'
FIRST_REPORT_SOURCE_SHA = '9450f4fd3615019dea197682ad23d6695d22fd29500b40b09769aa3bd5ed784d'
PROTOCOL_SHA = '21fbf98b3d778ae333a87aab9ca17c8ee5a36b1d64a3dc5903c11aec0d15de87'
AGES = ('allAges', 'ages6to12')


def profile(probabilities):
    return {'targets': len(probabilities), 'meanClassProbabilities': probabilities.mean(0).tolist(),
        'argmaxCounts': np.bincount(probabilities.argmax(1), minlength=3).tolist(),
        'meanMaximumProbability': float(probabilities.max(1).mean()),
        'meanEntropy': float(-(probabilities * np.log(probabilities.clip(1e-12, 1))).sum(1).mean())}


def profiles(clean, noisy, rows):
    masks = {'allAges': np.ones(len(rows), dtype=bool),
             'ages6to12': np.array([6 <= row['age'] <= 12 for row in rows])}
    require(all(mask.any() for mask in masks.values()), 'Both declared age slices are required')
    return {age: {'clean': profile(clean[mask]), 'noisy': profile(noisy[mask])} for age, mask in masks.items()}


def metrics(record, age):
    clean = record['cleanMetrics'][age]
    noise = record['sensitivity'][age]['cleanToNoisy']
    confidence = record['profiles'][age]
    return {'cleanMacroNLL': clean['macroTargetLogLoss'], 'cleanPerRaterBrier': clean['perRaterBrier'],
        'cleanRating0AUROC': clean['rating0']['auroc'], 'cleanRating0AP': clean['rating0']['averagePrecision'],
        'cleanBelow2AUROC': clean['ratingBelow2']['auroc'], 'cleanBelow2AP': clean['ratingBelow2']['averagePrecision'],
        'meanNoiseTotalVariation': noise['meanTotalVariation'], 'maxNoiseTotalVariation': noise['maxTotalVariation'],
        'meanAbsoluteExpectedRatingShift': noise['meanAbsoluteExpectedRatingShift'],
        'cleanMeanClass0Probability': confidence['clean']['meanClassProbabilities'][0],
        'cleanMeanClass2Probability': confidence['clean']['meanClassProbabilities'][2],
        'cleanMeanEntropy': confidence['clean']['meanEntropy'],
        'noisyMeanClass0Probability': confidence['noisy']['meanClassProbabilities'][0],
        'noisyMeanClass2Probability': confidence['noisy']['meanClassProbabilities'][2],
        'noisyMeanEntropy': confidence['noisy']['meanEntropy']}


def describe(values):
    require(len(values) == 5, 'Five explicitly ordered fold values are required')
    if any(value is None for value in values):
        return {'perFold': values, 'equalFoldMean': None, 'undefinedFolds': [i for i, v in enumerate(values) if v is None]}
    require(all(np.isfinite(value) for value in values), 'Nonfinite descriptive value')
    return {'perFold': values, 'equalFoldMean': float(np.mean(values)), 'undefinedFolds': []}


def signed_difference(current, reference):
    values = [a - b if a is not None and b is not None else None for a, b in zip(current, reference, strict=True)]
    result = describe(values)
    result['directionCounts'] = {name: sum(value is not None and test(value) for value in values)
        for name, test in [('lower', lambda x: x < 0), ('equal', lambda x: x == 0), ('higher', lambda x: x > 0)]}
    return result


def summarize(arms):
    inventory = [(fold, regime, coefficient) for fold in range(5)
                 for regime in trainer.REGIMES for coefficient in trainer.COEFFICIENTS]
    require([(a['fold'], a['regime'], a['coefficient']) for a in arms] == inventory,
            'The original six and all 24 replication arms are required in fixed order')
    lookup = {(a['fold'], a['regime'], a['coefficient']): a for a in arms}
    for fold in range(5):
        for regime in trainer.REGIMES:
            control = lookup[fold, regime, 0.]
            for coefficient in trainer.COEFFICIENTS:
                arm = lookup[fold, regime, coefficient]
                require(arm['original'] == control['original'], 'A same-fold original differs across coefficients')
                # Checks that metric differences use exactly matching label/phone support.
                first_report.comparison(arm, control)
                first_report.comparison(arm, arm['original'])
    summaries = []
    for regime in trainer.REGIMES:
        for coefficient in trainer.COEFFICIENTS:
            record = {'regime': regime, 'coefficient': coefficient, 'ages': {}}
            for age in AGES:
                selected = [metrics(lookup[f, regime, coefficient], age) for f in range(5)]
                original = [metrics(lookup[f, regime, coefficient]['original'], age) for f in range(5)]
                control = [metrics(lookup[f, regime, 0.], age) for f in range(5)]
                record['ages'][age] = {key: {
                    'selected': describe([v[key] for v in selected]),
                    'original': describe([v[key] for v in original]),
                    'coefficientZero': describe([v[key] for v in control]),
                    'differenceVsOriginal': signed_difference([v[key] for v in selected], [v[key] for v in original]),
                    'differenceVsCoefficientZero': signed_difference([v[key] for v in selected], [v[key] for v in control])}
                    for key in selected[0]}
            summaries.append(record)
    return {'arms': arms, 'descriptiveSummaries': summaries,
        'aggregation': 'Equal mean of five fold-specific summaries; folds and participants overlap; no inferential interval.',
        'differenceConvention': 'Selected model minus same-fold named reference; lower/higher counts are descriptive only.',
        'coefficientSelected': False, 'independentFoldConfidenceIntervalsComputed': False,
        'noisyAccuracyMeasured': False, 'authorTestInferencePerformed': False,
        'outerModelPerformanceEvaluationPerformed': False, 'clinicalUseEligible': False, 'learnerFeedbackEligible': False}


def memberships(cohort, splits):
    require(cohort['authorPartition'] == splits['authorPartition'] == 'train', 'Wrong author partition')
    result = {}
    for age in AGES:
        by_fold = []
        union = set()
        for fold in range(5):
            indices = [i for i in splits['folds'][fold]['innerValidationRows']
                       if age == 'allAges' or 6 <= cohort['rows'][i]['age'] <= 12]
            require(len(indices) == len(set(indices)), 'Duplicate row within a fold')
            union.update(indices)
            rows = [cohort['rows'][i] for i in indices]
            by_fold.append({'fold': fold, 'targets': len(rows), 'clips': len({r['clipId'] for r in rows}),
                'speakers': len({r['speakerId'] for r in rows}),
                'phones': sorted({r['targetPhone'] for r in rows}),
                'raterCounts': np.asarray([r['raterCounts'] for r in rows], dtype=int).sum(0).tolist()})
        unique = [cohort['rows'][i] for i in sorted(union)]
        multiplicity = Counter()
        for fold in range(5):
            multiplicity.update({cohort['rows'][i]['speakerId'] for i in splits['folds'][fold]['innerValidationRows']
                if age == 'allAges' or 6 <= cohort['rows'][i]['age'] <= 12})
        result[age] = {'perFold': by_fold, 'deduplicated': {'targets': len(unique),
            'clips': len({r['clipId'] for r in unique}), 'speakers': len(multiplicity),
            'raterCounts': np.asarray([r['raterCounts'] for r in unique], dtype=int).sum(0).tolist()},
            'foldMembershipSums': {key: sum(f[key] for f in by_fold) for key in ('targets', 'clips', 'speakers')},
            'speakerFoldMembershipHistogram': dict(sorted(Counter(multiplicity.values()).items())),
            'independentFolds': False}
    return result


def checked_queue(module, ledger_path, expected_sha, expected_folds, pins):
    require(digest(ledger_path) == expected_sha, 'Caller-pinned completed ledger differs')
    ledger = read_json(ledger_path)
    plan_path = Path(ledger['planPath'])
    plan = read_json(plan_path)
    require(ledger['complete'] is True and not ledger.get('failure') and ledger['contract'] == plan['contract'],
            'Queue is incomplete or differs from its declaration')
    training = module.guard_plan(plan, plan_path, ledger['planSha256'])
    expected = [(fold, regime, coefficient) for fold in expected_folds
                for regime in trainer.REGIMES for coefficient in trainer.COEFFICIENTS]
    identity = lambda job: (job.get('fold', 0), job['regime'], job['coefficient'])
    require([identity(job) for job in ledger['jobs']] == expected
            and [{k: j[k] for k in ('regime', 'coefficient', 'output')} for j in ledger['jobs']] ==
                [{k: j[k] for k in ('regime', 'coefficient', 'output')} for j in plan['jobs']], 'Fixed queue inventory differs')
    pins[str(ledger_path.resolve())] = expected_sha
    pins[str(plan_path.resolve())] = ledger['planSha256']
    records = []
    for job in ledger['jobs']:
        module.guard_outputs(job)
        require(module.verify_fitted(job, plan, training) == job['verified'], 'Fitted verification differs')
        require(module.verify_replay(job) == job['replaySha256'], 'Exact replay binding differs')
        directory = Path(job['output'])
        config, report = read_json(directory / 'config.json'), read_json(directory / 'report.json')
        fold = job.get('fold', 0)
        require(config.get('fold', 0) == report.get('fold', 0) == fold, 'Fold identity differs')
        bindings = config['inputFiles']
        for name in ('clean/cohort', 'clean/splits'):
            item = bindings[name]
            require(str(Path(item['path']).resolve()) not in pins or pins[str(Path(item['path']).resolve())] == item['sha256'],
                    'Cohort or speaker maps differ between studies')
            require(digest(Path(item['path'])) == item['sha256'], 'Cohort or speaker map changed')
            pins[str(Path(item['path']).resolve())] = item['sha256']
        cohort, splits = (read_json(Path(bindings[name]['path'])) for name in ('clean/cohort', 'clean/splits'))
        indices = config['validationRows']
        require(indices == splits['folds'][fold]['innerValidationRows'], 'Wrong fold validation membership')
        rows = [cohort['rows'][i] for i in indices]
        p = first_report.checked_predictions(read_json(directory / 'predictions.json'), indices)
        clean, noisy, warm, warm_noisy = (p[name] for name in first_report.PROBABILITIES)
        require(report['cleanEvaluation'] == first_report.score_predictions(clean, rows)
                and report['warmCleanEvaluation'] == first_report.score_predictions(warm, rows)
                and report['sensitivity'] == trainer.sensitivity(clean, noisy, warm, rows)
                and report['warmSensitivity'] == trainer.sensitivity(warm, warm_noisy, warm, rows),
                'Recorded clean metrics or paired sensitivity differs')
        records.append({'fold': fold, 'regime': job['regime'], 'coefficient': job['coefficient'],
            'bestEpoch': report['bestEpoch'], 'epochsRun': report['epochsRun'], 'exactReplayVerified': True,
            'reportPath': str(directory / 'report.json'), 'reportSha256': job['verified']['files']['report.json'],
            'checkpointSha256': job['verified']['files']['best.pt'], 'replaySha256': job['replaySha256'],
            'cleanMetrics': first_report.compact_metrics(report['cleanEvaluation']), 'sensitivity': report['sensitivity'],
            'profiles': profiles(clean, noisy, rows),
            'original': {'cleanMetrics': first_report.compact_metrics(report['warmCleanEvaluation']),
                'sensitivity': report['warmSensitivity'], 'profiles': profiles(warm, warm_noisy, rows)}})
    return records, (module, plan, plan_path, ledger), cohort, splits


def markdown(value):
    lines = ['# Fixed five-fold consistency replication', '',
        'All 30 fixed arms are retained: six previously completed fold-zero arms and 24 additional fits. '
        'The extension was declared after seeing fold zero. No coefficient is selected.', '',
        'These are descriptive development results on overlapping inner validation sets. '
        'No noisy human labels, pronunciation accuracy, independent-fold intervals or new outer scores are supplied.', '']
    support = value['support']['ages6to12']
    lines += [f"Child support: {support['deduplicated']['speakers']} distinct children in "
        f"{support['foldMembershipSums']['speakers']} fold memberships; "
        f"{support['deduplicated']['targets']} distinct target rows versus "
        f"{support['foldMembershipSums']['targets']} repeated row memberships.", '']
    for regime in trainer.REGIMES:
        lines += ['## ' + regime, '', 'Equal-fold descriptive means on clean child ratings and paired noisy predictions:', '',
            '| Coefficient | Clean NLL | Clean Brier | Rating-0 AUROC | Mean noise TV | Clean mean P(class 2) |',
            '| ---: | ---: | ---: | ---: | ---: | ---: |']
        for item in value['descriptiveSummaries']:
            if item['regime'] != regime:
                continue
            age = item['ages']['ages6to12']
            values = [age[k]['selected']['equalFoldMean'] for k in
                ('cleanMacroNLL', 'cleanPerRaterBrier', 'cleanRating0AUROC', 'meanNoiseTotalVariation', 'cleanMeanClass2Probability')]
            lines.append(f"| {item['coefficient']:g} | " + ' | '.join('undefined' if x is None else f'{x:.6f}' for x in values) + ' |')
        lines += ['', 'Paired differences from coefficient zero, in fold order 0–4:', '',
            '| Coefficient | Clean child NLL differences | Mean noise TV differences | Rating-0 AUROC differences |',
            '| ---: | --- | --- | --- |']
        for item in value['descriptiveSummaries']:
            if item['regime'] != regime:
                continue
            age = item['ages']['ages6to12']
            differences = [age[k]['differenceVsCoefficientZero']['perFold'] for k in
                           ('cleanMacroNLL', 'meanNoiseTotalVariation', 'cleanRating0AUROC')]
            lines.append(f"| {item['coefficient']:g} | " + ' | '.join(
                ', '.join('undefined' if x is None else f'{x:+.6f}' for x in sequence) for sequence in differences) + ' |')
        lines += ['', 'The JSON preserves every original, selected epoch, per-fold denominator, ranking support, '
                  'confidence distribution, clean/noisy argmax count and target/clip sensitivity.', '']
    lines += ['## Interpretation limits', '',
        '- Lower NLL/Brier means better fit to the corpus ratings; lower noise movement alone is not successful error detection.',
        '- Zero argmax changes can occur when every row is assigned class 2; inspect class probabilities and rare-rating rankings together.',
        '- Ranking means average each fold’s defined-phone macro; phone support and inner participants overlap across folds.',
        '- One synthetic 20 dB condition, one seed, and already used development data do not establish hardware robustness or clinical validity.',
        '- Ages 2–5, verified child/SSD labels and a genuinely independent final cohort remain missing.']
    return '\n'.join(lines) + '\n'


def build(first_ledger, new_ledger, new_sha, output):
    import multiphone_consistency_replication_queue as replication_queue
    require(not output.exists() and output.resolve().is_relative_to(trainer.HERE / 'outputs'), 'Choose fresh ignored report output')
    protocol = trainer.HERE / '../../docs/model/multiphone-consistency-replication-protocol.md'
    require(digest(protocol) == PROTOCOL_SHA, 'Replication protocol changed')
    require(digest(Path(first_report.__file__)) == FIRST_REPORT_SOURCE_SHA, 'Reviewed original report helper changed')
    pins = {str(Path(__file__).resolve()): digest(Path(__file__)),
            str(Path(first_report.__file__).resolve()): digest(Path(first_report.__file__)),
            str(protocol.resolve()): PROTOCOL_SHA}
    first, first_context, cohort, splits = checked_queue(first_report.queue, first_ledger, FIRST_LEDGER_SHA, [0], pins)
    extra, extra_context, second_cohort, second_splits = checked_queue(replication_queue, new_ledger, new_sha, [1, 2, 3, 4], pins)
    require(cohort == second_cohort and splits == second_splits, 'Source populations differ')
    value = summarize(first + extra)
    value['support'] = memberships(cohort, splits)
    child_support = value['support']['ages6to12']
    require(child_support['deduplicated']['speakers'] == 27 and child_support['foldMembershipSums']['speakers'] == 39,
            'Declared child membership counts differ')
    value.update(complete=True, sourceAndInputSha256=pins, firstLedgerSha256=FIRST_LEDGER_SHA, replicationLedgerSha256=new_sha)
    content = markdown(value)
    for module, plan, plan_path, ledger in (first_context, extra_context):
        module.guard_plan(plan, plan_path, ledger['planSha256'])
        require(ledger['contract'] == module.contract(), 'Queue contract changed during reporting')
        for job in ledger['jobs']:
            module.guard_outputs(job)
    require(all(digest(Path(path)) == sha for path, sha in pins.items()), 'Report source or captured inputs changed')
    output.mkdir(parents=True, mode=0o700)
    (output / 'report.md').write_text(content)
    value['markdownSha256'] = digest(output / 'report.md')
    atomic_json(output / 'report.json', value)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-ledger', type=Path, required=True)
    parser.add_argument('--replication-ledger', type=Path, required=True)
    parser.add_argument('--replication-ledger-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = build(args.first_ledger, args.replication_ledger, args.replication_ledger_sha256, args.output)
    print(json.dumps({'complete': value['complete'], 'arms': len(value['arms']), 'coefficientSelected': False}))
