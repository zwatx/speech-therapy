"""Three fixed supervised detectors, calibration-only selection and Platt fit."""
from datetime import datetime, timezone
import json
import time

import joblib
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits
import torch
from torch import nn

from .gop import pr_curve
from .runtime import device_setup
from .stage_d import RUN, check_identity, load_group, save_json, sha
from .stage_d_metrics import ranking

SEED = 43
BUDGET_SECONDS = 1800
CANDIDATES = ('logistic', 'hist_gradient_boosting', 'mlp')


def mlp(features):
    return nn.Sequential(nn.Linear(features,128),nn.ReLU(),nn.Dropout(.1),
                         nn.Linear(128,64),nn.ReLU(),nn.Dropout(.1),nn.Linear(64,1))


def standardize(x, scaling):
    return (x-np.asarray(scaling['mean']))/np.asarray(scaling['scale'])


def fit_platt(scores, y):
    scores, y = np.asarray(scores, dtype=float), np.asarray(y, dtype=float)
    mean, scale = float(scores.mean()), max(float(scores.std()), 1e-8)
    design = np.column_stack([np.ones(len(scores)), (scores-mean)/scale])

    def objective(weights):
        z = design@weights
        loss = np.logaddexp(0,z).sum()-y@z+.5*weights[1]**2
        gradient = design.T@(expit(z)-y)
        gradient[1] += weights[1]
        return loss, gradient

    result = minimize(objective, [0.,1.], jac=True, method='L-BFGS-B',
                      bounds=[(None,None),(1e-6,None)], options={'maxiter':1000,'ftol':1e-12})
    if not result.success:
        raise ValueError(f'Platt calibration failed: {result.message}')
    return dict(mean=mean,scale=scale,weights=result.x.tolist(),optimizer=str(result.message),
                objective=float(result.fun),phones=len(y),errors=int(y.sum()))


def platt_logits(scores, calibration):
    intercept, slope = calibration['weights']
    return intercept + slope*(np.asarray(scores)-calibration['mean'])/calibration['scale']


def predict_raw(name, x, scaling):
    if name == 'logistic':
        return joblib.load(RUN/f'{name}.joblib').decision_function(standardize(x,scaling))
    if name == 'hist_gradient_boosting':
        return joblib.load(RUN/f'{name}.joblib').decision_function(x)
    if name != 'mlp':
        raise ValueError('Unknown candidate')
    checkpoint = torch.load(RUN/'mlp.pt',weights_only=True)
    model = mlp(x.shape[1]).eval()
    model.load_state_dict(checkpoint['state'])
    with torch.inference_mode():
        return model(torch.from_numpy(standardize(x,scaling).astype('float32'))).squeeze(1).numpy().astype(float)


def predict_selected(x, selection):
    return platt_logits(predict_raw(selection['selected'],x,selection['scaling']),selection['platt'])


def train_mlp(x, y, deadline):
    device = device_setup(SEED)
    model = mlp(x.shape[1]).to(device)
    parameters = sum(p.numel() for p in model.parameters())
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.01)
    features = torch.from_numpy(x.astype('float32')).to(device)
    labels = torch.from_numpy(y.astype('float32')).to(device)
    history = []
    for epoch in range(1,21):
        model.train()
        order = torch.randperm(len(x)).to(device)
        total = 0.
        for offset in range(0,len(x),1024):
            if time.monotonic() >= deadline:
                raise TimeoutError('Combined Stage D fit budget exhausted')
            take = order[offset:offset+1024]
            optimizer.zero_grad(set_to_none=True)
            logits = model(features[take]).squeeze(1)
            loss = nn.functional.binary_cross_entropy_with_logits(logits, labels[take])
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite MLP loss')
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            total += loss.item()*len(take)
        history.append(dict(epoch=epoch,loss=total/len(x)))
        print(f'D MLP epoch={epoch} loss={total/len(x):.6f}',flush=True)
    torch.save(dict(state={k:v.detach().cpu() for k,v in model.state_dict().items()},
                    features=x.shape[1]), RUN/'mlp.pt')
    if device.type == 'mps':
        torch.mps.empty_cache()
    return dict(device=str(device),parameters=parameters,epochs=20,history=history)


def fit_candidate(name, x, y, scaling, parameters, charged):
    """A fit receipt survives prediction failures; an interrupted fit cannot retry."""
    receipt_path = RUN/f'fit-{name}.json'
    model_path = RUN/('mlp.pt' if name == 'mlp' else f'{name}.joblib')
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt['status'] != 'complete':
            raise RuntimeError(f'Unaccounted/failed {name} fit; preserve evidence, no automatic refit')
        if sha(model_path) != receipt['model_sha256']:
            raise ValueError('Completed candidate artifact changed')
        return receipt
    if model_path.exists():
        raise FileExistsError('Model artifact has no fit receipt; refusing overwrite')
    if charged >= BUDGET_SECONDS:
        raise TimeoutError('Combined candidate fit budget exhausted before fitting')
    receipt = dict(candidate=name, status='started',
                   started_utc=datetime.now(timezone.utc).isoformat(),
                   remaining_budget_seconds=BUDGET_SECONDS-charged)
    save_json(receipt_path, receipt)
    start = time.monotonic()
    extra = {}
    try:
        if name == 'logistic':
            model = LogisticRegression(C=1.,solver='lbfgs',max_iter=3000,random_state=SEED)
            model.fit(standardize(x,scaling),y)
            extra['iterations'] = model.n_iter_.tolist()
            joblib.dump(model,model_path)
        elif name == 'hist_gradient_boosting':
            model = HistGradientBoostingClassifier(random_state=SEED,**parameters)
            model.fit(x,y)
            joblib.dump(model,model_path)
        elif name == 'mlp':
            extra = train_mlp(standardize(x,scaling),y,start+BUDGET_SECONDS-charged)
        else:
            raise ValueError('Unknown candidate')
        seconds = time.monotonic()-start
        if charged+seconds > BUDGET_SECONDS:
            raise TimeoutError('Combined candidate fitting exceeded declaration')
    except BaseException as error:
        receipt.update(status='failed',fit_seconds=time.monotonic()-start,
                       failure=type(error).__name__,detail=str(error))
        save_json(receipt_path,receipt)
        raise
    receipt.update(status='complete',fit_seconds=seconds,model_sha256=sha(model_path),**extra)
    save_json(receipt_path,receipt)
    return receipt


def fit():
    if (RUN/'selection.json').exists():
        raise FileExistsError('Stage D selection frozen; do not refit')
    check_identity()
    torch.set_num_threads(4)
    x, records = load_group('train')
    xc, cal_records = load_group('calibration')
    if {r['speaker'] for r in records} & {r['speaker'] for r in cal_records}:
        raise ValueError('Training/calibration overlap')
    y = np.asarray([r['error'] for r in records])
    yc = np.asarray([r['error'] for r in cal_records])
    mean, scale = x.mean(0), x.std(0)
    scale[scale < 1e-8] = 1.
    scaling = dict(mean=mean.tolist(),scale=scale.tolist(),fitted_on='official train only')
    declaration = dict(seed=SEED,combined_budget_seconds=BUDGET_SECONDS,scaling=scaling,
                       fit_groups=['train'],selection_group='calibration',l2_fit_count=0,
                       reporting_fit_count=0,calibration_speakers=sorted({r['speaker'] for r in cal_records}),
                       parameters=dict(logistic=dict(C=1.,solver='lbfgs',max_iter=3000,L2=True),
                         hist_gradient_boosting=dict(learning_rate=.08,max_iter=200,max_leaf_nodes=15,
                            min_samples_leaf=50,l2_regularization=1.,early_stopping=False),
                         mlp=dict(hidden=[128,64],dropout=.1,epochs=20,batch_size=1024,lr=.001,weight_decay=.01,
                                  gradient_clip=5.)))
    save_json(RUN/'settings.json', declaration)
    results = {}
    charged = 0.
    for name in CANDIDATES:
        path = RUN/f'candidate-{name}.json'
        with threadpool_limits(limits=4):
            receipt = fit_candidate(name,x,y,scaling,declaration['parameters'][name],charged)
            seconds = receipt['fit_seconds']
            charged += seconds
            if charged > BUDGET_SECONDS:
                raise TimeoutError('Saved combined fit charge exceeds budget')
            if path.exists():
                results[name] = json.loads(path.read_text())
                if results[name]['fit_seconds'] != seconds:
                    raise ValueError('Candidate score/fit receipt mismatch')
                continue
            raw = predict_raw(name,xc,scaling)
        extra = {key:receipt[key] for key in ('iterations','device','parameters','epochs','history') if key in receipt}
        save_json(RUN/f'calibration-{name}-predictions.json',raw.tolist())
        result = dict(candidate=name,fit_seconds=seconds,calibration=ranking(yc,raw),**extra)
        results[name] = result
        save_json(path,result)
        print(json.dumps(result),flush=True)
    chosen = max(CANDIDATES,key=lambda name:results[name]['calibration']['AP'])
    raw = np.asarray(json.loads((RUN/f'calibration-{chosen}-predictions.json').read_text()))
    platt = fit_platt(raw,yc)
    logits = platt_logits(raw,platt)
    operating = max(pr_curve(yc,logits)[1:],key=lambda p:(p['F1'],p['threshold']))
    selection = dict(**declaration,selected=chosen,candidates=results,platt=platt,
                     threshold=operating['threshold'],calibration_at_threshold=operating,
                     combined_fit_seconds=charged,identity_sha256=sha(RUN/'identity.json'))
    save_json(RUN/'selection.json',selection)
    save_json(RUN/'predictions-calibration.json',
              [dict(**record,logit=float(score)) for record,score in zip(cal_records,logits)])
    print(json.dumps(dict(selected=chosen,threshold=selection['threshold'],combined_fit_seconds=charged)),flush=True)
