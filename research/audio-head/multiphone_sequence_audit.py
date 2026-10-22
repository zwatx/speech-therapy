"""Same-fold held-out development comparison after all sequence selections freeze."""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import torch
import multiphone_selection_audit as metrics
import multiphone_ranking_train as original
from multiphone_sequence_head import SequenceEvidenceHead

require = original.require


def decision(pooled, folds):
    keys = ('below2AP', 'rating0AP', 'macroNLL', 'Brier')
    require(len(folds) == 5 and all(type(pooled[k]) in (int, float) and np.isfinite(pooled[k]) for k in keys)
            and all(type(f['below2AP']) in (int, float) and np.isfinite(f['below2AP']) for f in folds),
            'Undefined primary decision metric')
    consistent = (pooled['below2AP'] > 1e-7 and all(f['below2AP'] >= -1e-7 for f in folds)
                  and pooled['rating0AP'] >= -1e-7 and pooled['macroNLL'] <= 1e-7 and pooled['Brier'] <= 1e-7)
    return dict(consistentDevelopmentGain=consistent,
                sequenceAugmentationLead='further-research-only' if consistent else 'mixed-or-no-consistent-gain',
                promotionEligible=False, featureInformationIsolatedFromCapacity=False)


def outer_values(data, sequence_matrix, feature_rows, outer):
    positions = {row: i for i, row in enumerate(feature_rows)}
    require(len(positions) == len(feature_rows) and set(positions) == set(data['positions']),
            'Sequence and acoustic row coverage differs')
    clean = (torch.from_numpy(data['values'][[data['positions'][i] for i in outer]].copy())
             - data['mean']) / data['std']
    sequence = (torch.from_numpy(sequence_matrix[[positions[i] for i in outer]].copy())
                - data['sequenceMean']) / data['sequenceStd']
    require(torch.isfinite(clean).all() and torch.isfinite(sequence).all(), 'Nonfinite outer features')
    return clean, torch.cat((clean, sequence), dim=1)


def checked_state(selected, manifest, declaration_sha, data, *, candidate):
    original.guard_files({'checkpoint': selected['checkpoint']})
    state = torch.load(selected['checkpoint']['path'], map_location='cpu', weights_only=True)
    require(state['epoch'] == selected['epoch'] and state['configSha256'] == manifest['config']['sha256']
            and state['declarationSha256'] == declaration_sha
            and torch.equal(state['mean'], data['mean']) and torch.equal(state['std'], data['std']),
            'Selected state lineage or acoustic fitting moments differ')
    if candidate:
        require(torch.equal(state['sequenceMean'], data['sequenceMean'])
                and torch.equal(state['sequenceStd'], data['sequenceStd']), 'Sequence fitting moments differ')
        network = SequenceEvidenceHead().eval()
    else:
        network = original.model()
    network.load_state_dict(state['model'], strict=True)
    return network


def audit(plan_path, plan_sha, frozen_path, frozen_sha, output):
    import multiphone_sequence_train as train
    plan_path, frozen_path, output = (Path(p).resolve() for p in (plan_path, frozen_path, output))
    require(not output.exists() and output.is_relative_to(original.HERE/'outputs'), 'Fresh ignored audit output required')
    torch.set_num_threads(2)
    plan = train.load_declaration(plan_path, plan_sha)
    frozen = train.validate_freeze(frozen_path, frozen_sha)
    require(frozen['declaration'] == dict(path=str(plan_path), sha256=plan_sha), 'Freeze declaration differs')
    runs = {r['fold']: train.read_bound(r) for r in frozen['runs']}
    controls = {r['fold']: train.read_bound(r) for r in frozen['controls']}
    require(set(runs) == set(controls) == set(range(5)), 'Incomplete frozen comparison')
    feature_report, matrix = train.load_features(plan['features']['path'], plan['features']['sha256'])
    output.mkdir(parents=True, mode=0o700)
    config = train.write_new(output/'config.json', dict(declaration=frozen['declaration'],
        freeze=dict(path=str(frozen_path), sha256=frozen_sha), source=train.binding(__file__),
        previouslyUsedDevelopmentCohort=True, independentFinalValidation=False,
        authorTestRead=False, learnerFeedbackEligible=False))
    fold_pins, predictions, summaries = [], {k: [] for k in ('control', 'sequence')}, {k: [] for k in ('control', 'sequence')}
    current = None
    try:
        for fold in range(5):
            current = fold
            data = original.load_data(fold, original.read_json(original.RECIPE), validation=False)
            data = train.prepare_data(data, matrix)
            cohort = data['cohort']
            outer = data['splits']['folds'][fold]['outerHoldoutRows']
            metrics.check_partitions(cohort['rows'], data['fit'], data['validation'], outer)
            rows = [cohort['rows'][i] for i in outer]
            seen = metrics.lexical_mask(rows, [cohort['rows'][i] for i in data['fit']])
            clean, augmented = outer_values(data, matrix, feature_report['rowIndices'], outer)
            ids = torch.tensor([r['targetId'] for r in rows], dtype=torch.long)
            for arm, manifest, values in (('control', controls[fold], clean), ('sequence', runs[fold], augmented)):
                candidate = arm == 'sequence'
                run_config = train.read_bound(manifest['config'])
                require(run_config['fold'] == fold and run_config['fitRows'] == data['fit']
                        and run_config['validationRows'] == data['validation'] and run_config['outerRows'] == outer,
                        'Frozen partition differs')
                selected = manifest['selection'] if candidate else manifest['selections']['nll']
                network = checked_state(selected, manifest, manifest['declaration']['sha256'], data, candidate=candidate)
                p = original.predict(network, values, ids)
                require(np.array_equal(p, original.predict(network, values, ids)), 'Outer prediction repeat differs')
                prediction = dict(fold=fold, arm=arm, epoch=selected['epoch'], rowIndices=outer,
                    probabilities=p.tolist(), seenInFitVocabulary=seen.tolist(), checkpoint=selected['checkpoint'],
                    frozenSelectionsSha256=frozen_sha, exactRepeatedPrediction=True)
                summary = metrics.summarize(p, rows, seen)
                predictions[arm].append(prediction); summaries[arm].append(summary)
                fold_pins.append(train.write_new(output/f'fold-{fold}-{arm}.json', dict(prediction=prediction, summary=summary)))
                print(f'Outer development fold={fold} arm={arm} selectedEpoch={selected["epoch"]}', flush=True)
        eligible = [i for i, r in enumerate(cohort['rows']) if r['trainingEligible']]
        require(len(eligible) == 14837 and {cohort['rows'][i]['targetPhone'] for i in eligible} == set(metrics.PHONES),
                'Eligible cross-fitted population differs')
        pooled, pooled_pins = {}, {}
        for arm in predictions:
            result = metrics.pool_predictions(predictions[arm], eligible)
            rows = [cohort['rows'][i] for i in result['rowIndices']]
            pooled[arm] = metrics.summarize(result['probabilities'], rows, result['seenInFitVocabulary'])
            pooled_pins[arm] = train.write_new(output/f'pooled-{arm}.json', result)
        contrast = metrics.contrast(pooled['sequence'], pooled['control'])
        fold_contrasts = [metrics.contrast(s, c) for s, c in zip(summaries['sequence'], summaries['control'], strict=True)]
        train.load_declaration(plan_path, plan_sha); train.validate_freeze(frozen_path, frozen_sha)
        original.guard_files({str(i): pin for i, pin in enumerate([config, *fold_pins, *pooled_pins.values()])})
        return train.write_new(output/'report.json', dict(complete=True, config=config, foldResults=fold_pins,
            pooledPredictions=pooled_pins, pooled=pooled, childContrastsSequenceMinusControl=dict(pooled=contrast, folds=fold_contrasts),
            decision=decision(contrast, fold_contrasts), independentFinalValidation=False,
            authorTestRead=False, learnerFeedbackEligible=False, clinicalUseEligible=False,
            primaryAggregation='pooled cross-fitted child macro-phone below-2 AP',
            evaluationScope='previously used author-training development cohort; same-fold speakers disjoint'))
    except Exception as error:
        train.write_new(output/'failure.json', dict(complete=False, fold=current,
            error=f'{type(error).__name__}: {error}', foldResults=fold_pins))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('plan', 'freeze', 'output'): parser.add_argument('--'+key, type=Path, required=True)
    for key in ('plan-sha256', 'freeze-sha256'): parser.add_argument('--'+key, required=True)
    args = parser.parse_args()
    print(audit(args.plan, args.plan_sha256, args.freeze, args.freeze_sha256, args.output))
