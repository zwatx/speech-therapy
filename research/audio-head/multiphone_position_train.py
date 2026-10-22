"""Fixed original-row versus all-position refits and separate frozen audit."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

import multiphone_head_outer as outer
import multiphone_local_head as head
import multiphone_position_phonetic as features
import multiphone_selection_audit as metrics
from multiphone_child_train import fit_priors, is_child
from multiphone_sequence_preflight import binding, guard, read_bound, require, write_new

HERE = Path(__file__).resolve().parent
BASE = HERE/'outputs/multiphone-20260926'
PROTOCOL = HERE/'../../docs/model/multiphone-position-training-protocol.md'
REGIMES = ('all-age', 'child-only')
ARMS = ('original', 'expanded')
SETTINGS = {'all-age': [(0.0003, n) for n in (5, 3, 4, 4, 3)],
            'child-only': list(zip((0.0003, 0.001, 0.0003, 0.001, 0.001), (5, 3, 7, 3, 2), strict=True))}


def partitions(cohort, splits, config, arm):
    rows = cohort['rows']; fold = splits['folds'][config['fold']]
    legacy = {r['legacyRowIndex']: i for i, r in enumerate(rows) if r['legacyRowIndex'] is not None}
    candidates = [i for i in fold['outerFitRows'] if config['regime'] == 'all-age' or is_child(rows[i])]
    original = [legacy[i] for i in config['fitRows']]
    require(set(original) == {i for i in candidates if rows[i]['legacyRowIndex'] is not None}, 'Historical fit membership differs')
    fit = original if arm == 'original' else candidates
    held = fold['outerHoldoutRows']
    require(arm in ARMS and fit and held and len(fit) == len(set(fit)) and len(held) == len(set(held))
            and not set(fit).intersection(held)
            and not {rows[i]['speakerId'] for i in fit}.intersection(rows[i]['speakerId'] for i in held),
            'Fit/holdout overlap or duplicate membership')
    return fit, held, original


def prepare(cohort, values, fit):
    fit_values = np.asarray(values[fit], dtype=np.float64)
    mean, std = fit_values.mean(0), fit_values.std(0)
    std = np.where(std < 1e-6, 1., std)
    require(np.isfinite(mean).all() and np.isfinite(std).all(), 'Invalid fit moments')
    return dict(cohort=cohort, values=values, positions={i: i for i in range(len(values))}, fit=fit,
                mean=torch.tensor(mean, dtype=torch.float32), std=torch.tensor(std, dtype=torch.float32),
                priors=fit_priors([cohort['rows'][i] for i in fit]))


def inputs(feature_path, feature_sha):
    pins = {'features': binding(feature_path, feature_sha),
            'release': binding(BASE/'outer-release-v1.json', '971bbc06a79847a69042b88abc750240b4b13917016ace4ee7a568807a6b0843')}
    report = read_bound(pins['features']); release = read_bound(pins['release'])
    require(report['complete'] is True and report['legacyParity'] == 14837 and report['positions'] == 28227
            and report['learnerFeedbackEligible'] is False and report['trainingPerformed'] is False,
            'Complete reviewed position features required')
    pins.update({'featureInput/'+k: v for k, v in report['inputs'].items()})
    pins.update({'matrix/'+k: v for k, v in report['matrices'].items()})
    for cid, artifact in report['clipArtifacts'].items():
        for kind in ('entry', 'vectors'): pins['featureUnit/'+cid+'/'+kind] = artifact[kind]
    for kind in ('entry', 'vectors'): pins['featureRepeat/'+kind] = report['repeat'][kind]
    cohort = read_bound(report['inputs']['cohort']); splits = read_bound(report['inputs']['splits'])
    require(report['rowIds'] == [r['id'] for r in cohort['rows']] and cohort['authorPartition'] == splits['authorPartition'] == 'train',
            'Feature/cohort row order differs')
    jobs = []
    for regime in REGIMES:
        for fold in range(5):
            name = f'phonetic-target-scalars-{regime}-f{fold}-refit'
            directory = BASE/'head-outer'/name
            historical = {}
            for filename in ('config.json', 'frozen.json', 'checkpoint.pt', 'history.json'):
                path = directory/filename
                historical[filename] = binding(path, release['filesSha256'][str(path)])
                pins[name+'/'+filename] = historical[filename]
            config = read_bound(historical['config.json']); frozen = read_bound(historical['frozen.json'])
            require(config['kind'] == 'phonetic' and config['family'] == 'target-scalars' and config['regime'] == regime
                    and config['fold'] == fold and (config['learningRate'], config['fixedEpochs']) == SETTINGS[regime][fold]
                    and frozen['complete'] is True and frozen['configSha256'] == historical['config.json']['sha256']
                    and frozen['checkpointSha256'] == historical['checkpoint.pt']['sha256']
                    and frozen['historySha256'] == historical['history.json']['sha256'], 'Historical settings or freeze differs')
            inner = Path(config['innerConfigPath'])
            pins[name+'/innerConfig'] = binding(inner, config['innerArtifactsSha256'][str(inner)])
            original = read_bound(pins[name+'/innerConfig'])
            expected = dict(hidden=128, dropout=0.1, weight_decay=0.01, batch_size=64, seed=7, device='cpu', threads=2)
            require(all(original[k] == v for k, v in expected.items()), 'Head architecture/runtime differs')
            for arm in ARMS:
                fit, held, lexical = partitions(cohort, splits, config, arm)
                jobs.append(dict(id=f'{regime}-{arm}-f{fold}', regime=regime, arm=arm, fold=fold,
                    args={**expected, 'lr': config['learningRate']}, epochs=config['fixedEpochs'], fitRows=fit,
                    holdoutRows=held, commonVocabularyFitRows=lexical, historical=historical))
    # Snapshot all local Python sources, including transitive metric imports.
    for path in sorted(HERE.glob('*.py')): pins['source/'+path.name] = binding(path)
    pins['protocol'] = binding(PROTOCOL); pins['runtime/python'] = binding(__import__('sys').executable)
    guard(pins)
    return pins, jobs


def declare(feature_path, feature_sha, output):
    root = Path(output).resolve()
    require(root.is_relative_to(HERE/'outputs') and not root.exists(), 'Fresh ignored output required')
    pins, jobs = inputs(feature_path, feature_sha)
    root.mkdir(mode=0o700)
    return write_new(root/'plan.json', dict(inputs=pins, jobs=jobs, runtime=features.runtime(),
        declaredAt=datetime.now(timezone.utc).isoformat(), previouslyUsedDevelopmentCohort=True,
        authorTestRead=False, learnerFeedbackEligible=False, trainingPerformed=False))


def load_plan(path, sha):
    pin = binding(path, sha); plan = read_bound(pin)
    require(Path(pin['path']).is_relative_to(HERE/'outputs'), 'Plan outside ignored outputs')
    source = plan['inputs']['features']; pins, jobs = inputs(source['path'], source['sha256'])
    require(plan['inputs'] == pins and plan['jobs'] == jobs and plan['runtime'] == features.runtime()
            and plan['trainingPerformed'] is False, 'Training declaration differs')
    return plan, pin


def load_data(plan):
    report = read_bound(plan['inputs']['features'])
    cohort = read_bound(report['inputs']['cohort'])
    values = features.checked_array(report['matrices']['combined'], (28227, 1037))
    return cohort, values


def historical_parity(job, data, model, history):
    previous = torch.load(job['historical']['checkpoint.pt']['path'], map_location='cpu', weights_only=True)
    require(torch.equal(previous['mean'], data['mean']) and torch.equal(previous['std'], data['std'])
            and read_bound(job['historical']['history.json']) == history
            and set(previous['model']) == set(model.state_dict())
            and all(torch.equal(v, previous['model'][k]) for k, v in model.state_dict().items()),
            'Original-row historical refit parity failed')


def run(path, sha):
    torch.set_num_threads(2)
    plan, pin = load_plan(path, sha); root = Path(pin['path']).parent
    write_new(root/'started.json', dict(plan=pin))
    runs = []
    try:
        cohort, values = load_data(plan)
        for job in plan['jobs']:
            directory = root/job['id']; directory.mkdir(mode=0o700)
            data = prepare(cohort, values, job['fitRows'])
            config = write_new(directory/'config.json', dict(plan=pin, job=job, prior=data['priors']))
            def progress(history):
                print(json.dumps(dict(run=job['id'], epoch=len(history), epochs=job['epochs'])), flush=True)
            model, history = outer.fit_epochs(SimpleNamespace(**job['args']), data, job['epochs'], progress)
            if job['arm'] == 'original': historical_parity(job, data, model, history)
            checkpoint = directory/'checkpoint.pt'
            torch.save(dict(model=model.state_dict(), mean=data['mean'], std=data['std'], epoch=job['epochs'],
                            configSha256=config['sha256'], planSha256=pin['sha256']), checkpoint)
            state = torch.load(checkpoint, map_location='cpu', weights_only=True)
            require(all(torch.equal(v, state['model'][k]) for k, v in model.state_dict().items()), 'Saved model differs')
            history_pin = write_new(directory/'history.json', history)
            runs.append(write_new(directory/'frozen.json', dict(complete=True, id=job['id'], config=config,
                checkpoint=binding(checkpoint), history=history_pin, epochs=job['epochs'],
                exactHistoricalParity=job['arm'] == 'original', holdoutPredictionsComputed=False)))
        guard(plan['inputs'])
        return write_new(root/'freeze.json', dict(complete=True, plan=pin, runs=runs, holdoutPredictionsComputed=False))
    except Exception as error:
        write_new(root/'failure.json', dict(errorType=type(error).__name__, message=str(error), completedRuns=runs))
        raise


@torch.inference_mode()
def predict(model, data, indices):
    model.eval(); result = []
    for start in range(0, len(indices), 64):
        values, phones, mask, _ = head.batch(data, indices[start:start+64], 'cpu')
        result.extend(model(values, mask, phones, mask)[:, 0].softmax(-1).cpu().numpy())
    return np.asarray(result, dtype=np.float64)


def populations(rows):
    old = np.array([r['legacyRowIndex'] is not None for r in rows], dtype=bool)
    return {'original': old, 'all': np.ones(len(rows), dtype=bool), 'added': ~old}


def summaries(prediction, cohort, probabilities=None):
    rows = [cohort['rows'][i] for i in prediction['rowIndices']]
    values = np.array(prediction['probabilities'] if probabilities is None else probabilities)
    seen = np.array(prediction['seenInFitVocabulary'], dtype=bool)
    return {name: metrics.summarize(values[mask], [r for r, keep in zip(rows, mask, strict=True) if keep], seen[mask])
            for name, mask in populations(rows).items()}


def decision(contrasts):
    passed = True
    for population in ('original', 'all'):
        item = contrasts[population]; p = item['pooled']; folds = item['folds']
        required = [p[k] for k in ('below2AP', 'rating0AP', 'macroNLL', 'Brier')] + [f['below2AP'] for f in folds]
        defined = len(folds) == 5 and all(v is not None and np.isfinite(v) for v in required)
        passed &= defined and p['below2AP'] > 1e-7 and p['rating0AP'] >= -1e-7 and p['macroNLL'] <= 1e-7 and p['Brier'] <= 1e-7 and all(f['below2AP'] >= -1e-7 for f in folds)
    return dict(consistentDevelopmentGain=bool(passed), promotionEligible=False,
                interpretation='further-research-only' if passed else 'mixed-or-no-consistent-gain')


def audit(path, sha, freeze_path, freeze_sha, output):
    torch.set_num_threads(2)
    plan, pin = load_plan(path, sha)
    freeze_pin = binding(freeze_path, freeze_sha); frozen = read_bound(freeze_pin)
    require(frozen['complete'] is True and frozen['plan'] == pin and frozen['holdoutPredictionsComputed'] is False
            and len(frozen['runs']) == 20, 'Complete twenty-run freeze required')
    saved_runs = [read_bound(p) for p in frozen['runs']]
    require([r['id'] for r in saved_runs] == [j['id'] for j in plan['jobs']], 'Frozen job matrix differs')
    root = Path(output).resolve()
    require(root.is_relative_to(HERE/'outputs') and not root.exists(), 'Fresh ignored audit output required')
    root.mkdir(mode=0o700)
    write_new(root/'config.json', dict(plan=pin, freeze=freeze_pin, authorTestRead=False,
              learnerFeedbackEligible=False, previouslyUsedDevelopmentCohort=True))
    cohort, values = load_data(plan)
    predictions, results, artifact_pins = defaultdict(list), defaultdict(list), []
    try:
        for job, frozen_run in zip(plan['jobs'], saved_runs, strict=True):
            config = read_bound(frozen_run['config'])
            require(config['plan'] == pin and config['job'] == job and frozen_run['holdoutPredictionsComputed'] is False,
                    'Frozen run config differs')
            guard({k: frozen_run[k] for k in ('checkpoint', 'history')})
            history = read_bound(frozen_run['history'])
            require(len(history) == frozen_run['epochs'] == job['epochs'], 'Fixed epoch count differs')
            data = prepare(cohort, values, job['fitRows'])
            require(config['prior'] == data['priors'], 'Fit-only prior differs')
            state = torch.load(frozen_run['checkpoint']['path'], map_location='cpu', weights_only=True)
            require(state['configSha256'] == frozen_run['config']['sha256'] and state['planSha256'] == pin['sha256']
                    and state['epoch'] == job['epochs'] and torch.equal(state['mean'], data['mean'])
                    and torch.equal(state['std'], data['std']), 'Saved checkpoint lineage/moments differ')
            model = head.make_model(SimpleNamespace(**job['args']), 1037); model.load_state_dict(state['model'], strict=True)
            if job['arm'] == 'original': historical_parity(job, data, model, history)
            held = job['holdoutRows']; rows = [cohort['rows'][i] for i in held]
            p = predict(model, data, held)
            require(np.array_equal(p, predict(model, data, held)), 'Repeated held-out prediction differs')
            common = metrics.lexical_mask(rows, [cohort['rows'][i] for i in job['commonVocabularyFitRows']])
            actual = metrics.lexical_mask(rows, [cohort['rows'][i] for i in job['fitRows']])
            prior = np.asarray([data['priors'][r['targetPhone']]['probabilities'] for r in rows])
            prediction = dict(rowIndices=held, probabilities=p.tolist(), seenInFitVocabulary=common.tolist(),
                              seenInActualFitVocabulary=actual.tolist(), priorProbabilities=prior.tolist(), checkpoint=frozen_run['checkpoint'])
            summary = summaries(prediction, cohort); prior_summary = summaries(prediction, cohort, prior)
            key = job['regime']+'/'+job['arm']; predictions[key].append(prediction); results[key].append(summary)
            artifact_pins.append(write_new(root/(job['id']+'.json'), dict(job=job['id'], prediction=prediction,
                                              summary=summary, priorSummary=prior_summary)))
            print(json.dumps(dict(audited=job['id'])), flush=True)
        pooled, pooled_pins = {}, {}
        for key, folds in predictions.items():
            prediction = metrics.pool_predictions(folds, list(range(28227)))
            pooled[key] = summaries(prediction, cohort)
            prior_folds = [{**f, 'probabilities': f['priorProbabilities']} for f in folds]
            prior_prediction = metrics.pool_predictions(prior_folds, list(range(28227)))
            pooled_pins[key] = write_new(root/(key.replace('/', '-')+'-pooled.json'), dict(prediction=prediction,
                summary=pooled[key], priorPrediction=prior_prediction, priorSummary=summaries(prior_prediction, cohort)))
        contrasts = {}
        for regime in REGIMES:
            expanded, original = regime+'/expanded', regime+'/original'
            contrast = {pop: dict(pooled=metrics.contrast(pooled[expanded][pop], pooled[original][pop]),
                folds=[metrics.contrast(e[pop], o[pop]) for e, o in zip(results[expanded], results[original], strict=True)])
                for pop in ('original', 'all', 'added')}
            contrasts[regime] = dict(populations=contrast, decision=decision(contrast))
        guard(plan['inputs']); guard({'freeze': freeze_pin})
        return write_new(root/'report.json', dict(complete=True, plan=pin, freeze=freeze_pin, folds=artifact_pins,
            pooled=pooled_pins, contrasts=contrasts, previouslyUsedDevelopmentCohort=True,
            independentValidation=False, authorTestRead=False, learnerFeedbackEligible=False, clinicalUseEligible=False))
    except Exception as error:
        write_new(root/'failure.json', dict(errorType=type(error).__name__, message=str(error)))
        raise



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run', 'audit'))
    for name in ('features', 'plan', 'freeze', 'output'): parser.add_argument('--'+name, type=Path)
    for name in ('features', 'plan', 'freeze'): parser.add_argument('--'+name+'-sha256')
    a = parser.parse_args()
    if a.command == 'declare': result = declare(a.features, a.features_sha256, a.output)
    elif a.command == 'run': result = run(a.plan, a.plan_sha256)
    else: result = audit(a.plan, a.plan_sha256, a.freeze, a.freeze_sha256, a.output)
    print(json.dumps(result), flush=True)
