"""Verify and summarize completed inner-only local-window head trials."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from multiphone_cache import atomic_json, digest
from multiphone_local_head import score_predictions, selection_loss
from multiphone_local_head_queue import BASE, guard, verify_complete
from multiphone_local_train import choose_trial, read_json, replay_checkpoint, require


def fully_defined_mean(values):
    return float(np.mean(values)) if all(value is not None for value in values) else None


def scalar_reference(base, fold, binding, expected_rows):
    directory = base/'local-scalar'/f'fold-{fold}-inner'
    config = read_json(directory/'config.json')
    selection = read_json(directory/'selection.json')
    chosen = selection['selected']
    require(chosen == choose_trial(selection['trials']), 'Scalar selection differs from its declared rule')
    require(selection['complete'] is True and selection['phase'] == 'inner'
            and selection['configSha256'] == digest(directory/'config.json')
            and all(config['binding'][name] == binding[name] for name in
                    ('cohortSha256', 'splitsSha256', 'featuresSha256'))
            and config['validationRows'] == expected_rows, 'Scalar comparison data/splits differ')
    checkpoint, predictions_path = directory/chosen['checkpointPath'], directory/chosen['predictionsPath']
    require(digest(checkpoint) == chosen['checkpointSha256'] and digest(predictions_path) == chosen['predictionsSha256'],
            'Scalar reference artifact digest differs')
    predictions = replay_checkpoint(checkpoint, Path(binding['cohortPath']), Path(binding['splitsPath']),
                                    Path(binding['featuresPath']))
    require(predictions == read_json(predictions_path), 'Scalar checkpoint does not replay exactly')
    cohort = read_json(Path(binding['cohortPath']))
    fold_rows = read_json(Path(binding['splitsPath']))['folds'][fold]
    require(config['fitRows'] == fold_rows['innerFitRows'], 'Scalar reference does not use all-age inner fit')
    metrics = score_predictions(np.asarray(predictions['probabilities']),
                                [cohort['rows'][index] for index in predictions['rowIndices']])
    require(abs(metrics['allAges']['macroTargetLogLoss']-chosen['metrics']['macroTargetLogLoss']) < 1e-12,
            'Scalar recomputed macro loss differs')
    return {'alpha': chosen['alpha'], 'selectionRule': 'all-age inner-validation macro-phone NLL',
            'fitRegime': 'all-age', 'evaluation': metrics, 'configSha256': digest(directory/'config.json'),
            'selectionSha256': digest(directory/'selection.json'), 'checkpointSha256': digest(checkpoint),
            'predictionsSha256': digest(predictions_path), 'checkpointReplayExact': True}


def summarize(base: Path, output: Path):
    ledger_path = base/'local-head-queue-v1.json'
    ledger = read_json(ledger_path)
    require(ledger.get('complete') is True and len(ledger['jobs']) == 40
            and all(job['state'] == 'complete' and 'verified' in job for job in ledger['jobs']),
            'All forty verified trials are required')
    contract = ledger['contract']
    guard(contract)
    trials = []
    for job in ledger['jobs']:
        verified = verify_complete(job, contract)
        require(verified == job['verified'], 'Completed trial changed since queue verification')
        if job['fold'] == 0:
            replay_path = Path(job['output'])/'replay.json'
            replay = read_json(replay_path)
            require(job['replay']['state'] == 'complete' and digest(replay_path) == job['replay']['sha256']
                    and replay['maximumAbsoluteProbabilityDifference'] == 0.
                    and replay['checkpointSha256'] == verified['checkpointSha256'], 'Fold-zero replay binding differs')
        report = read_json(Path(job['output'])/'report.json')
        trials.append({key: job[key] for key in ('family', 'regime', 'fold', 'seed', 'lr', 'output')} | {
            'verified': verified, 'evaluation': report['evaluation'], 'prior': report['sameFitPriorEvaluation'],
            'elapsedSeconds': report['elapsedSeconds']})
    references, selected = {}, []
    for fold in range(5):
        for family in ('embedding', 'embedding-scalars'):
            for regime in ('all-age', 'child-only'):
                candidates = [row for row in trials if (row['fold'], row['family'], row['regime']) == (fold, family, regime)]
                require(len(candidates) == 2 and {row['lr'] for row in candidates} == {.001, .0003},
                        'Learning-rate candidates are incomplete')
                chosen = min(candidates, key=lambda row: (selection_loss(row['evaluation'], regime), row['lr']))
                if fold not in references:
                    config = read_json(Path(chosen['output'])/'config.json')
                    references[fold] = scalar_reference(base, fold, contract['binding'], config['validationRows'])
                loss, prior, scalar = [selection_loss(value, regime) for value in
                    (chosen['evaluation'], chosen['prior'], references[fold]['evaluation'])]
                selected.append(chosen | {'selectionMacroNLL': loss, 'sameFitPriorMacroNLL': prior,
                    'scalarSameAgeSliceMacroNLL': scalar, 'differenceVsSameFitPrior': loss-prior,
                    'differenceVsScalar': loss-scalar,
                    'selectionCriterion': 'child macro-phone NLL' if regime == 'child-only' else 'all-age macro-phone NLL'})
    groups = []
    for family in ('embedding', 'embedding-scalars'):
        for regime in ('all-age', 'child-only'):
            rows = [row for row in selected if row['family'] == family and row['regime'] == regime]
            groups.append({'family': family, 'regime': regime,
                'meanSelectionMacroNLL': float(np.mean([row['selectionMacroNLL'] for row in rows])),
                'meanSameFitPriorMacroNLL': float(np.mean([row['sameFitPriorMacroNLL'] for row in rows])),
                'meanScalarSameAgeSliceMacroNLL': float(np.mean([row['scalarSameAgeSliceMacroNLL'] for row in rows])),
                'foldsBeatingPrior': sum(row['differenceVsSameFitPrior'] < 0 for row in rows),
                'foldsBeatingScalar': sum(row['differenceVsScalar'] < 0 for row in rows),
                'meanChildMacroNLL': float(np.mean([row['evaluation']['ages6to12']['macroTargetLogLoss'] for row in rows])),
                'meanChildRating0AUROC': fully_defined_mean([row['evaluation']['ages6to12']['discrimination']['rating0']['auroc'] for row in rows]),
                'meanChildBelow2AUROC': fully_defined_mean([row['evaluation']['ages6to12']['discrimination']['ratingBelow2']['auroc'] for row in rows]),
                'meanChildWithinPhoneRating0AUROC': fully_defined_mean([row['evaluation']['ages6to12']['targetDiscrimination']['macroTarget']['rating0']['auroc'] for row in rows]),
                'meanScalarChildWithinPhoneRating0AUROC': fully_defined_mean([references[row['fold']]['evaluation']['ages6to12']['targetDiscrimination']['macroTarget']['rating0']['auroc'] for row in rows]),
                'meanChildWithinPhoneBelow2AUROC': fully_defined_mean([row['evaluation']['ages6to12']['targetDiscrimination']['macroTarget']['ratingBelow2']['auroc'] for row in rows]),
                'meanScalarChildWithinPhoneBelow2AUROC': fully_defined_mean([references[row['fold']]['evaluation']['ages6to12']['targetDiscrimination']['macroTarget']['ratingBelow2']['auroc'] for row in rows]),
                'meanChildWithinPhoneRating0AveragePrecision': fully_defined_mean([row['evaluation']['ages6to12']['targetDiscrimination']['macroTarget']['rating0']['averagePrecision'] for row in rows]),
                'meanScalarChildWithinPhoneRating0AveragePrecision': fully_defined_mean([references[row['fold']]['evaluation']['ages6to12']['targetDiscrimination']['macroTarget']['rating0']['averagePrecision'] for row in rows]),
                'selectedLearningRatesByFold': [row['lr'] for row in rows]})
    result = {'complete': True, 'phase': 'inner', 'trials': 40, 'selectedConfigurations': selected,
              'aggregate': groups, 'scalarReferences': references, 'foldZeroExactReplays': 8,
              'sourceSha256': digest(Path(__file__)), 'queueLedgerSha256': digest(ledger_path),
              'contract': contract, 'queueWallSeconds': ledger['finishedAt']-ledger['startedAt'],
              'summedFitElapsedSeconds': sum(row['elapsedSeconds'] for row in trials),
              'selectionRule': 'Per family/regime/fold lowest declared inner metric; exact LR ties prefer0.0003',
              'aggregationRule': 'Unweighted descriptive mean across five overlapping inner-validation folds; not independent test estimates',
              'scalarComparisonLimitation': 'Scalar baseline was fitted and selected with all ages. Child-only comparison reports its child slice without child reselection; this differs in both fitting population and selection criterion.',
              'timingLimitation': 'Forced occupancy/context windows are unreviewed; contextual WavLM also encodes surrounding utterance. No produced-phone or clinical validation.',
              'outerOutcomesUsed': False, 'authorTestInferencePerformed': False,
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    guard(contract)
    require(not output.exists() and not output.with_suffix('.md').exists(), 'Choose new report output paths')
    atomic_json(output, result)
    lines = ['# Estimated local WavLM heads: inner-only results', '',
        'All 40 declared CPU trials completed; all eight fold-zero selected checkpoints replayed exactly. '
        'Learning rates were selected separately within each family, regime and fold. Lower NLL is better.', '',
        '| Inputs | Fit / selection | Mean selected NLL | Same-fit prior | Scalar same-age slice | Wins vs prior / scalar |',
        '|---|---|---:|---:|---:|---:|']
    for row in groups:
        lines.append(f"| {row['family']} | {row['regime']} | {row['meanSelectionMacroNLL']:.5f} | {row['meanSameFitPriorMacroNLL']:.5f} | {row['meanScalarSameAgeSliceMacroNLL']:.5f} | {row['foldsBeatingPrior']}/5; {row['foldsBeatingScalar']}/5 |")
    lines += ['', 'All-age rows select all-age macro-phone NLL. Child-only rows fit ages 6–12 and select child macro-phone NLL. '
        'The scalar model fits and selects all ages; its child slice is descriptive, without child reselection. '
        'Five-fold means summarize overlapping inner-validation cohorts, not independent test performance.', '',
        'Child probability fit and within-phone ranking must be assessed separately. '
        'For example, the combined child-only head improves mean child NLL while its mean within-phone rating-0 AUROC is lower than the scalar reference. '
        'These AUROCs average only phones with defined positive/negative support within each fold; excluded phone cells remain explicit in JSON. Higher AUROC is better.', '',
        '| Inputs | Regime | Child within-phone rating-0 AUROC | Scalar reference | Child within-phone below-2 AUROC | Scalar reference |',
        '|---|---|---:|---:|---:|---:|']
    for row in groups:
        lines.append(f"| {row['family']} | {row['regime']} | {row['meanChildWithinPhoneRating0AUROC']:.5f} | {row['meanScalarChildWithinPhoneRating0AUROC']:.5f} | {row['meanChildWithinPhoneBelow2AUROC']:.5f} | {row['meanScalarChildWithinPhoneBelow2AUROC']:.5f} |")
    lines += ['',
        '| Fold | Inputs | Regime | Selected LR | Epoch | Selected NLL | Prior NLL | Scalar slice NLL |',
        '|---:|---|---|---:|---:|---:|---:|---:|']
    for row in selected:
        lines.append(f"| {row['fold']} | {row['family']} | {row['regime']} | {row['lr']} | {row['verified']['bestEpoch']} | {row['selectionMacroNLL']:.5f} | {row['sameFitPriorMacroNLL']:.5f} | {row['scalarSameAgeSliceMacroNLL']:.5f} |")
    lines += ['', 'Detailed age-specific proper scores, rating-ranking metrics, class/phone support, undefined cells and artifact hashes are retained in the JSON report and individual trial reports. '
        'No outer or author-test evaluation was performed. Ages 2–5 are absent. Estimated windows and rating predictions are not clinical pronunciation validation.', '',
        f"Queue wall time: {result['queueWallSeconds']:.1f} seconds; summed fit elapsed time: {result['summedFitElapsedSeconds']:.1f} seconds.", '']
    output.with_suffix('.md').write_text('\n'.join(lines))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary = summarize(args.base, args.output)
    print(json.dumps({'aggregate': summary['aggregate'], 'queueWallSeconds': summary['queueWallSeconds']}), flush=True)
