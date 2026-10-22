"""Complete occurrence-aware scalar export, reusing old CTC and adding five clips."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

import multiphone_local_features as local
import multiphone_position_geometry as geometry
from multiphone_sequence_preflight import binding, guard, read_bound, require, write_new

HERE = Path(__file__).resolve().parent
BASE = HERE/'outputs/multiphone-20260926'
PROTOCOL = HERE/'../../docs/model/multiphone-position-geometry-protocol.md'
PINS = {
    'oldManifest': (BASE/'ctc-local-full/manifest.json', '65c3118b2ff14e7fcb115a8c0fb2fa195a6811ef14f3523eebd8b8902849e4d5'),
    'oldIndex': (BASE/'ctc-local-full/ctc-frames/index.json', 'ce21dcc8b47b6383509f64282adebe752bb79442231917a4012cb0c30845dc3e'),
    'oldConfig': (BASE/'ctc-local-full/ctc-frames/config.json', '89854c61a0396090dd934b936a9853440e5e7f5723e61cb2d08d4bebfd7dc76a'),
    'oldFeatures': (BASE/'ctc-local-full/features/features.json', 'd6dbcb1d4d36153af2e13577fb4e39d4c23e6cabcb511f69990b968dbde6279a'),
    'mapping': (local.RECIPE, '6ada55352a010f566ee3ebdcad36d90fd9c5a0da236cf2016bb2f6fc3d473eb0'),
    'vocabulary': (local.VOCAB, local.VOCAB_SHA),
}
MISSING = ['000530027', '001040026', '005600146', '010420047', '096110011']
OPTIONS = dict(intraOpNumThreads=2, interOpNumThreads=1, executionMode='sequential')


def inputs(data_report, data_sha):
    pins = {k: binding(*value) for k, value in PINS.items()}
    pins['dataReport'] = binding(data_report, data_sha)
    report = read_bound(pins['dataReport'])
    require(report['complete'] is True, 'Completed reviewed data report required')
    for key in ('cohort', 'splits'):
        pins[key] = report['outputs'][key]
    cohort, splits = (read_bound(pins[k]) for k in ('cohort', 'splits'))
    require(cohort['authorPartition'] == splits['authorPartition'] == 'train' and
            len(cohort['rows']) == 28227 and len(cohort['clips']) == 2500 and
            cohort['learnerFeedbackEligible'] is False, 'Unexpected complete position cohort')
    old_manifest, index, config, original = (read_bound(pins[k]) for k in
                                           ('oldManifest', 'oldIndex', 'oldConfig', 'oldFeatures'))
    require(index['complete'] is True and index['configSha256'] == pins['oldConfig']['sha256'] and
            config['manifestSha256'] == pins['oldManifest']['sha256'] and
            original['ctcIndexSha256'] == pins['oldIndex']['sha256'] and
            original['manifestSha256'] == pins['oldManifest']['sha256'], 'Historical CTC lineage differs')
    old_clips = {c['id']: c for c in old_manifest['clips']}
    require(set(index['entries']) == set(old_clips) and len(old_clips) == 2495 and
            sorted(c['id'] for c in cohort['clips'] if c['id'] not in old_clips) == MISSING,
            'Original/new CTC coverage differs')
    rows_by_clip = defaultdict(list)
    for ri, row in enumerate(cohort['rows']):
        rows_by_clip[row['clipId']].append(dict(row, rowIndex=ri))
    clips = []
    for source in cohort['clips']:
        clip = {key: source[key] for key in ('id', 'speakerId', 'age', 'sampleCount', 'audioPath', 'audioSha256', 'canonicalPhones')}
        # Strip ratings/notes at the feature boundary.
        clip['words'] = [{'text': w['text'], 'phones': w['phones']} for w in source['words']]
        clip['rows'] = [{k: r[k] for k in geometry.POSITION_FIELDS+('rowIndex',)} for r in rows_by_clip[clip['id']]]
        require(clip['rows'], 'Every train clip must have positions')
        pins['audio/'+clip['id']] = binding(clip['audioPath'], clip['audioSha256'])
        if clip['id'] in old_clips:
            old = old_clips[clip['id']]
            require(all(clip[k] == old[k] for k in ('id', 'speakerId', 'sampleCount', 'audioPath', 'audioSha256', 'canonicalPhones')),
                    'Existing source clip changed')
            entry = index['entries'][clip['id']]
            cache = Path(pins['oldIndex']['path']).parent
            path = (cache/entry['path']).resolve()
            require(path.is_relative_to(cache) and entry['audioSha256'] == clip['audioSha256'] and
                    entry['configSha256'] == pins['oldConfig']['sha256'] and
                    entry['frames'] == local.convolution_frames(clip['sampleCount'], read_bound(pins['mapping'])) and
                    path.stat().st_size == entry['frames']*392*4, 'Cached posterior identity differs')
            pins['posterior/'+clip['id']] = binding(path, entry['sha256'])
        clips.append(clip)
    for name in ('multiphone_position_scalar_export.py', 'multiphone_position_geometry.py',
                 'test_multiphone_position_geometry.py', 'test_multiphone_position_scalar_export.py',
                 'multiphone_local_features.py', 'alignment_pilot.py', 'multiphone_sequence_preflight.py',
                 'multiphone_research_ctc.ts', 'multiphone_ctc_cache.ts'):
        pins['source/'+name] = binding(HERE/name)
    for name in ('packages/audio-model-adapter/src/model-cache.ts', 'packages/audio-model-adapter/src/manifest.ts',
                 'pnpm-lock.yaml'):
        pins['source/'+name] = binding(HERE.parent.parent/name)
    node = shutil.which('node')
    require(node is not None and subprocess.check_output([node, '--version'], text=True).strip() == config['node'],
            'Expected original Node runtime')
    pins['runtime/node'] = binding(node)
    pins['runtime/python'] = binding(sys.executable)
    pins['protocol'] = binding(PROTOCOL)
    guard(pins)
    return clips, pins, config['checkpoint']


def declare(data_report, data_sha, output):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(), 'Fresh ignored output required')
    clips, pins, checkpoint = inputs(data_report, data_sha)
    output.mkdir(mode=0o700)
    return write_new(output/'plan.json', dict(declaredAt=datetime.now(timezone.utc).isoformat(), clips=clips,
        inputs=pins, ctcCheckpoint=checkpoint, ctcSessionOptions=OPTIONS, newCtcIds=MISSING,
        scalarNames=local.SCALAR_NAMES, numpy=np.__version__, python=sys.version,
        featureCalculationPerformed=False, modelInferencePerformed=False, trainingPerformed=False))


def load_plan(path, sha):
    path = Path(path).resolve()
    require(path.is_relative_to(HERE/'outputs'), 'Plan outside research outputs')
    plan = read_bound(dict(path=str(path), sha256=sha))
    data = plan['inputs']['dataReport']
    clips, pins, checkpoint = inputs(data['path'], data['sha256'])
    require(plan['clips'] == clips and plan['inputs'] == pins and plan['ctcCheckpoint'] == checkpoint and
            plan['ctcSessionOptions'] == OPTIONS and plan['newCtcIds'] == MISSING and
            plan['scalarNames'] == local.SCALAR_NAMES and plan['numpy'] == np.__version__ and
            plan['python'] == sys.version and all(plan[k] is False for k in
                ('featureCalculationPerformed', 'modelInferencePerformed', 'trainingPerformed')), 'Declaration changed')
    return plan


def expected_job(clip, plan, plan_pin):
    bindings = {k: v for k, v in plan['inputs'].items() if k.startswith(('source/', 'runtime/'))}
    bindings.update(plan=plan_pin, audio=plan['inputs']['audio/'+clip['id']])
    return dict(schemaVersion=1, researchOnly=True, audioPath=clip['audioPath'], audioSha256=clip['audioSha256'],
        sampleCount=clip['sampleCount'], expectedFrames=local.convolution_frames(clip['sampleCount'], read_bound(plan['inputs']['mapping'])),
        bindings=bindings, ctcCheckpoint=plan['ctcCheckpoint'], sessionOptions=OPTIONS)


def posterior(clip, plan, plan_pin, root, calculate):
    key = 'posterior/'+clip['id']
    if key in plan['inputs']:
        return plan['inputs'][key], None
    directory = root/'new-ctc'/clip['id']
    expected = expected_job(clip, plan, plan_pin)
    if calculate:
        directory.mkdir(parents=True, mode=0o700)
        job_pin = write_new(directory/'job.json', expected)
        subprocess.run([plan['inputs']['runtime/node']['path'], str(HERE/'multiphone_research_ctc.ts'),
            job_pin['path'], job_pin['sha256']], check=True,
            env={**os.environ, 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2'})
    else:
        job_pin = binding(directory/'job.json')
        require(read_bound(job_pin) == expected, 'Saved new CTC job differs')
    result_pin = binding(directory/'ctc.json')
    result = read_bound(result_pin)
    require(result['complete'] is True and result['jobSha256'] == job_pin['sha256'] and
            result['audioSha256'] == clip['audioSha256'] and result['sampleCount'] == clip['sampleCount'] and
            result['frames'] == expected['expectedFrames'] and result['checkpoint'] == plan['ctcCheckpoint'] and
            result['sessionOptions'] == OPTIONS and result['fetchAttempts'] == 0 and
            result['node'] == read_bound(plan['inputs']['oldConfig'])['node'] and result['posteriorsPath'] == 'ctc.f32',
            'New CTC result lineage differs')
    return binding(directory/'ctc.f32', result['posteriorsSha256']), dict(job=job_pin, result=result_pin)


def assemble(plan, plan_pin, root, calculate):
    recipe, vocab, old = (read_bound(plan['inputs'][k]) for k in ('mapping', 'vocabulary', 'oldFeatures'))
    legacy = defaultdict(list)
    for row in old['rows']: legacy[row['clipId']].append(row)
    diagnostics = {c['clipId']: c for c in old['clipDiagnostics']}
    if calculate: (root/'clips').mkdir(mode=0o700)
    rows, artifacts, posterior_pins, new_jobs = [], {}, {}, {}
    parity = groups = repeated = 0
    for number, clip in enumerate(plan['clips'], 1):
        pin, job = posterior(clip, plan, plan_pin, root, calculate)
        posterior_pins[clip['id']] = pin
        if job is not None: new_jobs[clip['id']] = job
        logp = np.fromfile(pin['path'], dtype='<f4').reshape((-1, 392))
        computed = geometry.clip_geometry(clip, clip['rows'], logp, recipe, vocab)
        parity += geometry.legacy_parity(computed, legacy[clip['id']], diagnostics.get(clip['id']))
        groups += computed['repeatedTargetGroups']; repeated += computed['repeatedPositions']
        for row, source in zip(computed['rows'], clip['rows'], strict=True): row['rowIndex'] = source['rowIndex']
        path = root/'clips'/(clip['id']+'.json')
        if calculate: artifacts[clip['id']] = write_new(path, computed)
        else:
            artifacts[clip['id']] = binding(path)
            require(read_bound(artifacts[clip['id']]) == computed, 'Saved geometry differs')
        rows.extend(computed['rows'])
        if number % 100 == 0: print(json.dumps(dict(clips=number, positions=len(rows), legacyParity=parity)), flush=True)
    require(len(rows) == 28227 and parity == 14837 and sorted(new_jobs) == MISSING and
            [r['rowIndex'] for r in rows] == list(range(28227)) and len({r['id'] for r in rows}) == len(rows),
            'Final geometry/legacy/new-CTC coverage differs')
    matrix = np.asarray([r['scalarFeatures'] for r in rows], dtype=np.float32)
    matrix_path = root/'scalars.npy'
    if calculate:
        with matrix_path.open('xb') as stream: np.save(stream, matrix, allow_pickle=False)
        matrix_path.chmod(0o600)
    else:
        saved = np.load(matrix_path, allow_pickle=False)
        require(saved.dtype == matrix.dtype and np.array_equal(saved, matrix), 'Saved scalar matrix differs')
    guard({**plan['inputs'], **{'derived/'+k: v for k, v in artifacts.items()},
           **{'ctc/'+k: v for k, v in posterior_pins.items()}, 'plan': plan_pin})
    ages = {c['id']: c['age'] for c in plan['clips']}
    support = {band: {phone: sum(r['targetPhone'] == phone and
        (band == 'all' or 6 <= ages[r['clipId']] <= 12) for r in rows) for phone in recipe['consonants'] if phone != 'ZH'}
        for band in ('all', 'child6to12')}
    return dict(complete=True, plan=plan_pin, inputs=plan['inputs'], clips=len(plan['clips']), positions=len(rows),
        legacyParity=parity, repeatedTargetGroups=groups, repeatedPositions=repeated, support=support,
        clipArtifacts=artifacts, posteriorBindings=posterior_pins, newCtcJobs=new_jobs,
        matrix=dict(**binding(matrix_path), dtype='float32', shape=list(matrix.shape), columns=local.SCALAR_NAMES),
        rowIds=[r['id'] for r in rows], featureCalculationPerformed=True, newCtcInferences=len(new_jobs),
        authorPartition='train', authorTestInferencePerformed=False, hiddenVectorsExtracted=False,
        trainingPerformed=False, learnerFeedbackEligible=False, clinicalUseEligible=False,
        frameTimesValidated=False, labelsUsedForExtraction=False)


def execute(path, sha, verify=False):
    path = Path(path).resolve(); root = path.parent
    plan = load_plan(path, sha)
    if not verify: require(not (root/'clips').exists() and not (root/'report.json').exists(), 'No implicit restart')
    try:
        report = assemble(plan, dict(path=str(path), sha256=sha), root, not verify)
        if verify:
            require(json.loads((root/'report.json').read_text()) == report, 'Saved export report differs')
            return dict(verified=True, report=binding(root/'report.json'))
        return write_new(root/'report.json', report)
    except Exception as error:
        if not verify and not (root/'failure.json').exists():
            write_new(root/'failure.json', dict(complete=False, error=f'{type(error).__name__}: {error}'))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['declare', 'run', 'verify'])
    parser.add_argument('--data-report', type=Path); parser.add_argument('--data-sha256')
    parser.add_argument('--output', type=Path); parser.add_argument('--plan', type=Path); parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.command == 'declare':
        require(args.data_report is not None and args.data_sha256 and args.output is not None, 'Data report/hash/output required')
        result = declare(args.data_report, args.data_sha256, args.output)
    else:
        require(args.plan is not None and args.plan_sha256, 'Plan/hash required')
        result = execute(args.plan, args.plan_sha256, args.command == 'verify')
    print(json.dumps(result, sort_keys=True))
