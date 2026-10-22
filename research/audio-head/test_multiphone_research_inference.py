"""Inference on copied synthetic exports with their training workspace removed."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np
import torch

import multiphone_research_inference as inference
import multiphone_phonetic_final as final
import test_multiphone_phonetic_final as fixtures


class PortableResearchInferenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def bundle(self, variant='weighted-child-only'):
        fixture = fixtures.FinalPhoneticTests()
        fixture.setUp()
        try:
            args = fixture.args(variant)
            final.fit(args)
            objective, regime = variant.split('-', 1)
            data = final.full_fit_data(fixture.bound, regime, objective)
            features, ids = final.features_for_fit(data)
            expected = np.asarray(final.read_json(args.output / 'verification.json')['probabilities'])
            # The synthetic full-fit fixture replaces source pins; restore the
            # real frozen model implementation pin for this inference contract.
            config = final.read_json(args.output / 'config.json')
            config['sourceSha256']['multiphone_models.py'] = inference.sha(Path(inference.models.__file__).read_bytes())
            final.atomic_json(args.output / 'config.json', config)
            saved = torch.load(args.output / 'checkpoint.pt', map_location='cpu', weights_only=True)
            saved['configSha256'] = final.digest(args.output / 'config.json')
            torch.save(saved, args.output / 'checkpoint.pt')
            output = self.root / variant
            shutil.copytree(args.output, output)
            self.repin(output)
        finally:
            fixture.doCleanups()  # Deletes original plan, data and every training path.
        self.assertFalse(Path(config['planPath']).exists())
        return output, features.copy(), ids.copy(), expected

    def repin(self, directory):
        path = directory / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['filesSha256'] = {name: inference.sha((directory / name).read_bytes()) for name in inference.FILES}
        path.write_text(json.dumps(manifest, sort_keys=True) + '\n')
        return inference.sha(path.read_bytes())

    def load(self, directory):
        return inference.load_head(directory, inference.sha((directory / 'manifest.json').read_bytes()))

    def test_all_four_copied_exports_reproduce_full_fit_without_training_archive(self):
        for variant in final.VARIANTS:
            with self.subTest(variant=variant):
                output, features, ids, expected = self.bundle(variant)
                predictor = self.load(output)
                np.testing.assert_array_equal(predictor.predict(features, ids), expected)
                self.assertEqual(predictor.variant, variant)
                self.assertEqual(len(predictor.feature_columns), 1037)
                self.assertNotIn('ZH', predictor.supported_phones)

    def test_invalid_features_and_untrained_targets_fail(self):
        output, features, ids, _ = self.bundle()
        predictor = self.load(output)
        for values, targets in [(features.astype(np.float64), ids), (features[:, :-1], ids),
            (features * np.nan, ids), (features[:0], ids[:0]), (features, ids.astype(float)),
            (features, np.full_like(ids, 23)), (features, np.full_like(ids, -1)),
            (features, np.full_like(ids, 2)), (features, ids[:-1])]:
            with self.subTest(shape=values.shape, ids=targets[:2]), self.assertRaises(ValueError):
                predictor.predict(values, targets)

    def test_file_corruption_and_unknown_manifest_are_rejected(self):
        output, *_ = self.bundle()
        with self.assertRaisesRegex(ValueError, 'manifest differs'):
            inference.load_head(output, '0' * 64)
        (output / 'checkpoint.pt').write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'bundle file changed'):
            self.load(output)

    def test_rehashed_unsupported_target_metadata_is_rejected(self):
        output, *_ = self.bundle()
        config = json.loads((output / 'config.json').read_text())
        manifest = json.loads((output / 'manifest.json').read_text())
        config['targets'][23]['supported'] = True
        manifest['targets'] = config['targets']
        (output / 'config.json').write_text(json.dumps(config))
        (output / 'manifest.json').write_text(json.dumps(manifest))
        self.repin(output)
        with self.assertRaisesRegex(ValueError, 'Supported targets differ'):
            self.load(output)

    def test_rehashed_zero_scale_is_rejected_before_prediction(self):
        output, *_ = self.bundle()
        saved = torch.load(output / 'checkpoint.pt', map_location='cpu', weights_only=True)
        saved['std'][0] = 0
        torch.save(saved, output / 'checkpoint.pt')
        norm = json.loads((output / 'normalization.json').read_text())
        norm['std'][0] = 0
        (output / 'normalization.json').write_text(json.dumps(norm))
        self.repin(output)
        with self.assertRaisesRegex(ValueError, 'Normalization provenance differs'):
            self.load(output)

    def test_manifest_cannot_add_paths_outside_bundle(self):
        output, *_ = self.bundle()
        path = output / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['filesSha256']['../unrelated-file'] = '0' * 64
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'export contract'):
            self.load(output)


if __name__ == '__main__':
    unittest.main()
