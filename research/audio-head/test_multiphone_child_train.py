"""Synthetic child-probe invariants; no corpus audio or real model fits."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_child_train as trainer


class ChildProbeTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        self.temporary = tempfile.TemporaryDirectory(prefix='cadence-child-probe-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in trainer.SOURCES:
            (self.root/name).write_bytes((trainer.HERE/name).read_bytes())
        self.recipe_path = self.root/'recipe.json'
        self.recipe = json.loads(trainer.RECIPE.read_text())
        self.recipe.update(hiddenWidth=8, maximumEpochs=2, patienceEpochs=2, batchSizeClips=2)
        self.cohort = {'clips': [], 'rows': []}
        for index, age in enumerate([8, 20, 10, 12, 25, 9]):
            clip_id = f'clip{index}'
            self.cohort['clips'].append({'id': clip_id, 'speakerId': f'speaker{index}',
                'audioSha256': hashlib.sha256(clip_id.encode()).hexdigest()})
            counts = ([3, 1, 1], [0, 1, 4]) if index == 0 else ([1, 0, 4], [0, 0, 5])
            for target in (0, 1):
                self.cohort['rows'].append({'clipId': clip_id, 'clipIndex': index, 'speakerId': f'speaker{index}',
                    'age': age, 'targetId': target, 'targetPhone': ('B', 'P')[target],
                    'trainingEligible': True, 'raterCounts': list(counts[target])})
        self.fold = {'innerFitRows': list(range(6)), 'innerValidationRows': list(range(6, 10)),
                     'outerFitRows': list(range(10)), 'outerHoldoutRows': [10, 11]}
        self.cohort_path = self.root/'cohort.json'
        self.splits_path = self.root/'splits.json'
        self.cache = self.root/'cache'
        self.cache.mkdir()
        self.feature_overrides = {}
        self.persist()

    def persist(self):
        trainer.atomic_json(self.cohort_path, self.cohort)
        canonical = hashlib.sha256(json.dumps(self.cohort, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        trainer.atomic_json(self.splits_path, {'cohortCanonicalSha256': canonical, 'folds': [self.fold]})
        self.recipe.update(cohortSha256=trainer.digest(self.cohort_path), splitsSha256=trainer.digest(self.splits_path))
        trainer.atomic_json(self.recipe_path, self.recipe)
        trainer.atomic_json(self.cache/'config.json', {'cohortSha256': trainer.digest(self.cohort_path),
            'encoder': trainer.IDENTITIES['wav2vec2-base']})
        entries = {}
        for index, clip in enumerate(self.cohort['clips']):
            frames = self.feature_overrides.get(index)
            if frames is None:
                frames = np.broadcast_to((np.arange(index+3, dtype=np.float32)+index*10)[:, None], (index+3, 768)).copy()
            path = self.cache/f'{clip["id"]}.npz'
            np.savez(path, frames=frames, audio_sha256=clip['audioSha256'], config_sha256=trainer.digest(self.cache/'config.json'))
            entries[clip['id']] = {'path': path.name, 'sha256': trainer.digest(path)}
        trainer.atomic_json(self.cache/'index.json', {'complete': True, 'configSha256': trainer.digest(self.cache/'config.json'),
                                                    'entries': entries})

    def args(self, regime='child-only', **updates):
        result = SimpleNamespace(cohort=self.cohort_path, splits=self.splits_path, cache=self.cache,
            output=self.root/'outputs'/regime, encoder='wav2vec2-base', regime=regime, fold=0, lr=.001,
            seed=7, hidden=8, dropout=.1, weight_decay=.01, batch_size=2, epochs=2, patience=2,
            device='cpu', threads=2, replay=False)
        for name, value in updates.items():
            setattr(result, name, value)
        return result

    @contextlib.contextmanager
    def environment(self):
        with patch.object(trainer, 'HERE', self.root), patch.object(trainer, 'RECIPE', self.recipe_path), \
             contextlib.redirect_stdout(io.StringIO()):
            yield

    def test_child_rows_and_feature_moments_exclude_older_fit_and_all_validation(self):
        args = self.args()
        with self.environment():
            setup = trainer.setup(args)
        _, fit, validation, children, clips, mean, std, state, priors = setup
        self.assertEqual(fit, [0, 1, 4, 5])
        self.assertEqual(validation, [6, 7, 8, 9])
        self.assertEqual(children, [6, 7])
        self.assertEqual(clips, [0, 2])
        expected_frames = np.concatenate((np.arange(3), np.arange(5)+20)).astype(float)
        torch.testing.assert_close(mean, torch.full((768,), expected_frames.mean(), dtype=torch.float32))
        torch.testing.assert_close(std, torch.full((768,), expected_frames.std(), dtype=torch.float32))
        # Neither older fit labels nor any validation feature changes fit statistics.
        self.cohort['rows'][2]['raterCounts'] = [5, 0, 0]
        self.feature_overrides[1] = np.full((4, 768), 1e9, dtype=np.float32)
        self.feature_overrides[3] = np.full((6, 768), 1e6, dtype=np.float32)
        self.feature_overrides[4] = np.full((7, 768), -1e6, dtype=np.float32)
        self.persist()
        with self.environment():
            again = trainer.setup(args)
        torch.testing.assert_close(again[5], mean, rtol=0, atol=0)
        torch.testing.assert_close(again[6], std, rtol=0, atol=0)
        self.assertEqual(again[7], state)
        self.assertEqual(again[8], priors)

    def test_all_age_class_weights_are_fit_only_capped_and_prevalence_normalized(self):
        args = self.args('balanced-all-age')
        with self.environment():
            setup = trainer.setup(args)
        self.assertEqual(setup[1], list(range(6)))
        state = setup[7]
        observed = np.asarray([row['raterCounts'] for row in self.cohort['rows'][:6]]).sum(0)
        self.assertEqual(state['observedRaterCounts'], observed.tolist())
        weights = np.asarray(state['weights'])
        prevalence = observed/observed.sum()
        self.assertAlmostEqual(float(weights@prevalence), 1.)
        expected = 1/np.sqrt(prevalence)
        expected /= expected@prevalence
        np.testing.assert_allclose(weights, expected)
        self.cohort['rows'][6]['raterCounts'] = [5, 0, 0]
        self.persist()
        with self.environment():
            self.assertEqual(trainer.setup(args)[7], state)
        sparse = [{'raterCounts': [0, 0, 5]} for _ in range(200)]+[{'raterCounts': [1, 1, 3]}]
        capped = trainer.fit_class_weights(sparse, 'balanced-all-age')
        self.assertAlmostEqual(max(capped['weights'])/min(capped['weights']), 10.)
        self.assertEqual(capped['observedRaterCounts'], [1, 1, 1003])
        self.assertEqual(capped['trainingPseudocounts'], 0)

    def test_absent_global_class_is_not_filled_with_synthetic_training_counts(self):
        rows = [{'raterCounts': [0, 0, 5]}]
        with self.assertRaisesRegex(ValueError, 'no pseudocounts'):
            trainer.fit_class_weights(rows, 'balanced-all-age')
        ordinary = trainer.fit_class_weights(rows, 'child-only')
        self.assertEqual(ordinary['weights'], [1., 1., 1.])
        self.assertEqual(ordinary['observedRaterCounts'], [0, 0, 5])

    def test_log_weight_correction_recovers_population_distribution_and_loss_is_not_row_normalized(self):
        population = torch.tensor([[.1, .2, .7], [.3, .1, .6]], dtype=torch.float64)
        weights = torch.tensor([4., 2., 1.], dtype=torch.float64)
        logits = (population*weights).log()
        torch.testing.assert_close(trainer.corrected_probabilities(logits, weights), population, atol=1e-15, rtol=0)
        targets = torch.tensor([[.8, .2, 0.], [0., 0., 1.]], dtype=torch.float64)
        actual = trainer.weighted_loss(logits, targets, weights)
        expected = -(targets*weights*logits.log_softmax(-1)).sum(-1)
        torch.testing.assert_close(actual, expected)
        row_normalized = expected/(targets*weights).sum(-1)
        self.assertNotEqual(float(actual[0]), float(row_normalized[0]))

    def test_same_fit_prior_keeps_observed_counts_separate_and_matches_corrected_weighted_prior(self):
        rows = [self.cohort['rows'][index] for index in (0, 1, 4, 5)]
        prior = trainer.fit_priors(rows)
        self.assertEqual(prior['B']['observedRaterCounts'], [4, 1, 5])
        self.assertEqual(prior['P']['observedRaterCounts'], [0, 1, 9])
        self.assertEqual(prior['M']['observedRaterCounts'], [0, 0, 0])
        np.testing.assert_allclose(prior['M']['probabilities'], [1/3]*3)
        weights = torch.tensor([4., 2., 1.], dtype=torch.float64)
        smoothed = torch.tensor(prior['B']['observedRaterCounts'], dtype=torch.float64)+1
        corrected = trainer.corrected_probabilities((smoothed*weights).log(), weights)
        np.testing.assert_allclose(corrected.numpy(), prior['B']['probabilities'], atol=1e-15)

    def test_inner_selection_uses_child_macro_loss_while_older_all_age_metrics_improve(self):
        self.recipe.update(maximumEpochs=6, patienceEpochs=2)
        self.persist()
        args = self.args(epochs=6, patience=2)
        values = iter([(.6, .4), (.4, .3), (.5, .2), (.55, .1), (.4, .3)])
        def evaluate(model, data, rows, *unused):
            self.assertEqual(rows, self.fold['innerValidationRows'])
            child, all_age = next(values)
            return {'ages6to12': {'macroTargetLogLoss': child}, 'allAges': {'perRaterLogLoss': all_age}}, {
                'rowIndices': rows, 'probabilities': [[.1, .2, .7]]*len(rows)}
        with self.environment(), patch.object(trainer, 'evaluate', side_effect=evaluate):
            report = trainer.train(args)
        self.assertEqual((report['bestEpoch'], report['epochsRun']), (2, 4))
        self.assertEqual(report['bestChildMacroLogLoss'], .4)
        self.assertEqual(torch.load(args.output/'best.pt', weights_only=True)['epoch'], 2)

    def test_child_only_never_loads_older_fit_or_outer_features_and_keeps_undefined_discrimination(self):
        self.cohort['rows'][10]['raterCounts'] = [-1, 0, 6]
        self.persist()
        (self.cache/'clip1.npz').unlink()
        (self.cache/'clip5.npz').unlink()
        with self.environment():
            report = trainer.train(self.args())
        child = report['evaluation']['ages6to12']
        self.assertEqual(child['macroTargetPhones'], ['B', 'P'])
        self.assertEqual(child['observedRaterCounts'], [1, 0, 9])
        self.assertIsNone(child['discrimination']['classes']['1']['conditionalNLL'])
        self.assertIsNone(child['targetDiscrimination']['perPhone']['P']['rating0']['auroc'])

    def test_selected_checkpoint_replay_reproduces_both_regimes_and_same_fit_prior(self):
        for regime in trainer.REGIMES:
            args = self.args(regime)
            with self.environment():
                report = trainer.train(args)
                replay = trainer.replay(args.output)
            self.assertEqual(replay['maximumAbsoluteProbabilityDifference'], 0.)
            self.assertEqual(replay['evaluation'], report['evaluation'])
            self.assertAlmostEqual(report['childMacroLogLossMinusPrior'],
                report['evaluation']['ages6to12']['macroTargetLogLoss']-
                report['sameFitPriorEvaluation']['ages6to12']['macroTargetLogLoss'])
            saved = torch.load(args.output/'best.pt', weights_only=True)
            config = json.loads((args.output/'config.json').read_text())
            self.assertEqual(saved['classWeightState'], config['classWeightState'])
            self.assertEqual(config['childSelectionRows'], [6, 7])
            path = args.output/'best.pt'
            path.write_bytes(path.read_bytes()+b'changed checkpoint')
            with self.environment(), self.assertRaisesRegex(ValueError, 'completed report'):
                trainer.replay(args.output)


if __name__ == '__main__':
    unittest.main()
