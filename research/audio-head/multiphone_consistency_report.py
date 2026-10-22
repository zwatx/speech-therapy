"""Describe all six verified consistency arms, without choosing a coefficient.

Only original clean audio has human ratings. Noisy predictions are paired
sensitivity measurements, never scored against those ratings.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import multiphone_consistency_queue as queue
from multiphone_cache import atomic_json, digest
from multiphone_child_train import score_predictions

trainer = queue.trainer
require, read_json = trainer.require, trainer.read_json
AGES = ('allAges', 'ages6to12')
PROBABILITIES = ('cleanProbabilities', 'noisyProbabilities',
                 'warmCleanProbabilities', 'warmNoisyProbabilities')


def checked_predictions(predictions, row_indices):
    require(predictions['rowIndices'] == row_indices and len(set(row_indices)) == len(row_indices)
            and predictions['noisyHumanLabelsAvailable'] is False, 'Prediction rows or label scope differ')
    arrays = {name: np.asarray(predictions[name], dtype=np.float64) for name in PROBABILITIES}
    require(all(value.shape == (len(row_indices), 3) and np.isfinite(value).all()
                and (value >= 0).all() and (value <= 1).all()
                and np.allclose(value.sum(1), 1, rtol=0, atol=1e-6)
                for value in arrays.values()), 'Invalid paired probability arrays')
    return arrays


def compact_metrics(evaluation):
    result = {}
    for age in AGES:
        value = evaluation[age]
        require(value is not None, 'Declared age slice is absent')
        ranking = value['targetDiscrimination']['macroTarget']
        result[age] = {key: value[key] for key in
            ('examples', 'speakers', 'observedRaterCounts', 'macroTargetPhones', 'macroTargetLogLoss', 'perRaterBrier')}
        result[age]['rating0'] = ranking['rating0']
        result[age]['ratingBelow2'] = ranking['ratingBelow2']
    return result


def comparison(current, reference):
    """Signed current-minus-reference differences; no winner or noisy accuracy."""
    result = {}
    for age in AGES:
        a, b = current['cleanMetrics'][age], reference['cleanMetrics'][age]
        require(all(a[key] == b[key] for key in
            ('examples', 'speakers', 'observedRaterCounts', 'macroTargetPhones')), 'Comparison support differs')
        row = {key: a[key] - b[key] for key in ('macroTargetLogLoss', 'perRaterBrier')}
        for event in ('rating0', 'ratingBelow2'):
            require(all(a[event][key] == b[event][key] for key in
                ('definedTargets', 'undefinedTargets', 'excludedPhones', 'prevalence')), 'Ranking support differs')
            row[event] = {key: a[event][key] - b[event][key]
                          if a[event][key] is not None and b[event][key] is not None else None
                          for key in ('auroc', 'averagePrecision')}
        for label in ('cleanToNoisy', 'warmCleanToStudentClean', 'warmCleanToStudentNoisy'):
            x, y = current['sensitivity'][age][label], reference['sensitivity'][age][label]
            require(x['targets'] == y['targets'], 'Sensitivity support differs')
            row[label] = {key: x[key] - y[key] for key in x if key != 'targets'}
        result[age] = row
    return result


def summarize(arms):
    require([(a['regime'], a['coefficient']) for a in arms] ==
            [(r, c) for r in trainer.REGIMES for c in trainer.COEFFICIENTS], 'All six fixed arms are required in order')
    baselines, comparisons = [], []
    for regime in trainer.REGIMES:
        selected = [a for a in arms if a['regime'] == regime]
        original = selected[0]['original']
        require(all(a['original'] == original for a in selected), 'Same-regime original model differs across arms')
        baselines.append({'regime': regime, 'epoch': 0, **original})
        for arm in selected:
            comparisons.append({'regime': regime, 'coefficient': arm['coefficient'],
                'againstOriginal': comparison(arm, original),
                'againstCoefficientZero': comparison(arm, selected[0])})
    return {'originalModels': baselines, 'arms': arms, 'comparisons': comparisons,
        'differenceDirection': 'current minus named reference', 'coefficientSelected': False,
        'confidenceIntervalsComputed': False, 'noisyHumanLabelsAvailable': False,
        **{key: False for key in trainer.FALSE_FLAGS},
        'limitations': [
            'Exploratory fold-zero inner validation already used for development and clean epoch selection.',
            'Only five children contribute the 545 child validation targets; target rows are not independent children.',
            'One deterministic 20 dB white-noise condition; no physical microphone or room evaluation.',
            'Distillation targets are fixed model probabilities, not new human annotations.',
            'Less sensitivity can preserve teacher mistakes or mask lost acoustic evidence; it is not noisy correctness.',
            'All six coefficients/population arms are retained, with no coefficient selection or outer inference.',
        ]}


def load_arms(plan, training, ledger):
    cohort = read_json(Path(training['inputFiles']['clean/cohort']['path']))
    result = []
    for job in ledger['jobs']:
        queue.guard_outputs(job)
        require(queue.verify_fitted(job, plan, training) == job['verified'], 'Fitted arm verification differs')
        require(queue.verify_replay(job) == job['replaySha256'], 'Pinned replay differs')
        directory = Path(job['output'])
        report = read_json(directory / 'report.json')
        indices = training['populations'][job['regime']]['validationRows']
        rows = [cohort['rows'][i] for i in indices]
        p = checked_predictions(read_json(directory / 'predictions.json'), indices)
        clean, noisy, warm, warm_noisy = (p[key] for key in PROBABILITIES)
        # Human labels are used only with the two original-audio probability sets.
        require(report['cleanEvaluation'] == score_predictions(clean, rows)
                and report['warmCleanEvaluation'] == score_predictions(warm, rows)
                and report['sensitivity'] == trainer.sensitivity(clean, noisy, warm, rows)
                and report['warmSensitivity'] == trainer.sensitivity(warm, warm_noisy, warm, rows),
                'Recorded clean metrics or paired sensitivity differ from saved predictions')
        result.append({'regime': job['regime'], 'coefficient': job['coefficient'],
            'bestEpoch': report['bestEpoch'], 'epochsRun': report['epochsRun'],
            'checkpointSha256': job['verified']['files']['best.pt'],
            'reportPath': str(directory / 'report.json'), 'reportSha256': job['verified']['files']['report.json'],
            'replaySha256': job['replaySha256'], 'exactReplayVerified': True,
            'cleanMetrics': compact_metrics(report['cleanEvaluation']),
            'sensitivity': report['sensitivity'],
            'original': {'cleanMetrics': compact_metrics(report['warmCleanEvaluation']),
                         'sensitivity': report['warmSensitivity']}})
    return result


def markdown(value):
    lines = ['# Fixed noise-consistency comparison', '',
        'All six arms completed separate exact checkpoint replay. Clean ratings are used only for original audio. '
        'No coefficient is selected and no noisy pronunciation accuracy is measured.', '',
        'Deltas in the JSON report are current minus original or coefficient-zero control. '
        'Smaller NLL/Brier means better corpus-rating fit; smaller probability movement alone is not better pronunciation judgment.', '']
    for regime in trainer.REGIMES:
        lines += ['## ' + regime, '',
            '| Model | Selected / run epochs | Clean child NLL | Clean child Brier | Child rating-0 AUROC | Child mean / max TV | All-age mean TV |',
            '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
        original = next(x for x in value['originalModels'] if x['regime'] == regime)
        choices = [('Original', '0', original)] + [
            (f"Coefficient {a['coefficient']:g}", f"{a['bestEpoch']} / {a['epochsRun']}", a)
            for a in value['arms'] if a['regime'] == regime]
        for name, epochs, item in choices:
            child = item['cleanMetrics']['ages6to12']
            drift = item['sensitivity']['ages6to12']['cleanToNoisy']
            auc = child['rating0']['auroc']
            auc_text = 'undefined' if auc is None else f'{auc:.6f}'
            lines.append(f"| {name} | {epochs} | {child['macroTargetLogLoss']:.6f} | {child['perRaterBrier']:.6f} | "
                         f"{auc_text} | {drift['meanTotalVariation']:.6f} / {drift['maxTotalVariation']:.6f} | "
                         f"{item['sensitivity']['allAges']['cleanToNoisy']['meanTotalVariation']:.6f} |")
        lines += ['', 'Full target/clip sensitivity, signed rating drift, confidence/entropy changes, '
                  'ranking denominators and matched-control differences are retained in `report.json`.', '']
    lines += ['## Limits', ''] + ['- ' + x for x in value['limitations']]
    return '\n'.join(lines) + '\n'


def build(ledger_path, ledger_sha, output):
    require(digest(ledger_path) == ledger_sha, 'Caller-pinned completed ledger differs')
    ledger = read_json(ledger_path)
    plan_path = Path(ledger['planPath'])
    plan = read_json(plan_path)
    require(ledger['complete'] is True and len(ledger['jobs']) == 6
            and ledger['contract'] == plan['contract'] and ledger_path.resolve() == Path(plan['base']) / 'queue-ledger.json',
            'Expected the complete declared six-arm queue')
    require([{k: j[k] for k in ('regime', 'coefficient', 'output')} for j in ledger['jobs']] ==
            [{k: j[k] for k in ('regime', 'coefficient', 'output')} for j in plan['jobs']], 'Ledger arm identities differ')
    require(not output.exists() and output.resolve().is_relative_to(trainer.HERE / 'outputs'), 'Choose fresh ignored report output')
    source_sha = digest(Path(__file__))
    training = queue.guard_plan(plan, plan_path, ledger['planSha256'])
    value = summarize(load_arms(plan, training, ledger))
    value.update(ledgerPath=str(ledger_path.resolve()), ledgerSha256=ledger_sha,
        planPath=str(plan_path), planSha256=ledger['planSha256'], sourceSha256=source_sha,
        queueContract=ledger['contract'], complete=True)
    content = markdown(value)
    queue.guard_plan(plan, plan_path, ledger['planSha256'])
    for job in ledger['jobs']:
        queue.guard_outputs(job)
    require(digest(ledger_path) == ledger_sha and digest(Path(__file__)) == source_sha,
            'Ledger or reporting source changed during summary')
    output.mkdir(parents=True, mode=0o700)
    (output / 'report.md').write_text(content)
    value['markdownSha256'] = digest(output / 'report.md')
    atomic_json(output / 'report.json', value)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--ledger-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.ledger, args.ledger_sha256, args.output)
    print(json.dumps({'complete': result['complete'], 'arms': len(result['arms']), 'coefficientSelected': False}))
