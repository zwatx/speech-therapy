"""Synthetic phonetic feature binding, leakage, regimes and exact replay tests."""
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

import multiphone_phonetic_head as trainer
from test_multiphone_controls import synthetic_study
from test_multiphone_local_train import fixture, save


class PhoneticHeadTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.temporary = tempfile.TemporaryDirectory(prefix='cadence-phonetic-head-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in trainer.SOURCES:
            (self.root / name).write_bytes((trainer.HERE / name).read_bytes())
        (self.root / 'outputs').mkdir()
        self.head_recipe = trainer.read_json(trainer.RECIPE)
        self.head_recipe.update(hiddenWidth=8, batchSizeTargetRows=4, maximumEpochs=2, patienceEpochs=2, threads=1)
        self.head_recipe_path = self.root / 'head-recipe.json'
        self.extract_recipe = trainer.read_json(trainer.EXTRACTION_RECIPE)
        self.extract_recipe_path = self.root / 'extraction-recipe.json'
        cohort, _ = synthetic_study()
        for clip in cohort['clips']:
            clip['sampleCount'] = 3200
        for row in cohort['rows']:
            row.update(wordIndex=0, phoneIndex=row['targetId'])
        self.paths = fixture(self.root / 'original', cohort)
        self.cohort = trainer.read_json(self.paths.cohort)
        self.splits = trainer.read_json(self.paths.splits)
        original = trainer.read_json(self.paths.features)
        for row in original['rows']:
            interval = [1, 2] if row['targetId'] == 0 else [6, 7]
            row.update(intervalFrames=interval, estimatedPoolingWindowFrames=[max(0, interval[0]-2), min(9, interval[1]+2)])
        save(self.paths.features, original)
        self.original = original
        self.directory = self.root / 'phonetic'
        (self.directory / 'clips').mkdir(parents=True)
        self.feature_path = self.directory / 'features.json'
        self.binding_path = self.root / 'outputs/binding.json'
        self.rows = [{**{key: row[key] for key in trainer.extraction.ROW_FIELDS}, 'outputIndex': i}
                     for i, row in enumerate(original['rows'])]
        self.target = np.arange(len(self.rows) * 1024, dtype=np.float32).reshape(len(self.rows), 1024) / 100
        self.target[:, 3] = 2.
        self.global_values = np.repeat(np.arange(10, dtype=np.float32), 2)[:, None] * np.ones((1, 1024), np.float32)
        checkpoint = self.root / 'checkpoint.bin'
        checkpoint.write_bytes(b'synthetic phonetic checkpoint, no inference')
        download = self.root / 'download.json'
        save(download, {'purpose': 'synthetic'})
        self.extract_recipe.update(expectedEligibleRows=20, expectedClips=10,
            cohortSha256=trainer.digest(self.paths.cohort), splitsSha256=trainer.digest(self.paths.splits),
            featuresSha256=trainer.digest(self.paths.features), artifactSha256={'checkpoint.bin': trainer.digest(checkpoint)},
            downloadRecordSha256=trainer.digest(download))
        save(self.extract_recipe_path, self.extract_recipe)
        bindings = {'recipe': trainer.extraction.file_binding(self.extract_recipe_path),
                    'checkpoint/checkpoint.bin': trainer.extraction.file_binding(checkpoint),
                    'checkpoint/downloadRecord': trainer.extraction.file_binding(download)}
        for name in trainer.extraction.SOURCES:
            bindings['source/' + name] = trainer.extraction.file_binding(trainer.extraction.HERE / name)
        for name, path in (('cohort', self.paths.cohort), ('splits', self.paths.splits), ('features', self.paths.features)):
            bindings[name] = trainer.extraction.file_binding(path)
        self.config = {'recipe': self.extract_recipe, 'bindings': bindings}
        self.publish()
        self.head_recipe.update(cohortSha256=trainer.digest(self.paths.cohort), splitsSha256=trainer.digest(self.paths.splits),
                                originalFeaturesSha256=trainer.digest(self.paths.features))
        save(self.head_recipe_path, self.head_recipe)

    def publish(self):
        save(self.directory / 'config.json', self.config)
        config_sha = trainer.digest(self.directory / 'config.json')
        entries = {}
        for clip in self.cohort['clips']:
            rows = [row for row in self.rows if row['clipId'] == clip['id']]
            ids = [row['outputIndex'] for row in rows]
            directory = self.directory / 'clips' / clip['id']
            directory.mkdir(exist_ok=True)
            np.savez_compressed(directory / 'vectors.npz', target=self.target[ids], **{'global': self.global_values[ids[0]]})
            expected = trainer.extraction.expected_entry(clip, rows, config_sha, 9)
            save(directory / 'entry.json', {'binding': expected, 'vectorsPath': 'vectors.npz',
                                           'sha256': trainer.digest(directory / 'vectors.npz')})
            entries[clip['id']] = {'path': f'clips/{clip["id"]}/vectors.npz', 'frames': 9,
                'targets': len(rows), 'audioSha256': clip['audioSha256'],
                'sha256': trainer.digest(directory / 'vectors.npz'), 'entrySha256': trainer.digest(directory / 'entry.json')}
        save(self.directory / 'index.json', {'complete': True, 'clipCount': 10, 'configSha256': config_sha, 'entries': entries})
        report = {'complete': True, 'fullCohortCoverage': True, 'failedRows': [], 'unmappableRows': [],
            'eligibleCohortRows': 20, 'clipCount': 10, 'rowIndices': self.original['rowIndices'], 'rows': self.rows,
            'originalWindowsUnchanged': True, 'globalVectorsRepeatedPerTarget': True,
            'encoderIdentity': {key: self.extract_recipe[key] for key in ('modelId', 'revision', 'artifactSha256', 'hiddenWidth')},
            'configPath': str(self.directory / 'config.json'), 'configSha256': config_sha,
            'indexSha256': trainer.digest(self.directory / 'index.json'), 'bindings': self.config['bindings'],
            **trainer.extraction.FALSE_FLAGS}
        for name, values in (('target', self.target), ('global', self.global_values)):
            np.save(self.directory / (name + '.npy'), values, allow_pickle=False)
            report[name + 'Features'] = {'path': name + '.npy', 'sha256': trainer.digest(self.directory / (name + '.npy')),
                                        'shape': list(values.shape), 'dtype': 'float32'}
        save(self.feature_path, report)

    @contextlib.contextmanager
    def environment(self):
        with patch.object(trainer, 'HERE', self.root), patch.object(trainer, 'RECIPE', self.head_recipe_path), \
             patch.object(trainer, 'EXTRACTION_RECIPE', self.extract_recipe_path), contextlib.redirect_stdout(io.StringIO()):
            yield

    def bundle(self):
        with self.environment():
            return trainer.validate_bundle(self.paths.cohort, self.paths.splits, self.paths.features, self.feature_path, self.head_recipe)

    def bind(self):
        with self.environment():
            return trainer.bind_features(SimpleNamespace(cohort=self.paths.cohort, splits=self.paths.splits,
                original_features=self.paths.features, phonetic_features=self.feature_path, output=self.binding_path))

    def args(self, family='target', regime='all-age', **updates):
        values = dict(binding=self.binding_path, output=self.root / 'outputs' / f'{family}-{regime}',
                      family=family, regime=regime, fold=0, seed=7, lr=.001, hidden=8, dropout=.1,
                      weight_decay=.01, batch_size=4, epochs=2, patience=2, threads=1, device='cpu')
        values.update(updates)
        return SimpleNamespace(**values)

    def test_binding_is_explicit_exclusive_and_revalidates_every_unit(self):
        evidence = self.bind()
        self.assertEqual(evidence['rowIndices'], self.original['rowIndices'])
        self.assertTrue(evidence['allPerClipUnitsAndGlobalRepetitionVerified'])
        with self.assertRaisesRegex(ValueError, 'new binding'):
            self.bind()
        path = self.directory / 'clips/clip-0/vectors.npz'
        path.write_bytes(path.read_bytes() + b'changed')
        with self.environment(), self.assertRaisesRegex(ValueError, 'artifact changed'):
            trainer.load_bound(self.binding_path, self.head_recipe)

    def test_coverage_row_identity_and_column_dtype_rejected(self):
        original = trainer.read_json(self.feature_path)
        for field, value in (('complete', False), ('rowIndices', original['rowIndices'][::-1])):
            report = deepcopy(original)
            report[field] = value
            save(self.feature_path, report)
            with self.assertRaisesRegex(ValueError, 'scope'):
                self.bundle()
        report = deepcopy(original)
        report['rows'][0]['rowId'] = report['rows'][1]['rowId']
        save(self.feature_path, report)
        with self.assertRaisesRegex(ValueError, 'row identity'):
            self.bundle()
        for matrix in (self.target.astype(np.float64), self.target[:, :-1], np.full_like(self.target, np.nan)):
            report = deepcopy(original)
            np.save(self.directory / 'target.npy', matrix, allow_pickle=False)
            report['targetFeatures']['sha256'] = trainer.digest(self.directory / 'target.npy')
            save(self.feature_path, report)
            with self.assertRaisesRegex(ValueError, 'matrix shape/dtype/values'):
                self.bundle()

    def test_global_repetition_and_assembled_target_binding_are_checked(self):
        self.global_values[1] += 1  # Same clip's second target must get the identical global vector.
        self.publish()
        with self.assertRaisesRegex(ValueError, 'repeated global vector'):
            self.bundle()
        self.global_values[1] -= 1
        self.publish()
        matrix = np.load(self.directory / 'target.npy')
        matrix[0] = matrix[1]
        np.save(self.directory / 'target.npy', matrix, allow_pickle=False)
        report = trainer.read_json(self.feature_path)
        report['targetFeatures']['sha256'] = trainer.digest(self.directory / 'target.npy')
        save(self.feature_path, report)
        with self.assertRaisesRegex(ValueError, 'assembled vectors'):
            self.bundle()

    def test_all_families_have_right_input_columns_and_isolated_target_rows(self):
        self.bind()
        for family in trainer.FAMILIES:
            with self.environment():
                data = trainer.setup(self.args(family))
            width = 1037 if family.endswith('-scalars') else 1024
            self.assertEqual(data['values'].shape, (20, width))
            np.testing.assert_array_equal(data['values'][:, :1024], self.target if family.startswith('target') else self.global_values)
            if width == 1037:
                np.testing.assert_array_equal(data['values'][:, 1024:], data['scalars'])
            x, phones, mask, _ = trainer.batch(data, data['fit'][:2], 'cpu')
            model = trainer.make_model(self.args(family), width).eval()
            first = model(x, mask, phones, mask)[0].detach().clone()
            x[1] += 1000
            torch.testing.assert_close(model(x, mask, phones, mask)[0], first, rtol=0, atol=0)

    def test_child_normalization_and_priors_use_only_child_fit_target_rows(self):
        self.bind()
        with self.environment():
            data = trainer.setup(self.args(regime='child-only'))
        self.assertTrue(all(6 <= self.cohort['rows'][i]['age'] <= 12 for i in data['fit']))
        expected = self.target[data['fit']].astype(np.float64)
        np.testing.assert_array_equal(data['mean'], expected.mean(0).astype(np.float32))
        self.assertEqual(data['std'][3].item(), 1.)
        original_load = trainer.load_bound

        def extreme_nonfit(path, recipe):
            bundle = original_load(path, recipe)
            bundle['cohort'] = deepcopy(bundle['cohort'])
            bundle['arrays'] = {name: np.array(values) for name, values in bundle['arrays'].items()}
            for index in set(range(20)) - set(data['fit']):
                bundle['arrays']['target'][index] = 1e9
                bundle['cohort']['rows'][index]['raterCounts'] = [0, 5, 0]
            return bundle

        with self.environment(), patch.object(trainer, 'load_bound', side_effect=extreme_nonfit):
            again = trainer.setup(self.args(regime='child-only'))
        torch.testing.assert_close(data['mean'], again['mean'], rtol=0, atol=0)
        torch.testing.assert_close(data['std'], again['std'], rtol=0, atol=0)
        self.assertEqual(data['priors'], again['priors'])

    def test_epoch_rule_is_regime_specific_and_ignores_adult_improvements(self):
        self.head_recipe.update(maximumEpochs=6, patienceEpochs=2)
        save(self.head_recipe_path, self.head_recipe)
        self.bind()
        values = iter([(.6, .4), (.4, .3), (.5, .2), (.55, .1), (.4, .3)])

        def evaluate(model, data, indices, *unused):
            child, all_age = next(values)
            return {'ages6to12': {'macroTargetLogLoss': child}, 'allAges': {'macroTargetLogLoss': all_age}}, {
                'rowIndices': indices, 'probabilities': [[.1, .2, .7]] * len(indices)}

        with self.environment(), patch.object(trainer, 'evaluate', side_effect=evaluate):
            report = trainer.train(self.args(regime='child-only', epochs=6))
        self.assertEqual((report['bestEpoch'], report['epochsRun']), (2, 4))
        self.assertEqual(report['bestSelectionMacroLogLoss'], .4)
        self.assertEqual(trainer.selection_loss({'allAges': {'macroTargetLogLoss': .1},
                         'ages6to12': {'macroTargetLogLoss': .9}}, 'all-age'), .1)

    def test_all_eight_family_regime_checkpoints_replay_exactly(self):
        self.bind()
        for family in trainer.FAMILIES:
            for regime in ('all-age', 'child-only'):
                args = self.args(family, regime)
                with self.environment():
                    report = trainer.train(args)
                    replay = trainer.replay(args.output)
                self.assertTrue(replay['exact'])
                self.assertEqual(replay['evaluation'], report['evaluation'])
                config = trainer.read_json(args.output / 'config.json')
                self.assertFalse(set(config['fitRows'] + config['validationRows']) & set(self.splits['folds'][0]['outerHoldoutRows']))
                self.assertFalse(config['classWeighting'])
                self.assertTrue((args.output / 'last.pt').is_file())
        checkpoint = args.output / 'best.pt'
        checkpoint.write_bytes(checkpoint.read_bytes() + b'changed')
        with self.environment(), self.assertRaisesRegex(ValueError, 'Replay artifacts'):
            trainer.replay(args.output)

    def test_binding_recipe_and_source_changes_refuse_fit(self):
        self.bind()
        binding = trainer.read_json(self.binding_path)
        binding['recipeSha256'] = 'wrong'
        save(self.binding_path, binding)
        with self.environment(), self.assertRaisesRegex(ValueError, 'binding recipe/source/scope'):
            trainer.setup(self.args())
        binding['recipeSha256'] = trainer.digest(self.head_recipe_path)
        save(self.binding_path, binding)
        (self.root / 'multiphone_models.py').write_text('changed')
        with self.environment(), self.assertRaisesRegex(ValueError, 'binding recipe/source/scope'):
            trainer.setup(self.args())


if __name__ == '__main__':
    unittest.main()
