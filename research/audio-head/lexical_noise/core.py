"""Label-free frozen-head inference and descriptive probability movement."""
import numpy as np
import torch
from multiphone_models import MeanPoolPhoneRatingHead


def require(ok, message):
    if not ok:
        raise ValueError(message)


@torch.no_grad()
def predict(state, target, scalars, offsets, phone_ids, transform=None, correction=None):
    """Consume saved parameters and feature arrays only; no ratings or fitting."""
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    require(target.dtype == scalars.dtype == np.float32 and target.shape == (len(scalars), 1024)
            and scalars.shape == (len(target), 13) and np.isfinite(target).all() and np.isfinite(scalars).all(),
            'Invalid feature arrays')
    require(len(offsets) > 0 and len(offsets) == len(phone_ids) and len(set(offsets)) == len(offsets)
            and all(type(i) is int and 0 <= i < len(target) for i in offsets)
            and all(type(p) is int and 0 <= p < 23 for p in phone_ids), 'Invalid row/phone identities')
    width = 13 if transform is None else 29
    for name in ('mean', 'std'):
        require(state[name].shape == (width,) and state[name].dtype == torch.float32
                and torch.isfinite(state[name]).all(), 'Invalid saved moments')
    require((state['std'] > 0).all(), 'Nonpositive saved scale')
    require(correction is None or transform is not None, 'Correction requires PCA')
    values = torch.tensor(scalars, dtype=torch.float32)
    if transform is not None:
        require(transform['center'].shape == (1024,) and transform['basis'].shape == (1024, 16)
                and all(transform[k].dtype == torch.float64 and torch.isfinite(transform[k]).all()
                        for k in ('center', 'basis')), 'Invalid saved PCA')
        centered = torch.tensor(target, dtype=torch.float64) - transform['center']
        values = torch.cat(((centered @ transform['basis']).float(), values), dim=1)
        if correction is not None:
            require(correction.shape == (1024, 16) and correction.dtype == torch.float64
                    and torch.isfinite(correction).all(), 'Invalid saved correction')
    require(torch.isfinite(values).all(), 'Nonfinite projected values')
    model = MeanPoolPhoneRatingHead(feature_dim=width, num_phones=24, hidden_dim=128, dropout=.1).cpu()
    model.load_state_dict(state['model'], strict=True)
    model.eval().requires_grad_(False)
    before = {k: v.clone() for k, v in model.state_dict().items()}
    logits = []
    for start in range(0, len(offsets), 64):
        ix = offsets[start:start+64]
        v = values[ix]
        if correction is not None:
            v = torch.cat((v[:, :16] + (centered[ix] @ correction).float(), v[:, 16:]), dim=1)
        v = ((v - state['mean']) / state['std'])[:, None, :]
        phones = torch.tensor(phone_ids[start:start+64], dtype=torch.long)[:, None]
        mask = torch.ones(phones.shape, dtype=torch.bool)
        logits.append(model(v, mask, phones, mask)[:, 0])
    logits = torch.cat(logits)
    require(logits.dtype == torch.float32 and torch.isfinite(logits).all(), 'Nonfinite model output')
    require(all(torch.equal(v, before[k]) for k, v in model.state_dict().items()), 'Head changed')
    logs = logits.double().log_softmax(-1).numpy()
    return dict(probabilities=np.exp(logs).tolist(), logProbabilities=logs.tolist(),
                rawProbabilities=logits.softmax(-1).numpy().tolist())


def probabilities(value):
    p = np.asarray(value['probabilities'], dtype=np.float64)
    lp = np.asarray(value['logProbabilities'], dtype=np.float64)
    require(p.ndim == 2 and p.shape[1] == 3 and p.shape == lp.shape and len(p)
            and np.isfinite(p).all() and np.isfinite(lp).all() and (p >= 0).all()
            and np.allclose(np.exp(lp), p, rtol=3e-13, atol=0)
            and np.allclose(p.sum(1), 1, atol=1e-12, rtol=0), 'Invalid probabilities/logs')
    return p, lp


def average(a, b):
    pa, la = probabilities(a)
    pb, lb = probabilities(b)
    require(pa.shape == pb.shape, 'Mixture shape differs')
    lp = np.logaddexp(la, lb) - np.log(2.)
    return dict(probabilities=np.exp(lp).tolist(), logProbabilities=lp.tolist())


def movement(clean, noisy):
    a, _ = probabilities(clean)
    b, _ = probabilities(noisy)
    require(a.shape == b.shape, 'Movement shape differs')
    diff = b - a
    expected = diff @ np.arange(3, dtype=np.float64)
    return dict(TV=(.5 * np.abs(diff).sum(1)).tolist(), expectedShift=expected.tolist(),
                absoluteExpectedShift=np.abs(expected).tolist(), rating0Shift=diff[:, 0].tolist(),
                below2Shift=diff[:, :2].sum(1).tolist(),
                argmaxChanged=(a.argmax(1) != b.argmax(1)).tolist())


def summarize(moves, rows):
    n = len(rows)
    require(set(moves) == {'TV', 'expectedShift', 'absoluteExpectedShift', 'rating0Shift', 'below2Shift', 'argmaxChanged'}
            and all(len(v) == n for v in moves.values()), 'Movement population differs')
    result = dict(positions=n, clips=len({r['clipId'] for r in rows}), speakers=len({r['speakerId'] for r in rows}),
                  phones=sorted({r['targetPhone'] for r in rows}))
    if not n:
        return dict(**result, measures=None)
    require(all(np.isfinite(v).all() for v in moves.values()), 'Nonfinite movement')
    result['measures'] = dict(meanTV=float(np.mean(moves['TV'])), maxTV=float(np.max(moves['TV'])),
        meanExpectedShift=float(np.mean(moves['expectedShift'])),
        meanAbsoluteExpectedShift=float(np.mean(moves['absoluteExpectedShift'])),
        maxAbsoluteExpectedShift=float(np.max(moves['absoluteExpectedShift'])),
        meanRating0Shift=float(np.mean(moves['rating0Shift'])), meanBelow2Shift=float(np.mean(moves['below2Shift'])),
        argmaxChanges=int(np.count_nonzero(moves['argmaxChanged'])))
    return result


def compare(candidate, reference):
    require(len(candidate['TV']) == len(reference['TV']), 'Paired movement population differs')
    n = len(candidate['TV'])
    if not n:
        return None
    tv = np.asarray(candidate['TV']) - np.asarray(reference['TV'])
    expected = np.asarray(candidate['absoluteExpectedShift']) - np.asarray(reference['absoluteExpectedShift'])
    return dict(meanTVChange=float(tv.mean()), maxTVChange=float(max(candidate['TV']) - max(reference['TV'])),
                meanAbsoluteExpectedShiftChange=float(expected.mean()),
                argmaxChangesDifference=int(np.count_nonzero(candidate['argmaxChanged']) - np.count_nonzero(reference['argmaxChanged'])),
                lowerTV=int((tv < -1e-12).sum()), sameTVWithinTolerance=int((np.abs(tv) <= 1e-12).sum()),
                higherTV=int((tv > 1e-12).sum()), perPositionTVChange=tv.tolist())
