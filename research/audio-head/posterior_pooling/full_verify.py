"""Separate-process verification of a completed full posterior-pooling extraction.

Run from research/audio-head after a complete 1,048-forward report:
  python -m posterior_pooling.full_verify --plan PLAN --sha256 SHA --report REPORT --review CLEAR --out NEW.json
Before any audio or model, every recording's full-vocabulary posteriors,
scalar-state CTC tables, dense source-normalized kernel, row occupancy/support/
centroid/displacement/outside-interval diagnostics, CTC audit fields, vector
distances and historical statistics are replayed with the reviewed fresh_verify
formulas (no core helpers), and matrices must equal the saved clip units. Then
four shared-encoder probe forwards reconstruct those 37 candidates independently
(1e-6) and fresh hard controls bit exact. This does not independently
reconstruct every acoustic vector. Any mismatch stops the route; no retry.
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

from posterior_pooling import extract as e, fresh_preflight as f, fresh_verify as v, full_extract as x

require = e.require


def replay_diagnostics(clip, record, values, posterior):
    """Every CTC audit field, row diagnostic and vector distance from independent tables and persisted pairs."""
    n, tokens, rows = clip['frames'], clip['fullTokens'], clip['rows']
    a, b, z, occupancy, diagnostics = posterior
    ctc = record['audit']['ctc']
    require(ctc['frames'] == n and ctc['vocabulary'] == 392 and ctc['tokens'] == len(tokens) and ctc['states'] == 2*len(tokens)+1
            and ctc['targetsAccessed'] is False
            and ctc['conditioning'] == 'complete canonical transcript, not produced-phone or deletion truth'
            and all(abs(ctc[k]-value) <= v.AUDIT_ATOL for k, value in diagnostics.items())
            and len(ctc['tokenOccupancies']) == len(tokens)
            and np.allclose(ctc['tokenOccupancies'], occupancy, rtol=0, atol=v.AUDIT_ATOL), f'CTC audit differs from independent tables for {clip["id"]}')
    audits = record['audit']['rows']
    require(len(audits) == len(rows), f'Row audit coverage differs for {clip["id"]}')
    frames = np.arange(n, dtype=np.float64)
    for i, (row, audit) in enumerate(zip(rows, audits, strict=True)):
        ci = row['canonicalIndex']
        require(type(ci) is int and 0 <= ci < len(tokens) and row['tokenId'] == tokens[ci] == audit['tokenId']
                and audit['id'] == row['id'] and audit['canonicalIndex'] == ci and audit['state'] == 2*ci+1
                and audit['targetsAccessed'] is False, f'Row audit identity differs for {row["id"]}')
        q, u, duration = v.weights(a, b, z, ci)
        lo, hi = row['intervalFrames']
        expected = dict(expectedOccupancy=float(np.exp(duration)), qMass=float(q.sum()), uMass=float(u.sum()),
            qEffectiveFrames=float(1./np.dot(q, q)), uEffectiveFrames=float(1./np.dot(u, u)),
            qCentroidFrame=float(q @ frames), uCentroidFrame=float(u @ frames),
            displacementFromIntervalCenter=float(q @ frames)-(lo+hi-1)/2,
            qMassOutsideViterbiInterval=float(q.sum()-q[lo:hi].sum()))
        va, vb = values['candidate'][i].astype(np.float64), values['hard'][i].astype(np.float64)
        na, nb = float(np.sqrt(va @ va)), float(np.sqrt(vb @ vb))
        cosine, recorded = (None if na == 0 or nb == 0 else 1.-float(va @ vb)/(na*nb)), audit['vectorDistance']['cosineDistance']
        require(all(abs(audit[k]-value) <= v.AUDIT_ATOL for k, value in expected.items())
                and abs(audit['vectorDistance']['l2']-float(np.sqrt((va-vb) @ (va-vb)))) <= v.AUDIT_ATOL
                and (cosine is None) == (recorded is None) and (cosine is None or abs(recorded-cosine) <= v.AUDIT_ATOL),
                f'Row audit differs from independent replay for {row["id"]}')
    return dict(clipId=clip['id'], positions=len(rows), logProbability=z)


def checked_report(plan, plan_binding, report, run, reviewed, env):
    """Complete report, started record and every start/cohort/end/matrix binding; no arrays consumed."""
    order = x.run_order(plan); probes = len(x.SELECTED); ids = order[probes:-probes]; n = len(ids)
    require(report.get('complete') is True and report['study'] == plan['study'] and report['plan'] == plan_binding
            and report['review'] == reviewed and report['environment'] == env
            and report['runner'] == e.file_binding(Path(x.__file__)) and report['outputDirectory'] == str(run)
            and report['runOrder'] == order and report['encoderForwards'] == len(order)
            and report['forwardCounts'] == dict(start=probes, cohort=n, end=probes)
            and report['references'] == {k: plan['inputs'][k] for k in f.REFERENCE_KEYS} and report['model'] == plan['model']
            and report['prerequisites'] == plan['prerequisites']
            and report['sourcePins'] == {p.name: plan['sources'][str(p)] for p in x.new_sources()}
            and report['processId'] != os.getpid(), 'Full report plan/review/runtime/reference/model/source/process binding differs')
    require(all(report[k] is True for k in ('frozenPreflightExact', 'cohortProbesExact', 'repeatsExact', 'freshHardSameForward',
                                            'encoderInferencePerformed', 'historicalControlsDescriptiveOnly', 'freshMatchedControls'))
            and report['historicalHardGate'] is False and all(report[k] is False for k in f.FLAGS),
            'Full report outcome or no-label/no-fit flags differ')
    start, records, end = report['start'], report['records'], report['end']
    require([r['clipId'] for r in start] == x.SELECTED and [r['forward'] for r in start] == list(range(1, probes+1))
            and [r['clipId'] for r in records] == ids and [r['forward'] for r in records] == list(range(probes+1, probes+n+1))
            and [r['clipId'] for r in end] == x.SELECTED and [r['forward'] for r in end] == list(range(probes+n+1, 2*probes+n+1)),
            'Ordered start/cohort/end forward coverage differs')
    expected = {'started.json', 'report.json'} | {k+'.npy' for k in x.KEYS} | {cid+s for cid in ids for s in ('.json', '.npz')} \
        | {stage+'-'+cid+s for stage in ('start', 'end') for cid in x.SELECTED for s in ('.json', '.npz')}
    require({p.name for p in run.iterdir()} == expected, 'Run directory has missing, extra or failure artifacts')
    started = e.read_json(run/'started.json')
    require(started['plan'] == plan_binding and started['review'] == reviewed and started['environment'] == env
            and started['runOrder'] == order and started['processId'] == report['processId']
            and started['expectedForwards'] == len(order) and all(started[k] is False for k in f.FLAGS), 'Started record binding differs')
    for stage, flags in (('start', ('Frozen',)), ('end', ('Start', 'Cohort'))):
        for record in report[stage]:
            cid = record['clipId']
            require(e.read_json(run/(stage+'-'+cid+'.json')) == record and record['stage'] == stage
                    and record['artifact'] == e.file_binding(run/(stage+'-'+cid+'.npz'))
                    and (stage == 'end' or record['frozenArtifact'] == plan['probes']['frozenArtifacts'][cid])
                    and all(record[k+label+'BitExact'] is True for k in x.KEYS for label in flags),
                    f'{stage} probe binding or exactness differs for {cid}')
    for record in records:
        cid = record['clipId']
        require(record['record'] == e.file_binding(run/(cid+'.json')) and record['artifact'] == e.file_binding(run/(cid+'.npz')),
                f'Cohort artifact binding differs for {cid}')
    require(all(report['matrices'][k] == dict(e.file_binding(run/(k+'.npy')), shape=[x.SUPPORT['positions'], x.WIDTH], dtype='float32')
                for k in x.KEYS) and set(report['matrices']) == set(x.KEYS), 'Matrix artifact binding differs')
    return order


def load_matrix(binding):
    require(e.file_binding(Path(binding['path'])) == {k: binding[k] for k in ('path', 'sha256')}, 'Saved matrix hash differs')
    value = np.load(binding['path'], allow_pickle=False)
    require(isinstance(value, np.ndarray) and value.dtype == np.dtype('<f4') and value.shape == (x.SUPPORT['positions'], x.WIDTH)
            and np.isfinite(value).all(), 'Saved matrix geometry, dtype or finiteness differs')
    return value


def checked_record(plan, entry, clip):
    record = e.read_json(Path(entry['record']['path']))
    rows, cid = clip['rows'], clip['id']
    require(e.file_binding(Path(entry['record']['path'])) == entry['record'] and record['stage'] == 'cohort'
            and record['clipId'] == cid and record['forward'] == entry['forward'] and record['seconds'] == entry['seconds']
            and record['roles'] == plan['probes']['roles'].get(cid, []) and record['rowIds'] == [r['id'] for r in rows]
            and record['outputIndices'] == x.indices(clip) and record['shape'] == [len(rows), x.WIDTH] and record['dtype'] == 'float32'
            and record['artifact'] == entry['artifact']
            and record['startProbeMatch'] == ({k+'StartBitExact': True for k in x.KEYS} if cid in x.SELECTED else None),
            f'Cohort record identity, role or probe binding differs for {cid}')
    return record


def verify(plan_path, sha, report_path, review, out):
    # Plan hash and clear review precede report, arrays, audio, posteriors and the model.
    plan_path, report_path, review, out = (Path(p).resolve() for p in (plan_path, report_path, review, out))
    require(e.digest(plan_path) == sha, 'Full plan SHA differs')
    e.base.checked_review(review, sha)
    reviewed = e.file_binding(review)
    require(out.suffix == '.json' and not out.exists() and out.parent.is_dir() and not out.is_relative_to(report_path.parent)
            and not out.is_relative_to(f.OLD) and not out.is_relative_to(x.FRESH)
            and (out.is_relative_to(e.HERE/'outputs') or out.is_relative_to(e.ROOT/'work')),
            'Full exclusive verification JSON required; no restart')
    started = time.monotonic(); diagnosed = []; verified = []; forwards = 0; stage = 'bindings'
    bindings = dict(plan=e.file_binding(plan_path), review=reviewed)
    try:
        plan = x.checked_plan(plan_path, sha)
        env = e.environment(plan['runtime'])
        require(report_path.name == 'report.json', 'Canonical full report required')
        bindings['report'] = e.file_binding(report_path); report = e.read_json(report_path)
        order = checked_report(plan, bindings['plan'], report, report_path.parent, reviewed, env)
        new = x.new_sources()
        require(all(plan['sources'][str(p)] == e.file_binding(p) for p in new), 'Full source pins differ')
        reference = e.checked_references(plan)
        frozen = x.frozen_probes(plan)
        by_id = {c['id']: c for c in plan['clips']}
        stage = 'diagnostics'
        matrices = {k: load_matrix(report['matrices'][k]) for k in x.KEYS}
        covered = np.zeros(x.SUPPORT['positions'], dtype=bool); histories = []; probes = {}
        for entry in report['records']:
            f.check_review(review, reviewed)
            clip = by_id[entry['clipId']]; rows = x.indices(clip); before = time.monotonic()
            record = checked_record(plan, entry, clip)
            values = v.load_arrays(entry['artifact'], clip)
            require(not covered[rows].any(), 'Output index covered more than once'); covered[rows] = True
            require(all(np.array_equal(matrices[k][rows], values[k]) for k in x.KEYS), f'Matrix slice differs from saved unit {clip["id"]}')
            e.guard_clip(clip)
            logp = np.fromfile(clip['posterior']['path'], dtype='<f4').reshape(clip['frames'], 392)
            posterior = v.posterior_checks(logp, clip['fullTokens'])
            result = replay_diagnostics(clip, record, values, posterior)
            history = v.historical_replay(values['hard'], reference[rows])
            require(record['historicalHardDescriptive'] == history, f'Historical descriptive diagnostics differ for {clip["id"]}')
            histories.append(history); diagnosed.append(dict(result, seconds=time.monotonic()-before))
            if clip['id'] in x.SELECTED: probes[clip['id']] = (record, values, posterior)
        require(covered.all() and len(diagnosed) == len(plan['clips']), 'Full output-index or clip diagnostic coverage differs')
        repeats = {}
        for cid in x.SELECTED:
            clip = by_id[cid]; saved = probes[cid][1]
            initial = v.load_arrays(report['start'][x.SELECTED.index(cid)]['artifact'], clip)
            repeats[cid] = v.load_arrays(report['end'][x.SELECTED.index(cid)]['artifact'], clip)
            require(all(np.array_equal(initial[k], frozen[cid][k]) and np.array_equal(saved[k], initial[k])
                        and np.array_equal(repeats[cid][k], initial[k]) for k in x.KEYS),
                    f'Frozen/start/cohort/end probe arrays differ for {cid}')
        stage = 'probe forwards'
        with e.load_encoder(plan) as encoder:
            for cid in x.SELECTED:
                f.check_review(review, reviewed)
                clip = by_id[cid]; (record, saved, posterior), rows = probes[cid], x.indices(clip); before = time.monotonic()
                e.guard_clip(clip)
                logp = np.fromfile(clip['posterior']['path'], dtype='<f4').reshape(clip['frames'], 392)
                samples = e.read_rating_pcm(Path(clip['audioPath']), clip['audioSha256'])
                require(samples.numel() == clip['sampleCount'], 'Original audio sample count differs')
                hidden = encoder(samples); forwards += 1
                # Wrapper in the shape the unchanged reviewed replay_clip expects.
                wrapped = dict(clipId=cid, roles=record['roles'], outputIndices=rows, audit=record['audit'],
                               historicalHardDescriptive=record['historicalHardDescriptive'])
                result = v.replay_clip(clip, wrapped, hidden, logp, saved, repeats[cid], reference[rows], posterior=posterior)
                e.guard_clip(clip)
                verified.append(dict(result, seconds=time.monotonic()-before))
        require(forwards == len(x.SELECTED) and [c['clipId'] for c in verified] == x.SELECTED, 'Four ordered verification forwards required')
        stage = 'final guards'
        e.guard(plan['model'])
        for clip in plan['clips']:
            e.guard_clip(clip)
        e.checked_references(plan)
        e.guard(plan['probes']['frozenArtifacts'])
        x.checked_plan(plan_path, sha)
        require(e.environment(plan['runtime']) == env, 'Runtime changed during verification')
        require(e.file_binding(report_path) == bindings['report'], 'Full report changed during verification')
        f.check_review(review, reviewed)
        # Artifacts verified before the probe forwards must still be bound at completion.
        checked_report(plan, bindings['plan'], report, report_path.parent, reviewed, env)
        history = dict(differingRows=sum(h['differingRows'] for h in histories), rows=sum(h['rows'] for h in histories),
                       maximumAbs=max(h['maximumAbs'] for h in histories), gate=False)
        require(report['historicalHardDescriptive'] == history, 'Report historical descriptive summary differs')
        return e.write_new(out, dict(complete=True, verified=True, separateProcess=True, processId=os.getpid(),
            runnerProcessId=report['processId'], **bindings, environment=env, verifier=e.file_binding(Path(__file__)),
            sourcePins={p.name: plan['sources'][str(p)] for p in new}, prerequisites=plan['prerequisites'],
            orderedClipIds=order[len(x.SELECTED):-len(x.SELECTED)], diagnosticsVerifiedClips=len(diagnosed),
            diagnosticsVerifiedPositions=int(covered.sum()), acousticReplayPositions=sum(c['positions'] for c in verified),
            probes=verified, runnerForwards=report['encoderForwards'], additionalEncoderForwards=forwards,
            totalActualForwards=report['encoderForwards']+forwards, sharedEncoder=True, independentTablesKernel=True,
            independentDPDenseKernel=True, coreHelpersUsedForCandidate=False, fullAcousticReconstruction=False,
            matricesEqualUnits=True, rowCoverageExact=True, frozenPreflightExact=True, cohortProbesExact=True,
            repeatsBitExact=True, hardCrossProcessBitExact=True,
            candidateAbsoluteTolerance=v.CANDIDATE_ATOL, auditAbsoluteTolerance=v.AUDIT_ATOL,
            historicalHardDescriptiveOnly=True, historicalHardDescriptive=history,
            diagnosticSeconds=dict(total=sum(c['seconds'] for c in diagnosed), maximum=max(c['seconds'] for c in diagnosed)),
            peakMemory=dict(value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, units='bytes', system=platform.system(),
                method='process lifetime resource.getrusage(RUSAGE_SELF).ru_maxrss on Darwin'),
            elapsedSeconds=time.monotonic()-started, **f.FLAGS))
    except BaseException as error:
        e.write_new(out, dict(complete=False, verified=False, fullRouteStopped=True, **bindings, stage=stage,
            errorType=type(error).__name__, errorMessage=str(error), errorTraceback=''.join(traceback.format_exception(error)),
            diagnosticsVerifiedClips=len(diagnosed), acousticReplayClips=len(verified), additionalEncoderForwards=forwards,
            sourceBindings={p.name: e.file_binding(p) for p in x.new_sources()},
            elapsedSeconds=time.monotonic()-started, restartAllowed=False, **f.FLAGS))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ('--plan', '--report', '--review', '--out'):
        parser.add_argument(name, required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.plan, args.sha256, args.report, args.review, args.out)))


if __name__ == '__main__': main()
