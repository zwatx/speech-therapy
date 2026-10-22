"""Synthetic summary integrity and matched-control checks; no model inference."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import multiphone_phonetic_adapt_summary as summary
from multiphone_cache import atomic_json, digest


class AdaptationSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / 'outputs'
        self.base.mkdir()
        self.output = self.base / 'summary.json'
        self.ledger_path = self.base / 'queue.json'
        self.plan_path = self.base / 'plan.json'
        self.preflight = self.base / 'preflight.json'
        atomic_json(self.preflight, {'complete': True})
        self.rows = [
            {'age': age, 'speakerId': str(i), 'targetPhone': phone, 'raterCounts': counts}
            for i, (age, phone, counts) in enumerate(((8, 'B', [1, 1, 3]), (10, 'P', [0, 0, 5]),
                                                      (20, 'B', [2, 1, 2]), (22, 'P', [0, 1, 4])))
        ]
        self.cohort = self.base / 'cohort.json'
        atomic_json(self.cohort, {'authorPartition': 'train', 'rows': self.rows})
        for name in ('multiphone_phonetic_preflight.py', 'multiphone_local_head_queue.py'):
            (self.root / name).write_text('synthetic source')
        self.contract = {'sources': {}, 'recipeSha256': digest(summary.queue.trainer.RECIPE),
            'preflightSourceSha256': digest(self.root / 'multiphone_phonetic_preflight.py'),
            'launchHelperSha256': digest(self.root / 'multiphone_local_head_queue.py')}
        plan_jobs = summary.queue.jobs(self.base)
        plan = {'base': str(self.base), 'contract': self.contract, 'jobs': plan_jobs}
        atomic_json(self.plan_path, plan)
        self.jobs = deepcopy(plan_jobs)
        for ordinal, job in enumerate(self.jobs):
            directory = Path(job['output'])
            directory.mkdir()
            identity = {'regime': job['regime'], 'fitRows': [10, 11], 'validationRows': list(range(4)),
                'selectionRows': [0, 1] if job['regime'] == 'child-only' else list(range(4)),
                'warmStart': {'regime': job['regime'], 'sha256': 'fixed'},
                'inputFiles': {'cohort': {'path': str(self.cohort), 'sha256': digest(self.cohort)}}}
            atomic_json(directory / 'config.json', identity)
            zero = np.tile([.25, .25, .5], (4, 1))
            selected = np.tile([.2, .2, .6] if job['arm'] == 'head-only' else [.3, .3, .4], (4, 1))
            best_epoch = 1
            if ordinal == 3:
                selected, best_epoch = zero.copy(), 0
            prior = np.tile([.1, .1, .8], (4, 1))
            metrics = [summary.queue.trainer.score_predictions(p, self.rows) for p in (selected, zero, prior)]
            for filename, probabilities in (('predictions.json', selected), ('epoch-zero-predictions.json', zero)):
                atomic_json(directory / filename, {'rowIndices': list(range(4)), 'probabilities': probabilities.tolist()})
            atomic_json(directory / 'epoch-zero.json', {'evaluation': metrics[1],
                'predictionsSha256': digest(directory / 'epoch-zero-predictions.json')})
            atomic_json(directory / 'prior.json', {'rowIndices': list(range(4)), 'probabilities': prior.tolist(),
                                                   'evaluation': metrics[2], 'state': {'regime': job['regime']}})
            atomic_json(directory / 'history.json', [{'epoch': 0}, {'epoch': 1}])
            (directory / 'best.pt').write_bytes(b'synthetic checkpoint; never loaded')
            report = {'complete': True, 'bestEpoch': best_epoch, 'epochsRun': 3, 'updates': 12,
                'evaluation': metrics[0], 'sameFitPriorEvaluation': metrics[2],
                **{key + 'Sha256': digest(directory / name) for key, name in (
                    ('config', 'config.json'), ('checkpoint', 'best.pt'), ('history', 'history.json'),
                    ('predictions', 'predictions.json'), ('prior', 'prior.json'), ('epochZero', 'epoch-zero.json'))}}
            atomic_json(directory / 'report.json', report)
            atomic_json(directory / 'replay.json', {'exact': True, 'device': 'mps', 'rows': 4,
                'checkpointSha256': report['checkpointSha256'], 'evaluation': metrics[0]})
            job.update(state='complete', exitCode=0,
                verified={'configSha256': report['configSha256'], 'reportSha256': digest(directory / 'report.json'),
                          'checkpointSha256': report['checkpointSha256']},
                replay={'state': 'complete', 'exitCode': 0, 'verifiedExact': True,
                        'sha256': digest(directory / 'replay.json')})
        self.ledger = {'complete': True, 'contract': self.contract, 'jobs': self.jobs,
            'planPath': str(self.plan_path), 'planSha256': digest(self.plan_path),
            'preflightPath': str(self.preflight), 'preflightSha256': digest(self.preflight)}
        self.save_ledger()
        recipe = summary.queue.trainer.read_json(summary.RECIPE)
        recipe.update(requiredPlanSha256=digest(self.plan_path), requiredPreflightSha256=digest(self.preflight))
        self.recipe_path = self.root / 'recipe.json'
        atomic_json(self.recipe_path, recipe)
        self.enterContext(patch.object(summary, 'HERE', self.root))
        self.enterContext(patch.object(summary, 'RECIPE', self.recipe_path))
        self.enterContext(patch.object(summary.queue, 'contract', return_value=self.contract))
        self.enterContext(patch.object(summary.queue, 'verify_preflight'))
        # State/history replay verification is covered by the real queue tests.
        # This suite tests the additional reader and immutable-ledger boundary.
        self.verifier = self.enterContext(patch.object(summary.queue, 'verify_completed',
                                                       side_effect=lambda job, _: job['verified']))

    def save_ledger(self):
        atomic_json(self.ledger_path, self.ledger)
        self.expected = digest(self.ledger_path)

    def build(self):
        return summary.build(self.ledger_path, self.expected, self.output)

    def read(self, path):
        return summary.queue.trainer.read_json(path)

    def test_all_six_retained_with_signed_control_differences_and_epoch_zero(self):
        result = self.build()
        self.assertEqual(result['arms'], 6)
        report = self.read(self.output)
        self.assertFalse(report['inferencePerformed'])
        self.assertFalse(report['selectionPerformed'])
        self.assertEqual([(r['regime'], r['arm']) for r in report['arms']], list(summary.queue.ORDER))
        upper = report['arms'][1]
        self.assertGreater(upper['differenceVsMatchedHeadOnly']['allAges']['proper']['macroTargetLogLoss'], 0)
        self.assertEqual(report['arms'][3]['bestEpoch'], 0)
        self.assertEqual(report['arms'][3]['differenceVsOwnEpochZero']['ages6to12']['proper']['perRaterBrier'], 0)
        self.assertTrue(all(r['startingPredictionsVsHeadOnly']['exactlyEqual'] for r in report['arms']))
        self.assertIsNone(upper['selected']['ages6to12']['perPhoneDiscrimination']['P']['rating0']['auroc'])
        self.assertEqual(upper['selected']['ages6to12']['withinPhone']['rating0']['undefinedTargets'], 1)
        summary.guard(report['artifactSha256'])
        with self.assertRaisesRegex(ValueError, 'fresh'):
            self.build()

    def test_incomplete_ledger_and_missing_replay_fail_without_publication(self):
        self.ledger['complete'] = False
        self.save_ledger()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.build()
        self.verifier.assert_not_called()
        self.ledger['complete'] = True
        self.ledger['jobs'][2]['replay']['verifiedExact'] = False
        self.save_ledger()
        with self.assertRaisesRegex(ValueError, 'exact replay must be complete'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_caller_ledger_hash_and_fixed_inventory_reject_changes(self):
        self.ledger_path.write_text(self.ledger_path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'Caller-pinned'):
            self.build()
        self.ledger['jobs'][1], self.ledger['jobs'][2] = self.ledger['jobs'][2], self.ledger['jobs'][1]
        self.save_ledger()
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.build()

    def test_tampered_prediction_or_replay_digest_is_rejected(self):
        path = Path(self.jobs[0]['output']) / 'predictions.json'
        original = path.read_bytes()
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Previously verified'):
            self.build()
        path.write_bytes(original)
        path = Path(self.jobs[0]['output']) / 'replay.json'
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Previously verified'):
            self.build()

    def test_recomputed_zero_metrics_reject_self_consistent_rehash(self):
        job = self.jobs[0]
        directory = Path(job['output'])
        path = directory / 'epoch-zero-predictions.json'
        value = self.read(path)
        value['probabilities'][0] = [.7, .2, .1]
        atomic_json(path, value)
        zero = self.read(directory / 'epoch-zero.json')
        zero['predictionsSha256'] = digest(path)
        atomic_json(directory / 'epoch-zero.json', zero)
        report = self.read(directory / 'report.json')
        report['epochZeroSha256'] = digest(directory / 'epoch-zero.json')
        atomic_json(directory / 'report.json', report)
        job['verified']['reportSha256'] = digest(directory / 'report.json')
        self.save_ledger()
        with self.assertRaisesRegex(ValueError, 'reproduce all reported metrics'):
            self.build()

    def test_different_regime_fit_binding_cannot_be_called_a_matched_control(self):
        job = self.jobs[1]
        directory = Path(job['output'])
        config = self.read(directory / 'config.json')
        config['fitRows'] = [10]
        atomic_json(directory / 'config.json', config)
        report = self.read(directory / 'report.json')
        report['configSha256'] = digest(directory / 'config.json')
        atomic_json(directory / 'report.json', report)
        job['verified'].update(configSha256=report['configSha256'], reportSha256=digest(directory / 'report.json'))
        self.save_ledger()
        with self.assertRaisesRegex(ValueError, 'matched control binding'):
            self.build()

    def test_late_mutation_of_earlier_artifact_prevents_complete_summary(self):
        original = summary.checked_arm
        def mutate(job, contract, pins):
            result = original(job, contract, pins)
            if job['output'] == self.jobs[-1]['output']:
                (Path(self.jobs[0]['output']) / 'history.json').write_text('changed')
            return result
        with patch.object(summary, 'checked_arm', side_effect=mutate), \
             self.assertRaisesRegex(ValueError, 'Captured input, output or source changed'):
            self.build()
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
