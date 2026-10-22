"""Run an explicitly selected part of the locked adaptation matrix, serially.

The ledger records the immutable recipe/input/source contract and every child
attempt. A failed child stops the queue. Restarting incomplete work requires
--resume-existing; completed work is skipped only after artifact verification.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, suppress
import fcntl
import itertools
import json
import math
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

import numpy as np
import torch

from encoders import Wav2VecEncoder, WavLMEncoder
from multiphone_adapt import SOURCES, read_study
from multiphone_cache import atomic_json, digest
from multiphone_train import distribution_metrics

HERE = Path(__file__).resolve().parent
BASE = HERE/'outputs/multiphone-20260926'
RECIPE = HERE/'experiments/multiphone-adaptation-v1.json'
LOCKED_RECIPE_SHA256 = '216fd167cbc60e8036926d31b2f4b5f8b7415383a17de20cbac820d31af0a9e7'
CACHE = {'wav2vec2-base': 'wav2vec-frames', 'wavlm-base-plus': 'wavlm-frames'}
SHORT = {'wav2vec2-base': 'wav2vec', 'wavlm-base-plus': 'wavlm'}
IDENTITIES = {'wav2vec2-base': Wav2VecEncoder.identity, 'wavlm-base-plus': WavLMEncoder.identity}
RECIPE_ARGUMENTS = {
    'head': 'head', 'hidden': 'hiddenWidth', 'dropout': 'headDropout',
    'backbone_lr': 'backboneLearningRate', 'head_lr': 'headLearningRate',
    'weight_decay': 'weightDecay', 'max_gradient_norm': 'maximumGradientNorm',
    'accumulation_clips': 'gradientAccumulationClips', 'epochs': 'maximumInnerEpochs',
    'patience': 'patienceEpochs', 'save_every_updates': 'checkpointEveryUpdates',
}
LAUNCH_GATE = """import os, sys
if sys.stdin.buffer.read(1) != b'1':
    raise SystemExit(125)
os.execv(sys.argv[1], sys.argv[1:])
"""


def load_json(path: Path):
    return json.loads(path.read_text())


def alive(pid) -> bool:
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def exclusive_lock(path: Path):
    # The OS releases the lock on process exit; stale lock files are harmless.
    with path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Another adaptation queue owns this local execution lock') from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def capture_contract(args) -> tuple[dict, dict]:
    if digest(RECIPE) != LOCKED_RECIPE_SHA256:
        raise ValueError('The locked adaptation recipe changed')
    recipe = load_json(RECIPE)
    for selected, allowed in ((args.encoders, recipe['encoders']),
                              (args.depths, recipe['upperEncoderLayers']), (args.folds, recipe['folds'])):
        if not selected or len(set(selected)) != len(selected) or any(value not in allowed for value in selected):
            raise ValueError('Each explicit matrix subset must be nonempty, unique and within the locked recipe')
    if not args.base.resolve().is_relative_to((HERE/'outputs').resolve()):
        raise ValueError('Keep adaptation outputs inside ignored local research outputs')
    cohort_path, splits_path = args.base/'cohort.json', args.base/'splits.json'
    if digest(cohort_path) != recipe['cohortSha256'] or digest(splits_path) != recipe['splitsSha256']:
        raise ValueError('Recipe cohort or split digest differs')
    cohort = load_json(cohort_path)
    caches = {}
    for encoder in args.encoders:
        cache = args.base/CACHE[encoder]
        config, index = load_json(cache/'config.json'), load_json(cache/'index.json')
        if (config.get('encoder') != IDENTITIES[encoder] or config.get('cohortSha256') != recipe['cohortSha256']
                or index.get('complete') is not True or index.get('configSha256') != digest(cache/'config.json')
                or set(index['entries']) != {clip['id'] for clip in cohort['clips']}):
            raise ValueError('Feature cache identity or coverage differs')
        # Verify the files named by the index once before executing this queue.
        for clip in cohort['clips']:
            entry = index['entries'][clip['id']]
            path = cache/entry['path']
            if (not path.resolve().is_relative_to(cache.resolve()) or entry.get('audioSha256') != clip['audioSha256']
                    or digest(path) != entry['sha256']):
                raise ValueError('Feature cache entry differs from its verified index')
        caches[encoder] = {'configSha256': digest(cache/'config.json'), 'indexSha256': digest(cache/'index.json'),
                           'encoderIdentity': IDENTITIES[encoder]}
    contract = {'recipePath': str(RECIPE.resolve()), 'recipeSha256': LOCKED_RECIPE_SHA256,
                'base': str(args.base.resolve()), 'cohortSha256': recipe['cohortSha256'],
                'splitsSha256': recipe['splitsSha256'], 'caches': caches,
                'sourceSha256': {name: digest(HERE/name) for name in SOURCES},
                'queueSourceSha256': digest(Path(__file__)),
                'encoders': args.encoders, 'depths': args.depths, 'folds': args.folds,
                'seeds': recipe['initializationSeeds'], 'python': str(Path(sys.executable).resolve()),
                'torch': str(torch.__version__), 'numpy': np.__version__, 'device': 'mps', 'threads': 2}
    return recipe, contract


def guard(contract: dict) -> None:
    base = Path(contract['base'])
    if digest(RECIPE) != contract['recipeSha256'] or digest(Path(__file__)) != contract['queueSourceSha256']:
        raise ValueError('Recipe or queue source changed during execution')
    if digest(base/'cohort.json') != contract['cohortSha256'] or digest(base/'splits.json') != contract['splitsSha256']:
        raise ValueError('Cohort or splits changed during execution')
    if any(digest(HERE/name) != value for name, value in contract['sourceSha256'].items()):
        raise ValueError('Training implementation changed during execution')
    for encoder, saved in contract['caches'].items():
        cache = base/CACHE[encoder]
        if digest(cache/'config.json') != saved['configSha256'] or digest(cache/'index.json') != saved['indexSha256']:
            raise ValueError('Feature cache identity changed during execution')


def job_arguments(recipe: dict, contract: dict, encoder: str, depth: int, fold: int, seed: int) -> dict:
    base = Path(contract['base'])
    output = base/f'adapt-{SHORT[encoder]}-u{depth}-f{fold}-s{seed}'
    arguments = {name: recipe[key] for name, key in RECIPE_ARGUMENTS.items()}
    arguments.update({'cohort': str(base/'cohort.json'), 'splits': str(base/'splits.json'),
                      'cache': str(base/CACHE[encoder]), 'output': str(output), 'encoder': encoder,
                      'upper_layers': depth, 'fold': fold, 'seed': seed, 'phase': 'inner',
                      'device': 'mps', 'threads': 2, 'warm_head': None, 'selection': None})
    return arguments


def command(arguments: dict, resume: bool) -> list[str]:
    result = [sys.executable, str(HERE/'multiphone_adapt.py')]
    for name, value in arguments.items():
        if value is not None:
            result.extend(['--'+name.replace('_', '-'), str(value)])
    if resume:
        result.append('--resume')
    return result


def verify_config(output: Path, arguments: dict, contract: dict) -> dict:
    config = load_json(output/'config.json')
    expected = dict(arguments)
    expected.update({'sourceSha256': contract['sourceSha256'], 'cohortSha256': contract['cohortSha256'],
        'splitsSha256': contract['splitsSha256'], 'cacheIndexSha256': contract['caches'][arguments['encoder']]['indexSha256'],
        'encoderIdentity': IDENTITIES[arguments['encoder']], 'warmStart': None,
        'torch': contract['torch'], 'numpy': contract['numpy'], 'authorPartition': 'train',
        'authorTestInferencePerformed': False, 'clinicalUseEligible': False, 'learnerFeedbackEligible': False,
        'normalization': 'fixed frame moments from fit speakers only in pinned frozen encoder cache',
        'encoderMode': 'eval; upper transformer layers receive gradients; lower weights/preprocessor frozen'})
    namespace = argparse.Namespace(cohort=Path(arguments['cohort']), splits=Path(arguments['splits']),
                                  fold=arguments['fold'], phase='inner')
    _, fit_rows, eval_rows = read_study(namespace)
    expected.update(fitRows=fit_rows, evaluationRows=eval_rows)
    metadata = {'trainableEncoderNames', 'trainableEncoderParameters', 'trainableHeadParameters'}
    if set(config) != set(expected) | metadata or any(config.get(key) != value for key, value in expected.items()):
        raise ValueError('Existing run configuration does not exactly match the locked matrix contract')
    allowed_prefixes = tuple(f'encoder.layers.{index}.' for index in range(12-arguments['upper_layers'], 12))
    names = config['trainableEncoderNames']
    if (not names or len(set(names)) != len(names) or any(not name.startswith(allowed_prefixes) for name in names)
            or any(type(config[key]) is not int or config[key] < 1
                   for key in ('trainableEncoderParameters', 'trainableHeadParameters'))):
        raise ValueError('Existing run has invalid trainable-parameter metadata')
    return config


def finite_tensors(value) -> bool:
    if isinstance(value, torch.Tensor):
        return bool(torch.isfinite(value).all())
    if isinstance(value, dict):
        return all(finite_tensors(entry) for entry in value.values())
    if isinstance(value, (list, tuple)):
        return all(finite_tensors(entry) for entry in value)
    return True


def verify_checkpoint(path: Path, config: dict, *, resume: bool) -> dict:
    saved = torch.load(path, map_location='cpu', weights_only=True)
    if (saved.get('schemaVersion') != 1 or saved.get('configSha256') != digest(path.parent/'config.json')
            or saved.get('encoderIdentity') != config['encoderIdentity']
            or set(saved.get('encoder', {})) != set(config['trainableEncoderNames'])
            or not saved.get('head') or not finite_tensors(saved)):
        raise ValueError('Checkpoint model/configuration binding or finite-state validation failed')
    for key, count in [('encoder', 'trainableEncoderParameters'), ('head', 'trainableHeadParameters')]:
        if (any(not isinstance(value, torch.Tensor) for value in saved[key].values())
                or sum(value.numel() for value in saved[key].values()) != config[count]):
            raise ValueError('Checkpoint tensor inventory differs from the recorded model')
    if (saved['mean'].shape != (768,) or saved['std'].shape != (768,) or not (saved['std'] > 0).all()):
        raise ValueError('Checkpoint normalization is invalid')
    progress = saved['progress']
    if (type(progress['epoch']) is not int or not 1 <= progress['epoch'] <= config['epochs']+1
            or type(progress['bestEpoch']) is not int or not 0 <= progress['bestEpoch'] < progress['epoch']
            or type(progress['updates']) is not int or progress['updates'] < 0
            or len(progress['history']) != progress['epoch']-1):
        raise ValueError('Checkpoint epoch/update progress is invalid')
    if resume:
        if (not isinstance(saved.get('optimizer'), dict) or len(saved['optimizer'].get('param_groups', [])) != 2
                or not isinstance(saved['rng'].get('torch'), torch.Tensor)
                or not isinstance(saved['rng'].get('mps'), torch.Tensor)):
            raise ValueError('Resume checkpoint lacks optimizer or CPU/MPS RNG state')
        random.Random().setstate(saved['rng']['python'])
        generator = np.random.default_rng()
        generator.bit_generator.state = saved['rng']['numpy']
        cohort = load_json(Path(config['cohort']))
        clips = {cohort['rows'][row]['clipIndex'] for row in config['fitRows']}
        order, cursor = progress['order'], progress['cursor']
        if (type(cursor) is not int or not 0 <= cursor <= len(order)
                or (order and (set(order) != clips or len(order) != len(clips)))
                or (not order and cursor != 0)):
            raise ValueError('Resume checkpoint clip order/cursor is invalid')
        selected = progress['bestCheckpoint']
        if selected is not None:
            selected_path = path.parent/selected
            if (not selected_path.resolve().is_relative_to(path.parent.resolve())
                    or digest(selected_path) != progress['bestCheckpointSha256']):
                raise ValueError('Resume selected-checkpoint binding differs')
    return saved


def verify_complete(output: Path, arguments: dict, contract: dict) -> dict:
    config = verify_config(output, arguments, contract)
    report, status = load_json(output/'report.json'), load_json(output/'status.json')
    if (report.get('complete') is not True or status.get('complete') is not True
            or report.get('configSha256') != digest(output/'config.json')
            or report.get('checkpointSha256') != digest(output/'best.pt')
            or report.get('evaluationRole') != 'inner selection'
            or report.get('clinicalUseEligible') is not False or report.get('learnerFeedbackEligible') is not False):
        raise ValueError('Completed run report/status/checkpoint binding differs')
    saved = verify_checkpoint(output/'best.pt', config, resume=False)
    if (report.get('bestEpoch') != saved['progress']['bestEpoch']
            or not 1 <= report['bestEpoch'] <= report['epochsRun'] <= arguments['epochs']):
        raise ValueError('Completed report selected epoch differs from the checkpoint')
    predictions = load_json(output/'predictions.json')
    probabilities = np.asarray(predictions['probabilities'], dtype=float)
    if (predictions['rowIndices'] != sorted(config['evaluationRows'])
            or probabilities.shape != (len(config['evaluationRows']), 3)
            or not np.isfinite(probabilities).all() or (probabilities < 0).any()
            or not np.allclose(probabilities.sum(1), 1., atol=1e-5)):
        raise ValueError('Completed evaluation predictions are incomplete or invalid')
    rows = load_json(Path(config['cohort']))['rows']
    ordered = predictions['rowIndices']
    counts = np.asarray([rows[index]['raterCounts'] for index in ordered], dtype=float)
    metrics = distribution_metrics(probabilities, counts)
    per_target = {}
    for phone in sorted({rows[index]['targetPhone'] for index in ordered}):
        mask = np.asarray([rows[index]['targetPhone'] == phone for index in ordered])
        per_target[phone] = distribution_metrics(probabilities[mask], counts[mask])
    metrics['perTarget'] = per_target
    metrics['macroTargetLogLoss'] = float(np.mean([entry['perRaterLogLoss'] for entry in per_target.values()]))
    for name, condition in [('ages6to12', lambda age: 6 <= age <= 12), ('ages13plus', lambda age: age >= 13)]:
        mask = np.asarray([condition(rows[index]['age']) for index in ordered])
        metrics[name] = distribution_metrics(probabilities[mask], counts[mask]) if mask.any() else None
    if not same_metrics(report.get('evaluation'), metrics):
        raise ValueError('Completed evaluation metrics differ from saved predictions and labels')
    verify_history(output, arguments, report, saved)
    return {name+'Sha256': digest(output/(name+'.json')) for name in ('config', 'report', 'predictions', 'history')} | {
        'checkpointSha256': digest(output/'best.pt'), 'bestEpoch': report['bestEpoch'], 'epochsRun': report['epochsRun']}


def same_metrics(actual, expected) -> bool:
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and set(actual) == set(expected)
                and all(same_metrics(actual[key], value) for key, value in expected.items()))
    if type(expected) in (int, float):
        return type(actual) in (int, float) and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
    return actual == expected


def verify_history(output: Path, arguments: dict, report: dict, saved: dict) -> None:
    history = load_json(output/'history.json')
    if not isinstance(history, list) or len(history) != report['epochsRun']:
        raise ValueError('Full learning history length differs from the completed report')
    best_epoch, best_loss = 0, math.inf
    for epoch, record in enumerate(history, 1):
        loss = record.get('validation', {}).get('macroTargetLogLoss')
        train_loss = record.get('trainPerRaterLogLoss')
        if (record.get('epoch') != epoch or type(loss) not in (int, float) or not math.isfinite(loss) or loss < 0
                or type(train_loss) not in (int, float) or not math.isfinite(train_loss) or train_loss < 0):
            raise ValueError('Learning history contains invalid epochs or losses')
        if loss < best_loss-1e-7:
            best_epoch, best_loss = epoch, loss
        if epoch < len(history) and epoch-best_epoch >= arguments['patience']:
            raise ValueError('Learning history continues beyond the locked patience rule')
    if (best_epoch != report['bestEpoch'] or best_epoch != saved['progress']['bestEpoch']
            or not math.isclose(best_loss, saved['progress']['bestLoss'], rel_tol=1e-9, abs_tol=1e-9)
            or not math.isclose(best_loss, report['evaluation']['macroTargetLogLoss'], rel_tol=1e-6, abs_tol=1e-6)
            or saved['progress']['history'] != history[:best_epoch]
            or (len(history) < arguments['epochs'] and len(history)-best_epoch < arguments['patience'])):
        raise ValueError('History, selected checkpoint, report or early-stopping rule disagree')


def verify_resumable(output: Path, arguments: dict, contract: dict) -> dict:
    config = verify_config(output, arguments, contract)
    status_path = output/'status.json'
    if status_path.exists() and alive(load_json(status_path).get('pid')):
        raise ValueError('Existing run still has a live recorded process; do not resume it concurrently')
    saved = verify_checkpoint(output/'last.pt', config, resume=True)
    return {'lastCheckpointSha256': digest(output/'last.pt'), 'resumeEpoch': saved['progress']['epoch'],
            'resumeCursor': saved['progress']['cursor']}


def run(args) -> dict:
    torch.set_num_threads(2)
    args.base = args.base.resolve()
    args.ledger = args.ledger.resolve()
    if not args.ledger.is_relative_to(args.base) or args.ledger.name in ('cohort.json', 'splits.json'):
        raise ValueError('Choose a dedicated queue ledger inside the study output directory')
    with exclusive_lock(args.base/'adaptation-mps.lock'):
        recipe, contract = capture_contract(args)
        if args.ledger.exists():
            ledger = load_json(args.ledger)
            if ledger.get('contract') != contract:
                raise ValueError('Existing queue ledger has a different immutable execution contract')
            for job in ledger['jobs']:
                for attempt in job['attempts']:
                    if attempt['state'] in ('running', 'launching'):
                        if alive(attempt.get('pid')):
                            raise ValueError('An earlier queue child is still alive')
                        # A vanished parent cannot report its child's exit code.
                        # Record the new observation without inventing an exit.
                        attempt.update(state='not-running-on-restart', observedInactiveAt=time.time())
        else:
            ledger = {'schemaVersion': 1, 'contract': contract, 'createdAt': time.time(), 'jobs': [], 'invocations': []}
        invocation = {'pid': os.getpid(), 'startedAt': time.time(), 'state': 'running',
                      'resumeExisting': args.resume_existing}
        ledger['invocations'].append(invocation)
        ledger.update(complete=False, state='running')
        atomic_json(args.ledger, ledger)
        current = None
        process = None
        try:
            for encoder, depth, fold, seed in itertools.product(args.encoders, args.depths, args.folds, recipe['initializationSeeds']):
                guard(contract)
                arguments = job_arguments(recipe, contract, encoder, depth, fold, seed)
                output = Path(arguments['output'])
                job = next((entry for entry in ledger['jobs'] if entry['run'] == output.name), None)
                if job is None:
                    job = {'run': output.name, 'arguments': arguments, 'attempts': []}
                    ledger['jobs'].append(job)
                current = {'state': 'verifying', 'startedAt': time.time(), 'pid': None, 'exitCode': None}
                job['attempts'].append(current)
                atomic_json(args.ledger, ledger)
                if (output/'report.json').exists():
                    evidence = verify_complete(output, arguments, contract)
                    prior = next((attempt['evidence'] for attempt in reversed(job['attempts'][:-1])
                                  if attempt['state'] in ('complete', 'already-complete')), None)
                    if prior is not None and evidence != prior:
                        raise ValueError('Previously verified completed artifacts changed')
                    current.update(state='already-complete', finishedAt=time.time(), evidence=evidence)
                    job['state'] = 'complete'
                    atomic_json(args.ledger, ledger)
                    print(json.dumps({'run': output.name, 'state': current['state']}), flush=True)
                    continue
                resume = output.exists()
                if resume:
                    if not args.resume_existing:
                        raise ValueError(f'Incomplete run requires explicit --resume-existing: {output.name}')
                    current['resumeEvidence'] = verify_resumable(output, arguments, contract)
                command_line = command(arguments, resume)
                log_path = args.base/f'{output.name}.queue-attempt-{time.time_ns()}.log'
                current.update(state='launching', command=command_line, log=str(log_path))
                atomic_json(args.ledger, ledger)
                guard(contract)
                with log_path.open('x') as log:
                    # The child cannot start training until its PID is durably
                    # recorded. If the parent dies before then, EOF ends the gate.
                    process = subprocess.Popen([sys.executable, '-c', LAUNCH_GATE, *command_line],
                                               stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, cwd=HERE)
                    current.update(state='running', pid=process.pid, childStartedAt=time.time())
                    atomic_json(args.ledger, ledger)
                    process.stdin.write(b'1')
                    process.stdin.flush()
                    process.stdin.close()
                    print(json.dumps({'run': output.name, 'pid': process.pid, 'state': 'running'}), flush=True)
                    code = process.wait()
                    current.update(exitCode=code, childFinishedAt=time.time())
                    process = None
                guard(contract)
                if code != 0:
                    raise RuntimeError(f'Training exited {code}; inspect {log_path.name}')
                current.update(evidence=verify_complete(output, arguments, contract), state='complete', finishedAt=time.time())
                job['state'] = 'complete'
                atomic_json(args.ledger, ledger)
                print(json.dumps({'run': output.name, 'state': 'complete', 'exitCode': code}), flush=True)
            ledger.update(complete=True, state='complete', finishedAt=time.time())
            invocation.update(state='complete', finishedAt=time.time())
            atomic_json(args.ledger, ledger)
            return ledger
        except BaseException as error:
            if process is not None and process.stdin is not None and not process.stdin.closed:
                with suppress(BrokenPipeError):
                    process.stdin.close()
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                if current is not None:
                    current.update(exitCode=process.returncode, childFinishedAt=time.time())
            state = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed'
            if current is not None:
                current.update(state=state, finishedAt=time.time(), error=str(error) or type(error).__name__)
                job['state'] = state
            ledger.update(complete=False, state=state, finishedAt=time.time())
            invocation.update(state=state, finishedAt=time.time(), error=str(error) or type(error).__name__)
            atomic_json(args.ledger, ledger)
            raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--encoders', choices=list(CACHE), nargs='+', required=True)
    result.add_argument('--depths', type=int, choices=[1, 2], nargs='+', required=True)
    result.add_argument('--folds', type=int, choices=range(5), nargs='+', required=True)
    result.add_argument('--base', type=Path, default=BASE)
    result.add_argument('--ledger', type=Path, required=True)
    result.add_argument('--resume-existing', action='store_true')
    return result


if __name__ == '__main__':
    def stop(_signal, _frame):
        raise KeyboardInterrupt('Queue termination requested')
    signal.signal(signal.SIGTERM, stop)
    run(parser().parse_args())
