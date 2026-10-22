"""Separate-process independent replay of a completed fresh-control CPU preflight.

Run from research/audio-head after a complete eight-forward report:
  python -m posterior_pooling.fresh_verify --plan PLAN --sha256 SHA --report REPORT --review CLEAR --out NEW.json
Scalar-state CTC tables and the explicit dense context kernel are independently
written (transferred from verify-preflight.py); core.CTCPosterior, core pooling
helpers and extract.pool_clip are not used. The original encoder/processor are
shared: four more forwards. Fresh hard vectors must match the saved controls bit
for bit; independently summed candidates use the fixed 1e-6 and audits the fixed
1e-10 absolute tolerance, never a runner gate. Historical hard means are
descriptive only. Any mismatch stops the CPU route; outputs stay intact.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import resource
import time
import traceback

import numpy as np

from posterior_pooling import extract as e, fresh_preflight as f

CANDIDATE_ATOL = 1e-6
AUDIT_ATOL = 1e-10
require = e.require


def tables(logp, target):
    """Scalar-state recurrence, independently summed incoming/outgoing edges."""
    states = [0]
    for token in target:
        states.extend((token, 0))
    n, m = len(logp), len(states)
    predecessors = []
    for s in range(m):
        incoming = [s]
        if s > 0:
            incoming.append(s-1)
        if s > 1 and states[s] != 0 and states[s] != states[s-2]:
            incoming.append(s-2)
        predecessors.append(incoming)
    successors = [[j for j in range(m) if s in predecessors[j]] for s in range(m)]
    a = np.full((n+1, m), -np.inf, dtype=np.float64)
    b = a.copy()
    a[0, 0] = 0.
    b[n, m-1] = 0.
    if target:
        b[n, m-2] = 0.
    for t in range(n):
        for s in range(m):
            a[t+1, s] = np.logaddexp.reduce(a[t, predecessors[s]]) + float(logp[t, states[s]])
    for t in range(n-1, -1, -1):
        for s in range(m):
            b[t, s] = np.logaddexp.reduce([float(logp[t, states[j]])+b[t+1, j] for j in successors[s]])
    z = float(np.logaddexp(a[n, m-1], a[n, m-2]) if target else a[n, 0])
    require(np.isfinite(z), 'Impossible or nonfinite canonical CTC path in independent tables')
    return a, b, z


def dense_kernel(frames):
    """Explicit dense kernel, independently representing each source window."""
    kernel = np.zeros((frames, frames), dtype=np.float64)
    for source in range(frames):
        lo, hi = max(0, source-2), min(frames, source+3)
        kernel[lo:hi, source] = 1./(hi-lo)
    return kernel


def weights(a, b, z, index):
    values = a[1:, 2*index+1] + b[1:, 2*index+1] - z
    duration = float(np.logaddexp.reduce(values))
    require(np.isfinite(duration), 'Zero or nonfinite independent token occupancy')
    q = np.exp(values-duration)
    u = dense_kernel(len(q)) @ q
    require((q >= 0).all() and (u >= 0).all() and np.isclose(q.sum(), 1., rtol=0, atol=AUDIT_ATOL)
            and np.isclose(u.sum(), 1., rtol=0, atol=AUDIT_ATOL), 'Independent q/u mass differs from one')
    return q, u, duration


def weighted_vector(hidden, u):
    """Sequential float64 frame accumulation, persisted as float32."""
    total = np.zeros(hidden.shape[1], dtype=np.float64)
    for t, weight in enumerate(u):
        total += weight*hidden[t].astype(np.float64)
    return total.astype(np.float32)


def historical_replay(hard, historical):
    """Independent descriptive replay; differences never gate."""
    rows, differing = [], 0
    for fresh, old in zip(hard, historical, strict=True):
        rows.append(float(np.max(np.abs(np.subtract(fresh, old, dtype=np.float64)))))
        differing += not np.array_equal(fresh, old)
    return dict(rowMaxAbs=rows, differingRows=differing, rows=len(rows), maximumAbs=max(rows), gate=False)


def posterior_checks(logp, tokens):
    """Independent full-vocabulary checks, before audio or any encoder forward."""
    require(isinstance(logp, np.ndarray) and logp.dtype == np.dtype('<f4')
            and logp.ndim == 2 and len(logp) > 0 and logp.shape[1] == 392
            and np.isfinite(logp).all(), 'Finite full-vocabulary float32 posteriors required')
    require((logp <= 1e-6).all(), 'Positive log probability in independent verification')
    require(isinstance(tokens, (tuple, list)) and all(type(t) is int and 0 < t < 392 for t in tokens),
            'Invalid full canonical tokens in independent verification')
    normalization = np.logaddexp.reduce(logp.astype(np.float64), axis=1)
    # This is the original fixed core tolerance, not a new data-dependent choice.
    require(np.all(np.abs(normalization) <= 3e-5), 'Independent full-vocabulary normalization differs')
    a, b, z = tables(logp, tokens)
    atol = float(min(1e-6, max(1e-10, 64*np.finfo(np.float64).eps*max(len(logp), abs(z)))))
    agreement = float(abs(z-b[0, 0]))
    gamma = np.exp(a[1:]+b[1:]-z)
    occupancy = gamma[:, 1::2].sum(0)
    frame_error = float(np.max(np.abs(gamma.sum(1)-1.)))
    require(np.isfinite(gamma).all() and agreement <= atol and frame_error <= atol
            and (occupancy >= 1.-atol).all(), 'Independent CTC occupancy or likelihood invariant differs')
    diagnostics = dict(logProbability=z, forwardBackwardAbs=agreement, frameMassMaxAbs=frame_error,
                       logNormalizationMaxAbs=float(np.max(np.abs(normalization))), invariantAtol=atol)
    return a, b, z, occupancy, diagnostics


def replay_clip(clip, record, hidden, logp, saved, repeat, historical, posterior=None):
    """Independent tables, dense kernel, weighted sums, audits and descriptive history for one probe."""
    n, tokens, rows = clip['frames'], clip['fullTokens'], clip['rows']
    require(isinstance(logp, np.ndarray) and logp.dtype == np.dtype('<f4') and logp.shape == (n, 392) and np.isfinite(logp).all()
            and isinstance(hidden, np.ndarray) and hidden.dtype == np.dtype('<f4') and hidden.shape == (n, f.WIDTH)
            and np.isfinite(hidden).all(), 'Verification hidden/quantized CTC geometry differs')
    f.checked_values(saved, clip); f.checked_values(repeat, clip)
    a, b, z, occupancy, diagnostics = posterior_checks(logp, tokens) if posterior is None else posterior
    ctc = record['audit']['ctc']
    require(ctc['frames'] == n and ctc['vocabulary'] == 392 and ctc['tokens'] == len(tokens) and ctc['states'] == 2*len(tokens)+1
            and ctc['targetsAccessed'] is False
            and ctc['conditioning'] == 'complete canonical transcript, not produced-phone or deletion truth'
            and all(abs(ctc[k]-value) <= AUDIT_ATOL for k, value in diagnostics.items())
            and len(ctc['tokenOccupancies']) == len(tokens)
            and np.allclose(ctc['tokenOccupancies'], occupancy, rtol=0, atol=AUDIT_ATOL), 'CTC audit differs from independent tables')
    fresh = e.pooled_vectors(hidden, rows, n)[0]
    candidate_max = 0.
    frames = np.arange(n, dtype=np.float64)
    for i, (row, audit) in enumerate(zip(rows, record['audit']['rows'], strict=True)):
        ci = row['canonicalIndex']
        require(type(ci) is int and 0 <= ci < len(tokens) and row['tokenId'] == tokens[ci] == audit['tokenId']
                and audit['id'] == row['id'] and audit['canonicalIndex'] == ci and audit['state'] == 2*ci+1
                and audit['targetsAccessed'] is False, f'Row audit identity differs for {row["id"]}')
        q, u, duration = weights(a, b, z, ci)
        difference = float(np.max(np.abs(weighted_vector(hidden, u).astype(np.float64)-saved['candidate'][i].astype(np.float64))))
        candidate_max = max(candidate_max, difference)
        require(difference <= CANDIDATE_ATOL, f'Independent candidate replay differs for {row["id"]} (maxAbs={difference})')
        require(np.array_equal(fresh[i], saved['hard'][i]), f'Fresh hard control differs across processes for {row["id"]}')
        lo, hi = row['intervalFrames']
        expected = dict(expectedOccupancy=float(np.exp(duration)), qMass=float(q.sum()), uMass=float(u.sum()),
            qEffectiveFrames=float(1./np.dot(q, q)), uEffectiveFrames=float(1./np.dot(u, u)),
            qCentroidFrame=float(q @ frames), uCentroidFrame=float(u @ frames),
            displacementFromIntervalCenter=float(q @ frames)-(lo+hi-1)/2,
            qMassOutsideViterbiInterval=float(q.sum()-q[lo:hi].sum()))
        va, vb = saved['candidate'][i].astype(np.float64), fresh[i].astype(np.float64)
        na, nb = float(np.sqrt(va @ va)), float(np.sqrt(vb @ vb))
        cosine, recorded = (None if na == 0 or nb == 0 else 1.-float(va @ vb)/(na*nb)), audit['vectorDistance']['cosineDistance']
        require(all(abs(audit[k]-v) <= AUDIT_ATOL for k, v in expected.items())
                and abs(audit['vectorDistance']['l2']-float(np.sqrt((va-vb) @ (va-vb)))) <= AUDIT_ATOL
                and (cosine is None) == (recorded is None) and (cosine is None or abs(recorded-cosine) <= AUDIT_ATOL),
                f'Row audit differs from independent replay for {row["id"]}')
    require(all(np.array_equal(saved[k], repeat[k]) for k in f.KEYS), f'Saved within-run repeat differs for {clip["id"]}')
    history = historical_replay(saved['hard'], historical)
    require(record['historicalHardDescriptive'] == history, f'Historical descriptive diagnostics differ for {clip["id"]}')
    return dict(clipId=clip['id'], positions=len(rows), logProbability=z, maximumCandidateReplayAbs=candidate_max,
                hardCrossProcessBitExact=True, repeatBitExact=True, historicalHardDescriptive=history)


def checked_report(plan, plan_binding, report, run, reviewed, env):
    """Complete report, started record and every per-clip/repeat artifact binding; no data consumed."""
    order = f.run_order(plan)
    require(report.get('complete') is True and report['study'] == plan['study'] and report['plan'] == plan_binding
            and report['review'] == reviewed and report['environment'] == env
            and report['runner'] == e.file_binding(Path(f.__file__)) and report['outputDirectory'] == str(run)
            and report['runOrder'] == order*2 and report['encoderForwards'] == 2*len(order)
            and report['references'] == {k: plan['inputs'][k] for k in f.REFERENCE_KEYS} and report['model'] == plan['model']
            and report['processId'] != os.getpid(), 'Fresh report plan/review/runtime/reference/model/process binding differs')
    require(report['repeatsExact'] is True and report['freshHardSameForward'] is True and report['encoderInferencePerformed'] is True
            and report['historicalControlsDescriptiveOnly'] is True and report['freshMatchedControls'] is True
            and report['historicalHardGate'] is False and 'cachedHardExact' not in report
            and all(report[k] is False for k in f.FLAGS), 'Fresh report outcome or no-label/no-fit flags differ')
    records, repeats = report['records'], report['repeats']
    require([r['clipId'] for r in records] == order and [r['forward'] for r in records] == [1, 2, 3, 4]
            and set(repeats) == set(order) and sorted(repeats, key=lambda c: repeats[c]['forward']) == order
            and sorted(r['forward'] for r in repeats.values()) == [5, 6, 7, 8], 'Ordered four-probe/repeat coverage differs')
    expected = {'started.json', 'report.json'} | {cid+suffix for cid in order for suffix in ('.json', '.npz', '-repeat.npz')}
    require({p.name for p in run.iterdir()} == expected, 'Run directory has missing, extra or failure artifacts')
    started = e.read_json(run/'started.json')
    require(started['plan'] == plan_binding and started['review'] == reviewed and started['environment'] == env
            and started['runOrder'] == order*2 and started['processId'] == report['processId'], 'Started record binding differs')
    by_id = {c['id']: c for c in plan['clips']}
    for record in records:
        cid = record['clipId']; rows = by_id[cid]['rows']; repeat = repeats[cid]
        require(e.read_json(run/(cid+'.json')) == record and record['roles'] == plan['probes']['roles'][cid]
                and record['rowIds'] == [r['id'] for r in rows] and record['outputIndices'] == [r['outputIndex'] for r in rows]
                and record['shape'] == [len(rows), f.WIDTH] and record['dtype'] == 'float32'
                and record['artifact'] == e.file_binding(run/(cid+'.npz')) and repeat['clipId'] == cid
                and repeat['artifact'] == e.file_binding(run/(cid+'-repeat.npz'))
                and repeat['candidateBitExact'] is True and repeat['hardBitExact'] is True,
                f'Artifact, identity, role or repeat binding differs for {cid}')
    return order


def load_arrays(binding, clip):
    require(e.file_binding(Path(binding['path'])) == binding, 'Saved artifact hash differs')
    with np.load(binding['path'], allow_pickle=False) as archive:
        require(set(archive.files) == set(f.KEYS), 'Saved artifact keys differ')
        values = {k: archive[k].copy() for k in f.KEYS}
    return f.checked_values(values, clip)


def verify(plan_path, sha, report_path, review, out):
    # Plan hash and clear review precede report, arrays, audio, posteriors and the model.
    plan_path, report_path, review, out = (Path(p).resolve() for p in (plan_path, report_path, review, out))
    require(e.digest(plan_path) == sha, 'Fresh plan SHA differs')
    e.base.checked_review(review, sha)
    reviewed = e.file_binding(review)
    require(out.suffix == '.json' and not out.exists() and out.parent.is_dir() and not out.is_relative_to(report_path.parent)
            and not out.is_relative_to(f.OLD) and (out.is_relative_to(e.HERE/'outputs') or out.is_relative_to(e.ROOT/'work')),
            'Fresh exclusive verification JSON required; no restart')
    started = time.monotonic(); verified = []; forwards = 0
    bindings = dict(plan=e.file_binding(plan_path), review=reviewed)
    try:
        plan = f.checked_plan(plan_path, sha)
        env = e.environment(plan['runtime'])
        require(report_path.name == 'report.json', 'Canonical fresh report required')
        bindings['report'] = e.file_binding(report_path); report = e.read_json(report_path)
        order = checked_report(plan, bindings['plan'], report, report_path.parent, reviewed, env)
        new = f.new_sources()
        require(all(plan['sources'][str(p)] == e.file_binding(p) for p in new), 'Fresh source pins differ')
        reference = e.checked_references(plan)
        by_id = {c['id']: c for c in plan['clips']}
        with e.load_encoder(plan) as encoder:
            for record in report['records']:
                f.check_review(review, reviewed)
                cid = record['clipId']; clip = by_id[cid]; before = time.monotonic()
                e.guard_clip(clip)
                logp = np.fromfile(clip['posterior']['path'], dtype='<f4').reshape(clip['frames'], 392)
                posterior = posterior_checks(logp, clip['fullTokens'])
                samples = e.read_rating_pcm(Path(clip['audioPath']), clip['audioSha256'])
                require(samples.numel() == clip['sampleCount'], 'Original audio sample count differs')
                hidden = encoder(samples); forwards += 1
                saved = load_arrays(record['artifact'], clip)
                repeat = load_arrays(report['repeats'][cid]['artifact'], clip)
                result = replay_clip(clip, record, hidden, logp, saved, repeat,
                                     reference[[r['outputIndex'] for r in clip['rows']]], posterior=posterior)
                e.guard_clip(clip)
                verified.append(dict(result, seconds=time.monotonic()-before))
        require(forwards == 4 and [c['clipId'] for c in verified] == order, 'Four ordered verification forwards required')
        e.guard(plan['model'])
        for clip in plan['clips']:
            e.guard_clip(clip)
        e.checked_references(plan)
        f.checked_plan(plan_path, sha)
        require(e.environment(plan['runtime']) == env, 'Runtime changed during verification')
        require(e.file_binding(report_path) == bindings['report'], 'Fresh report changed during verification')
        f.check_review(review, reviewed)
        histories = [c['historicalHardDescriptive'] for c in verified]
        history = dict(differingRows=sum(h['differingRows'] for h in histories), rows=sum(h['rows'] for h in histories),
                       maximumAbs=max(h['maximumAbs'] for h in histories), gate=False)
        require(report['historicalHardDescriptive'] == history, 'Report historical descriptive summary differs')
        return e.write_new(out, dict(complete=True, verified=True, separateProcess=True, processId=os.getpid(),
            runnerProcessId=report['processId'], **bindings, environment=env, verifier=e.file_binding(Path(__file__)),
            sourcePins={p.name: plan['sources'][str(p)] for p in new}, orderedCoverage=order, clips=verified,
            additionalEncoderForwards=forwards, sharedEncoder=True, independentTablesKernel=True,
            coreHelpersUsedForCandidate=False, hardCrossProcessBitExact=True, repeatsBitExact=True,
            candidateAbsoluteTolerance=CANDIDATE_ATOL, auditAbsoluteTolerance=AUDIT_ATOL,
            historicalHardDescriptiveOnly=True, historicalHardDescriptive=history,
            peakMemory=dict(value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, units='bytes', system=platform.system(),
                method='process lifetime resource.getrusage(RUSAGE_SELF).ru_maxrss on Darwin'),
            elapsedSeconds=time.monotonic()-started, **f.FLAGS))
    except BaseException as error:
        e.write_new(out, dict(complete=False, verified=False, cpuRouteStopped=True, **bindings,
            errorType=type(error).__name__, errorMessage=str(error), errorTraceback=''.join(traceback.format_exception(error)),
            verifiedClips=len(verified), additionalEncoderForwards=forwards, elapsedSeconds=time.monotonic()-started,
            restartAllowed=False, **f.FLAGS))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ('--plan', '--report', '--review', '--out'):
        parser.add_argument(name, required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.plan, args.sha256, args.report, args.review, args.out)))


if __name__ == '__main__': main()
