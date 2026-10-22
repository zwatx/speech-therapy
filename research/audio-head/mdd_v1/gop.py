"""Alignment-free CTC GOP and development-only calibration; high score = error."""
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
import torch
from torch.nn import functional as F
from .evaluate import anchored
from .inventory import PHONE_TO_ID


def ctc_log_likelihoods(log_probs, sequences, chunk=64):
    """CPU float32 CTC, all paths marginalized; empty targets supported."""
    log_probs = log_probs.detach().float().cpu().contiguous()
    output = []
    for offset in range(0, len(sequences), chunk):
        group = sequences[offset:offset+chunk]
        lengths = torch.tensor([len(s) for s in group], dtype=torch.long)
        targets = torch.tensor([p for s in group for p in s], dtype=torch.long)
        probabilities = log_probs[:, None, :].expand(-1,len(group),-1).contiguous()
        losses = F.ctc_loss(probabilities, targets,
                            torch.full((len(group),),len(log_probs),dtype=torch.long),
                            lengths, blank=0, reduction='none', zero_infinity=False)
        output.extend((-losses).tolist())
    return np.asarray(output, dtype=np.float64)


def ctc_gop(log_probs, canonical):
    """Max log P(single deletion/substitution)/P(canonical), per canonical phone."""
    if not canonical:
        raise ValueError('Empty canonical prompt')
    alternatives, positions = [list(canonical)], []
    for i, phone in enumerate(canonical):
        for replacement in range(1,log_probs.shape[-1]):
            if replacement != phone:
                alternatives.append(canonical[:i]+[replacement]+canonical[i+1:]); positions.append(i)
        alternatives.append(canonical[:i]+canonical[i+1:]); positions.append(i)
    values = ctc_log_likelihoods(log_probs,alternatives)
    if not np.isfinite(values[0]):
        raise ValueError('Canonical sequence has no finite CTC alignment')
    best = np.full(len(canonical), -np.inf)
    np.maximum.at(best,positions,values[1:])
    result = best-values[0]
    if not np.isfinite(result).all():
        raise ValueError('No finite CTC competitor')
    return result


def labels(row):
    if row['source'] == 'l2-arctic':
        return {e['canonical_index']: int(e['event'] != 'unchanged')
                for e in row['events'] if e['canonical'] is not None}
    return {i:int(score in (0,1)) for i,score in enumerate(row['scores']) if score in (0,1,2)}


def phone_features(row, log_probs, hypothesis):
    target = [PHONE_TO_ID[p] for p in row['canonical']]
    gop = ctc_gop(log_probs,target)
    slots, _ = anchored(row['canonical'], hypothesis)
    truth = labels(row)
    return [dict(id=row['id'],speaker=row['speaker'],index=i,phone=phone,
                 gop=float(gop[i]),disagreement=int(slots[i]!=phone),error=truth[i])
            for i,phone in enumerate(row['canonical']) if i in truth]


def features(records):
    return np.asarray([[r['gop'],r['disagreement']] for r in records],dtype=np.float64)


def fit_calibration(records):
    x = features(records)
    y = np.asarray([r['error'] for r in records],dtype=float)
    mean, scale = x.mean(0),x.std(0)
    scale[scale<1e-8] = 1
    design = np.column_stack([np.ones(len(x)),(x-mean)/scale])

    def objective(weights):
        z = design@weights
        loss = np.logaddexp(0,z).sum()-y@z+.5*np.dot(weights[1:],weights[1:])
        gradient = design.T@(expit(z)-y)
        gradient[1:] += weights[1:]
        return loss,gradient

    result = minimize(objective,np.zeros(3),jac=True,method='L-BFGS-B',options={'maxiter':1000,'ftol':1e-12})
    if not result.success:
        raise ValueError(f'Calibration optimizer failed: {result.message}')
    logits = design@result.x
    curve = pr_curve(y,logits)
    operating = max(curve[1:],key=lambda p:(p['F1'],p['threshold']))
    return dict(mean=mean.tolist(),scale=scale.tolist(),weights=result.x.tolist(),
                threshold=operating['threshold'],objective=float(result.fun),
                optimizer=str(result.message),phones=len(y),errors=int(y.sum()),
                calibration_at_threshold=operating)


def calibrated_logits(records,calibration):
    x = (features(records)-calibration['mean'])/calibration['scale']
    return np.column_stack([np.ones(len(x)),x])@np.asarray(calibration['weights'])


def operating_counts(y,predicted):
    y,predicted = np.asarray(y,dtype=bool),np.asarray(predicted,dtype=bool)
    tp,fp,fn,tn = int((y&predicted).sum()),int((~y&predicted).sum()),int((y&~predicted).sum()),int((~y&~predicted).sum())
    return dict(TP=tp,FP=fp,FN=fn,TN=tn,precision=tp/(tp+fp) if tp+fp else None,
                recall=tp/(tp+fn) if tp+fn else None,F1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)


def pr_curve(y,scores):
    y,scores = np.asarray(y,dtype=bool),np.asarray(scores,dtype=float)
    order = np.argsort(-scores,kind='stable')
    ys,ss = y[order],scores[order]
    endpoints = np.r_[np.flatnonzero(ss[:-1]!=ss[1:]),len(ss)-1]
    tp = np.cumsum(ys)
    total = int(ys.sum())
    curve = [dict(threshold=None,precision=1.,recall=0.,F1=0.,flagged=0)]
    for end in endpoints:
        positives = int(end)+1
        t = int(tp[end])
        curve.append(dict(threshold=float(ss[end]),precision=t/positives,
                          recall=t/total if total else 0.,F1=2*t/(positives+total),flagged=positives))
    return curve


def coverage_curve(y,scores,threshold):
    """Distance from fixed threshold; abstained reference errors count as missed."""
    y,scores = np.asarray(y,dtype=bool),np.asarray(scores,dtype=float)
    confidence = np.abs(scores-threshold)
    order = np.argsort(-confidence,kind='stable')
    ys,ss,cc = y[order],scores[order],confidence[order]
    endpoints = np.r_[np.flatnonzero(cc[:-1]!=cc[1:]),len(cc)-1]
    predicted = ss>=threshold
    tp = np.cumsum(ys&predicted)
    fp = np.cumsum(~ys&predicted)
    correct = np.cumsum(ys==predicted)
    total_errors = int(y.sum())
    return [dict(coverage=(int(e)+1)/len(y),phones=int(e)+1,
                 precision=float(tp[e]/(tp[e]+fp[e])) if tp[e]+fp[e] else None,
                 verdict_accuracy=float(correct[e]/(e+1)),
                 end_to_end_recall=float(tp[e]/total_errors) if total_errors else None,
                 confidence=float(cc[e])) for e in endpoints]


def summarize(records,calibration):
    y = np.asarray([r['error'] for r in records],dtype=bool)
    scores = calibrated_logits(records,calibration)
    curve = pr_curve(y,scores)
    return dict(phones=len(y),errors=int(y.sum()),speakers=len({r['speaker'] for r in records}),
                at_frozen_threshold=operating_counts(y,scores>=calibration['threshold']),
                precision_at_recall={str(r):max((p['precision'] for p in curve if p['recall']>=r),default=0.) for r in (.3,.5,.7)},
                recall_at_precision_0_9=max((p['recall'] for p in curve if p['precision']>=.9),default=0.),
                average_precision=sum((b['recall']-a['recall'])*b['precision'] for a,b in zip(curve,curve[1:])),
                pr_curve=curve,coverage_curve=coverage_curve(y,scores,calibration['threshold']),
                disagreement_only=operating_counts(y,[r['disagreement'] for r in records]))
