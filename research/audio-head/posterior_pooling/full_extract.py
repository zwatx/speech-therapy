"""Full 1,040-recording paired posterior-pooling CPU extraction after the passing fresh preflight.

Run from research/audio-head:
  python -m posterior_pooling.full_extract declare --out outputs/.../NEW
  python -m posterior_pooling.full_extract run --plan PLAN --sha256 SHA --review CLEAR --out NEWRUN
The failed v1 route and the passing fresh preflight stay frozen and are never
rerun. Four fixed probes first match the frozen preflight artifacts bit for bit,
then every manifest-ordered recording is read once (the four probes must match
their start forwards), then the four probes repeat: 1,048 forwards, both arms
bit exact. Candidate and fresh hard vectors come from one unchanged v1
extract_clip forward. Historical hard means are descriptive only. No labels,
fits, resume or restart.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import platform
import resource
import time
import traceback

import numpy as np

from posterior_pooling import extract as e, fresh_preflight as f

PROTOCOL = e.ROOT/'docs/model/posterior-pooling-full-extraction-v1.md'
FRESH = e.BASE/'posterior-pooling-fresh-controls-preflight-v1'
PREREQUISITES = {
    'freshPlan': (FRESH/'plan.json', '7fa7cfdd28ec650138cd5ecd53007cc96793946f99d66dd4c2a3b6b3075a7a99'),
    'freshReport': (FRESH/'run/report.json', 'bd6fb43cfa8fd88089c02403bf3203c9a1e25a7d1f2a61ad891be9911999db70'),
    'freshVerification': (f.WORK/'fresh-preflight-verification.json', '8bf83966290bbbddee2073ad3b55f9f324324235f57ca25ce629cf2b68497977'),
    'freshObservation': (f.WORK/'fresh-preflight-root-observation.json', '9098fab1ec4aeec417f526d6c20078399517b209ad37b10aebcef5c1645af77e'),
    'freshResultsReview': (f.WORK/'opus-fresh-results-review.json', '3d6514a116a4cd4a0dec961338b26f1bfa698aad97dbb582853588883c06ab66'),
}
# Frozen preflight per-probe arrays; start probes must equal them bit for bit.
FROZEN = {
    '000010168': '05a9605a743852fb470e294a60ec9a8b905f2fea906f4c1ee35c14befdfc7143',
    '014190030': '717b933d45f8ccbcbcde5684ac9b54b9bf4abe09c86cf0442f976ec7181df8ec',
    '001450051': 'd3bbf9cd4695b5a6a04d7319877e70c58603b08f8ce463db44ff1fd5379a71b7',
    '000560117': '1aa49a3166238d525b709aa68480c464cd5ef0276b9cec2682ed224a788b01fb',
}
SELECTED = list(f.SELECTED)
SUPPORT = dict(clips=1040, positions=9891, children=52, targets=23)
WIDTH, KEYS, FLAGS = f.WIDTH, f.KEYS, f.FLAGS
RECIPE = {k: v for k, v in f.RECIPE.items() if k not in ('version', 'runOrder', 'repeat', 'verifier')} | dict(
    version='posterior-pooling-full-extraction-v1',
    runOrder='four fixed probes, all manifest-ordered clips once, the four fixed probes again; 1048 forwards',
    startProbes='candidate and fresh hard np.array_equal to the frozen preflight artifacts',
    cohortProbes='the four probes, when encountered in cohort order, np.array_equal to their start forwards',
    repeat='four end probes np.array_equal to start and cohort forwards, both arms, no tolerance',
    matrices='two (9891,1024) float32 matrices, every output index assigned once, saved only after all repeats',
    verifier='separate-process full_verify: all-clip independent CTC/kernel diagnostics, four probe forwards',
    resume=False, deviceSwitch=False, historicalControlsDescriptiveOnly=True, freshMatchedControls=True, **FLAGS)


def new_sources():
    here = Path(__file__).resolve().parent
    return [here/name for name in ('full_extract.py', 'full_verify.py', 'test_full_extract.py', 'test_full_verify.py')]


def sources():
    """Frozen fresh closure plus the four full sources, full protocol and prerequisite freezes."""
    bound = f.sources()
    new = new_sources()
    missing = sorted(str(p) for p in f.local_imports(new) if str(p) not in bound and p not in new)
    e.require(not missing, 'Full source import closure incomplete: '+', '.join(missing))
    for path in (*new, PROTOCOL, *(path for path, _ in PREREQUISITES.values())):
        bound[str(Path(path).resolve())] = e.file_binding(Path(path).resolve())
    return dict(sorted(bound.items()))


def frozen_binding(cid):
    return {'path': str(FRESH/'run'/(cid+'.npz')), 'sha256': FROZEN[cid]}


def checked_prerequisites():
    """Passing fresh preflight, verification, root audit and results review; metadata only."""
    pins = {k: e.file_binding(Path(path)) for k, (path, _) in PREREQUISITES.items()}
    e.require(all(pins[k]['sha256'] == sha for k, (_, sha) in PREREQUISITES.items()), 'Frozen fresh preflight prerequisites differ')
    report, verification, observation, review = (e.read_json(Path(pins[k]['path']))
        for k in ('freshReport', 'freshVerification', 'freshObservation', 'freshResultsReview'))
    records = report['records']
    e.require(report['complete'] is True and report['plan'] == pins['freshPlan'] and report['study'] == f.RECIPE['version']
        and report['runOrder'] == SELECTED*2 and report['encoderForwards'] == 8 and report['repeatsExact'] is True
        and [r['clipId'] for r in records] == SELECTED and set(report['repeats']) == set(SELECTED)
        and all(r['artifact'] == frozen_binding(r['clipId']) for r in records)
        and all(report['repeats'][c]['artifact']['sha256'] == FROZEN[c] and report['repeats'][c]['candidateBitExact'] is True
                and report['repeats'][c]['hardBitExact'] is True for c in SELECTED),
        'Fresh preflight report or frozen artifact pins differ')
    e.require(verification['complete'] is True and verification['verified'] is True
        and verification['plan'] == pins['freshPlan'] and verification['report'] == pins['freshReport']
        and verification['review'] == report['review'] and verification['runnerProcessId'] == report['processId']
        and verification['processId'] != report['processId'] and verification['additionalEncoderForwards'] == 4
        and verification['hardCrossProcessBitExact'] is True and verification['orderedCoverage'] == SELECTED,
        'Fresh separate-process verification lineage differs')
    e.require(observation['complete'] is True and observation['runner'] == pins['freshReport']
        and observation['verification'] == pins['freshVerification'] and observation['allWithinRunRepeatsBitExact'] is True
        and observation['hardCrossProcessBitExact'] is True and observation['processesDistinct'] is True
        and observation['totalRealEncoderForwards'] == 12, 'Fresh root observation lineage differs')
    e.require(review['verdict'] == 'clear' and review['reviewer'] == 'claude-opus-5-5' and review['blockingFindings'] == []
        and review['preflightPassed'] is True and review['readyToPrepareFullExtractionDeclaration'] is True
        and review['observedOutcome'] == 'FRESH_CPU_PREFLIGHT_AND_SEPARATE_PROCESS_VERIFICATION_PASS',
        'Fresh results review does not clear full-extraction preparation')
    # Frozen preflight checked function: source/metadata pins must still rebuild exactly; nothing reruns.
    preflight = f.checked_plan(Path(pins['freshPlan']['path']), pins['freshPlan']['sha256'])
    return dict(bindings=pins, frozenArtifacts={c: frozen_binding(c) for c in SELECTED}), preflight


def full_join():
    """Unchanged e._metadata lineage, then unchanged e.join_clips on all manifest clips."""
    pins, selected, _, model, runtime, encoder_recipe = e._metadata()
    keys = ('manifest', 'positionPlan', 'scalarPlan', 'scalarReport', 'mapping', 'vocabulary', 'oldIndex')
    e.guard({k: pins[k] for k in keys})
    manifest, position, sp, sr, recipe, vocabulary, index = (e.read_json(Path(pins[k]['path'])) for k in keys)
    metadata = {cid: {k: entry[k] for k in ('frames', 'vocabularySize', 'audioSha256', 'sampleCount')}
                for cid, entry in index['entries'].items()}
    for cid in sr['newCtcJobs']:
        binding = pins['newCTC/'+cid+'/result']; e.guard({cid: binding}); result = e.read_json(Path(binding['path']))
        e.require(cid not in metadata, 'New CTC result duplicates an old index entry')
        metadata[cid] = dict(frames=result['frames'], vocabularySize=392, audioSha256=result['audioSha256'], sampleCount=result['sampleCount'])
    e.require(set(metadata) == set(sr['posteriorBindings']), 'Old index plus new CTC metadata coverage differs')
    clips = e.join_clips(manifest, position['clips'], sp['clips'], sr['posteriorBindings'], metadata, recipe, vocabulary)
    rows = [r for c in clips for r in c['rows']]
    e.require([c['id'] for c in clips] == [c['id'] for c in manifest['clips']] and len(clips) == SUPPORT['clips']
        and sorted(r['outputIndex'] for r in rows) == list(range(SUPPORT['positions']))
        and len({c['speakerId'] for c in clips}) == SUPPORT['children'] and len({r['targetId'] for r in rows}) == SUPPORT['targets'],
        'Full ordered clip/output-index/child/phone support differs')
    by_id = {c['id']: c for c in clips}
    e.require([by_id.get(cid) for cid in SELECTED] == selected, 'Full join differs from the four declared probes')
    return pins, clips, model, runtime, encoder_recipe


def declaration():
    """Metadata only: no array, audio, weight or CTC payload is opened."""
    prerequisites, preflight = checked_prerequisites()
    pins, clips, model, runtime, encoder_recipe = full_join()
    e.require(pins == preflight['inputs'] and model == preflight['model'] and encoder_recipe == preflight['encoderRecipe']
              and runtime == preflight['runtime'], 'Full inputs, model or runtime differ from the frozen preflight')
    by_id = {c['id']: c for c in clips}
    e.require([by_id[cid] for cid in SELECTED] == preflight['clips'] and preflight['probes']['selectedClipIds'] == SELECTED,
              'Four preflight clips differ from the original declaration')
    return dict(study=RECIPE['version'], recipe=copy.deepcopy(RECIPE), inputs=pins, clips=clips,
        probes=dict(selectedClipIds=list(SELECTED), startClipIds=list(SELECTED), endClipIds=list(SELECTED),
                    roles=copy.deepcopy(preflight['probes']['roles']), frozenArtifacts=prerequisites['frozenArtifacts']),
        support=dict(SUPPORT), model=model, encoderRecipe=encoder_recipe, runtime=runtime,
        prerequisites=prerequisites, sources=sources(), **FLAGS)


def fresh_directory(out, message):
    out = Path(out).resolve()
    e.require(out.is_relative_to(e.HERE/'outputs') and not out.is_relative_to(f.OLD) and not out.is_relative_to(FRESH)
              and not out.exists(), message)
    return out


def declare(out):
    out = fresh_directory(out, 'Full exclusive declaration directory required')
    plan = declaration()
    out.mkdir(parents=True, mode=0o700)
    return e.write_new(out/'plan.json', plan)


def checked_plan(path, sha):
    path = Path(path).resolve()
    e.require(path.is_relative_to(e.HERE/'outputs') and not path.is_relative_to(f.OLD) and not path.is_relative_to(FRESH)
              and path.name == 'plan.json', 'Canonical full plan required')
    e.require(e.digest(path) == sha, 'Full plan SHA differs')
    plan = e.read_json(path)
    e.require(plan == declaration(), 'Full plan source, lineage, metadata, recipe or runtime changed')
    return plan


def run_order(plan):
    """Four start probes, every declared clip once, four end probes; full output-index coverage."""
    probes, ids = plan['probes'], [c['id'] for c in plan['clips']]
    rows = [r['outputIndex'] for c in plan['clips'] for r in c['rows']]
    e.require(probes['selectedClipIds'] == probes['startClipIds'] == probes['endClipIds'] == SELECTED
        and set(probes['frozenArtifacts']) == set(SELECTED) and set(SELECTED) <= set(probes['roles'])
        and len(ids) == len(set(ids)) == SUPPORT['clips'] and set(SELECTED) <= set(ids)
        and sorted(rows) == list(range(SUPPORT['positions'])), 'Declared full clip order, probes or output-index coverage differs')
    return SELECTED+ids+SELECTED


def indices(clip):
    return [r['outputIndex'] for r in clip['rows']]


def bit_exact(values, other, label):
    return {k+label+'BitExact': bool(np.array_equal(values[k], other[k])) for k in KEYS}


def frozen_probes(plan):
    """Actual run only: the four frozen preflight arrays behind their pinned hashes."""
    frozen, by_id = {}, {c['id']: c for c in plan['clips']}
    for cid in SELECTED:
        binding = plan['probes']['frozenArtifacts'][cid]
        e.require(binding == frozen_binding(cid) and e.file_binding(Path(binding['path'])) == binding, 'Frozen preflight artifact differs')
        with np.load(binding['path'], allow_pickle=False) as archive:
            e.require(set(archive.files) == set(KEYS), 'Frozen preflight artifact keys differ')
            frozen[cid] = f.checked_values({k: archive[k].copy() for k in KEYS}, by_id[cid])
    return frozen


def assign(matrices, assigned, rows, values):
    e.require(not assigned[rows].any(), 'Output index assigned more than once')
    for k in KEYS:
        matrices[k][rows] = values[k]
    assigned[rows] = True


def save_matrix(path, value):
    with Path(path).open('xb') as stream:
        Path(path).chmod(0o600)
        np.save(stream, value, allow_pickle=False)
    return dict(e.file_binding(Path(path)), shape=list(value.shape), dtype='float32')


def run(path, sha, review, out):
    # Plan hash and clear review precede source recomputation, reference arrays, audio, posteriors and the model.
    path, review = Path(path).resolve(), Path(review).resolve()
    e.require(e.digest(path) == sha, 'Full plan SHA differs')
    e.base.checked_review(review, sha)
    reviewed = e.file_binding(review)
    plan = checked_plan(path, sha)
    env = e.environment(plan['runtime'])
    order = run_order(plan)
    out = fresh_directory(out, 'Full run directory required; preserve partial outputs, no implicit restart')
    out.mkdir(parents=True, mode=0o700)
    e.write_new(out/'started.json', dict(plan=e.file_binding(path), review=reviewed, environment=env, runOrder=order,
        expectedForwards=len(order), processId=os.getpid(), **FLAGS))
    started = time.monotonic(); counts = dict(start=0, cohort=0, end=0); forwards = 0; stage = 'references'
    start, records, end, histories = [], [], [], []
    try:
        by_id, roles = {c['id']: c for c in plan['clips']}, plan['probes']['roles']
        # Exact 28227-to-9891 reference/scalar lineage and frozen probe pins precede every forward.
        reference = e.checked_references(plan)
        frozen = frozen_probes(plan)
        e.guard(plan['model'])
        for clip in plan['clips']:
            e.guard_clip(clip)
        shape = (SUPPORT['positions'], WIDTH)
        matrices = {k: np.full(shape, np.nan, dtype=np.float32) for k in KEYS}; assigned = np.zeros(shape[0], dtype=bool)
        initial, cohort = {}, {}
        with e.load_encoder(plan) as encoder:
            def forward(cid):
                nonlocal forwards
                f.check_review(review, reviewed)
                clip = by_id[cid]; before = time.monotonic()
                values, audit = e.extract_clip(encoder, clip); forwards += 1
                return clip, f.checked_values(values, clip), audit, before

            def unit(stage, clip, values, before, **fields):
                # Arrays and the record are persisted before any exactness gate raises.
                name = clip['id'] if stage == 'cohort' else stage+'-'+clip['id']
                record = dict(stage=stage, clipId=clip['id'], forward=forwards, roles=roles.get(clip['id'], []),
                    rowIds=[r['id'] for r in clip['rows']], outputIndices=indices(clip), shape=[len(clip['rows']), WIDTH],
                    dtype='float32', artifact=f.save_arrays(out/(name+'.npz'), values), **fields, seconds=time.monotonic()-before)
                return record, e.write_new(out/(name+'.json'), record)

            stage = 'start'
            for cid in SELECTED:
                clip, values, _, before = forward(cid)
                exact = bit_exact(values, frozen[cid], 'Frozen')
                record, _ = unit('start', clip, values, before, frozenArtifact=plan['probes']['frozenArtifacts'][cid], **exact)
                start.append(record)
                e.require(all(exact.values()), f'Start probe {cid} differs from frozen preflight: {exact}')
                initial[cid] = values; counts['start'] += 1
            stage = 'cohort'
            for cid in order[len(SELECTED):-len(SELECTED)]:
                clip, values, audit, before = forward(cid)
                probe = bit_exact(values, initial[cid], 'Start') if cid in initial else None
                history = f.historical_differences(values['hard'], reference[indices(clip)])
                record, binding = unit('cohort', clip, values, before, audit=audit, historicalHardDescriptive=history, startProbeMatch=probe)
                records.append(dict(clipId=cid, forward=forwards, record=binding, artifact=record['artifact'], seconds=record['seconds']))
                e.require(probe is None or all(probe.values()), f'Cohort probe {cid} differs from its start probe: {probe}')
                assign(matrices, assigned, indices(clip), values)
                histories.append(history)
                if cid in initial: cohort[cid] = values
                counts['cohort'] += 1
            stage = 'end'
            for cid in SELECTED:
                clip, values, _, before = forward(cid)
                exact = bit_exact(values, initial[cid], 'Start') | bit_exact(values, cohort[cid], 'Cohort')
                record, _ = unit('end', clip, values, before, **exact)
                end.append(record)
                e.require(all(exact.values()), f'End probe {cid} differs from start/cohort forwards: {exact}')
                counts['end'] += 1
        stage = 'assembly'
        e.require(forwards == len(order) and counts == dict(start=len(SELECTED), cohort=len(plan['clips']), end=len(SELECTED)),
                  'Exact ordered forward count differs')
        e.require(assigned.all() and all(np.isfinite(m).all() for m in matrices.values()),
                  'Every output index must be assigned exactly once with finite values')
        for entry in records:
            # Persisted per-clip units, not in-memory copies, must equal the assembled slices.
            e.require(e.file_binding(Path(entry['artifact']['path'])) == entry['artifact'], 'Saved clip artifact changed')
            with np.load(entry['artifact']['path'], allow_pickle=False) as archive:
                rows = indices(by_id[entry['clipId']])
                e.require(all(np.array_equal(archive[k], matrices[k][rows]) for k in KEYS), 'Assembled matrix differs from saved clip unit')
        stage = 'final guards'
        e.guard(plan['model'])
        for clip in plan['clips']:
            e.guard_clip(clip)
        e.checked_references(plan)
        e.guard(plan['probes']['frozenArtifacts'])
        checked_plan(path, sha)
        e.require(e.environment(plan['runtime']) == env, 'Runtime changed during full extraction')
        f.check_review(review, reviewed)
        e.guard({r['record']['path']: r['record'] for r in records})
        for record in start+end:
            e.require(e.file_binding(Path(record['artifact']['path'])) == record['artifact']
                      and e.read_json(out/(record['stage']+'-'+record['clipId']+'.json')) == record,
                      'Saved probe artifact or record changed before completion')
        stage = 'persist'
        saved = {k: save_matrix(out/(k+'.npy'), matrices[k]) for k in KEYS}
        seconds = [r['seconds'] for r in records]
        return e.write_new(out/'report.json', dict(complete=True, study=plan['study'], plan=e.file_binding(path),
            review=reviewed, environment=env, runner=e.file_binding(Path(__file__)), processId=os.getpid(),
            outputDirectory=str(out), runOrder=order, encoderForwards=forwards, forwardCounts=counts,
            start=start, records=records, end=end, matrices=saved,
            rowOrder='matrix row i is outputIndex i, aligned with declared rowIndices and scalars',
            references={k: plan['inputs'][k] for k in f.REFERENCE_KEYS}, model=plan['model'],
            prerequisites=plan['prerequisites'], sourcePins={p.name: plan['sources'][str(p)] for p in new_sources()},
            probeMatches={cid: dict(frozen=True, cohortVsStart=True, endVsStart=True, endVsCohort=True) for cid in SELECTED},
            frozenPreflightExact=True, cohortProbesExact=True, repeatsExact=True, freshHardSameForward=True,
            historicalHardGate=False, historicalControlsDescriptiveOnly=True, freshMatchedControls=True,
            historicalHardDescriptive=dict(differingRows=sum(h['differingRows'] for h in histories),
                rows=sum(h['rows'] for h in histories), maximumAbs=max(h['maximumAbs'] for h in histories), gate=False),
            cohortClipSeconds=dict(total=sum(seconds), maximum=max(seconds)),
            peakMemory=dict(value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, units='bytes', system=platform.system(),
                method='process lifetime resource.getrusage(RUSAGE_SELF).ru_maxrss on Darwin'),
            elapsedSeconds=time.monotonic()-started, encoderInferencePerformed=True, **FLAGS))
    except BaseException as error:
        e.write_new(out/'failure.json', dict(complete=False, successFrozen=False, planSha256=sha, stage=stage,
            errorType=type(error).__name__, errorMessage=str(error), errorTraceback=''.join(traceback.format_exception(error)),
            completedForwards=counts, encoderForwards=forwards,
            forwardCountSemantics='completed extract_clip calls; an encoder call inside a failing extract_clip is not counted',
            artifacts={p.name: e.file_binding(p) for p in sorted(out.iterdir()) if p.name != 'failure.json'},
            elapsedSeconds=time.monotonic()-started, partialOutputsPreserved=True, restartAllowed=False, **FLAGS))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('declare').add_argument('--out', required=True, type=Path)
    runner = commands.add_parser('run')
    for name in ('--plan', '--review', '--out'):
        runner.add_argument(name, required=True, type=Path)
    runner.add_argument('--sha256', required=True)
    args = parser.parse_args()
    result = declare(args.out) if args.command == 'declare' else run(args.plan, args.sha256, args.review, args.out)
    print(json.dumps(result))


if __name__ == '__main__': main()
