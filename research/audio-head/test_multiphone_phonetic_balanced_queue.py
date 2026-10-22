"""Weighted queue contracts and synthetic fitted-checkpoint verification."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import multiphone_phonetic_balanced_queue as queue
import test_multiphone_phonetic_balanced as fixtures
from test_multiphone_local_train import save


class BalancedQueueTests(unittest.TestCase):
    def test_exact_twenty_cpu_jobs_have_two_rates_per_fold_and_regime(self):
        recipe = queue.read_json(queue.trainer.RECIPE)
        jobs = queue.plan_jobs(Path('/tmp/weighted'), recipe)
        self.assertEqual(len(jobs), 20)
        self.assertEqual(len({j['output'] for j in jobs}), 20)
        for fold in range(5):
            for regime in ('all-age', 'child-only'):
                selected = [j for j in jobs if (j['fold'], j['regime']) == (fold, regime)]
                self.assertEqual({j['lr'] for j in selected}, {.001, .0003})
                for job in selected:
                    cmd = queue.command(job, Path('/tmp/binding.json'))
                    self.assertNotIn('--resume', cmd)
                    self.assertNotIn('mps', cmd)
                    self.assertEqual(cmd[cmd.index('--fold') + 1], str(fold))
        changed = {**recipe, 'folds': [0, 1, 2, 3]}
        with self.assertRaisesRegex(ValueError, 'matrix'):
            queue.plan_jobs(Path('/tmp/weighted'), changed)

    def test_lr_tie_prefers_lower_rate_without_reselecting_baseline_by_weighted_results(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            jobs = queue.plan_jobs(base, queue.read_json(queue.trainer.RECIPE))
            plan = {'baselines': {}}
            for job in jobs:
                baseline_loss = .25 if job['lr'] == .001 else .26
                plan['baselines'][job['baselineOutput']] = {'selectionMacroNLL': baseline_loss}
                if (job['fold'], job['regime']) != (0, 'all-age'):
                    continue
                Path(job['output']).mkdir()
                Path(job['baselineOutput']).mkdir()
                report = {'evaluation': {}, 'sameFitPriorEvaluation': {}, 'bestSelectionMacroLogLoss': .3}
                save(Path(job['output']) / 'report.json', report)
                save(Path(job['baselineOutput']) / 'report.json', {**report, 'bestSelectionMacroLogLoss': baseline_loss})
                job.update(verified={'selectionMacroNLL': .3, 'bestEpoch': 3,
                                     'reportSha256': queue.digest(Path(job['output']) / 'report.json')},
                           replay={'verifiedExact': True})
            result = queue.selections(jobs, plan)
            self.assertFalse(result['complete'])
            self.assertEqual(result['selectedGroups'], 1)
            selected = result['selections'][0]
            self.assertEqual(selected['lr'], .0003)
            self.assertEqual(selected['unweightedLR'], .001)
            self.assertAlmostEqual(selected['selectionMacroNLLMinusUnweighted'], .05)
            jobs[0]['replay']['verifiedExact'] = False
            self.assertEqual(queue.selections(jobs, plan)['selectedGroups'], 0)

    def test_weighted_history_uses_corrected_same_regime_loss_and_declared_patience(self):
        recipe = {'maximumEpochs': 5, 'minimumImprovement': 1e-7, 'patienceEpochs': 2}
        history = [{'epoch': i, 'trainWeightedObjective': 1., 'selectionMacroTargetLogLoss': loss,
                    'evaluation': {'allAges': {'macroTargetLogLoss': 2-loss}, 'ages6to12': {'macroTargetLogLoss': loss}}}
                   for i, loss in enumerate([.4, .3, .35, .36], 1)]
        report = {'epochsRun': 4, 'bestEpoch': 2, 'bestSelectionMacroLogLoss': .3}
        queue.verify_history(history, report, 'child-only', recipe)
        with self.assertRaisesRegex(ValueError, 'metric'):
            queue.verify_history(history, report, 'all-age', recipe)
        changed = deepcopy(history)
        changed[1]['trainWeightedObjective'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'metric'):
            queue.verify_history(changed, report, 'child-only', recipe)

    def test_synthetic_fit_verification_exact_replay_and_late_artifact_tamper(self):
        suite = fixtures.BalancedPhoneticTests()
        with suite.study() as fixture:
            original = suite.args(fixture, output=fixture.root / 'outputs/unweighted')
            queue.trainer.baseline.train(original)
            queue.trainer.baseline.replay(original.output)
            args = suite.args(fixture, output=fixture.root / 'outputs/weighted')
            queue.trainer.train(args)
            job = {'family': 'target-scalars', 'regime': 'all-age', 'fold': 0, 'lr': .001,
                   'output': str(args.output.resolve()), 'baselineOutput': str(original.output.resolve())}
            plan = {'binding': str(args.binding.resolve()), 'bindingSha256': queue.digest(args.binding),
                    'contract': {'sourceSha256': queue.trainer.source_hashes(), 'recipeSha256': queue.digest(queue.trainer.RECIPE)}}
            job['verified'] = queue.verify_completed(job, plan)
            result = queue.trainer.replay(args.output)
            self.assertTrue(result['exact'])
            job['replay'] = {'verifiedExact': True, 'sha256': queue.digest(args.output / 'replay.json')}
            queue.guard_outputs(job)
            with (args.output / 'predictions.json').open('ab') as stream:
                stream.write(b' ')
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                queue.guard_outputs(job)

    def test_rehashed_wrong_fit_class_weights_cannot_pass_completed_verifier(self):
        suite = fixtures.BalancedPhoneticTests()
        with suite.study() as fixture:
            original = suite.args(fixture, output=fixture.root / 'outputs/unweighted')
            queue.trainer.baseline.train(original)
            args = suite.args(fixture, output=fixture.root / 'outputs/weighted')
            queue.trainer.train(args)
            config = queue.read_json(args.output / 'config.json')
            config['classWeightState']['weights'][0] *= 2
            save(args.output / 'config.json', config)
            report = queue.read_json(args.output / 'report.json')
            report['configSha256'] = queue.digest(args.output / 'config.json')
            save(args.output / 'report.json', report)
            job = {'family': 'target-scalars', 'regime': 'all-age', 'fold': 0, 'lr': .001,
                   'output': str(args.output.resolve()), 'baselineOutput': str(original.output.resolve())}
            plan = {'binding': str(args.binding.resolve()), 'bindingSha256': queue.digest(args.binding),
                    'contract': {'sourceSha256': queue.trainer.source_hashes(), 'recipeSha256': queue.digest(queue.trainer.RECIPE)}}
            with self.assertRaisesRegex(ValueError, 'actual-fit statistics'):
                queue.verify_completed(job, plan)


if __name__ == '__main__':
    unittest.main()
