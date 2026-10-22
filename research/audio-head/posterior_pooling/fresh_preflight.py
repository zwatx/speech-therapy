"""Fresh-matched CPU posterior-pooling preflight after the failed v1 historical-parity gate.

Run from research/audio-head:
  python -m posterior_pooling.fresh_preflight declare --out outputs/.../NEW
  python -m posterior_pooling.fresh_preflight run --plan PLAN --sha256 SHA --review CLEAR --out NEWRUN
The v1 source, plan, run directory and failure stay frozen; this route never
invokes the v1 runner or its historical-parity gate. Every candidate vector and
its fresh hard control come from one unchanged v1 extract_clip forward. All four
declared probes run in order, then all four repeat: eight forwards, bit exact.
Historical hard means are descriptive only. No labels, fits or restart.
"""
from __future__ import annotations

import argparse
import ast
import copy
import json
import os
from pathlib import Path
import platform
import resource
import time
import traceback

import numpy as np

from posterior_pooling import extract as e

PROTOCOL = e.ROOT/'docs/model/posterior-pooling-fresh-controls-v1.md'
WORK = e.ROOT/'work/core-model-next-method-20260927'
OLD = e.BASE/'posterior-pooling-preflight-v1'
LINEAGE = {
    'protocol': (PROTOCOL, '7f14d60436f7175762865753d20d29f397effb8af2230938f29314590e375dc9'),
    'oldPlan': (OLD/'plan.json', '016d4dcedd029111e1ee9703d98d597b747a6a63590382f32230cb6eef187a63'),
    'oldFailure': (OLD/'run/failure.json', 'c1182fcfd20d87dcc99b5d5f41c00e0a468b32b5d8e848c472b0ae8a337b56bc'),
    'failureObservation': (WORK/'preflight-failure-root-observation.json', '6e369ddedd55f9057cec566cad987eb63afec7d9e886625e1b78614e0c950fb6'),
    'failureReview': (WORK/'opus-preflight-failure-review.json', '76c9b0bbb7c83a2d981261840d8b403e11ce2a55be29391bca6cd47a2d11f226'),
    'historicalVerifier': (WORK/'verify-preflight.py', '2f92811130d38b38529c71555b1e022e1008f337cdd83e63d1856b90b8d3eef4'),
    'historicalVerifierSynthetic': (WORK/'preflight-replay-synthetic-verification.json', '6b14fe8e830a2f533a85e8b58e0ae959472d54d8346025406d2987acd4ce629d'),
}
SELECTED = ['000010168', '014190030', '001450051', '000560117']
WIDTH = 1024
KEYS = ('candidate', 'hard')
FIXED = ('inputs', 'clips', 'probes', 'model', 'encoderRecipe', 'runtime')
REFERENCE_KEYS = ('reference', 'passingFinal', 'scalars', 'rowIndices', 'parentTarget', 'parentScalars', 'manifest')
FLAGS = dict(e.FLAGS, labelsRead=False, fitsPerformed=False, pronunciationAccuracyMeasured=False)
RECIPE = {k: v for k, v in e.RECIPE.items() if k not in ('version', 'repeat', 'historicalParity')} | dict(
    version='posterior-pooling-fresh-controls-cpu-preflight-v1',
    runOrder='plan.probes.selectedClipIds as declared, then all four again; eight forwards',
    repeat='all four probes; candidate and fresh hard np.array_equal within run, no tolerance',
    hardControl='fresh same-forward unchanged pooled_vectors padded mean via v1 extract_clip',
    historicalHard='descriptive per-row maxAbs and differing-row count; never a gate',
    verifier='separate-process fresh_verify: four forwards, hard bit exact, candidate atol 1e-6, audit atol 1e-10',
    historicalControlsDescriptiveOnly=True, freshMatchedControls=True, **FLAGS)


def new_sources():
    here = Path(__file__).resolve().parent
    return [here/name for name in ('fresh_preflight.py', 'fresh_verify.py', 'test_fresh_preflight.py', 'test_fresh_verify.py')]


def local_imports(paths):
    """Local files imported by the given sources, resolved as e.sources() resolves them."""
    found = set()
    for path in paths:
        for node in ast.walk(ast.parse(Path(path).read_text())):
            if isinstance(node, ast.Import):
                modules = [(alias.name, []) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                e.require(not node.level, 'Relative imports are not source-bound')
                modules = [(node.module, [alias.name for alias in node.names])]
            else:
                continue
            for module, members in modules:
                stem = e.HERE.joinpath(*module.split('.'))
                for candidate in (stem.with_suffix('.py'), stem/'__init__.py', *(stem/(m+'.py') for m in members)):
                    if candidate.is_file():
                        found.add(candidate.resolve())
    return found


def sources():
    """Transitive v1 closure plus the four fresh sources, new protocol and immutable lineage."""
    bound = e.sources()
    new = new_sources()
    missing = sorted(str(p) for p in local_imports(new) if str(p) not in bound and p not in new)
    e.require(not missing, 'Fresh source import closure incomplete: '+', '.join(missing))
    for path in (*new, PROTOCOL, *(path for path, _ in LINEAGE.values())):
        bound[str(Path(path).resolve())] = e.file_binding(Path(path).resolve())
    return dict(sorted(bound.items()))


def checked_lineage():
    """The v1 failure stays closed; its plan/failure pins precede any new declaration."""
    pins = {k: e.file_binding(Path(path)) for k, (path, _) in LINEAGE.items()}
    e.require(all(pins[k]['sha256'] == sha for k, (_, sha) in LINEAGE.items()), 'Immutable v1 plan/failure/advice lineage differs')
    failure, observation, review = (e.read_json(Path(pins[k]['path'])) for k in ('oldFailure', 'failureObservation', 'failureReview'))
    e.require(failure['planSha256'] == pins['oldPlan']['sha256'] and failure['errorType'] == 'ValueError'
        and failure['completedClips'] == 3 and failure['partialOutputsPreserved'] is True
        and observation['outcome'] == review['observedOutcome'] == 'FAILED_HISTORICAL_EXACT_PARITY'
        and observation['plan'] == pins['oldPlan'] and observation['failure'] == pins['oldFailure'] and observation['noRestart'] is True
        and review['verdict'] == 'clear' and review['reviewer'] == 'claude-opus-5-5' and review['preflightPassed'] is False
        and review['recommendedNextRoute'] == 'fresh-matched-cpu-preflight',
        'v1 failure must remain closed; fresh route lineage differs')
    return dict(bindings=pins, outcome='FAILED_HISTORICAL_EXACT_PARITY', failedClipId=observation['failedClipId'],
        failedClipMaximumHardMeanAbs=observation['failedClipMaximumHardMeanAbs'],
        historicalControlsDescriptiveOnly=True, freshMatchedControls=True)


def declaration():
    """Metadata-only: v1 declaration identities, then explicit fresh-route overrides."""
    lineage = checked_lineage()
    historical = e.declaration()
    previous = e.read_json(Path(lineage['bindings']['oldPlan']['path']))
    e.require(all(historical[k] == previous[k] for k in FIXED), 'Fixed v1 metadata, probes, model or runtime differ')
    probes = historical['probes']
    e.require(probes['selectedClipIds'] == SELECTED and probes['fitClipIds'] == SELECTED[:3]
        and probes['globalLongestClipId'] == SELECTED[3] and [c['id'] for c in historical['clips']] == SELECTED,
        'Fixed four declared probes differ')
    return dict(historical, study=RECIPE['version'], recipe=copy.deepcopy(RECIPE),
        probes=dict(probes, repeatClipIds=list(SELECTED), historicalRepeatClipIds=probes['repeatClipIds']),
        sources=sources(), lineage=lineage, **FLAGS)


def fresh_directory(out, message):
    out = Path(out).resolve()
    e.require(out.is_relative_to(e.HERE/'outputs') and not out.is_relative_to(OLD) and not out.exists(), message)
    return out


def declare(out):
    out = fresh_directory(out, 'Fresh exclusive declaration directory required')
    plan = declaration()
    out.mkdir(parents=True, mode=0o700)
    return e.write_new(out/'plan.json', plan)


def checked_plan(path, sha):
    path = Path(path).resolve()
    e.require(path.is_relative_to(e.HERE/'outputs') and not path.is_relative_to(OLD) and path.name == 'plan.json',
              'Canonical fresh plan required')
    e.require(e.digest(path) == sha, 'Fresh plan SHA differs')
    plan = e.read_json(path)
    e.require(plan == declaration(), 'Fresh plan source, lineage, metadata, recipe or runtime changed')
    return plan


def run_order(plan):
    probes = plan['probes']
    order = list(probes['selectedClipIds'])
    e.require(len(order) == len(set(order)) == 4 and probes['repeatClipIds'] == order
        and [c['id'] for c in plan['clips']] == order and set(probes['roles']) == set(order),
        'Declared four-probe order/repeat coverage differs')
    return order


def checked_values(values, clip):
    e.require(isinstance(values, dict) and set(values) == set(KEYS)
        and all(isinstance(v, np.ndarray) and v.dtype == np.dtype('<f4') and v.shape == (len(clip['rows']), WIDTH)
                and np.isfinite(v).all() for v in values.values()),
        'Fresh candidate/hard geometry, dtype or finiteness differs')
    return values


def historical_differences(hard, historical):
    """Descriptive only: per-row max |fresh-historical| and differing-row count; never a gate."""
    e.require(hard.ndim == 2 and hard.shape == historical.shape and hard.shape[1] == WIDTH
              and hard.dtype == historical.dtype == np.float32, 'Historical descriptive geometry differs')
    delta = np.abs(hard.astype(np.float64)-historical.astype(np.float64)).max(axis=1)
    return dict(rowMaxAbs=delta.tolist(), differingRows=int((delta > 0).sum()), rows=len(delta),
                maximumAbs=float(delta.max()), gate=False)


def save_arrays(path, values):
    with Path(path).open('xb') as stream:
        Path(path).chmod(0o600)
        np.savez(stream, allow_pickle=False, **values)
    return e.file_binding(Path(path))


def check_review(review, reviewed):
    e.require(e.file_binding(Path(review)) == reviewed, 'Clear review changed during fresh route')


def run(path, sha, review, out):
    # Plan hash and clear review precede source recomputation, reference arrays, audio, posteriors and the model.
    path, review = Path(path).resolve(), Path(review).resolve()
    e.require(e.digest(path) == sha, 'Fresh plan SHA differs')
    e.base.checked_review(review, sha)
    reviewed = e.file_binding(review)
    plan = checked_plan(path, sha)
    env = e.environment(plan['runtime'])
    order = run_order(plan)
    out = fresh_directory(out, 'Fresh run directory required; preserve partial outputs, no implicit restart')
    out.mkdir(parents=True, mode=0o700)
    e.write_new(out/'started.json', dict(plan=e.file_binding(path), review=reviewed, environment=env,
        runOrder=order*2, processId=os.getpid(), **FLAGS))
    started = time.monotonic(); records = []; repeats = {}; forwards = 0
    try:
        by_id = {c['id']: c for c in plan['clips']}
        # Exact 28227-to-9891 provenance/scalar lineage precedes every forward; history never gates.
        reference = e.checked_references(plan)
        e.guard(plan['model'])
        for clip in plan['clips']:
            e.guard_clip(clip)
        cached = {}
        with e.load_encoder(plan) as encoder:
            for cid in order:
                check_review(review, reviewed)
                clip = by_id[cid]; before = time.monotonic()
                values, audit = e.extract_clip(encoder, clip); forwards += 1
                checked_values(values, clip)
                history = historical_differences(values['hard'], reference[[r['outputIndex'] for r in clip['rows']]])
                record = dict(clipId=cid, forward=forwards, roles=plan['probes']['roles'][cid],
                    rowIds=[r['id'] for r in clip['rows']], outputIndices=[r['outputIndex'] for r in clip['rows']],
                    shape=[len(clip['rows']), WIDTH], dtype='float32', artifact=save_arrays(out/(cid+'.npz'), values),
                    audit=audit, historicalHardDescriptive=history, seconds=time.monotonic()-before)
                e.write_new(out/(cid+'.json'), record); records.append(record); cached[cid] = values
            for cid in order:
                check_review(review, reviewed)
                clip = by_id[cid]; before = time.monotonic()
                values, _ = e.extract_clip(encoder, clip); forwards += 1
                checked_values(values, clip)
                exact = {k+'BitExact': bool(np.array_equal(values[k], cached[cid][k])) for k in KEYS}
                # The repeat artifact is persisted first, so a mismatch leaves its evidence intact.
                artifact = save_arrays(out/(cid+'-repeat.npz'), values)
                e.require(all(exact.values()), f'Within-run repeat of {cid} differs: {exact}; candidate and fresh hard must be bit exact')
                repeats[cid] = dict(clipId=cid, forward=forwards, artifact=artifact, seconds=time.monotonic()-before, **exact)
        e.guard(plan['model'])
        for clip in plan['clips']:
            e.guard_clip(clip)
        e.checked_references(plan)
        checked_plan(path, sha)
        e.require(e.environment(plan['runtime']) == env, 'Runtime changed during fresh preflight')
        check_review(review, reviewed)
        histories = [r['historicalHardDescriptive'] for r in records]
        return e.write_new(out/'report.json', dict(complete=True, study=plan['study'], plan=e.file_binding(path),
            review=reviewed, environment=env, runner=e.file_binding(Path(__file__)), processId=os.getpid(),
            outputDirectory=str(out), runOrder=order*2, encoderForwards=forwards, records=records, repeats=repeats,
            references={k: plan['inputs'][k] for k in REFERENCE_KEYS}, model=plan['model'],
            repeatsExact=True, freshHardSameForward=True, historicalHardGate=False,
            historicalControlsDescriptiveOnly=True, freshMatchedControls=True,
            historicalHardDescriptive=dict(differingRows=sum(h['differingRows'] for h in histories),
                rows=sum(h['rows'] for h in histories), maximumAbs=max(h['maximumAbs'] for h in histories), gate=False),
            peakMemory=dict(value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, units='bytes', system=platform.system(),
                method='process lifetime resource.getrusage(RUSAGE_SELF).ru_maxrss on Darwin'),
            elapsedSeconds=time.monotonic()-started, encoderInferencePerformed=True, **FLAGS))
    except BaseException as error:
        e.write_new(out/'failure.json', dict(complete=False, successFrozen=False, planSha256=sha,
            errorType=type(error).__name__, errorMessage=str(error), errorTraceback=''.join(traceback.format_exception(error)),
            completedClips=len(records), completedRepeats=len(repeats), encoderForwards=forwards,
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
