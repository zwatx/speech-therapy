"""Synthetic local-head provenance, split, target-row and checkpoint tests."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_local_head as trainer
from test_multiphone_local_train import fixture, save


class LocalHeadTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        self.temporary = tempfile.TemporaryDirectory(prefix='cadence-local-head-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in set(trainer.SOURCES) | {'multiphone_local_features.py', 'alignment_pilot.py'}:
            (self.root/name).write_bytes((trainer.HERE/name).read_bytes())
        self.recipe = json.loads(trainer.RECIPE.read_text())
        self.recipe.update(hiddenWidth=8, phoneEmbeddingWidth=8, batchSizeTargetRows=4, maximumEpochs=2, patienceEpochs=2)
        self.recipe_path = self.root/'training-recipe.json'
        self.serial = 0
        self.rebuild()

    def rebuild(self, cohort=None, pooled=None):
        self.serial += 1
        directory = self.root/f'data{self.serial}'
        self.paths = fixture(directory, cohort)
        self.cohort = trainer.read_json(self.paths.cohort)
        self.splits = trainer.read_json(self.paths.splits)
        count = len(self.cohort['rows'])
        if pooled is None:
            pooled = np.arange(count*768, dtype=np.float32).reshape(count, 768)/100
            pooled[:, 3] = 4.  # Stable zero-SD column.
        self.pooled = pooled.copy()
        np.save(directory/'pooled.npy', pooled, allow_pickle=False)
        wavlm = directory/'wavlm'
        wavlm.mkdir()
        save(wavlm/'config.json', {'encoder': trainer.WavLMEncoder.identity,
             'cohortSha256': trainer.digest(self.paths.cohort), 'authorPartition': 'train', 'dtype': 'float32'})
        save(wavlm/'index.json', {'complete': True, 'configSha256': trainer.digest(wavlm/'config.json'),
            'entries': {clip['id']: {'frames': 9, 'audioSha256': clip['audioSha256']}
                        for clip in self.cohort['clips']}})
        self.metadata = trainer.read_json(self.paths.features)
        extraction_recipe = trainer.read_json(directory/'recipe.json')
        extraction_recipe['poolingContextFrames'] = 2
        save(directory/'recipe.json', extraction_recipe)
        ctc_index = trainer.read_json(directory/'ctc/index.json')
        ctc_index['entries'] = {clip['id']: {'frames': 9, 'audioSha256': clip['audioSha256']}
                               for clip in self.cohort['clips']}
        save(directory/'ctc/index.json', ctc_index)
        self.metadata.update(recipeSha256=trainer.digest(directory/'recipe.json'),
                             ctcIndexSha256=trainer.digest(directory/'ctc/index.json'))
        for position, row in enumerate(self.metadata['rows']):
            row.update(pooledFeatureIndex=position, intervalFrames=[3, 4], estimatedPoolingWindowFrames=[1, 6])
        self.metadata.update(pooledFeatures={'path': 'pooled.npy', 'sha256': trainer.digest(directory/'pooled.npy'),
                'dtype': 'float32', 'shape': [count, 768]},
            pooledFeaturesSha256=trainer.digest(directory/'pooled.npy'),
            wavlmIndexPath=str(wavlm/'index.json'), wavlmIndexSha256=trainer.digest(wavlm/'index.json'),
            inputSha256={'wavlmConfig': trainer.digest(wavlm/'config.json')})
        self.persist_metadata()

    def persist_metadata(self):
        save(self.paths.features, self.metadata)
        self.recipe.update(cohortSha256=trainer.digest(self.paths.cohort), splitsSha256=trainer.digest(self.paths.splits),
                           featuresSha256=trainer.digest(self.paths.features))
        save(self.recipe_path, self.recipe)

    def args(self, family='embedding', regime='all-age', **updates):
        values = dict(cohort=self.paths.cohort, splits=self.paths.splits, features=self.paths.features,
            output=self.root/'outputs'/f'{family}-{regime}', family=family, regime=regime, fold=0, lr=.001,
            hidden=8, dropout=.1, weight_decay=.01, batch_size=4, epochs=2, patience=2,
            seed=7, device='cpu', threads=2, replay=False)
        values.update(updates)
        return SimpleNamespace(**values)

    @contextlib.contextmanager
    def environment(self):
        with patch.object(trainer, 'HERE', self.root), patch.object(trainer, 'RECIPE', self.recipe_path), \
             contextlib.redirect_stdout(io.StringIO()):
            yield

    def load(self):
        return trainer.load_local_inputs(self.paths.cohort, self.paths.splits, self.paths.features)

    def test_each_target_is_its_own_singleton_model_row_in_both_families(self):
        for family, width in [('embedding', 768), ('embedding-scalars', 781)]:
            with self.environment():
                data = trainer.setup(self.args(family))
            indices = data['fit'][:2]
            values, phones, mask, targets = trainer.batch(data, indices, 'cpu')
            self.assertEqual(values.shape, (2, 1, width))
            self.assertEqual(phones.shape, (2, 1))
            self.assertTrue(mask.all())
            for offset, index in enumerate(indices):
                expected = (torch.tensor(data['values'][index])-data['mean'])/data['std']
                torch.testing.assert_close(values[offset, 0], expected, rtol=0, atol=0)
                self.assertEqual(phones[offset, 0].item(), self.cohort['rows'][index]['targetId'])
            model = trainer.make_model(self.args(family), width).eval()
            logits = model(values, mask, phones, mask)
            self.assertEqual(logits.shape, (2, 1, 3))
            # A prediction cannot receive another target row's pooled vector.
            changed = values.clone()
            changed[1] += 1000
            torch.testing.assert_close(model(changed, mask, phones, mask)[0], logits[0], rtol=0, atol=0)
            np.testing.assert_allclose(targets.sum(1), 1.)

    def test_pooled_index_window_and_audio_binding_refused(self):
        original = deepcopy(self.metadata)
        for key, value in [('pooledFeatureIndex', 1), ('estimatedPoolingWindowFrames', [0, 20]),
                           ('estimatedPoolingWindowFrames', [2, 5]),
                           ('intervalFrames', [4, 4])]:
            self.metadata = deepcopy(original)
            self.metadata['rows'][0][key] = value
            self.persist_metadata()
            with self.assertRaisesRegex(ValueError, 'mapping or window'):
                self.load()
        self.metadata = original
        self.persist_metadata()
        path = Path(self.metadata['wavlmIndexPath'])
        index = trainer.read_json(path)
        index['entries'][self.cohort['clips'][0]['id']]['audioSha256'] = 'wrong-audio'
        save(path, index)
        self.metadata['wavlmIndexSha256'] = trainer.digest(path)
        self.persist_metadata()
        with self.assertRaisesRegex(ValueError, 'mapping or window'):
            self.load()

    def test_pooled_hash_shape_dtype_nonfinite_and_cache_identity_refused(self):
        path = self.paths.features.parent/'pooled.npy'
        original = path.read_bytes()
        path.write_bytes(original+b'changed')
        with self.assertRaisesRegex(ValueError, 'path/digest'):
            self.load()
        for matrix in [self.pooled.astype(np.float64), self.pooled[:, :-1], self.pooled.copy()]:
            if matrix.shape == self.pooled.shape and matrix.dtype == np.float32:
                matrix[0, 0] = np.nan
            np.save(path, matrix, allow_pickle=False)
            self.metadata['pooledFeatures']['sha256'] = trainer.digest(path)
            self.metadata['pooledFeaturesSha256'] = trainer.digest(path)
            self.persist_metadata()
            with self.assertRaisesRegex(ValueError, 'Invalid pooled matrix'):
                self.load()
        path.write_bytes(original)
        self.metadata['pooledFeatures']['sha256'] = trainer.digest(path)
        self.metadata['pooledFeaturesSha256'] = trainer.digest(path)
        index_path = Path(self.metadata['wavlmIndexPath'])
        config_path = index_path.parent/'config.json'
        config = trainer.read_json(config_path)
        config['encoder']['revision'] = 'different-revision'
        save(config_path, config)
        index = trainer.read_json(index_path)
        index['configSha256'] = trainer.digest(config_path)
        save(index_path, index)
        self.metadata['wavlmIndexSha256'] = trainer.digest(index_path)
        self.metadata['inputSha256']['wavlmConfig'] = trainer.digest(config_path)
        self.persist_metadata()
        with self.assertRaisesRegex(ValueError, 'cache identity/config'):
            self.load()

    def test_child_moments_and_priors_ignore_older_fit_validation_and_outer_rows(self):
        with self.environment():
            data = trainer.setup(self.args(regime='child-only'))
        self.assertTrue(all(6 <= self.cohort['rows'][i]['age'] <= 12 for i in data['fit']))
        expected = self.pooled[data['fit']].astype(np.float64)
        np.testing.assert_array_equal(data['mean'].numpy(), expected.mean(0).astype(np.float32))
        self.assertEqual(data['std'][3].item(), 1.)
        changed, pooled = deepcopy(self.cohort), self.pooled.copy()
        for index in set(range(len(changed['rows'])))-set(data['fit']):
            pooled[index] = 1e9+index
            changed['rows'][index]['raterCounts'] = [0, 5, 0]
        self.rebuild(changed, pooled)
        with self.environment():
            again = trainer.setup(self.args(regime='child-only'))
        self.assertEqual(data['fit'], again['fit'])
        torch.testing.assert_close(data['mean'], again['mean'], rtol=0, atol=0)
        torch.testing.assert_close(data['std'], again['std'], rtol=0, atol=0)
        self.assertEqual(data['priors'], again['priors'])

    def test_all_age_scaling_uses_fit_target_rows_and_same_fit_smoothed_priors(self):
        with self.environment():
            data = trainer.setup(self.args('embedding-scalars'))
        self.assertEqual(data['fit'], self.splits['folds'][0]['innerFitRows'])
        expected = data['values'][data['fit']].astype(np.float64)
        np.testing.assert_array_equal(data['mean'].numpy(), expected.mean(0).astype(np.float32))
        for phone in ('B', 'P'):
            observed = np.asarray([self.cohort['rows'][i]['raterCounts'] for i in data['fit']
                                   if self.cohort['rows'][i]['targetPhone'] == phone]).sum(0)
            np.testing.assert_array_equal(data['priors'][phone]['observedRaterCounts'], observed)
            np.testing.assert_allclose(data['priors'][phone]['probabilities'], (observed+1)/(observed.sum()+3))
        self.assertEqual(data['priors']['M']['observedRaterCounts'], [0, 0, 0])
        np.testing.assert_allclose(data['priors']['M']['probabilities'], [1/3]*3)

    def test_epoch_selection_uses_regime_metric_and_child_patience_ignores_adult_improvement(self):
        self.recipe.update(maximumEpochs=6, patienceEpochs=2)
        self.persist_metadata()
        values = iter([(.6, .4), (.4, .3), (.5, .2), (.55, .1), (.4, .3)])
        def evaluate(model, data, indices, *unused):
            self.assertEqual(indices, self.splits['folds'][0]['innerValidationRows'])
            child, all_age = next(values)
            return {'ages6to12': {'macroTargetLogLoss': child}, 'allAges': {'macroTargetLogLoss': all_age}}, {
                'rowIndices': indices, 'probabilities': [[.1, .2, .7]]*len(indices)}
        with self.environment(), patch.object(trainer, 'evaluate', side_effect=evaluate):
            report = trainer.train(self.args(regime='child-only', epochs=6, patience=2))
        self.assertEqual((report['bestEpoch'], report['epochsRun']), (2, 4))
        self.assertEqual(report['bestSelectionMacroLogLoss'], .4)
        self.assertEqual(trainer.selection_loss({'allAges': {'macroTargetLogLoss': .2},
            'ages6to12': {'macroTargetLogLoss': .9}}, 'all-age'), .2)

    def test_all_four_family_regime_checkpoints_replay_exactly_and_leave_undefined_support_visible(self):
        for family in trainer.FAMILIES:
            for regime in trainer.REGIMES:
                args = self.args(family, regime)
                with self.environment():
                    report = trainer.train(args)
                    replay = trainer.replay(args.output)
                self.assertEqual(replay['maximumAbsoluteProbabilityDifference'], 0.)
                self.assertEqual(replay['evaluation'], report['evaluation'])
                self.assertIsNone(report['evaluation']['allAges']['discrimination']['classes']['1']['conditionalNLL'])
                config = trainer.read_json(args.output/'config.json')
                self.assertFalse(config['classWeighting'])
                self.assertFalse(config['outerOutcomesUsed'])
                self.assertFalse(set(config['fitRows']+config['validationRows']) & set(self.splits['folds'][0]['outerHoldoutRows']))
                saved = torch.load(args.output/'best.pt', weights_only=True)
                self.assertEqual(saved['epoch'], report['bestEpoch'])
                self.assertEqual(saved['configSha256'], trainer.digest(args.output/'config.json'))
        checkpoint = args.output/'best.pt'
        checkpoint.write_bytes(checkpoint.read_bytes()+b'changed')
        with self.environment(), self.assertRaisesRegex(ValueError, 'completed report'):
            trainer.replay(args.output)

    def test_input_change_during_fit_prevents_completed_report_and_source_change_blocks_replay(self):
        args = self.args()
        original_evaluate = trainer.evaluate
        mutated = False
        def evaluate(*values):
            nonlocal mutated
            result = original_evaluate(*values)
            if not mutated:
                path = self.paths.features.parent/'pooled.npy'
                path.write_bytes(path.read_bytes()+b'changed-during-run')
                mutated = True
            return result
        with self.environment(), patch.object(trainer, 'evaluate', side_effect=evaluate), \
             self.assertRaisesRegex(ValueError, 'input binding changed'):
            trainer.train(args)
        self.assertFalse((args.output/'report.json').exists())
        self.rebuild()
        args = self.args(output=self.root/'outputs'/'source-tamper')
        with self.environment():
            trainer.train(args)
        (self.root/'multiphone_models.py').write_text('changed source')
        with self.environment(), self.assertRaisesRegex(ValueError, 'implementation changed'):
            trainer.replay(args.output)


if __name__ == '__main__':
    unittest.main()
