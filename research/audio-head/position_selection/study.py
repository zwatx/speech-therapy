"""Inner stopping selection and frozen outer refits on complete positions."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from types import SimpleNamespace

import numpy as np
import torch

import multiphone_position_train as previous
from multiphone_train import distribution_metrics
from multiphone_sequence_preflight import binding, guard, read_bound, require, write_new

HERE = previous.HERE
BASE = previous.features.NEW
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = HERE/'../../docs/model/multiphone-position-selection-protocol.md'
PINS = {
    'previousPlan': (BASE/'position-study-v1/plan.json', 'ed9e72662331ea42261170c7c4c825c67d00c491b7b657c60646f35153f7d80b'),
    'previousFreeze': (BASE/'position-study-v1/freeze.json', '3077f3a4cb2059e6b784de0e09284a31781b9a4a580b28e954b6a4731e037e7e'),
}
LR = (0.0003, 0.001)
RECIPE = dict(maximumEpochs=100, patience=15, minimumImprovement=1e-7, seed=7, threads=2,
              batch_size=64, hidden=128, dropout=0.1, weight_decay=0.01, gradientNorm=5., device='cpu')


def selection_loss(p, rows, regime):
    p = np.asarray(p)
    require(regime in previous.REGIMES and p.shape == (len(rows), 3) and np.isfinite(p).all()
            and (p >= 0).all() and (p <= 1).all() and np.allclose(p.sum(1), 1., rtol=0, atol=2e-7),
            'Invalid selection population or probabilities')
    values = []
    for phone in sorted({r['targetPhone'] for r in rows}):
        mask = np.array([r['targetPhone'] == phone and (regime == 'all-age' or previous.is_child(r)) for r in rows])
        if mask.any():
            counts = np.array([r['raterCounts'] for r, keep in zip(rows, mask, strict=True) if keep], dtype=float)
            values.append(distribution_metrics(np.asarray(p)[mask], counts)['perRaterLogLoss'])
    require(values and np.isfinite(values).all(), 'Undefined selection NLL')
    return float(np.mean(values))


def stopping(history, maximum=100, patience=15):
    require(history and len(history) <= maximum, 'Missing or excessive history')
    best, epoch = float('inf'), 0
    for i, item in enumerate(history, 1):
        require(item['epoch'] == i and (i == 1 or i-1-epoch < patience), 'History continued after stopping')
        value = item['selectionMacroNLL']
        require(np.isfinite(value), 'Nonfinite selection NLL')
        if value < best-1e-7: best, epoch = value, i
    return epoch, best, len(history) == maximum or len(history)-epoch >= patience


def select_candidate(trials):
    require(len(trials) == 2 and {t['lr'] for t in trials} == set(LR), 'Complete LR pair required')
    return min(trials, key=lambda t: (t['bestLoss'], t['lr'], t['bestEpoch']))


def inner_rows(cohort, splits, fold, regime):
    rows = cohort['rows']; split = splits['folds'][fold]
    fit = [i for i in split['innerFitRows'] if regime == 'all-age' or previous.is_child(rows[i])]
    validation, outer = split['innerValidationRows'], split['outerHoldoutRows']
    previous.metrics.check_partitions(rows, fit, validation, outer)
    require({rows[i]['speakerId'] for i in fit+validation} <=
            {rows[i]['speakerId'] for i in split['outerFitRows']}, 'Inner speakers outside outer fit')
    return fit, validation


def inputs():
    pins = {k: binding(*v) for k, v in PINS.items()}
    old_plan, _ = previous.load_plan(pins['previousPlan']['path'], pins['previousPlan']['sha256'])
    pins.update({'previousInput/'+k: v for k, v in old_plan['inputs'].items()})
    freeze = read_bound(pins['previousFreeze'])
    require(freeze['complete'] is True and freeze['plan'] == pins['previousPlan'] and len(freeze['runs']) == 20,
            'Complete previous control freeze required')
    controls = []
    for job, run_pin in zip(old_plan['jobs'], freeze['runs'], strict=True):
        run = read_bound(run_pin); config = read_bound(run['config'])
        require(run['id'] == job['id'] and config['job'] == job and config['plan'] == pins['previousPlan'], 'Control binding differs')
        controls.append(dict(job=job, run=run, runBinding=run_pin))
        pins['control/'+job['id']+'/run'] = run_pin
        for k in ('config', 'checkpoint', 'history'): pins['control/'+job['id']+'/'+k] = run[k]
    report = read_bound(old_plan['inputs']['features'])
    cohort = read_bound(report['inputs']['cohort']); splits = read_bound(report['inputs']['splits'])
    legacy = {r['legacyRowIndex']: i for i, r in enumerate(cohort['rows']) if r['legacyRowIndex'] is not None}
    jobs, originals = [], []
    for control in controls:
        job = control['job']
        if job['arm'] != 'original': continue
        regime, fold = job['regime'], job['fold']
        fit, validation = inner_rows(cohort, splits, fold, regime)
        historical = read_bound(job['historical']['config.json'])
        selected = Path(historical['selected']['directory'])
        selected_pins = {}
        for filename in ('config.json', 'report.json', 'history.json', 'best.pt', 'predictions.json'):
            path = selected/filename
            selected_pins[filename] = binding(path, historical['innerArtifactsSha256'][str(path)])
            pins[f'originalInner/{regime}/{fold}/{filename}'] = selected_pins[filename]
        config, report_old, history = (read_bound(selected_pins[k]) for k in ('config.json', 'report.json', 'history.json'))
        previous.outer.verified_epoch(config, report_old, history)
        original_fit = [legacy[i] for i in config['fitRows']]
        original_validation = [legacy[i] for i in config['validationRows']]
        require(set(original_fit) == {i for i in fit if cohort['rows'][i]['legacyRowIndex'] is not None}
                and set(original_validation) == {i for i in validation if cohort['rows'][i]['legacyRowIndex'] is not None},
                'Original and expanded inner speaker memberships differ')
        originals.append(dict(regime=regime, fold=fold, files=selected_pins, fitRows=original_fit,
                              validationRows=original_validation, expandedValidationRows=validation))
        for lr in LR:
            jobs.append(dict(id=f'{regime}-f{fold}-lr{lr:g}', regime=regime, fold=fold, lr=lr,
                fitRows=fit, validationRows=validation, outerFitRows=next(c['job']['fitRows'] for c in controls
                    if c['job']['regime'] == regime and c['job']['fold'] == fold and c['job']['arm'] == 'expanded'),
                holdoutRows=job['holdoutRows'], commonVocabularyFitRows=job['commonVocabularyFitRows']))
    for path in sorted(DIRECTORY.glob('*.py')): pins['source/'+path.name] = binding(path)
    pins['protocol'] = binding(PROTOCOL)
    guard(pins)
    return pins, jobs, controls, originals


def declare(output):
    root = Path(output).resolve()
    require(root.is_relative_to(HERE/'outputs') and not root.exists(), 'Fresh ignored directory required')
    pins, jobs, controls, originals = inputs(); root.mkdir(mode=0o700)
    return write_new(root/'plan.json', dict(inputs=pins, jobs=jobs, controls=controls, originals=originals,
        recipe=RECIPE, runtime=previous.features.runtime(), declaredAt=datetime.now(timezone.utc).isoformat(),
        outerPredictionsComputed=False, previouslyUsedDevelopmentCohort=True, learnerFeedbackEligible=False))


def load_plan(path, sha):
    pin = binding(path, sha); plan = read_bound(pin)
    require(Path(pin['path']).is_relative_to(HERE/'outputs'), 'Plan outside research outputs')
    pins, jobs, controls, originals = inputs()
    require(plan['inputs'] == pins and plan['jobs'] == jobs and plan['controls'] == controls
            and plan['originals'] == originals and plan['recipe'] == RECIPE and plan['runtime'] == previous.features.runtime(),
            'Selection declaration differs')
    return plan, pin


def load_data(plan):
    old_plan = read_bound(plan['inputs']['previousPlan'])
    return previous.load_data(old_plan)


def args(lr):
    return SimpleNamespace(**{k: RECIPE[k] for k in ('hidden','dropout','weight_decay','batch_size','seed','device','threads')}, lr=lr)


def save_state(path, model, data, config, plan_pin, epoch):
    require(not path.exists(), 'Checkpoint already exists')
    torch.save(dict(model=model.state_dict(), mean=data['mean'], std=data['std'], epoch=epoch,
                    configSha256=config['sha256'], planSha256=plan_pin['sha256']), path)
    return binding(path)


def checked_model(pin, config_pin, plan_pin, data, lr, epoch):
    guard({'checkpoint': pin}); state = torch.load(pin['path'], map_location='cpu', weights_only=True)
    require(state['configSha256'] == config_pin['sha256'] and state['planSha256'] == plan_pin['sha256']
            and state['epoch'] == epoch and torch.equal(state['mean'], data['mean']) and torch.equal(state['std'], data['std']),
            'Checkpoint lineage or fitting moments differ')
    model = previous.head.make_model(args(lr), 1037); model.load_state_dict(state['model'], strict=True)
    return model


def train_inner(job, cohort, values, root, plan_pin):
    directory = root/'inner'/job['id']; directory.mkdir(parents=True, mode=0o700)
    data = previous.prepare(cohort, values, job['fitRows'])
    config = write_new(directory/'config.json', dict(plan=plan_pin, job=job, prior=data['priors']))
    random.seed(7); torch.manual_seed(7); rng = np.random.default_rng(7)
    model = previous.head.make_model(args(job['lr']), 1037)
    optimizer = torch.optim.AdamW(model.parameters(), lr=job['lr'], weight_decay=.01)
    history = []; validation_rows = [cohort['rows'][i] for i in job['validationRows']]
    for epoch in range(1, 101):
        model.train(); order = rng.permutation(job['fitRows']).tolist(); loss_sum = 0.
        for start in range(0, len(order), 64):
            x, phones, mask, target = previous.head.batch(data, order[start:start+64], 'cpu')
            optimizer.zero_grad(set_to_none=True)
            loss = -(target*model(x,mask,phones,mask)[:,0].log_softmax(-1)).sum(-1)
            require(bool(torch.isfinite(loss).all()), 'Nonfinite training loss')
            loss.mean().backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step(); loss_sum += float(loss.detach().sum())
        prediction = previous.predict(model, data, job['validationRows'])
        value = selection_loss(prediction, validation_rows, job['regime'])
        array_path = directory/f'epoch-{epoch:03d}.npy'
        previous.features.old.atomic_array(array_path, prediction)
        state = save_state(directory/f'epoch-{epoch:03d}.pt', model, data, config, plan_pin, epoch)
        history.append(dict(epoch=epoch, trainPerRaterLogLoss=loss_sum/len(order), selectionMacroNLL=value,
                            checkpoint=state, predictions=binding(array_path)))
        best_epoch, best_loss, stop = stopping(history)
        previous.features.old.atomic_json(directory/'history.json', history)
        print(json.dumps(dict(run=job['id'], epoch=epoch, bestEpoch=best_epoch, selectionNLL=value)), flush=True)
        if stop: break
    selected = history[best_epoch-1]
    model = checked_model(selected['checkpoint'], config, plan_pin, data, job['lr'], best_epoch)
    expected = np.load(selected['predictions']['path'], allow_pickle=False)
    require(np.array_equal(previous.predict(model, data, job['validationRows']), expected), 'Selected inner replay differs')
    require(selection_loss(expected, validation_rows, job['regime']) == best_loss, 'Selected loss differs')
    return write_new(directory/'report.json', dict(complete=True, id=job['id'], regime=job['regime'], fold=job['fold'],
        lr=job['lr'], config=config, history=binding(directory/'history.json'), epochsRun=len(history),
        bestEpoch=best_epoch, bestLoss=best_loss, selected=selected, outerPredictionsComputed=False))


def validate_trial(pin, plan_pin, job, cohort):
    trial = read_bound(pin); config = read_bound(trial['config']); history = read_bound(trial['history'])
    require(trial['complete'] is True and config['plan'] == plan_pin and config['job'] == job
            and trial['id'] == job['id'] and trial['lr'] == job['lr'] and trial['regime'] == job['regime']
            and trial['fold'] == job['fold'] and trial['outerPredictionsComputed'] is False, 'Trial identity differs')
    rows = [cohort['rows'][i] for i in job['validationRows']]
    for item in history:
        guard({k: item[k] for k in ('checkpoint', 'predictions')})
        p = np.load(item['predictions']['path'], allow_pickle=False)
        require(p.dtype == np.float64 and p.shape == (len(rows),3)
                and selection_loss(p, rows, job['regime']) == item['selectionMacroNLL'], 'Saved selection probabilities/loss differ')
    epoch, loss, complete = stopping(history)
    require(complete and len(history) == trial['epochsRun'] and epoch == trial['bestEpoch']
            and loss == trial['bestLoss'] and trial['selected'] == history[epoch-1], 'Stopping or selected state differs')
    return trial


def inner(path, sha):
    torch.set_num_threads(2); plan, pin = load_plan(path, sha); root = Path(pin['path']).parent
    write_new(root/'inner-started.json', dict(plan=pin)); trials = []
    try:
        cohort, values = load_data(plan)
        for job in plan['jobs']: trials.append(train_inner(job, cohort, values, root, pin))
        selected = []
        checked = [validate_trial(p, pin, j, cohort) for p,j in zip(trials,plan['jobs'],strict=True)]
        for regime in previous.REGIMES:
            for fold in range(5):
                candidates = [t for t in checked if t['regime'] == regime and t['fold'] == fold]
                winner = select_candidate(candidates)
                selected.append(dict(regime=regime, fold=fold, trial=trials[checked.index(winner)],
                                     lr=winner['lr'], epochs=winner['bestEpoch']))
        guard(plan['inputs'])
        return write_new(root/'inner-freeze.json', dict(complete=True, plan=pin, trials=trials, selected=selected,
                                                       outerPredictionsComputed=False))
    except Exception as error:
        write_new(root/'inner-failure.json', dict(errorType=type(error).__name__, message=str(error), completedTrials=trials)); raise


def load_inner(plan, pin, freeze_path, freeze_sha, cohort):
    freeze_pin = binding(freeze_path, freeze_sha); freeze = read_bound(freeze_pin)
    require(freeze['complete'] is True and freeze['plan'] == pin and freeze['outerPredictionsComputed'] is False
            and len(freeze['trials']) == 20 and len(freeze['selected']) == 10, 'Complete inner freeze required')
    trials = [validate_trial(p, pin, j, cohort) for p,j in zip(freeze['trials'], plan['jobs'], strict=True)]
    expected=[]
    for regime in previous.REGIMES:
        for fold in range(5):
            winner=select_candidate([t for t in trials if t['regime']==regime and t['fold']==fold])
            expected.append(dict(regime=regime,fold=fold,trial=freeze['trials'][trials.index(winner)],lr=winner['lr'],epochs=winner['bestEpoch']))
    require(freeze['selected']==expected,'Frozen LR/epoch selection differs')
    return freeze, freeze_pin


def refit(path, sha, freeze_path, freeze_sha):
    torch.set_num_threads(2); plan, pin = load_plan(path, sha); root=Path(pin['path']).parent
    cohort, values=load_data(plan); inner_freeze, inner_pin=load_inner(plan,pin,freeze_path,freeze_sha,cohort)
    write_new(root/'outer-started.json',dict(plan=pin,innerFreeze=inner_pin)); runs=[]
    try:
        for selected in inner_freeze['selected']:
            job=next(j for j in plan['jobs'] if j['regime']==selected['regime'] and j['fold']==selected['fold'] and j['lr']==selected['lr'])
            directory=root/'outer'/f"{job['regime']}-f{job['fold']}";directory.mkdir(parents=True,mode=0o700)
            data=previous.prepare(cohort,values,job['outerFitRows'])
            config=write_new(directory/'config.json',dict(plan=pin,innerFreeze=inner_pin,job=job,selection=selected,prior=data['priors']))
            model,history=previous.outer.fit_epochs(args(selected['lr']),data,selected['epochs'])
            control=next(c for c in plan['controls'] if c['job']['regime']==job['regime'] and c['job']['fold']==job['fold'] and c['job']['arm']=='expanded')
            equal_setting=(control['job']['args']['lr']==selected['lr'] and control['job']['epochs']==selected['epochs'])
            if equal_setting:
                previous.historical_parity({'historical':{'checkpoint.pt':control['run']['checkpoint'],'history.json':control['run']['history']}},data,model,history)
            checkpoint=save_state(directory/'checkpoint.pt',model,data,config,pin,selected['epochs'])
            runs.append(write_new(directory/'frozen.json',dict(complete=True,regime=job['regime'],fold=job['fold'],config=config,
                checkpoint=checkpoint,history=write_new(directory/'history.json',history),sameSettingControlExact=equal_setting,
                outerPredictionsComputed=False)))
            print(json.dumps(dict(refit=directory.name,lr=selected['lr'],epochs=selected['epochs'],sameSettingControlExact=equal_setting)),flush=True)
        guard(plan['inputs'])
        return write_new(root/'outer-freeze.json',dict(complete=True,plan=pin,innerFreeze=inner_pin,runs=runs,outerPredictionsComputed=False))
    except Exception as error:
        write_new(root/'outer-failure.json',dict(errorType=type(error).__name__,message=str(error),completedRuns=runs));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('declare','inner','refit'))
    for name in ('plan','freeze','output'):parser.add_argument('--'+name,type=Path)
    for name in ('plan','freeze'):parser.add_argument('--'+name+'-sha256')
    a=parser.parse_args()
    if a.command=='declare':result=declare(a.output)
    elif a.command=='inner':result=inner(a.plan,a.plan_sha256)
    else:result=refit(a.plan,a.plan_sha256,a.freeze,a.freeze_sha256)
    print(json.dumps(result),flush=True)
