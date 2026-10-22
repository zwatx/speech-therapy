"""Read a pinned completed six-arm queue; no fitting, inference or new selection."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

import multiphone_phonetic_adapt_queue as queue
from multiphone_cache import digest

HERE = Path(__file__).resolve().parent
RECIPE = HERE / 'experiments/multiphone-phonetic-adaptation-summary-v1.json'
ARTIFACTS = ('config.json', 'report.json', 'best.pt', 'history.json', 'predictions.json',
             'prior.json', 'epoch-zero.json', 'epoch-zero-predictions.json', 'replay.json')
PROPER = ('perRaterLogLoss', 'macroTargetLogLoss', 'perRaterBrier')
RANKING = ('rating0', 'ratingBelow2')
AGES = ('allAges', 'ages6to12', 'ages13plus')
require = queue.trainer.require


def read_pinned(path, pins, expected=None):
    path = Path(path).absolute()
    payload = path.read_bytes()
    sha = hashlib.sha256(payload).hexdigest()
    require(expected is None or sha == expected, 'Caller-pinned artifact differs')
    require(str(path) not in pins or pins[str(path)] == sha, 'Captured artifact changed')
    pins[str(path)] = sha
    return json.loads(payload)


def add_pin(path, sha, pins):
    path = str(Path(path).absolute())
    require(path not in pins or pins[path] == sha, 'Conflicting artifact bindings')
    require(digest(Path(path)) == sha, 'Bound artifact changed')
    pins[path] = sha


def guard(pins):
    require(all(digest(Path(path)) == sha for path, sha in pins.items()), 'Captured input, output or source changed')


def measurements(evaluation):
    """Preserve all age slices, proper scores, phone support and undefined ranks."""
    result = {}
    for age in AGES:
        score = evaluation[age]
        result[age] = {
            'examples': score['examples'], 'speakers': score['speakers'],
            'observedRaterCounts': score['observedRaterCounts'],
            'proper': {key: score[key] for key in PROPER},
            'withinPhone': score['targetDiscrimination']['macroTarget'],
            'pooledDiscrimination': score['discrimination'],
            'perPhoneProper': score['perTarget'],
            'perPhoneDiscrimination': score['targetDiscrimination']['perPhone'],
        }
    return result


def differences(current, reference):
    output = {}
    for age in AGES:
        a, b = current[age], reference[age]
        require(all(a[key] == b[key] for key in ('examples', 'speakers', 'observedRaterCounts')),
                'Comparison population differs')
        rankings = {}
        for target in RANKING:
            left, right = a['withinPhone'][target], b['withinPhone'][target]
            require(all(left[key] == right[key] for key in ('definedTargets', 'undefinedTargets', 'excludedPhones')),
                    'Ranking support differs')
            rankings[target] = {key: None if left[key] is None or right[key] is None else left[key] - right[key]
                                for key in ('auroc', 'averagePrecision')}
        output[age] = {'proper': {key: a['proper'][key] - b['proper'][key] for key in PROPER},
                       'withinPhone': rankings}
    return output


def scored_predictions(path, indices, rows, pins):
    saved = read_pinned(path, pins)
    p = np.asarray(saved['probabilities'], dtype=np.float64)
    require(saved['rowIndices'] == indices and len(set(indices)) == len(indices)
            and p.shape == (len(indices), 3) and np.isfinite(p).all()
            and (p >= 0).all() and (p <= 1).all()
            and np.allclose(p.sum(1), 1., rtol=0, atol=1e-6), 'Invalid complete ordered probabilities')
    return queue.trainer.score_predictions(p, rows), p


def checked_arm(job, contract, pins):
    output = Path(job['output'])
    require(job['state'] == 'complete' and job.get('exitCode') == 0
            and job.get('replay', {}).get('state') == 'complete'
            and job['replay'].get('exitCode') == 0 and job['replay'].get('verifiedExact') is True,
            'Every arm and exact replay must be complete')
    for name in ARTIFACTS:
        add_pin(output / name, digest(output / name), pins)
    config, report = [read_pinned(output / name, pins) for name in ('config.json', 'report.json')]
    require(queue.verify_completed(job, contract) == job['verified'], 'Queue verification evidence differs')
    queue.guard_completed_files(job)
    replay = read_pinned(output / 'replay.json', pins, job['replay']['sha256'])
    require(replay['exact'] is True and replay['device'] == 'mps'
            and replay['checkpointSha256'] == report['checkpointSha256']
            and replay['evaluation'] == report['evaluation'] and replay['rows'] == len(config['validationRows']),
            'Exact saved replay binding differs')
    for value in config['inputFiles'].values():
        add_pin(value['path'], value['sha256'], pins)
    cohort_pin = config['inputFiles']['cohort']
    cohort = read_pinned(cohort_pin['path'], pins, cohort_pin['sha256'])
    require(cohort['authorPartition'] == 'train', 'Not author training')
    indices = config['validationRows']
    rows = [cohort['rows'][index] for index in indices]
    evaluation, _ = scored_predictions(output / 'predictions.json', indices, rows, pins)
    zero = read_pinned(output / 'epoch-zero.json', pins)
    zero_metrics, zero_p = scored_predictions(output / 'epoch-zero-predictions.json', indices, rows, pins)
    prior = read_pinned(output / 'prior.json', pins)
    prior_metrics, prior_p = scored_predictions(output / 'prior.json', indices, rows, pins)
    require(evaluation == report['evaluation'] and zero_metrics == zero['evaluation']
            and prior_metrics == prior['evaluation'] == report['sameFitPriorEvaluation'],
            'Saved probabilities do not reproduce all reported metrics')
    measured, initial, prior_measured = map(measurements, (evaluation, zero_metrics, prior_metrics))
    record = {'regime': job['regime'], 'arm': job['arm'], 'output': str(output),
              'bestEpoch': report['bestEpoch'], 'epochsRun': report['epochsRun'], 'updates': report['updates'],
              'checkpointSha256': report['checkpointSha256'], 'exactSameDeviceReplay': True,
              'selected': measured, 'epochZero': initial, 'sameFitPrior': prior_measured,
              'differenceVsOwnEpochZero': differences(measured, initial),
              'differenceVsSameFitPrior': differences(measured, prior_measured)}
    identity = {key: config[key] for key in ('regime', 'fitRows', 'validationRows', 'selectionRows', 'warmStart', 'inputFiles')}
    return record, identity, zero_p, prior_p, prior['state']


def build(ledger_path, expected_sha, output):
    require(not output.exists() and output.resolve().is_relative_to((HERE / 'outputs').resolve()),
            'Choose a fresh ignored summary file')
    torch.set_num_threads(2)
    pins = {}
    recipe = read_pinned(RECIPE, pins)
    require(recipe['ageSlices'] == list(AGES) and recipe['properScores'] == list(PROPER)
            and recipe['rankingScores'] == list(RANKING) and recipe['requiredArms'] == len(queue.ORDER) == 6,
            'Reporting specification differs')
    add_pin(Path(__file__), digest(Path(__file__)), pins)
    add_pin(Path(queue.__file__), digest(Path(queue.__file__)), pins)
    ledger = read_pinned(ledger_path, pins, expected_sha)
    require(ledger['complete'] is True and not ledger.get('failure'), 'Six-arm queue is incomplete or failed')
    plan = read_pinned(ledger['planPath'], pins, recipe['requiredPlanSha256'])
    require(ledger['planSha256'] == recipe['requiredPlanSha256']
            and ledger['preflightSha256'] == recipe['requiredPreflightSha256']
            and ledger['contract'] == plan['contract'] == queue.contract()
            and ledger['contract']['recipeSha256'] == recipe['requiredTrainingRecipeSha256'],
            'Training plan, preflight or source contract differs')
    add_pin(queue.trainer.RECIPE, recipe['requiredTrainingRecipeSha256'], pins)
    for name, sha in ledger['contract']['sources'].items():
        add_pin(Path(queue.trainer.HERE) / name, sha, pins)
    for field, name in (('preflightSourceSha256', 'multiphone_phonetic_preflight.py'),
                        ('launchHelperSha256', 'multiphone_local_head_queue.py')):
        add_pin(HERE / name, ledger['contract'][field], pins)
    preflight = read_pinned(ledger['preflightPath'], pins, recipe['requiredPreflightSha256'])
    queue.verify_preflight(preflight, ledger['contract'])
    expected = queue.jobs(Path(plan['base']))
    require(plan['jobs'] == expected and len(ledger['jobs']) == len(expected)
            and all(all(actual[key] == declaration[key] for key in ('regime', 'arm', 'device', 'output'))
                    for actual, declaration in zip(ledger['jobs'], expected, strict=True)), 'Fixed six-arm inventory differs')
    records, identities, zeros, priors, prior_states = {}, {}, {}, {}, {}
    for job in ledger['jobs']:
        key = (job['regime'], job['arm'])
        records[key], identities[key], zeros[key], priors[key], prior_states[key] = checked_arm(job, ledger['contract'], pins)
    for key, record in records.items():
        control_key = (key[0], 'head-only')
        require(identities[key] == identities[control_key] and prior_states[key] == prior_states[control_key]
                and np.array_equal(priors[key], priors[control_key]), 'Same-regime matched control binding differs')
        record['startingPredictionsVsHeadOnly'] = {
            'exactlyEqual': bool(np.array_equal(zeros[key], zeros[control_key])),
            'maximumAbsoluteProbabilityDifference': float(np.abs(zeros[key] - zeros[control_key]).max())}
        if key[1] != 'head-only':
            record['differenceVsMatchedHeadOnly'] = differences(record['selected'], records[control_key]['selected'])
    report = {'complete': True, 'scope': 'Descriptive fold0 inner-validation comparison; no new model selection',
              'ledgerPath': str(ledger_path.absolute()), 'ledgerSha256': expected_sha,
              'reportingSpecification': recipe, 'arms': [records[key] for key in queue.ORDER],
              'artifactSha256': pins, 'inferencePerformed': False, 'selectionPerformed': False,
              'outerOutcomesUsed': False, 'authorTestInferencePerformed': False,
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    guard(pins)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return {'output': str(output.absolute()), 'sha256': digest(output), 'arms': len(report['arms'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.ledger, args.expected_sha256, args.output)))
