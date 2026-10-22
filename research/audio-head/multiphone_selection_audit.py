"""Held-out-speaker development audit after all selection policies are frozen."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

import multiphone_ranking_train as ranking
from multiphone_cache import atomic_json, digest
from multiphone_child_train import score_predictions
from multiphone_data import TARGETS

PHONES = TARGETS[:23]
require = ranking.require


def check_partitions(rows, fit, validation, outer):
    groups = (fit, validation, outer)
    require(all(len(g) == len(set(g)) and g for g in groups), 'Empty or duplicate partition')
    require(all(type(i) is int and 0 <= i < len(rows) for g in groups for i in g), 'Invalid row index')
    speakers = [{rows[i]['speakerId'] for i in g} for g in groups]
    require(all(not speakers[i] & speakers[j] for i in range(3) for j in range(i)),
            'Fit, selection and audit speakers overlap')
    require(all(rows[i]['trainingEligible'] is True for g in groups for i in g), 'Ineligible cohort row')


def lexical_mask(rows, fit_rows):
    vocabulary = {r['targetWord'].upper() for r in fit_rows}
    require(vocabulary and all(isinstance(w, str) and w for w in vocabulary), 'Empty fitting vocabulary')
    return np.array([r['targetWord'].upper() in vocabulary for r in rows], dtype=bool)


def support(rows):
    per_phone = {}
    for phone in PHONES:
        selected = [r for r in rows if r['targetPhone'] == phone]
        counts = np.array([r['raterCounts'] for r in selected], dtype=int).reshape(-1, 3)
        per_phone[phone] = {
            'positions': len(selected), 'speakers': len({r['speakerId'] for r in selected}),
            'raterVotes': counts.sum(0).tolist(),
            'events': {event: {
                'positiveVotes': sum(sum(r['raterCounts'][:end]) for r in selected),
                'negativeVotes': sum(sum(r['raterCounts'][end:]) for r in selected),
                'positiveSpeakers': len({r['speakerId'] for r in selected if sum(r['raterCounts'][:end]) > 0}),
                'negativeSpeakers': len({r['speakerId'] for r in selected if sum(r['raterCounts'][end:]) > 0}),
            } for event, end in (('rating0', 1), ('ratingBelow2', 2))},
        }
    return {'positions': len(rows), 'speakers': len({r['speakerId'] for r in rows}),
            'recordings': len({r['clipId'] for r in rows}),
            'targetWords': len({r['targetWord'].upper() for r in rows}), 'perPhone': per_phone}


def summarize(probabilities, rows, seen):
    p = np.asarray(probabilities, dtype=np.float64)
    seen = np.asarray(seen, dtype=bool)
    require(p.shape == (len(rows), 3) and seen.shape == (len(rows),)
            and np.isfinite(p).all() and (p >= 0).all() and (p <= 1).all()
            and np.allclose(p.sum(1), 1., rtol=0, atol=2e-7), 'Invalid audit predictions')
    result = {}
    for name, mask in (('allWords', np.ones(len(rows), dtype=bool)), ('seenWords', seen), ('unseenWords', ~seen)):
        selected = [r for r, keep in zip(rows, mask, strict=True) if keep]
        metrics = score_predictions(p[mask], selected) if selected else {age: None for age in ('allAges', 'ages6to12', 'ages13plus')}
        for value in metrics.values():
            if value is not None:
                # Keep absent phones visible rather than silently shrinking the inventory.
                for phone in PHONES:
                    value['perTarget'].setdefault(phone, None)
                    value['targetDiscrimination']['perPhone'].setdefault(phone, None)
        age_support = {}
        for age, condition in (('allAges', lambda r: True), ('ages6to12', lambda r: 6 <= r['age'] <= 12),
                               ('ages13plus', lambda r: r['age'] >= 13)):
            age_support[age] = support([r for r in selected if condition(r)])
        result[name] = {'metrics': metrics, 'support': age_support,
                        'confidence': ranking.confidence(p[mask], selected)}
    return result


def child_scalars(summary):
    m = summary['allWords']['metrics']['ages6to12']
    require(m is not None, 'Child evaluation is required')
    d = m['targetDiscrimination']['macroTarget']
    return {'macroNLL': m['macroTargetLogLoss'], 'perRaterNLL': m['perRaterLogLoss'],
            'Brier': m['perRaterBrier'], 'rating0AP': d['rating0']['averagePrecision'],
            'rating0AUROC': d['rating0']['auroc'], 'below2AP': d['ratingBelow2']['averagePrecision'],
            'below2AUROC': d['ratingBelow2']['auroc']}


def contrast(ap_summary, nll_summary):
    a, n = child_scalars(ap_summary), child_scalars(nll_summary)
    return {k: a[k] - n[k] if a[k] is not None and n[k] is not None else None for k in a}


def pool_predictions(folds, expected_rows):
    """Merge one policy's outer folds; duplicates are never averaged away."""
    merged = {}
    for fold in folds:
        require(len(fold['rowIndices']) == len(fold['probabilities']) == len(fold['seenInFitVocabulary']),
                'Audit fold columns differ')
        for i, p, seen in zip(fold['rowIndices'], fold['probabilities'], fold['seenInFitVocabulary'], strict=True):
            require(i not in merged, 'Outer row predicted more than once')
            merged[i] = (p, seen)
    require(set(merged) == set(expected_rows), 'Outer predictions do not cover the cohort exactly')
    indices = sorted(merged)
    return {'rowIndices': indices, 'probabilities': [merged[i][0] for i in indices],
            'seenInFitVocabulary': [merged[i][1] for i in indices]}


def read_bound(binding):
    path = Path(binding['path'])
    require(digest(path) == binding['sha256'], 'Bound audit artifact changed')
    return ranking.read_json(path)


def binding(path):
    return {'path': str(path.resolve()), 'sha256': digest(path)}


def decision(contrasts):
    pooled = [v['pooled']['below2AP'] for v in contrasts.values()]
    folds = [f['below2AP'] for v in contrasts.values() for f in v['folds']]
    require(all(v is not None and np.isfinite(v) for v in pooled + folds), 'Primary contrast undefined')
    consistent = all(v > 1e-7 for v in pooled) and all(v >= -1e-7 for v in folds)
    return {'consistentDevelopmentRankingGain': consistent,
            'selectionPolicyLead': 'further-research-only' if consistent else 'closed-for-now-mixed-or-no-consistent-gain',
            'promotionEligible': False, 'properScoreTradeoffsMustBeRetained': True}


def audit(plan_path, plan_sha, frozen_path, frozen_sha, output):
    # Imported here so metric helpers remain independently testable.
    import multiphone_selection_train as train

    plan_path, frozen_path, output = Path(plan_path).resolve(), Path(frozen_path).resolve(), Path(output).resolve()
    require(not output.exists() and output.is_relative_to(ranking.HERE/'outputs'), 'Choose fresh audit output')
    plan = train.load_declaration(plan_path, plan_sha)
    frozen = train.validate_freeze(frozen_path, frozen_sha)
    require(frozen['declarationSha256'] == plan_sha and frozen['declarationPath'] == str(plan_path),
            'Frozen selections refer to another declaration')
    runs = {(r['fold'], r['coefficient']): read_bound(r) for r in frozen['runs']}
    require(set(runs) == {(fold, coefficient) for fold in range(5) for coefficient in (0., .1)},
            'Frozen selection matrix differs')
    source_sha = digest(Path(__file__))
    output.mkdir(parents=True, mode=0o700)
    atomic_json(output/'config.json', {
        'declaration': {'path': str(plan_path), 'sha256': plan_sha},
        'frozenSelections': {'path': str(frozen_path), 'sha256': frozen_sha},
        'sourceSha256': source_sha, 'startedAtUTC': datetime.now(timezone.utc).isoformat(),
        'authorPartition': 'train', 'previouslyUsedDevelopmentCohort': True,
        'authorTestInferencePerformed': False, 'learnerFeedbackEligible': False})
    config_binding = binding(output/'config.json')
    torch.set_num_threads(2)
    recipe = ranking.read_json(ranking.RECIPE)
    ranking.validate_recipe(recipe)
    predictions = {f'{c:g}/{rule}': [] for c in (0., .1) for rule in ('nll', 'ap')}
    fold_summaries = {key: [] for key in predictions}
    fold_bindings = []
    cohort = None
    for fold in range(5):
        data = ranking.load_data(fold, recipe, validation=False)
        cohort = data['cohort']
        outer = data['splits']['folds'][fold]['outerHoldoutRows']
        check_partitions(cohort['rows'], data['fit'], data['validation'], outer)
        rows = [cohort['rows'][i] for i in outer]
        seen = lexical_mask(rows, [cohort['rows'][i] for i in data['fit']])
        clean = (torch.from_numpy(data['values'][[data['positions'][i] for i in outer]].copy()) - data['mean']) / data['std']
        ids = torch.tensor([r['targetId'] for r in rows], dtype=torch.long)
        for coefficient in (0., .1):
            run = runs[(fold, coefficient)]
            config = read_bound(run['config'])
            require(config['fitRows'] == data['fit'] and config['validationRows'] == data['validation']
                    and config['outerRows'] == outer, 'Audit row membership differs from frozen fit')
            for rule in ('nll', 'ap'):
                selected = run['selections'][rule]
                checkpoint_path = Path(selected['checkpoint']['path'])
                require(digest(checkpoint_path) == selected['checkpoint']['sha256'], 'Selected checkpoint changed')
                saved = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
                require(saved['epoch'] == selected['epoch'] and saved['configSha256'] == run['config']['sha256']
                        and saved['declarationSha256'] == plan_sha
                        and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std']),
                        'Audit checkpoint lineage or fit-only normalization differs')
                network = ranking.model()
                network.load_state_dict(saved['model'], strict=True)
                p = ranking.predict(network, clean, ids)
                require(np.array_equal(p, ranking.predict(network, clean, ids)), 'Outer prediction replay differs')
                prediction = {'fold': fold, 'coefficient': coefficient, 'rule': rule, 'epoch': selected['epoch'],
                              'rowIndices': outer, 'probabilities': p.tolist(), 'seenInFitVocabulary': seen.tolist(),
                              'checkpoint': selected['checkpoint'], 'frozenSelectionsSha256': frozen_sha,
                              'exactRepeatedPrediction': True}
                key = f'{coefficient:g}/{rule}'
                predictions[key].append(prediction)
                summary = summarize(p, rows, seen)
                fold_summaries[key].append(summary)
                path = output/f'fold-{fold}-coefficient-{coefficient:g}-{rule}.json'
                atomic_json(path, {'prediction': prediction, 'summary': summary})
                fold_bindings.append(binding(path))
                print(f'Outer development audit fold={fold} coefficient={coefficient:g} rule={rule} epoch={selected["epoch"]}', flush=True)
    eligible = [i for i, row in enumerate(cohort['rows']) if row['trainingEligible']]
    require(len(eligible) == 14837 and {cohort['rows'][i]['targetPhone'] for i in eligible} == set(PHONES),
            'Unexpected eligible outer population')
    pooled = {}
    pooled_bindings = {}
    for key, folds in predictions.items():
        prediction = pool_predictions(folds, eligible)
        rows = [cohort['rows'][i] for i in prediction['rowIndices']]
        pooled[key] = summarize(prediction['probabilities'], rows, prediction['seenInFitVocabulary'])
        path = output/f'pooled-{key.replace("/", "-")}.json'
        atomic_json(path, prediction)
        pooled_bindings[key] = binding(path)
    contrasts = {}
    for coefficient in (0., .1):
        nll_key, ap_key = f'{coefficient:g}/nll', f'{coefficient:g}/ap'
        fold_contrasts = [contrast(a, n) for a, n in zip(fold_summaries[ap_key], fold_summaries[nll_key], strict=True)]
        contrasts[f'{coefficient:g}'] = {'pooled': contrast(pooled[ap_key], pooled[nll_key]),
            'folds': fold_contrasts,
            'descriptiveEqualFoldMean': {k: float(np.mean([f[k] for f in fold_contrasts]))
                if all(f[k] is not None for f in fold_contrasts) else None for k in fold_contrasts[0]}}
    train.load_declaration(plan_path, plan_sha)
    train.validate_freeze(frozen_path, frozen_sha)
    require(digest(Path(__file__)) == source_sha, 'Audit source changed while running')
    ranking.guard_files({str(i): b for i, b in enumerate([config_binding, *fold_bindings, *pooled_bindings.values()])})
    report = {'complete': True, 'config': config_binding, 'foldResults': fold_bindings,
              'pooledPredictions': pooled_bindings, 'pooled': pooled, 'childContrastsAPminusNLL': contrasts,
              'decision': decision(contrasts), 'primaryAggregation': 'pooled cross-fitted child macro-phone below2 AP',
              'evaluationScope': 'previously used author-training development cohort, same-fold speaker-disjoint',
              'authorTestInferencePerformed': False, 'learnerFeedbackEligible': False,
              'independentFinalValidation': False, 'completedAtUTC': datetime.now(timezone.utc).isoformat()}
    atomic_json(output/'report.json', report)
    write_report(report, output/'report.md')
    return binding(output/'report.json')


def write_report(report, path):
    lines = ['# Checkpoint selection development audit', '',
             'All ten six-epoch trajectories and twenty selections were frozen before this audit.',
             'Results are on previously used author-training development data, not an independent final cohort.', '',
             '| Objective / rule | Child macro NLL | Child Brier | Rating-0 AP | Below-2 AP |',
             '| --- | ---: | ---: | ---: | ---: |']
    for key, summary in report['pooled'].items():
        m = child_scalars(summary)
        lines.append(f'| {key} | {m["macroNLL"]:.6f} | {m["Brier"]:.6f} | {m["rating0AP"]:.6f} | {m["below2AP"]:.6f} |')
    lines += ['', 'Primary contrasts are AP-selected minus NLL-selected child below-2 AP, pooled across outer folds.', '',
              '| Auxiliary coefficient | Pooled contrast | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for key, value in report['childContrastsAPminusNLL'].items():
        values = [value['pooled']['below2AP']] + [f['below2AP'] for f in value['folds']]
        lines.append('| '+key+' | '+' | '.join(f'{v:+.6f}' for v in values)+' |')
    lines += ['', 'Decision: '+report['decision']['selectionPolicyLead']+'.', '',
              'The JSON report retains all age/word slices, all 23 phones, positive-vote and positive-speaker support,',
              'probability-score tradeoffs and bound prediction artifacts. Word slices use each fold’s child fitting vocabulary;',
              'they are not a word-disjoint evaluation. Fold training sets overlap. No independence-based intervals are claimed.',
              'Warm heads inherited previous NLL selection. Subjective five-rater labels are not clinical correctness.',
              'No author-test access, deployment promotion or learner judgments.']
    path.write_text('\n'.join(lines)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--freeze-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(audit(args.plan, args.plan_sha256, args.freeze, args.freeze_sha256, args.output))


if __name__ == '__main__': main()
