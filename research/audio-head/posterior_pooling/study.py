"""Paired posterior-pooled versus fresh-hard compact heads on the 75 fixed cells.

Run from research/audio-head, one exclusive phase at a time:
  python -m posterior_pooling.study declare --out outputs/multiphone-20260927/NEW
  python -m posterior_pooling.study controls --plan PLAN --sha256 SHA --review CLEAR
  python -m posterior_pooling.study inner --plan PLAN --sha256 SHA --review CLEAR
  python -m posterior_pooling.study refit --plan PLAN --sha256 SHA --review CLEAR --freeze INNER --freeze-sha256 SHA
  python -m posterior_pooling.study outer --plan PLAN --sha256 SHA --review CLEAR --freeze REFIT --freeze-sha256 SHA
  python -m posterior_pooling.study verify --plan PLAN --sha256 SHA --phase PHASE [--freeze FREEZE --freeze-sha256 SHA]
Both acoustic arms use the passed full extraction's candidate and fresh hard
(9891,1024) matrices with the original raw-1024 PCA16 compact trainer; the
historical compact features are never a control. Before any fit, all 75
original scalar controls are validated and replayed. An explicit scientific
incompatibility routes every cell to a fresh scalar fit; malformed, drifted or
unbound lineage stops. experiment='lexical-seed-replication-v1' is only the
frozen trainer's compatibility tag; study/arm/representation identify this study.
"""
from __future__ import annotations

import argparse
import ast
import functools
import json
from pathlib import Path
import time
import traceback

import numpy as np
import torch

from lexical_feasibility.study import word_group
from lexical_seed_replication import core, study as historical, validation
from middle_layer import heads
from middle_layer_replication import study as previous
from posterior_pooling import extract as e, fresh_preflight as f, full_extract as x

files, read, require = historical.files, historical.read, historical.require
HERE, ROOT, BASE = e.HERE, e.ROOT, e.BASE
STUDY = 'posterior-pooling-model-comparison-v1'
LEGACY_EXPERIMENT = 'lexical-seed-replication-v1'
PROTOCOL = ROOT/'docs/model/posterior-pooling-model-comparison-v1.md'
FULL = BASE/'posterior-pooling-full-extraction-v1'
SEEDS = (17, 29, 43)
ROLES = ('fitRows', 'selectionRows', 'addedValidationRows', 'refitRows')
ARMS = ('candidate', 'freshHard')
MATRIX_KEYS = dict(candidate='candidate', freshHard='hard')
REPRESENTATIONS = dict(candidate='posterior-weighted-final-1024', freshHard='fresh-hard-interval-mean-final-1024',
                       scalar='position-scalars-13')
TEMPORAL_REPRESENTATION = 'final-pre-interval-post'
CELLS, POSITIONS, OUTER_POSITIONS, WIDTH, SCALAR_WIDTH = 75, 9891, 5654, 1024, 13
PHASES = {'inner': 'inner', 'outer-refit': 'refit'}
FIT_ROLE = {'inner': 'fitRows', 'outer-refit': 'refitRows'}
RUN_FILES = frozenset({'config.json', 'weights.json', 'prior.json', 'initial.pt', 'best.pt', 'last.pt', 'history.json', 'report.json'})
SELECTION_FILES = frozenset({'selection.json', 'selected-replay.json'})
STATES = ('initial.pt', 'best.pt', 'last.pt')
FLAGS = dict(heads.FLAGS, learnerJudgmentsEnabled=False, encoderUpdated=False, newAlignmentPerformed=False)
LINEAGE = {
    'fullPlan': (FULL/'plan.json', 'e84733457ab5ce7577044010baafeaeb317e8a6e66f68489915fcf3eefe11a7c'),
    'fullReport': (FULL/'run/report.json', '456802fb6b6519dc170d59a66896a9176ec2af7b5395639fcd383d0ae987bd0a'),
    'fullVerification': (f.WORK/'full-extraction-verification.json', '6da9d0a19ccfc5431a4dc94908571c0fc1cc96622336f8271e86c8c9580db59b'),
    'fullRootObservation': (f.WORK/'full-extraction-root-observation.json', '87a0910fc7791526b588eb466958d448e43ee7c2f11dc257378be340e68e1eae'),
    'fullRunnerRootObservation': (f.WORK/'full-extraction-runner-root-observation.json', 'f1f32116bb8785cea2aede353e46ce1ab8609924f5ae0fb8f000bc4676d9c940'),
    'fullResultsReview': (f.WORK/'opus-full-results-review.json', '2fb67584d72dd5ee92e33a73173a830d99a2b39da7dd9f9af17efda0877bead2'),
    'fullSourceReview': (f.WORK/'astra-full-source-review.json', '7db9e2a1f16566b712a073fd763b8a40a758f6cbeae1f535f52dbc1de3bda18e'),
    'protocolReview': (f.WORK/'astra-training-protocol-review.json', '58cad38fb41be564acd592fb2299e3ed760b9652a3642ace95172ac3c9baddd7'),
    'protocol': (PROTOCOL, 'ef76090f89513171a712f75896ac4e849ad7f0d47cac57858003375dc0e75fcf'),
    'temporalPlan': (BASE/'temporal-pooling-heads-v1/plan.json', '3dccff741a91de7185484479d467d732dca5cbd100d59b33b7b32b142626a151'),
    'priorProbePlan': (BASE/'middle-layer-replication-v1/plan.json', 'fd24799ff5e1226f7c14514b4c09e52e7781937710e2c3efe69b94e32ad1cef0'),
    'priorProbeFreeze': (BASE/'middle-layer-replication-v1/controls-freeze.json', 'b5a9453cd2afdae905250c735ef79af3d6d22381d94e3abff0a327f7c446df0a'),
    'priorProbeReview': (ROOT/'work/middle-layer-replication-review-20260927/results-review.json', '835ea9a253fce0c4fc1cb9b2b4cfada51fb520fc1121fcd0384ae163f6e2333d'),
    **{key: previous.PINS[key] for key in ('historicalPlan', 'historicalInner', 'historicalRefit', 'historicalOuter')},
}
MATRICES = {'candidate': '73c5200e7d5d1e5008012fe5ff7fa3e19977aaa18919fedf306284380b34bcbe',
            'hard': '06ee1d2a63ad431dc182e9ca26e6c3301b811d542d38b4f95fa0244ece2af8d0'}
PROBE_INPUTS = ('historicalPlan', 'historicalInner', 'historicalRefit', 'historicalOuter', 'cohort',
                'historicalFeatureReport', 'historicalScalars')
GATES = dict(
    pooledMixtureNllDelta='< -1e-7', relativeNllReduction='>= 0.05 of the same-seed fresh-hard mixture NLL',
    rating0ApDelta='>= +0.01', foldMixtureNllDelta='<= 1e-7 at each of the five speaker folds',
    macroNllDelta='<= 1e-7', brierDelta='<= 1e-7', below2ApDelta='>= -1e-7', compactNllDelta='< -1e-7',
    seeds='17, 29 and 43 must each pass; no seed selection or averaged rescue',
    ageGuard='fail if any age 6-12 mixture NLL worsens by more than 1e-7 at all three seeds',
    phoneGuard='fail if any of the 23 consonants mixture NLL worsens by more than 1e-7 at all three seeds',
    undefinedPrimary='undefined or nonfinite primary endpoints invalidate the evaluation',
    undefinedSubgroupAp='null with its actual positive/negative support')
LIMITATIONS = [
    'Independent acoustic replay covered only the 37 probe positions; all 9891 vectors rely on the shared original '
    'encoder, cross-process probe determinism and full-cohort diagnostic replay (fullAcousticReconstruction=false).',
    'Historical compact features differ from the fresh hard matrix on 2094 of 9891 rows (maximum 2.29e-5); they are '
    'descriptive only and never a control.',
    'Development evidence on an extensively explored cohort, not untouched confirmation.',
    'No learner judgments, clinical use, promotion or independent final validation, even if every gate passes.',
    'Independent child production/localization, recording-usability and nonspeech references remain missing.']

PASS, SKIP = 'pass', 'not-evaluated'
GLOBAL_CHECKS = ('historicalRuntime', 'historicalRecipe', 'historicalTrainerSource', 'parityReceipt')
CELL_CHECKS = ('recipe', 'fittingWeights', 'fitPriors', 'normalization', 'initialState',
               'selectionReplay', 'outerReplay', 'savedState')
CODES = ('historical-runtime-differs', 'historical-recipe-differs',
         'recipe-differs', 'fitting-weights-differ', 'fit-priors-differ', 'normalization-differs',
         'initial-state-differs', 'selection-replay-differs', 'outer-replay-differs')


class IntegrityFailure(ValueError):
    """Malformed, drifted or unbound lineage: stop under this declaration; never a fallback."""


class CompatibilityFailure(Exception):
    """A valid old scalar state that is scientifically incompatible with the current trainer."""

    def __init__(self, code, detail=''):
        integrity(code in CODES, 'Unknown compatibility reason code: '+str(code))
        super().__init__(code if not detail else f'{code}: {detail}')
        self.code = code


def integrity(condition, message):
    if not condition:
        raise IntegrityFailure(message)


def compatible(condition, code):
    if not condition:
        raise CompatibilityFailure(code)


def outcome(check):
    """Only an explicit CompatibilityFailure becomes a reason code; everything else stops."""
    try:
        check()
    except CompatibilityFailure as failure:
        return failure.code
    return PASS


# ---------------------------------------------------------------- declaration

def checked_extraction(pins):
    """Passed full plan/report/verification/root observation/reviews; metadata only, nothing reruns."""
    full = x.checked_plan(pins['fullPlan']['path'], pins['fullPlan']['sha256'])
    report, verification, root, results, source, protocol = (read(pins[k]) for k in (
        'fullReport', 'fullVerification', 'fullRootObservation', 'fullResultsReview', 'fullSourceReview', 'protocolReview'))
    integrity(report.get('complete') is True and report['study'] == full['study'] and report['plan'] == pins['fullPlan']
              and report['review'] == pins['fullSourceReview'] and report['encoderForwards'] == 1048
              and report['forwardCounts'] == dict(start=4, cohort=1040, end=4)
              and all(report[k] is True for k in ('frozenPreflightExact', 'cohortProbesExact', 'repeatsExact',
                                                  'freshHardSameForward', 'historicalControlsDescriptiveOnly', 'freshMatchedControls'))
              and report['historicalHardGate'] is False and all(report[k] is False for k in f.FLAGS)
              and report['references'] == {k: full['inputs'][k] for k in f.REFERENCE_KEYS}, 'Passed full runner report lineage differs')
    for key, sha in MATRICES.items():
        matrix = report['matrices'][key]
        integrity(matrix['sha256'] == sha and matrix['shape'] == [POSITIONS, WIDTH] and matrix['dtype'] == 'float32'
                  and Path(matrix['path']).parent == Path(pins['fullReport']['path']).parent, 'Pinned feature matrix binding differs: '+key)
    integrity(verification.get('complete') is True and verification['verified'] is True and verification['plan'] == pins['fullPlan']
              and verification['report'] == pins['fullReport'] and verification['review'] == pins['fullSourceReview']
              and verification['runnerProcessId'] == report['processId'] != verification['processId']
              and verification['diagnosticsVerifiedPositions'] == POSITIONS and verification['diagnosticsVerifiedClips'] == 1040
              and verification['acousticReplayPositions'] == 37 and verification['fullAcousticReconstruction'] is False
              and all(verification[k] is True for k in ('matricesEqualUnits', 'rowCoverageExact', 'hardCrossProcessBitExact',
                                                        'historicalHardDescriptiveOnly', 'sharedEncoder'))
              and verification['totalActualForwards'] == 1052, 'Passed full verification lineage differs')
    integrity(root.get('complete') is True and root['plan'] == pins['fullPlan'] and root['runner'] == pins['fullReport']
              and root['verification'] == pins['fullVerification'] and root['review'] == pins['fullSourceReview']
              and root['runnerRootAudit'] == pins['fullRunnerRootObservation']
              and all(root[k] is True for k in ('all9891MatrixAndUnitPositionsRootAudited', 'allProbeEqualityChecksPass',
                                                'all1040AlignmentDiagnosticsIndependentlyVerified', 'sharedEncoder'))
              and root['fullAcousticReconstruction'] is False and root['independentAcousticReplayPositions'] == 37
              and root['totalActualEncoderForwards'] == 1052 and root['historicalHardDescriptive']['gate'] is False
              and root['labelsRead'] is False and root['fitsPerformed'] is False, 'Root extraction observation differs')
    integrity(results.get('verdict') == 'clear' and results.get('independent') is True and results.get('blockingFindings') == []
              and results.get('reviewer') == 'claude-opus-5-5' and results.get('fullExtractionPassed') is True
              and results.get('readyToPrepareTrainingDeclaration') is True
              and results.get('observedOutcome') == 'FULL_FRESH_CPU_EXTRACTION_AND_VERIFICATION_PASS', 'Full results review does not clear training')
    integrity(source.get('verdict') == 'clear' and source.get('independent') is True and source.get('blockingFindings') == []
              and source.get('fullExtractionExecutionAuthorized') is True, 'Full source review differs')
    integrity(protocol.get('verdict') == 'clear' and protocol.get('independent') is True and protocol.get('blockingFindings') == []
              and protocol.get('reviewedProtocol') == pins['protocol'], 'Training protocol review differs')
    facts = dict(runnerForwards=report['encoderForwards'], verifierForwards=verification['additionalEncoderForwards'],
                 totalActualForwards=root['totalActualEncoderForwards'], runnerElapsedSeconds=root['runnerElapsedSeconds'],
                 verifierElapsedSeconds=root['verifierElapsedSeconds'], sharedEncoder=True,
                 independentAcousticReplayPositions=root['independentAcousticReplayPositions'], fullAcousticReconstruction=False,
                 diagnosticsVerifiedPositions=verification['diagnosticsVerifiedPositions'],
                 historicalHardDescriptive=root['historicalHardDescriptive'],
                 historicalCompactFeatures='descriptive only; never a control or substitute for the fresh hard matrix')
    return full, report, facts


def load_matrix(binding):
    integrity(files.digest(binding['path']) == binding['sha256'], 'Feature matrix hash differs')
    value = np.load(binding['path'], allow_pickle=False)
    integrity(isinstance(value, np.ndarray) and value.dtype == np.dtype('<f4') and value.shape == (POSITIONS, WIDTH)
              and np.isfinite(value).all(), 'Feature matrix geometry, dtype or finiteness differs')
    return value


def arrays(full, pins):
    """Exact 28227-to-9891 scalar/reference lineage, then the two pinned matrices."""
    e.checked_references(full)
    indices = np.load(pins['rowIndices']['path'], allow_pickle=False)
    scalars = np.load(pins['scalars']['path'], allow_pickle=False)
    parent = np.load(pins['historicalScalars']['path'], allow_pickle=False)
    integrity(indices.shape == (POSITIONS,) and scalars.shape == (POSITIONS, SCALAR_WIDTH) and parent.ndim == 2
              and parent.shape[1] == SCALAR_WIDTH and scalars.dtype == parent.dtype == np.float32 and np.isfinite(parent).all()
              and np.array_equal(scalars, parent[indices]), 'Scalar/row-index lineage differs')
    return indices.tolist(), scalars, parent, {arm: load_matrix(pins['matrix/'+arm]) for arm in ARMS}


def make_cells(historical_jobs, temporal_jobs, rows, *, positions=OUTER_POSITIONS):
    """The 75 neutral cells copied from the frozen temporal declaration and rechecked against the original controls."""
    originals = {j['id']: j for j in historical_jobs}
    require(len(originals) == len(historical_jobs), 'Duplicate historical job identity')
    order = [(seed, sf, wg) for seed in SEEDS for sf in range(5) for wg in range(5)]
    require([(j['seed'], j['speakerFold'], j['wordGroup']) for j in temporal_jobs] == order, 'Temporal cell order or coverage differs')
    child = [i for i, r in enumerate(rows) if 6 <= r['age'] <= 12 and r['legacyRowIndex'] is not None]
    cells = []
    for source, (seed, sf, wg) in zip(temporal_jobs, order, strict=True):
        prefix = f'seed{seed}-unweighted-child-only-'
        refs = dict(scalar=prefix+f'scalars-s{sf}-w{wg}', final=prefix+f'pca16-scalars-s{sf}-w{wg}')
        require(all(ref in originals for ref in refs.values()), 'Missing historical control')
        for name, ref in refs.items():
            control = originals[ref]
            require(control['seed'] == seed and control['objective'] == 'unweighted' and control['regime'] == 'child-only'
                    and control['family'] == ('scalars' if name == 'scalar' else 'pca16-scalars')
                    and control['speakerFold'] == sf and control['wordGroup'] == wg, 'Control identity differs')
            require(all(control[k] == source[k] for k in ROLES), 'Ordered fitting/selection/refit membership differs')
            require([i for i in control['outerRows'] if 6 <= rows[i]['age'] <= 12 and rows[i]['legacyRowIndex'] is not None]
                    == source['outerRows'], 'Original-child outer membership/order differs')
        final = originals[refs['final']]
        require(source == dict(final, id='temporal-'+final['id'], outerRows=source['outerRows'],
                               representation=TEMPORAL_REPRESENTATION, references=refs), 'Temporal job differs from its frozen control')
        cells.append(dict(id=f'seed{seed}-s{sf}-w{wg}', seed=seed, speakerFold=sf, wordGroup=wg,
                          outerRows=list(source['outerRows']), references=refs, temporalJobId=source['id'],
                          jobs=dict(candidate='posterior-candidate-'+refs['final'], freshHard='posterior-freshHard-'+refs['final'],
                                    scalar='posterior-scalar-'+refs['scalar'])))
    for seed in SEEDS:
        ids = [i for c in cells if c['seed'] == seed for i in c['outerRows']]
        require(len(ids) == len(set(ids)) == positions and set(ids) == set(child), 'Incomplete original-child outer coverage')
    return cells


def check_purging(cells, originals, rows, lexicon):
    """Disjoint roles, refit is their union, outer is never fitted, and whole utterances are word purged."""
    for cell in cells:
        job, wg = originals[cell['references']['final']], cell['wordGroup']
        roles = {k: job[k] for k in ROLES}
        fit, selection, added = (set(roles[k]) for k in ROLES[:3])
        integrity(all(len(v) == len(set(v)) for v in roles.values()) and not fit & selection and not fit & added
                  and not selection & added and sorted(fit | selection | added) == sorted(roles['refitRows'])
                  and not set(roles['refitRows']) & set(job['outerRows']), 'Role disjointness or refit union differs')
        integrity(all(i in lexicon and all(word_group(w) != wg for w in lexicon[i]) for v in roles.values() for i in v),
                  'Held-out word remains in a fitting or validation utterance')
        integrity(all(i in lexicon and word_group(rows[i]['targetWord'].upper()) == wg for i in cell['outerRows']),
                  'Outer target word group differs')


def make_jobs(cells, historical_jobs):
    """Two acoustic jobs and one potential fallback scalar job per cell; legacy job fields are kept verbatim."""
    originals = {j['id']: j for j in historical_jobs}
    jobs = []
    for cell in cells:
        for arm in (*ARMS, 'scalar'):
            old = originals[cell['references']['scalar' if arm == 'scalar' else 'final']]
            jobs.append(dict(old, id=cell['jobs'][arm], outerRows=cell['outerRows'], study=STUDY, arm=arm,
                             representation=REPRESENTATIONS[arm], cell=cell['id'], references=cell['references']))
    require(all(set(validation.JOB_FIELDS) <= set(j) for j in jobs), 'Legacy job fields missing')
    return jobs


def control_pins(cells, pins):
    """Every selected historical scalar artifact: configs, weights, priors, states, histories, replays and outer."""
    selected = [c['references']['scalar'] for c in cells]
    bound = {}
    for phase in ('Inner', 'Refit', 'Outer'):
        frozen = read(pins['historical'+phase])
        integrity(frozen['complete'] is True and frozen['plan'] == pins['historicalPlan'], 'Incomplete historical phase')
        records = {r['jobId']: r for r in frozen['predictions' if phase == 'Outer' else 'runs']}
        integrity(set(selected) <= records.keys(), 'Missing historical scalar controls')
        for job_id in selected:
            artifacts = {'prediction': records[job_id]['artifact']} if phase == 'Outer' else records[job_id]['artifacts']
            for name, binding in artifacts.items():
                bound[f'control/{phase}/{job_id}/{name}'] = binding
    return bound


def new_sources():
    here = Path(__file__).resolve().parent
    return [here/name for name in ('study.py', 'evaluation.py', 'test_study.py', 'test_evaluation.py')]


def local_closure(paths):
    """Transitive local imports, resolved as extract.sources resolves them; no package globbing."""
    found, queue = set(), [Path(p).resolve() for p in paths]
    while queue:
        path = queue.pop()
        if path in found:
            continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                modules = [(alias.name, [], 0) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [(node.module or '', [alias.name for alias in node.names], node.level)]
            else:
                continue
            for module, members, level in modules:
                root = path.parent if level else HERE
                for _ in range(max(0, level-1)):
                    root = root.parent
                stem = root.joinpath(*module.split('.')) if module else root
                for candidate in (stem.with_suffix('.py'), stem/'__init__.py', *(stem/(m+'.py') for m in members)):
                    if candidate.is_file() and candidate.resolve().is_relative_to(HERE):
                        queue.append(candidate.resolve())
    return found


def sources(full):
    """Four new files, their transitive closure, numerical runtime, requirements, protocol and the frozen extraction closure."""
    paths = local_closure(new_sources()) | {Path(np.__file__), Path(torch.__file__), HERE/'requirements.txt',
                                            HERE/'requirements.lock.txt', PROTOCOL}
    bound = {str(p.resolve()): e.file_binding(p.resolve()) for p in sorted(paths)}
    for key, binding in full['sources'].items():
        integrity(bound.setdefault(key, binding) == binding, 'Frozen extraction source differs: '+key)
    return dict(sorted(bound.items()))


def build():
    """Declaration value plus loaded bundles; metadata, exact lineage and bindings only, never fits or scores."""
    pins = {key: files.binding(path, sha) for key, (path, sha) in LINEAGE.items()}
    full, report, facts = checked_extraction(pins)
    for arm in ARMS:
        pins['matrix/'+arm] = {k: report['matrices'][MATRIX_KEYS[arm]][k] for k in ('path', 'sha256')}
    pins.update({k: full['inputs'][k] for k in ('scalars', 'rowIndices', 'manifest')})
    old, temporal = read(pins['historicalPlan']), read(pins['temporalPlan'])
    # Frozen trainer and reviewed parity sources are integrity inputs, even on
    # the scientific scalar fallback path. Never bless changed source hashes.
    pins.update({'historicalTrainerSource/'+key: binding for key, binding in old['inputs'].items()
                 if key.startswith(('seedSource/', 'seedCoreReviewedSource/'))})
    pins.update({'priorProbeSource/'+key: binding for key, binding in read(pins['priorProbePlan'])['sources'].items()})
    pins.update(cohort=old['inputs']['cohort'], historicalFeatureReport=old['inputs']['featureReport'])
    pins['historicalScalars'] = read(pins['historicalFeatureReport'])['inputs']['scalars']
    integrity(temporal.get('study') == 'temporal-pooling-heads-v1' and pins['historicalScalars'] == full['inputs']['parentScalars']
              and all(temporal['inputs'].get(k) == pins[k] for k in (*PROBE_INPUTS, 'priorProbePlan', 'priorProbeFreeze', 'priorProbeReview')),
              'Temporal, historical and extraction lineage differ')
    files.guard(pins)
    indices, scalars, parent, matrices = arrays(full, pins)
    cohort = read(pins['cohort'])
    rows = cohort['rows']
    integrity(len(rows) == len(parent), 'Cohort and parent scalar rows differ')
    cells = make_cells(old['jobs'], temporal['jobs'], rows)
    lexicon = {r['rowIndex']: [w['text'].upper() for w in c['words']] for c in full['clips'] for r in c['rows']}
    integrity(sorted(lexicon) == indices, 'Clip word lexicon differs from the 9891 row indices')
    check_purging(cells, {j['id']: j for j in old['jobs']}, rows, lexicon)
    jobs = make_jobs(cells, old['jobs'])
    bound = control_pins(cells, pins)
    integrity(all(temporal['inputs'].get(k) == v for k, v in bound.items()), 'Scalar control bindings differ from the temporal declaration')
    pins.update(bound)
    files.guard(bound)
    value = dict(study=STUDY, legacyExperiment=LEGACY_EXPERIMENT, inputs=pins, sources=sources(full), cells=cells, jobs=jobs,
                 arms=dict(REPRESENTATIONS), matrixKeys=dict(MATRIX_KEYS), seeds=list(SEEDS), objectives=['unweighted'],
                 recipes={str(seed): core.recipe(seed) for seed in SEEDS}, weightRecipe=core.UNWEIGHTED_RECIPE,
                 transform=core.compact.TRANSFORM_RECIPE, featureWidths=dict(raw=WIDTH, compact=29, scalar=SCALAR_WIDTH),
                 support=dict(positions=POSITIONS, outerPerSeed=OUTER_POSITIONS, cells=CELLS, children=x.SUPPORT['children'],
                              targets=x.SUPPORT['targets']),
                 outerRowsBySeed={str(seed): sorted(i for c in cells if c['seed'] == seed for i in c['outerRows']) for seed in SEEDS},
                 runtime=e.environment(full['runtime']), mixtureWeights=[.5, .5], gates=GATES,
                 phaseCounts=dict(reuse=dict(historicalScalarReplays=CELLS, inner=2*CELLS, refit=2*CELLS, outer=2*CELLS),
                                  fallback=dict(historicalScalarReplays=CELLS, inner=3*CELLS, refit=3*CELLS, outer=3*CELLS)),
                 phaseOrder='controls (every historical scalar check and the all-cell decision), then every inner fit, '
                            'then every refit, then every outer pass; nothing is evaluated from an incomplete phase',
                 scalarPolicy='All 75 historical scalar predictions are reused only if every check passes; any scientific '
                              'incompatibility means fresh scalar fits for all 75 cells; integrity failures stop',
                 extraction=facts, limitations=LIMITATIONS, trainingPerformed=False, outerInferencePerformed=False, **FLAGS)
    positions = {i: p for p, i in enumerate(indices)}
    shared = dict(cohort=cohort, positions=positions, scalars=scalars)
    bundles = dict(cohort=cohort, scalar=shared, **{arm: dict(shared, target=matrices[arm]) for arm in ARMS},
                   historical=dict(cohort=cohort, positions={i: i for i in range(len(rows))}, scalars=parent))
    return value, bundles


def declaration():
    return build()[0]


def declare(out):
    out = Path(out).resolve()
    integrity(not out.exists() and out.is_relative_to(BASE), 'Fresh exclusive research output required')
    value = declaration()
    out.mkdir(mode=0o700)
    files.write_json(out/'plan.json', value)
    return files.binding(out/'plan.json')


def review_binding(path, sha):
    binding = files.binding(path)
    e.base.checked_review(Path(binding['path']), sha)
    return binding


def load_plan(path, sha, review=None):
    """Exact plan hash and a clear review precede the cohort, arrays, controls and any model state."""
    pin = files.binding(Path(path).resolve(), sha)
    reviewed = None if review is None else review_binding(review, sha)
    integrity(Path(pin['path']).name == 'plan.json' and Path(pin['path']).is_relative_to(BASE), 'Canonical study plan required')
    plan = read(pin)
    value, bundles = build()
    integrity(plan == value, 'Posterior-pooling declaration changed')
    return plan, pin, reviewed, bundles


def final_guards(plan, review=None, reviewed=None):
    files.guard(plan['inputs'])
    files.guard(plan['sources'])
    integrity(e.environment(plan['runtime']) == plan['runtime'], 'Runtime changed')
    integrity(review is None or files.binding(review) == reviewed, 'Review changed during the phase')


def guard_records(runs=(), predictions=()):
    """Rehash the captured current-phase inventory after every job has finished."""
    files.guard({r['jobId']+'/'+name: binding for r in runs for name, binding in r['artifacts'].items()})
    files.guard({r['jobId']: r['artifact'] for r in predictions})


def guard_freeze(binding, seen=None):
    """Rehash the consumed freeze chain and its captured artifacts before success."""
    seen = set() if seen is None else seen
    key = (binding['path'], binding['sha256'])
    if key in seen:
        return
    seen.add(key)
    files.guard({'freeze': binding})
    value = read(binding)
    if 'review' in value:
        files.guard({'review': value['review']})
    if 'records' in value:
        files.guard({'records': value['records']})
    guard_records(value.get('runs', ()), value.get('predictions', ()))
    for name in ('controls', 'innerFreeze', 'refitFreeze'):
        if name in value:
            guard_freeze(value[name], seen)


def fresh_phase(root, label):
    integrity(not any((root/name).exists() for name in (label, label+'-started.json', label+'-freeze.json', label+'-failure.json')),
              'Preserve partial phase; no implicit restart')
    (root/label).mkdir()


def write_failure(root, label, error, stage, started, completed):
    files.write_json(root/(label+'-failure.json'), dict(
        complete=False, study=STUDY, phase=label, stage=stage, errorType=type(error).__name__, errorMessage=str(error),
        errorTraceback=''.join(traceback.format_exception(error)), completed=completed, elapsedSeconds=time.monotonic()-started,
        partialOutputsPreserved=True, restartAllowed=False, **FLAGS))


def same_state(left, right):
    return list(left) == list(right) and all(torch.equal(left[k], right[k]) for k in left)


def same_model(left, right):
    a, b = (torch.load(p['path'], map_location='cpu', weights_only=True)['model'] for p in (left, right))
    integrity(same_state(a, b), 'Paired initial model tensors differ')


# ------------------------------------------------------ historical scalar controls

@functools.cache
def parameter_shapes(width):
    return {k: (tuple(v.shape), v.dtype) for k, v in core.initialize(width, 0)[0].state_dict().items()}


def saved_state(binding, cfg, config_sha, weights_sha):
    state = torch.load(binding['path'], map_location='cpu', weights_only=True)
    shapes = parameter_shapes(SCALAR_WIDTH)
    integrity(isinstance(state, dict) and {'model', 'optimizer', 'mean', 'std', 'priorState', 'epoch', 'bestEpoch', 'bestLoss',
                                           'configSha256', 'weightsSha256', 'rng'} <= set(state)
              and state['configSha256'] == config_sha and state['weightsSha256'] == weights_sha
              and state['priorState'] == cfg['priorState'] and list(state['model']) == list(shapes)
              and all(tuple(v.shape) == shapes[k][0] and v.dtype == shapes[k][1] and bool(torch.isfinite(v).all())
                      for k, v in state['model'].items())
              and tuple(state['mean'].shape) == tuple(state['std'].shape) == (SCALAR_WIDTH,)
              and state['mean'].dtype == state['std'].dtype == torch.float32 and bool(torch.isfinite(state['mean']).all())
              and bool(torch.isfinite(state['std']).all()) and bool((state['std'] > 0).all()), 'Malformed historical saved state')
    return state


def structural(job, first, fitted, outer_entry, pins, rows):
    """Declaration-bound hashes, exact inventories, configs, freeze lineage and finite states; any failure stops."""
    ref = job['id']
    integrity(job['seed'] in SEEDS and job['objective'] == 'unweighted' and job['regime'] == 'child-only'
              and job['family'] == 'scalars', 'Historical scalar control identity differs')
    integrity(first['jobId'] == fitted['jobId'] == outer_entry['jobId'] == ref, 'Historical scalar record identity differs')
    for label, record, required in (('Inner', first, RUN_FILES | SELECTION_FILES), ('Refit', fitted, RUN_FILES)):
        integrity(set(record['artifacts']) == required, 'Historical scalar artifact inventory differs')
        for name, binding in record['artifacts'].items():
            integrity(pins.get(f'control/{label}/{ref}/{name}') == binding, 'Historical scalar artifact is not declaration-bound: '+name)
            integrity(files.digest(binding['path']) == binding['sha256'], 'Historical scalar artifact hash drift: '+name)
    binding = outer_entry['artifact']
    integrity(pins.get(f'control/Outer/{ref}/prediction') == binding and files.digest(binding['path']) == binding['sha256'],
              'Historical outer prediction is not declaration-bound')
    states = {}
    for phase, record in (('inner', first), ('outer-refit', fitted)):
        artifacts = record['artifacts']
        cfg, report = read(artifacts['config.json']), read(artifacts['report.json'])
        fit, selection = job[FIT_ROLE[phase]], job['selectionRows'] if phase == 'inner' else []
        integrity(cfg.get('experiment') == LEGACY_EXPERIMENT and cfg.get('plan') == pins['historicalPlan'] and cfg.get('phase') == phase
                  and cfg.get('job') == {k: job[k] for k in validation.JOB_FIELDS} and cfg.get('seed') == job['seed']
                  and cfg.get('objective') == 'unweighted' and cfg.get('family') == 'scalars' and cfg.get('featureWidth') == SCALAR_WIDTH
                  and cfg.get('fitRows') == fit and cfg.get('selectionRows') == selection and cfg.get('weights') == artifacts['weights.json']
                  and cfg.get('priorState') == read(artifacts['prior.json']), 'Historical scalar configuration lineage differs')
        integrity(report.get('complete') is True and report.get('bestEpoch') == record['selectedEpoch']
                  and report.get('configSha256') == artifacts['config.json']['sha256'], 'Historical scalar report differs')
        states[phase] = dict(config=cfg, artifacts=artifacts, weights=read(artifacts['weights.json']),
                             checkpoints={name: saved_state(artifacts[name], cfg, artifacts['config.json']['sha256'],
                                                            artifacts['weights.json']['sha256']) for name in STATES})
        if phase == 'inner':
            selected = read(artifacts['selection.json'])
            integrity(selected == read(artifacts['selected-replay.json']), 'Historical saved selection records differ')
            validation.prior.evaluation.checked_prediction(selected, selection, [rows[i] for i in selection])
            states[phase]['selection'] = selected
    integrity(states['outer-refit']['config'].get('innerSelection') == dict(innerFreeze=pins['historicalInner'],
              checkpoint=first['artifacts']['best.pt'], epoch=first['selectedEpoch']) and fitted['selectedEpoch'] == first['selectedEpoch'],
              'Historical refit selection lineage differs')
    outer_record = read(binding)
    integrity(outer_record.get('job') == {k: job[k] for k in validation.JOB_FIELDS}
              and outer_record.get('refitCheckpoint') == fitted['artifacts']['best.pt']
              and outer_record.get('headInferencePerformed') is True, 'Historical outer prediction lineage differs')
    validation.prior.evaluation.checked_prediction(outer_record['prediction'], job['outerRows'], [rows[i] for i in job['outerRows']])
    return states, outer_record


def static_checks(job, states, data):
    """Saved old states against the current recipe and fit-only preparation; each mismatch has its own code."""
    seed = job['seed']

    def recipe():
        compatible(all(s['config']['recipe'] == core.recipe(seed) and s['config']['weightRecipe'] == core.UNWEIGHTED_RECIPE
                       for s in states.values()), 'recipe-differs')

    def weights():
        compatible(all(s['weights'] == data[p]['weightState'] for p, s in states.items()), 'fitting-weights-differ')

    def priors():
        compatible(all(s['config']['priorState'] == data[p]['priors'] for p, s in states.items()), 'fit-priors-differ')

    def normalization():
        compatible(all(torch.equal(c['mean'], data[p]['mean']) and torch.equal(c['std'], data[p]['std'])
                       for p, s in states.items() for c in s['checkpoints'].values()), 'normalization-differs')

    def initial():
        fresh = core.initialize(SCALAR_WIDTH, seed)[0].state_dict()
        compatible(all(same_state(s['checkpoints']['initial.pt']['model'], fresh) for s in states.values()), 'initial-state-differs')

    return dict(recipe=recipe, fittingWeights=weights, fitPriors=priors, normalization=normalization, initialState=initial)


def predict_state(binding, data, indices, seed):
    """Existing seeded head and backend predict on one saved state whose configuration was compared first."""
    state = torch.load(binding['path'], map_location='cpu', weights_only=True)
    model, _ = core.initialize(data['values'].shape[1], seed)
    model.load_state_dict(state['model'], strict=True)
    return core.implementation(data['family']).predict(model, data, list(indices))


def replay_checks(job, states, outer_record, data, predict=predict_state):
    """Selected inner and original-order full outer replays on the 28227-row parent bundle."""
    def selection():
        value = predict(states['inner']['artifacts']['best.pt'], data['inner'], job['selectionRows'], job['seed'])
        compatible(value == states['inner']['selection'], 'selection-replay-differs')

    def outer():
        value = predict(states['outer-refit']['artifacts']['best.pt'], data['outer-refit'], job['outerRows'], job['seed'])
        compatible(value == outer_record['prediction'], 'outer-replay-differs')

    return dict(selectionReplay=selection, outerReplay=outer)


def subset(prediction, rows):
    lookup = {i: n for n, i in enumerate(prediction['rowIndices'])}
    integrity(all(i in lookup for i in rows), 'Historical scalar prediction lacks a child outer row')
    return dict(rowIndices=list(rows), **{k: [prediction[k][lookup[i]] for i in rows] for k in ('probabilities', 'logProbabilities')})


def scalar_cell(cell, job, first, fitted, outer_entry, pins, bundles, global_ok):
    """Full internal integrity precedes compatibility: fallback cannot hide malformed saved lineage."""
    states, outer_record = structural(job, first, fitted, outer_entry, pins, bundles['cohort']['rows'])
    for phase, record in (('inner', first), ('outer-refit', fitted)):
        try:
            validation.run(job, record, pins['historicalPlan'], phase, bundles['cohort'])
        except ValueError as error:
            raise IntegrityFailure('Historical saved-state integrity differs: '+str(error)) from error
    data = {phase: core.prepare(bundles['historical'], 'scalars', job[FIT_ROLE[phase]], 'unweighted') for phase in PHASES}
    checks = {name: outcome(check) for name, check in static_checks(job, states, data).items()}
    for name, check in replay_checks(job, states, outer_record, data).items():
        checks[name] = outcome(check) if all(v == PASS for v in checks.values()) else SKIP
    ready = global_ok and all(v == PASS for v in checks.values())
    rows = bundles['cohort']['rows']
    saved_priors = states['outer-refit']['config']['priorState']
    prior = np.asarray([saved_priors[rows[i]['targetPhone']]['probabilities'] for i in job['outerRows']])
    integrity(outer_record['prior'] == dict(rowIndices=job['outerRows'], probabilities=prior.tolist(),
                                           logProbabilities=np.log(prior).tolist()), 'Historical outer prior differs')
    checks['savedState'] = PASS
    return dict(cell=cell['id'], jobId=job['id'], checks=checks), (subset(outer_record['prediction'], cell['outerRows']) if ready else None)


def parity_receipt(plan):
    """Reviewed trainer-parity probes are reusable only with exact runtime, sources and control inputs."""
    pins = plan['inputs']
    prior, receipt = read(pins['priorProbePlan']), read(pins['priorProbeReview'])
    bindings = receipt.get('bindings', {})
    integrity(receipt.get('independent') is True and receipt.get('verdict') == 'clear' and receipt.get('blockingFindings') == []
              and bindings.get('plan.json') == pins['priorProbePlan'] and bindings.get('controls-freeze.json') == pins['priorProbeFreeze'],
              'Trainer parity receipt review lineage differs')
    integrity(prior.get('runtime') == plan['runtime'], 'Matching trainer-parity runtime required; new reviewed preparation needed')
    files.guard(prior['sources'])
    integrity(all(prior['inputs'].get(k) == pins[k] for k in PROBE_INPUTS), 'Matching trainer-parity inputs required')
    integrity(previous.checked_control_freeze(prior, pins['priorProbePlan']) == pins['priorProbeFreeze'],
              'Trainer parity receipt validation differs')


def historical_compatibility(plan, old):
    """Source/parity are mandatory; valid old runtime/recipe differences may route to scalar fallback."""
    trainer = [b for k, b in old['inputs'].items() if k.startswith(('seedSource/', 'seedCoreReviewedSource/'))]
    integrity(bool(trainer), 'Historical trainer source bindings missing')
    files.guard({str(i): binding for i, binding in enumerate(trainer)})
    parity_receipt(plan)  # Fresh scalar fitting never substitutes for reviewed trainer parity.
    return dict(
        historicalRuntime=outcome(lambda: compatible(old['runtime'] == historical.parent.inventory.features.runtime(),
                                                     'historical-runtime-differs')),
        historicalRecipe=outcome(lambda: compatible(all(old['recipes'].get(str(s)) == core.recipe(s) for s in SEEDS)
                                                    and old['weightRecipes'].get('unweighted') == core.UNWEIGHTED_RECIPE,
                                                    'historical-recipe-differs')),
        historicalTrainerSource=PASS,
        parityReceipt=PASS)


def decide(global_checks, cells, count=CELLS):
    """All-cell reuse only when every global and per-cell check passed; otherwise fresh scalar fits for every cell."""
    outcomes = [*global_checks.values(), *(v for c in cells for v in c['checks'].values())]
    integrity(len(cells) == count and set(global_checks) == set(GLOBAL_CHECKS)
              and all(set(c['checks']) == set(CELL_CHECKS) for c in cells)
              and all(v in (PASS, SKIP) or v in CODES for v in outcomes), 'Incomplete or unknown scalar control outcomes')
    failures = sorted({v for v in outcomes if v in CODES})
    integrity(bool(failures) or SKIP not in outcomes, 'Unevaluated scalar check without a recorded compatibility failure')
    reuse = not failures
    return dict(scalarReuse=reuse, mode='historical-scalar-reuse-all-cells' if reuse else 'fresh-scalar-fallback-all-cells',
                failureCodes=failures, failedCells=[c['cell'] for c in cells if any(v in CODES for v in c['checks'].values())],
                requiredJobs={phase: (2 if reuse else 3) * count for phase in ('inner', 'refit', 'outer')})


def scalar_controls(plan, bundles, completed):
    """Every one of the 75 scalar controls is checked and recorded before the all-cell decision."""
    pins = plan['inputs']
    old = read(pins['historicalPlan'])
    inner, refit, outer_value = (read(pins['historical'+p]) for p in ('Inner', 'Refit', 'Outer'))
    integrity(all(v['complete'] is True and v['plan'] == pins['historicalPlan'] for v in (inner, refit, outer_value))
              and refit['innerFreeze'] == pins['historicalInner'] and outer_value['refitFreeze'] == pins['historicalRefit'],
              'Historical scalar freeze chain differs')
    originals = {j['id']: j for j in old['jobs']}
    first, fitted = ({r['jobId']: r for r in v['runs']} for v in (inner, refit))
    predictions = {r['jobId']: r for r in outer_value['predictions']}
    global_checks = historical_compatibility(plan, old)
    global_ok = all(v == PASS for v in global_checks.values())
    cells, records = [], {}
    for cell in plan['cells']:
        ref = cell['references']['scalar']
        integrity(ref in originals and ref in first and ref in fitted and ref in predictions, 'Missing historical scalar control')
        result, prediction = scalar_cell(cell, originals[ref], first[ref], fitted[ref], predictions[ref], pins, bundles, global_ok)
        cells.append(result)
        if prediction is not None:
            records[cell['id']] = dict(jobId=ref, prediction=prediction)
        completed.append(cell['id'])
    decision = decide(global_checks, cells, len(plan['cells']))
    return dict(globalChecks=global_checks, cells=cells, decision=decision), (records if decision['scalarReuse'] else {})


def checked_control_freeze(plan, pin):
    root = Path(pin['path']).parent
    binding = files.binding(root/'controls-freeze.json')
    value = read(binding)
    integrity(value.get('complete') is True and value.get('study') == STUDY and value.get('phase') == 'controls'
              and value.get('plan') == pin and value.get('runtime') == plan['runtime'] and value.get('trainingPerformed') is False
              and value.get('outerInferencePerformed') is False and value.get('historicalScalarReplayPerformed') is True
              and value.get('scoresComputed') is False and all(value.get(k) is v for k, v in FLAGS.items()),
              'Incomplete scalar control freeze')
    integrity(review_binding(value['review']['path'], pin['sha256']) == value['review'], 'Control review changed')
    integrity([c['cell'] for c in value['cells']] == [c['id'] for c in plan['cells']]
              and [c['jobId'] for c in value['cells']] == [c['references']['scalar'] for c in plan['cells']], 'Scalar control cells differ')
    integrity(value['decision'] == decide(value['globalChecks'], value['cells'], len(plan['cells'])),
              'Recorded scalar decision differs from its outcomes')
    integrity(Path(value['records']['path']) == root/'controls'/'records.json', 'Scalar control records path differs')
    records = read(value['records'])
    integrity(set(records) == ({c['id'] for c in plan['cells']} if value['decision']['scalarReuse'] else set()),
              'Scalar reuse records differ from the decision')
    return value, binding


def controls(path, sha, review):
    """Prephase exception to the outer barrier: historical scalar replays decide reuse or all-cell fallback."""
    plan, pin, reviewed, bundles = load_plan(path, sha, review)
    root = Path(pin['path']).parent
    fresh_phase(root, 'controls')
    files.write_json(root/'controls-started.json', dict(plan=pin, review=reviewed, runtime=plan['runtime']))
    started, stage, completed = time.monotonic(), 'scalar controls', []
    try:
        outcomes, records = scalar_controls(plan, bundles, completed)
        stage = 'final guards'
        final_guards(plan, review, reviewed)
        files.write_json(root/'controls'/'records.json', records)
        files.write_json(root/'controls-freeze.json', dict(
            complete=True, study=STUDY, phase='controls', plan=pin, review=reviewed, runtime=plan['runtime'], **outcomes,
            records=files.binding(root/'controls'/'records.json'), elapsedSeconds=time.monotonic()-started,
            historicalScalarReplayPerformed=True, historicalReplayInfluencesRecipe=False, scoresComputed=False,
            trainingPerformed=False, outerInferencePerformed=False, **FLAGS))
        _, binding = checked_control_freeze(plan, pin)
        print(json.dumps(dict(phase='controls', mode=outcomes['decision']['mode'], failureCodes=outcomes['decision']['failureCodes'])), flush=True)
        return binding
    except BaseException as error:
        write_failure(root, 'controls', error, stage, started, completed)
        raise


# ---------------------------------------------------------------- fitting phases

def required_jobs(plan, controls):
    reuse = controls['decision']['scalarReuse']
    jobs = [j for j in plan['jobs'] if j['arm'] != 'scalar' or not reuse]
    integrity(len(jobs) == (2 if reuse else 3) * len(plan['cells']), 'Required job inventory differs from the scalar decision')
    return jobs


def config_value(job, pin, phase, reviewed, inputs, selection=None):
    return dict(historical.config_value(job, pin, phase, selection), study=STUDY, arm=job['arm'],
                representation=job['representation'], cell=job['cell'], review=reviewed,
                featureMatrix=inputs.get('matrix/'+job['arm']), scalars=inputs['scalars'])


def validate_run(plan, pin, job, record, phase, reviewed, bundles):
    """Unchanged legacy saved-state validation plus lineage, exact fit-only preparation and selected replay."""
    report = validation.run(job, record, pin, phase, bundles['cohort'])
    artifacts = record['artifacts']
    cfg = read(artifacts['config.json'])
    integrity(cfg.get('study') == STUDY and cfg.get('arm') == job['arm'] and cfg.get('representation') == job['representation']
              and cfg.get('cell') == job['cell'] and cfg.get('review') == reviewed and cfg.get('scalars') == plan['inputs']['scalars']
              and cfg.get('featureMatrix') == plan['inputs'].get('matrix/'+job['arm']), 'Posterior-pooling run lineage differs')
    expected = Path(pin['path']).parent/PHASES[phase]/job['id']
    integrity(all(Path(p['path']).parent == expected for p in artifacts.values()), 'Run artifact path differs')
    data = core.prepare(bundles[job['arm']], job['family'], job[FIT_ROLE[phase]], 'unweighted')
    for name in STATES:
        state = torch.load(artifacts[name]['path'], map_location='cpu', weights_only=True)
        integrity(torch.equal(state['mean'], data['mean']) and torch.equal(state['std'], data['std'])
                  and state['priorState'] == data['priors'], 'Fit-only normalization or prior preparation differs')
    if job['family'] == 'pca16-scalars':
        saved = torch.load(artifacts['transform.pt']['path'], map_location='cpu', weights_only=True)
        integrity(core.compact.same_transform(saved, data['transform']), 'Fit-only raw-1024 PCA preparation differs')
    if phase == 'inner':
        integrity(core.replay(expected, data, job['selectionRows'], seed=job['seed']) == read(artifacts['selected-replay.json']),
                  'Selected checkpoint replay differs')
    return report


def paired_initial(jobs, runs):
    """Corresponding candidate and fresh-hard fits start from bit-identical model tensors."""
    by_cell = {}
    for job, record in zip(jobs, runs, strict=True):
        if job['arm'] in ARMS:
            by_cell.setdefault(job['cell'], {})[job['arm']] = record
    for arms in by_cell.values():
        integrity(set(arms) == set(ARMS), 'Missing paired acoustic arm')
        same_model(arms['candidate']['artifacts']['initial.pt'], arms['freshHard']['artifacts']['initial.pt'])


def check_freeze(plan, pin, path, sha, phase, bundles):
    integrity(phase in PHASES, 'Unknown phase')
    root, label = Path(pin['path']).parent, PHASES[phase]
    integrity(path is not None and Path(path).resolve() == (root/(label+'-freeze.json')).resolve(), 'Canonical phase freeze required')
    binding = files.binding(root/(label+'-freeze.json'), sha)
    frozen = read(binding)
    controls, control_pin = checked_control_freeze(plan, pin)
    jobs = required_jobs(plan, controls)
    integrity(frozen.get('complete') is True and frozen.get('study') == STUDY and frozen.get('phase') == phase
              and frozen.get('plan') == pin and frozen.get('controls') == control_pin and frozen.get('runtime') == plan['runtime']
              and frozen.get('jobCount') == len(jobs) and frozen.get('trainingPerformed') is True
              and frozen.get('outerInferencePerformed') is False and all(frozen.get(k) is v for k, v in FLAGS.items())
              and [r['jobId'] for r in frozen.get('runs', [])] == [j['id'] for j in jobs], f'Incomplete {len(jobs)}-job {phase} freeze')
    integrity(review_binding(frozen['review']['path'], pin['sha256']) == frozen['review'], 'Phase review changed')
    for job, record in zip(jobs, frozen['runs'], strict=True):
        validate_run(plan, pin, job, record, phase, frozen['review'], bundles)
    paired_initial(jobs, frozen['runs'])
    if phase == 'outer-refit':
        inner, inner_pin = check_freeze(plan, pin, frozen['innerFreeze']['path'], frozen['innerFreeze']['sha256'], 'inner', bundles)
        integrity(inner_pin == frozen['innerFreeze'], 'Inner freeze binding differs')
        for record, selected in zip(frozen['runs'], inner['runs'], strict=True):
            integrity(record['selectedEpoch'] == selected['selectedEpoch']
                      and read(record['artifacts']['config.json'])['innerSelection'] == dict(
                          innerFreeze=inner_pin, checkpoint=selected['artifacts']['best.pt'], epoch=selected['selectedEpoch']),
                      'Refit selection lineage differs')
    return frozen, binding


def fit(path, sha, phase, review, freeze_path=None, freeze_sha=None):
    integrity(phase in PHASES, 'Unknown phase')
    plan, pin, reviewed, bundles = load_plan(path, sha, review)
    controls, control_pin = checked_control_freeze(plan, pin)
    jobs = required_jobs(plan, controls)
    previous_runs, previous_pin = (None, None) if phase == 'inner' else check_freeze(plan, pin, freeze_path, freeze_sha, 'inner', bundles)
    root, label = Path(pin['path']).parent, PHASES[phase]
    fresh_phase(root, label)
    files.write_json(root/(label+'-started.json'), dict(plan=pin, review=reviewed, controls=control_pin, innerFreeze=previous_pin,
                                                         runtime=plan['runtime'], jobIds=[j['id'] for j in jobs]))
    runs, started, stage, paired = [], time.monotonic(), 'fits', {}
    try:
        for number, job in enumerate(jobs):
            before = time.monotonic()
            data = core.prepare(bundles[job['arm']], job['family'], job[FIT_ROLE[phase]], 'unweighted')
            selected = None if previous_runs is None else previous_runs['runs'][number]
            integrity(selected is None or selected['jobId'] == job['id'], 'Inner/refit job order differs')
            selection = None if selected is None else dict(innerFreeze=previous_pin, checkpoint=selected['artifacts']['best.pt'],
                                                           epoch=selected['selectedEpoch'])
            output = root/label/job['id']
            core.train(data, job['selectionRows'] if phase == 'inner' else [], output,
                       config_value(job, pin, phase, reviewed, plan['inputs'], selection), seed=job['seed'],
                       epochs=None if selected is None else selected['selectedEpoch'])
            if phase == 'inner':
                files.write_json(output/'selected-replay.json', core.replay(output, data, job['selectionRows'], seed=job['seed']))
            artifacts = historical.parent.scalar.manifest(output)
            report = historical.parent.scalar.check_manifest(artifacts)
            record = dict(jobId=job['id'], artifacts=artifacts, selectedEpoch=report['bestEpoch'], seconds=time.monotonic()-before)
            validate_run(plan, pin, job, record, phase, reviewed, bundles)
            if job['arm'] in ARMS:
                paired.setdefault(job['cell'], []).append(record['artifacts']['initial.pt'])
                if len(paired[job['cell']]) == 2:
                    same_model(*paired[job['cell']])
            runs.append(record)
            print(json.dumps(dict(phase=phase, completed=len(runs), total=len(jobs), job=job['id'])), flush=True)
        stage = 'final guards'
        final_guards(plan, review, reviewed)
        guard_records(runs=runs)
        guard_freeze(control_pin)
        if previous_pin is not None:
            guard_freeze(previous_pin)
        integrity(files.binding(root/'controls-freeze.json') == control_pin
                  and (previous_pin is None or files.binding(previous_pin['path']) == previous_pin), 'Earlier phase freeze changed')
        frozen = dict(complete=True, study=STUDY, phase=phase, plan=pin, review=reviewed, controls=control_pin, runtime=plan['runtime'],
                      jobCount=len(jobs), runs=runs, elapsedSeconds=time.monotonic()-started, trainingPerformed=True,
                      outerInferencePerformed=False, **FLAGS)
        if previous_pin is not None:
            frozen['innerFreeze'] = previous_pin
        files.write_json(root/(label+'-freeze.json'), frozen)
        return files.binding(root/(label+'-freeze.json'))
    except BaseException as error:
        write_failure(root, label, error, stage, started, [r['jobId'] for r in runs])
        raise


def prior_value(data, rows, indices):
    prior = np.asarray([data['priors'][rows[i]['targetPhone']]['probabilities'] for i in indices])
    return dict(rowIndices=list(indices), probabilities=prior.tolist(), logProbabilities=np.log(prior).tolist())


def outer(path, sha, review, freeze_path, freeze_sha):
    plan, pin, reviewed, bundles = load_plan(path, sha, review)
    controls, control_pin = checked_control_freeze(plan, pin)
    refits, refit_pin = check_freeze(plan, pin, freeze_path, freeze_sha, 'outer-refit', bundles)
    jobs, rows = required_jobs(plan, controls), bundles['cohort']['rows']
    root = Path(pin['path']).parent
    fresh_phase(root, 'outer')
    files.write_json(root/'outer-started.json', dict(plan=pin, review=reviewed, controls=control_pin, refitFreeze=refit_pin,
                                                     runtime=plan['runtime']))
    predictions, started, stage = [], time.monotonic(), 'outer passes'
    try:
        for job, fitted in zip(jobs, refits['runs'], strict=True):
            integrity(fitted['jobId'] == job['id'], 'Refit/outer job order differs')
            data = core.prepare(bundles[job['arm']], job['family'], job['refitRows'], 'unweighted')
            value = core.replay(Path(fitted['artifacts']['best.pt']['path']).parent, data, job['outerRows'], seed=job['seed'])
            output = root/'outer'/(job['id']+'.json')
            files.write_json(output, dict(study=STUDY, arm=job['arm'], representation=job['representation'], cell=job['cell'],
                                          job={k: job[k] for k in validation.JOB_FIELDS}, refitCheckpoint=fitted['artifacts']['best.pt'],
                                          prediction=value, prior=prior_value(data, rows, job['outerRows']),
                                          headInferencePerformed=True, **FLAGS))
            predictions.append(dict(jobId=job['id'], artifact=files.binding(output)))
            print(json.dumps(dict(phase='outer', completed=len(predictions), total=len(jobs), job=job['id'])), flush=True)
        stage = 'final guards'
        final_guards(plan, review, reviewed)
        guard_records(predictions=predictions)
        guard_freeze(control_pin)
        guard_freeze(refit_pin)
        integrity(files.binding(root/'controls-freeze.json') == control_pin and files.binding(refit_pin['path']) == refit_pin,
                  'Earlier phase freeze changed')
        files.write_json(root/'outer-freeze.json', dict(
            complete=True, study=STUDY, phase='outer', plan=pin, review=reviewed, controls=control_pin, refitFreeze=refit_pin,
            runtime=plan['runtime'], jobCount=len(jobs), predictions=predictions, elapsedSeconds=time.monotonic()-started,
            trainingPerformed=False, outerInferencePerformed=True, **FLAGS))
        return files.binding(root/'outer-freeze.json')
    except BaseException as error:
        write_failure(root, 'outer', error, stage, started, [p['jobId'] for p in predictions])
        raise


def replay_record(job, record, fitted, bundles):
    integrity(record.get('study') == STUDY and record.get('arm') == job['arm'] and record.get('cell') == job['cell']
              and record.get('representation') == job['representation']
              and record.get('job') == {k: job[k] for k in validation.JOB_FIELDS}
              and record.get('refitCheckpoint') == fitted['artifacts']['best.pt'] and record.get('headInferencePerformed') is True
              and all(record.get(k) is v for k, v in FLAGS.items()), 'Outer arm/seed/checkpoint lineage differs')
    data = core.prepare(bundles[job['arm']], job['family'], job['refitRows'], job['objective'])
    integrity(core.replay(Path(fitted['artifacts']['best.pt']['path']).parent, data, job['outerRows'], seed=job['seed'])
              == record['prediction'], 'Outer exact replay differs')
    integrity(record['prior'] == prior_value(data, bundles['cohort']['rows'], job['outerRows']), 'Outer prior differs')
    return dict(prediction=record['prediction'], prior=record['prior'])


def checked_outer(plan, pin, bundles, path, sha):
    """Complete outer freeze, then the complete refit and inner chain, then exact replays of every outer record."""
    root = Path(pin['path']).parent
    integrity(path is not None and Path(path).resolve() == (root/'outer-freeze.json').resolve(), 'Canonical outer freeze required')
    binding = files.binding(root/'outer-freeze.json', sha)
    frozen = read(binding)
    controls, control_pin = checked_control_freeze(plan, pin)
    jobs = required_jobs(plan, controls)
    integrity(frozen.get('complete') is True and frozen.get('study') == STUDY and frozen.get('phase') == 'outer'
              and frozen.get('plan') == pin and frozen.get('controls') == control_pin and frozen.get('runtime') == plan['runtime']
              and frozen.get('jobCount') == len(jobs) and frozen.get('trainingPerformed') is False
              and frozen.get('outerInferencePerformed') is True and all(frozen.get(k) is v for k, v in FLAGS.items())
              and [p['jobId'] for p in frozen.get('predictions', [])] == [j['id'] for j in jobs], f'Incomplete {len(jobs)}-job outer freeze')
    integrity(review_binding(frozen['review']['path'], pin['sha256']) == frozen['review'], 'Outer review changed')
    refits, refit_pin = check_freeze(plan, pin, frozen['refitFreeze']['path'], frozen['refitFreeze']['sha256'], 'outer-refit', bundles)
    integrity(refit_pin == frozen['refitFreeze'], 'Refit freeze binding differs')
    records = {}
    for job, entry, fitted in zip(jobs, frozen['predictions'], refits['runs'], strict=True):
        integrity(Path(entry['artifact']['path']) == root/'outer'/(job['id']+'.json'), 'Outer artifact path differs')
        records[job['id']] = replay_record(job, read(entry['artifact']), fitted, bundles)
    return records, binding


def scalar_component(plan, controls, records, predictions):
    """One source for every cell: replayed historical subsets, or fresh fallback outer predictions; never mixed."""
    scalar_jobs = {c['jobs']['scalar'] for c in plan['cells']}
    if controls['decision']['scalarReuse']:
        integrity(set(records) == {c['id'] for c in plan['cells']} and not scalar_jobs & set(predictions),
                  'Historical scalar reuse must cover every cell with no fresh scalar prediction')
        return {c['id']: records[c['id']] for c in plan['cells']}
    integrity(not records and scalar_jobs <= set(predictions), 'Fresh scalar fallback must cover every cell with no historical record')
    return {c['id']: predictions[c['jobs']['scalar']] for c in plan['cells']}


def verify(path, sha, phase, freeze_path=None, freeze_sha=None):
    """Separate reconstruction of one completed phase; nothing is written."""
    plan, pin, _, bundles = load_plan(path, sha)
    if phase == 'controls':
        frozen, binding = checked_control_freeze(plan, pin)
        outcomes, records = scalar_controls(plan, bundles, [])
        integrity({k: frozen[k] for k in outcomes} == outcomes and read(frozen['records']) == records,
                  'Scalar control decision does not reconstruct exactly')
    elif phase in PHASES:
        _, binding = check_freeze(plan, pin, freeze_path, freeze_sha, phase, bundles)
    else:
        integrity(phase == 'outer', 'Unknown phase')
        _, binding = checked_outer(plan, pin, bundles, freeze_path, freeze_sha)
    final_guards(plan)
    return dict(verified=True, phase=phase, freeze=binding)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('declare').add_argument('--out', required=True, type=Path)
    for name in ('controls', 'inner', 'refit', 'outer', 'verify'):
        command = commands.add_parser(name)
        command.add_argument('--plan', required=True, type=Path)
        command.add_argument('--sha256', required=True)
        if name != 'verify':
            command.add_argument('--review', required=True, type=Path)
        if name in ('refit', 'outer'):
            command.add_argument('--freeze', required=True, type=Path)
            command.add_argument('--freeze-sha256', required=True)
        if name == 'verify':
            command.add_argument('--phase', required=True, choices=('controls', 'inner', 'outer-refit', 'outer'))
            command.add_argument('--freeze', type=Path)
            command.add_argument('--freeze-sha256')
    args = parser.parse_args()
    if args.command == 'declare':
        value = declare(args.out)
    elif args.command == 'controls':
        value = controls(args.plan, args.sha256, args.review)
    elif args.command in ('inner', 'refit'):
        value = fit(args.plan, args.sha256, 'inner' if args.command == 'inner' else 'outer-refit', args.review,
                    getattr(args, 'freeze', None), getattr(args, 'freeze_sha256', None))
    elif args.command == 'outer':
        value = outer(args.plan, args.sha256, args.review, args.freeze, args.freeze_sha256)
    else:
        value = verify(args.plan, args.sha256, args.phase, args.freeze, args.freeze_sha256)
    print(json.dumps(value), flush=True)


if __name__ == '__main__':
    main()
