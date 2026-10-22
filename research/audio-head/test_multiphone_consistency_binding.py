"""Small on-disk producer artifacts exercise the consistency consumer boundary.

Only the full-corpus producer-plan reconstruction is mocked. Matrix loading,
checksums, per-clip NPZ validation, parity and canonical-row checks stay real.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import multiphone_consistency_train as trainer


class ConsistencyBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / 'features'
        self.output.mkdir()
        self.path = self.output / 'features.json'
        self.producer = trainer.noise_source
        self.protocol = self.root / 'protocol.md'
        self.protocol.write_text('Fixed synthetic 20 dB protocol.\n')
        (self.root / 'lexical').mkdir()
        self.producer_recipe = self.root / 'producer-recipe.json'
        self.write(self.producer_recipe, {'condition': 'noise20db'})
        self.binding = self.root / 'clean-binding.json'
        self.write(self.binding, {'synthetic': 'clean-study'})
        self.recipe = self.root / 'trainer-recipe.json'
        self.write(self.recipe, {'cleanFeatureBindingSha256': trainer.digest(self.binding),
            'protocolPath': str(self.protocol), 'protocolSha256': trainer.digest(self.protocol)})
        self.enterContext(patch.object(trainer, 'RECIPE', self.recipe))
        self.enterContext(patch.object(self.producer, 'RECIPE', self.producer_recipe))

        # Deliberately interleave clip order and global, noncontiguous row IDs.
        records = [self.row(5, 'fit', 'P', 1, 0), self.row(1, 'fit', 'B', 0, 1),
                   self.row(3, 'validation', 'M', 2, 0)]
        cohort_rows = [{} for _ in range(6)]
        for row in records:
            cohort_rows[row['rowIndex']] = {**row, 'id': row['rowId']}
        self.bound = {'cohort': {'rows': cohort_rows},
            'splits': {'folds': [{'innerFitRows': [5, 1], 'innerValidationRows': [3]}]},
            'bindings': {'clean': self.pin(self.binding)}}
        self.plan = {'rowIndices': [1, 3, 5], 'clips': [
            {'id': name, 'audioSha256': 'original-' + name,
             'targets': [row for row in records if row['clipId'] == name]}
            for name in ('fit', 'validation')], 'parityClips': [{'clipId': 'fit'}]}
        self.plan_path = self.root / 'producer-plan.json'
        self.write(self.plan_path, self.plan)
        self.plan_sha = trainer.digest(self.plan_path)
        self.inputs = {'recipe': self.pin(self.producer_recipe),
            'cleanFeatureBinding': self.pin(self.binding), 'plan': self.pin(self.plan_path),
            'protocol': self.pin(self.root / 'lexical/../protocol.md')}
        self.plan_validator = self.enterContext(patch.object(self.producer, 'validate_plan',
            return_value=(deepcopy(self.bound), {}, deepcopy(self.inputs))))

        entries, audio, ctc = {}, {}, {'entries': {}}
        for clip in self.plan['clips']:
            name = clip['id']
            audio[name] = {'id': name, 'audioPath': '/synthetic/' + name,
                           'audioSha256': 'noisy-' + name, 'sampleCount': 1600}
            ctc['entries'][name] = {'frames': 4, 'sha256': 'ctc-' + name}
            rows = [{**row, 'intervalFrames': [1, 2], 'estimatedPoolingWindowFrames': [0, 4]}
                    for row in clip['targets']]
            target = np.asarray([np.arange(1024) / 1024 + row['rowIndex'] for row in rows], dtype=np.float32)
            scalars = np.asarray([np.arange(13) / 16 - row['rowIndex'] for row in rows], dtype=np.float32)
            entries[name] = self.producer.save_unit(self.output / 'clips' / name, clip, audio[name],
                {'requestedSNRdB': 20}, rows, target, scalars, ctc['entries'][name], self.plan_sha)
        rows, descriptors, derived = self.producer.assemble(self.plan, self.plan_sha, entries, audio, ctc, self.output)
        index = {'complete': True, 'planSha256': self.plan_sha, 'rowIndices': [1, 3, 5],
            'entries': entries, 'noisyAudio': audio, 'clipCount': 2}
        self.write(self.output / 'index.json', index)
        self.write(self.output / 'ctc-index.json', ctc)
        parity = {'complete': True, 'planSha256': self.plan_sha, 'clips': [{
            'clipId': 'fit', 'windowsExact': True,
            'maximumAbsoluteDifferences': {'ctcLogPosterior': 0., 'scalar': 0., 'phoneticPooled': 1e-6}}],
            'tolerances': {'ctcLogPosterior': 0., 'scalar': 0., 'phoneticPooled': 2e-6}}
        self.write(self.output / 'parity.json', parity)
        derived.update({'index': self.pin(self.output / 'index.json'),
                        'parity': self.pin(self.output / 'parity.json'),
                        'ctcIndex/noise20db': self.pin(self.output / 'ctc-index.json')})
        self.report = {'complete': True, 'authorPartition': 'train', 'fold': 0,
            'partition': 'innerFitRows+innerValidationRows', 'rowIndices': [1, 3, 5],
            'completeCoverage': True, 'failedRows': [], 'unmappableRows': [],
            'condition': 'noise20db', 'snrDb': 20,
            'cleanFeatureBindingSha256': trainer.digest(self.binding),
            'featureSourceBindingSha256': trainer.digest(self.binding),
            'scalarFeatureNames': trainer.baseline.SCALAR_NAMES,
            **{key: False for key in ('trainingPerformed', 'outerInferencePerformed',
                'authorTestInferencePerformed', 'labelsTransferred', 'learnerFeedbackEligible', 'clinicalUseEligible')},
            'inputFiles': self.inputs, 'derivedFiles': derived,
            'recipeSha256': trainer.digest(self.producer_recipe), 'planPath': str(self.plan_path),
            'planSha256': self.plan_sha, 'indexPath': 'index.json',
            'indexSha256': derived['index']['sha256'], 'parityPath': 'parity.json',
            'paritySha256': derived['parity']['sha256'], 'expectedClips': 2, 'expectedRows': 3,
            'originalParityComplete': True, 'originalParity': parity['clips'],
            'targetFeatures': descriptors['target'], 'scalarFeatures': descriptors['scalars'], 'rows': rows}

    @staticmethod
    def row(index, clip, phone, target, position):
        return {'rowIndex': index, 'rowId': f'{clip}-{phone}', 'clipId': clip,
                'targetId': target, 'targetPhone': phone, 'canonicalIndex': position,
                'wordIndex': 0, 'phoneIndex': position}

    @staticmethod
    def write(path, value):
        trainer.atomic_json(path, value)

    @staticmethod
    def pin(path):
        return {'path': str(path.absolute()), 'sha256': trainer.digest(path)}

    def consume(self, report=None):
        self.write(self.path, self.report if report is None else report)
        # Every adversarial report is freshly caller-pinned, not a stale-hash test.
        return trainer.feature_matrix(self.path, trainer.digest(self.path), self.bound)

    def refresh_derived(self, report, key, path):
        report['derivedFiles'][key] = self.pin(path)
        if key in ('index', 'parity'):
            report[key + 'Sha256'] = trainer.digest(path)

    def test_valid_producer_exact_noncontiguous_row_and_column_order(self):
        values, positions, files = self.consume()
        expected = np.concatenate([np.load(self.output / name, allow_pickle=False)
                                   for name in ('target.npy', 'scalars.npy')], axis=1)
        np.testing.assert_array_equal(values, expected)
        self.assertEqual(values.dtype, np.float32)
        self.assertEqual(values.shape, (3, 1037))
        self.assertEqual(positions, {1: 0, 3: 1, 5: 2})
        np.testing.assert_array_equal(values[:, 0], [1, 3, 5])
        np.testing.assert_array_equal(values[:, 1024], [-1, -3, -5])
        self.assertIn('derived/unit/fit', files)
        self.assertIn('derived/unitMeta/validation', files)
        self.assertEqual(files['protocol']['path'], str(self.root / 'lexical/../protocol.md'))
        trainer.guard_files(files)
        self.plan_validator.assert_called_once_with(self.plan, self.inputs['plan'])

    def test_missing_or_changed_derived_bytes_rejected_with_rehashed_report(self):
        path = Path(self.report['derivedFiles']['unit/fit']['path'])
        original = path.read_bytes()
        path.write_bytes(original + b'changed')
        with self.assertRaisesRegex(ValueError, 'Pinned consistency input changed'):
            self.consume()
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.consume()

    def test_condition_coverage_binding_and_canonical_identity_rejected(self):
        for key, changed in (('condition', 'noise10db'), ('snrDb', 10), ('completeCoverage', False),
                ('failedRows', [1]), ('unmappableRows', [3]), ('rowIndices', [1, 5, 3]),
                ('cleanFeatureBindingSha256', '0' * 64), ('featureSourceBindingSha256', '0' * 64)):
            with self.subTest(key=key):
                report = deepcopy(self.report); report[key] = changed
                with self.assertRaisesRegex(ValueError, 'scope, row coverage'):
                    self.consume(report)
        report = deepcopy(self.report); report['rows'][0]['phoneIndex'] += 1
        with self.assertRaisesRegex(ValueError, 'canonical target identity'):
            self.consume(report)

    def test_rehashed_protocol_and_producer_recipe_substitution_rejected(self):
        alternate = self.root / 'alternate-protocol.md'; alternate.write_text('Another protocol')
        report = deepcopy(self.report); report['inputFiles']['protocol'] = self.pin(alternate)
        with self.assertRaisesRegex(ValueError, 'protocol binding differs'):
            self.consume(report)
        alternate = self.root / 'alternate-recipe.json'; self.write(alternate, {'condition': 'noise20db'})
        report = deepcopy(self.report); report['inputFiles']['recipe'] = self.pin(alternate)
        report['recipeSha256'] = trainer.digest(alternate)
        with self.assertRaisesRegex(ValueError, 'producer recipe'):
            self.consume(report)

    def test_rehashed_parity_proof_cannot_change_tolerances_or_claim_failure_success(self):
        path = self.output / 'parity.json'; original = trainer.read_json(path)
        for defect in ('incomplete', 'window', 'excess-difference', 'negative-difference', 'tolerance', 'missing-clip'):
            with self.subTest(defect=defect):
                parity, report = deepcopy(original), deepcopy(self.report)
                if defect == 'incomplete': parity['complete'] = False
                elif defect == 'window': parity['clips'][0]['windowsExact'] = False
                elif defect == 'excess-difference': parity['clips'][0]['maximumAbsoluteDifferences']['phoneticPooled'] = 3e-6
                elif defect == 'negative-difference': parity['clips'][0]['maximumAbsoluteDifferences']['scalar'] = -1e-9
                elif defect == 'tolerance': parity['tolerances']['phoneticPooled'] = 1e-2
                else: parity['clips'] = []
                self.write(path, parity); self.refresh_derived(report, 'parity', path)
                report['originalParity'] = parity['clips']
                with self.assertRaisesRegex(ValueError, 'Original parity'):
                    self.consume(report)

    def test_rehashed_assembled_values_and_row_swaps_rejected_against_real_npz(self):
        for filename, key in (('target.npy', 'targetFeatures'), ('scalars.npy', 'scalarFeatures')):
            path = self.output / filename; original = np.load(path, allow_pickle=False)
            for change in ('value', 'row-order'):
                with self.subTest(filename=filename, change=change):
                    value = original.copy()
                    if change == 'value': value[0, 0] += .25
                    else: value[[0, 1]] = value[[1, 0]]
                    np.save(path, value, allow_pickle=False)
                    report = deepcopy(self.report); report[key]['sha256'] = trainer.digest(path)
                    self.refresh_derived(report, 'matrix/' + path.stem, path)
                    with self.assertRaisesRegex(ValueError, 'assembled matrix differs'):
                        self.consume(report)
            np.save(path, original, allow_pickle=False)

    def test_rehashed_index_missing_clip_rejected_before_loading_units(self):
        path = self.output / 'index.json'; index = trainer.read_json(path)
        del index['entries']['validation']
        self.write(path, index)
        report = deepcopy(self.report); self.refresh_derived(report, 'index', path)
        with self.assertRaisesRegex(ValueError, 'index scope or coverage'):
            self.consume(report)


if __name__ == '__main__':
    unittest.main()
