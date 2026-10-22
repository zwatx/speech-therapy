"""Synthetic consistency mechanics, selection boundaries and artifact checks."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_consistency_train as trainer
from test_multiphone_controls import synthetic_study


def synthetic_data(regime):
    cohort, splits = synthetic_study()
    fit, validation, selection = trainer.baseline.select_rows(cohort, splits, 0, regime)
    torch.manual_seed(29)
    network = trainer.model()
    generator = np.random.default_rng(91)
    indices = fit + validation
    clean = torch.tensor(generator.normal(size=(len(indices), 1037)), dtype=torch.float32)
    noisy = clean + torch.tensor(generator.normal(scale=.2, size=clean.shape), dtype=torch.float32)
    ids = torch.tensor([cohort['rows'][i]['targetId'] for i in indices], dtype=torch.long)
    return dict(cohort=cohort, splits=splits, fit=fit, validation=validation, selection=selection,
        clean=clean, noisy=noisy, ids=ids, fitCount=len(fit), mean=torch.zeros(1037), std=torch.ones(1037),
        teacherFit=trainer.predict(network, clean[:len(fit)], ids[:len(fit)]),
        warmPredictions=trainer.predict(network, clean[len(fit):], ids[len(fit):]),
        warmState=deepcopy(network.state_dict()), warmModel=network.requires_grad_(False), allBindings={},
        labels=torch.tensor([cohort['rows'][i]['raterCounts'] for i in fit], dtype=torch.float32) / 5)


class ConsistencyTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / 'outputs').mkdir()
        self.plan_path = self.root / 'outputs/plan.json'
        self.data = {regime: synthetic_data(regime) for regime in trainer.REGIMES}
        self.plan = {'complete': True, 'recipeSha256': trainer.digest(trainer.RECIPE),
            'sourceSha256': {'synthetic': 'stable'}, 'inputFiles': {},
            'arms': [{'regime': r, 'coefficient': c} for r in trainer.REGIMES for c in trainer.COEFFICIENTS],
            'noisyFeatures': 'unused-synthetic', 'noisyFeaturesSha256': 'unused-synthetic',
            'populations': {r: {k + 'Rows': self.data[r][k] for k in ('fit', 'validation', 'selection')}
                            for r in trainer.REGIMES}}
        trainer.atomic_json(self.plan_path, self.plan)
        self.plan_sha = trainer.digest(self.plan_path)
        self.enterContext(patch.object(trainer, 'HERE', self.root))
        self.enterContext(patch.object(trainer, 'source_hashes', return_value={'synthetic': 'stable'}))
        self.enterContext(patch.object(trainer, 'load_data', side_effect=lambda regime, *_: deepcopy(self.data[regime])))

    def args(self, regime='all-age', coefficient=.1, name='trial'):
        return SimpleNamespace(plan=self.plan_path, plan_sha256=self.plan_sha, regime=regime,
            coefficient=coefficient, output=self.root / 'outputs' / name)

    def test_zero_coefficient_never_uses_noisy_values_for_updates(self):
        data = self.data['all-age']; n = data['fitCount']
        parameters = []
        for noise in (data['noisy'][:n], torch.full_like(data['noisy'][:n], float('nan'))):
            student = trainer.model(); student.load_state_dict(data['warmState'])
            optimizer = torch.optim.AdamW(student.parameters(), lr=3e-5, weight_decay=.01)
            trainer.train_epoch(student, optimizer, data['clean'][:n], noise, data['ids'][:n], data['labels'],
                torch.tensor(data['teacherFit'], dtype=torch.float32), np.arange(n), 0.)
            self.assertFalse(student.training)
            parameters.append(deepcopy(student.state_dict()))
        self.assertTrue(all(torch.equal(parameters[0][k], parameters[1][k]) for k in parameters[0]))
        self.assertTrue(any(not torch.equal(parameters[0][k], data['warmState'][k]) for k in parameters[0]))

    def test_teacher_is_detached_and_positive_coefficient_changes_update(self):
        data = self.data['all-age']; n = data['fitCount']; weights = []
        teacher = torch.tensor(data['teacherFit'], dtype=torch.float32, requires_grad=True)
        for coefficient in (0., 1.):
            student = trainer.model(); student.load_state_dict(data['warmState'])
            optimizer = torch.optim.AdamW(student.parameters(), lr=3e-5, weight_decay=.01)
            losses = trainer.train_epoch(student, optimizer, data['clean'][:n], data['noisy'][:n],
                data['ids'][:n], data['labels'], teacher, np.arange(n), coefficient)
            self.assertIsNone(teacher.grad)
            self.assertFalse(student.training)
            if coefficient: self.assertGreater(losses['fixedTeacherKL'], 0)
            weights.append(deepcopy(student.state_dict()))
        self.assertTrue(any(not torch.equal(weights[0][k], weights[1][k]) for k in weights[0]))

    def test_both_populations_fit_and_exact_clean_noisy_checkpoint_replay(self):
        for regime in trainer.REGIMES:
            args = self.args(regime=regime, name=regime)
            report = trainer.fit(args)
            self.assertTrue(report['fitComplete'])
            self.assertFalse(report['complete'])
            self.assertFalse(report['noisyAccuracyMeasured'])
            self.assertNotIn('noisyEvaluation', report)
            replay = trainer.replay(args.output)
            self.assertTrue(replay['exact'])
            self.assertTrue(replay['complete'])
            self.assertEqual(replay['rows'], len(self.data[regime]['validation']))
            checkpoint = torch.load(args.output / 'best.pt', weights_only=True)
            self.assertEqual(checkpoint['configSha256'], trainer.digest(args.output / 'config.json'))

    def test_original_epoch_zero_remains_eligible_and_earlier_ties_win(self):
        args = self.args()
        with patch.object(trainer, 'selection_value', return_value=.25):
            report = trainer.fit(args)
            self.assertEqual(report['bestEpoch'], 0)
            self.assertEqual(report['epochsRun'], 2)
            self.assertTrue(trainer.replay(args.output)['exact'])
        checkpoint = torch.load(args.output / 'best.pt', weights_only=True)
        self.assertTrue(all(torch.equal(checkpoint['model'][k], self.data['all-age']['warmState'][k])
                            for k in checkpoint['model']))

    def test_noisy_validation_cannot_change_training_or_epoch_selection(self):
        before = self.args(coefficient=1., name='before'); trainer.fit(before)
        data = self.data['all-age']; data['noisy'][data['fitCount']:] *= -20
        after = self.args(coefficient=1., name='after'); trainer.fit(after)
        self.assertEqual(trainer.read_json(before.output / 'history.json'), trainer.read_json(after.output / 'history.json'))
        a = torch.load(before.output / 'best.pt', weights_only=True)
        b = torch.load(after.output / 'best.pt', weights_only=True)
        self.assertEqual(a['epoch'], b['epoch'])
        self.assertTrue(all(torch.equal(a['model'][k], b['model'][k]) for k in a['model']))
        self.assertNotEqual(trainer.read_json(before.output / 'predictions.json')['noisyProbabilities'],
                            trainer.read_json(after.output / 'predictions.json')['noisyProbabilities'])

    def test_mutated_output_after_last_epoch_cannot_publish_complete(self):
        original = trainer.sensitivity
        for filename in ('config.json', 'teacher-fit.npy', 'best.pt', 'history.json'):
            args = self.args(name=filename.replace('.', '-'))
            mutated = False
            def change(*values):
                nonlocal mutated
                if not mutated:
                    with (args.output / filename).open('ab') as stream: stream.write(b' ')
                    mutated = True
                return original(*values)
            with patch.object(trainer, 'sensitivity', side_effect=change):
                with self.assertRaisesRegex(ValueError, 'Owned training artifact'):
                    trainer.fit(args)
            self.assertFalse((args.output / 'report.json').exists())

    def test_changed_predictions_and_changed_plan_rejected(self):
        args = self.args(); trainer.fit(args)
        predictions = trainer.read_json(args.output / 'predictions.json')
        predictions['noisyProbabilities'][0] = [.1, .2, .7]
        trainer.atomic_json(args.output / 'predictions.json', predictions)
        with self.assertRaisesRegex(ValueError, 'artifacts differ'):
            trainer.replay(args.output)
        changed = deepcopy(self.plan); changed['arms'][0]['coefficient'] = .2
        trainer.atomic_json(self.plan_path, changed)
        with self.assertRaisesRegex(ValueError, 'declaration changed'):
            trainer.fit(self.args(name='changed-plan'))

    def test_probability_movement_is_not_a_label_score(self):
        original = np.array([[.2, .3, .5], [1., 0., 0.]])
        changed = np.array([[.1, .3, .6], [0., 0., 1.]])
        result = trainer.movement(original, changed)
        self.assertAlmostEqual(result['meanTotalVariation'], .55)
        self.assertAlmostEqual(result['meanExpectedRatingShift'], 1.1)
        self.assertEqual(result['argmaxChanges'], 1)
        self.assertNotIn('accuracy', result)

    def test_changed_protocol_or_design_parameters_rejected(self):
        recipe = trainer.read_json(trainer.RECIPE)
        trainer.validate_recipe(recipe)
        recipe['learningRate'] = 1e-3
        with self.assertRaisesRegex(ValueError, 'fixed six-arm'):
            trainer.validate_recipe(recipe)

    def test_declaration_retains_distinct_lexical_protocol_pins(self):
        recipe = trainer.read_json(trainer.RECIPE)
        original = Path(recipe['protocolPath'])
        alias = original.parent / '..' / original.parent.name / original.name
        for data in self.data.values():
            data['allBindings']['protocol'] = {'path': str(alias), 'sha256': recipe['protocolSha256']}
        result = trainer.declare(self.root / 'noisy-features.json', 'synthetic-noise-sha',
                                 self.root / 'outputs' / 'second-plan.json')
        self.assertEqual(result['inputFiles']['protocol']['path'], str(alias))
        self.assertEqual(result['inputFiles']['declaredProtocol']['path'], str(original))
        self.assertEqual(result['inputFiles']['protocol']['sha256'], result['inputFiles']['declaredProtocol']['sha256'])

    def test_history_enforces_patience_and_full_budget(self):
        def history(values):
            return [{'epoch': i, 'selectionMacroNLL': v} for i, v in enumerate(values)]
        self.assertEqual(trainer.validate_history(history([.5, .4, .41, .42]), .5), (.4, 1))
        self.assertEqual(trainer.validate_history(history([.5, .5, .5]), .5), (.5, 0))
        with self.assertRaisesRegex(ValueError, 'Invalid epoch history'):
            trainer.validate_history(history([.5, .4]), .5)
        with self.assertRaisesRegex(ValueError, 'continued after'):
            trainer.validate_history(history([.5, .51, .52, .53]), .5)
        with self.assertRaisesRegex(ValueError, 'stopped before'):
            trainer.validate_history(history([.5, .4, .3]), .5)
        recipe = trainer.read_json(trainer.RECIPE); recipe['protocolSha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'protocol changed'):
            trainer.validate_recipe(recipe)


if __name__ == '__main__':
    unittest.main()
