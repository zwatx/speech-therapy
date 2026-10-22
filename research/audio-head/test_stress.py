from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import torch

from data import digest, make_fixtures, read_json, write_json
from encoders import SpectralEncoder
from pipeline import train
from stress import RECIPE, check_original_metrics, run_stress, transform


class TransformTests(unittest.TestCase):
    def setUp(self):
        self.samples = (0.4 * torch.sin(torch.arange(16000) * 0.04)).float()
        self.sha = digest(b"recording identity")

    def test_original_is_exact_and_gain_is_minus_six_db(self):
        original, clean = transform(self.samples, "original", self.sha)
        self.assertTrue(torch.equal(original, self.samples))
        gained, result = transform(self.samples, "gain-minus-6db", self.sha)
        self.assertTrue(torch.equal(gained, self.samples * 10 ** (-6 / 20)))
        self.assertEqual(len(gained), len(self.samples))
        self.assertIsNone(clean["achievedSnrDb"])
        self.assertIsNone(result["achievedSnrDb"])
        self.assertLess(float(gained.abs().max()), 1)

    def test_noise_is_deterministic_identity_specific_and_measured(self):
        for level in (20, 10):
            name = f"white-noise-{level}db"
            first, evidence = transform(self.samples, name, self.sha)
            second, repeated = transform(self.samples, name, self.sha)
            other, _ = transform(self.samples, name, digest(b"another recording"))
            self.assertTrue(torch.equal(first, second))
            self.assertEqual(evidence, repeated)
            self.assertFalse(torch.equal(first, other))
            self.assertAlmostEqual(evidence["achievedSnrDb"], level, places=5)
            self.assertEqual(len(first), len(self.samples))
            self.assertTrue(torch.isfinite(first).all())
        # Local generators must not perturb a caller's global training RNG.
        state = torch.get_rng_state()
        transform(self.samples, "white-noise-10db", self.sha)
        self.assertTrue(torch.equal(state, torch.get_rng_state()))

    def test_shared_scaling_preserves_snr_without_hard_clipping(self):
        loud = torch.full((16000,), 0.98)
        mixed, evidence = transform(loud, "white-noise-10db", self.sha)
        self.assertLess(evidence["mixtureScale"], 1)
        self.assertAlmostEqual(evidence["achievedSnrDb"], 10, places=5)
        self.assertLessEqual(float(mixed.abs().max()), 0.990001)
        self.assertEqual(int((mixed.abs() >= 0.99).sum()), 1)

    def test_bad_inputs_and_undeclared_conditions_fail(self):
        for samples in (torch.zeros(20), torch.ones(20), torch.tensor([float("nan")]),
                        self.samples.double(), self.samples.reshape(1, -1), torch.tensor([])):
            with self.subTest(samples=samples.shape), self.assertRaises(ValueError):
                transform(samples, "original", self.sha)
        with self.assertRaisesRegex(ValueError, "predeclared"):
            transform(self.samples, "pitch-shift", self.sha)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            transform(self.samples, "original", "bad")


class StressReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = make_fixtures(self.root / "data")
        self.directories = [self.root / "first", self.root / "second"]
        for seed, directory in enumerate(self.directories):
            train(self.manifest, directory, "spectral-engineering-v1", self.root / "cache", steps=2, seed=seed)
        self.recipe = self.root / "recipe.json"
        write_json(self.recipe, RECIPE)
        self.runs = [(directory, self.manifest) for directory in self.directories]
        self.output = self.root / "stress.json"

    def run_report(self):
        return run_stress(self.runs, self.output, self.root / "cache", self.recipe)

    def test_shared_features_original_equivalence_order_and_release_flags(self):
        encoder = SpectralEncoder()
        with patch("stress.load_encoder", return_value=encoder) as loader, patch.object(
                SpectralEncoder, "__call__", autospec=True, side_effect=SpectralEncoder.__call__) as encode:
            report = self.run_report()
        loader.assert_called_once_with("spectral-engineering-v1", self.root / "cache", allow_download=False)
        self.assertEqual(encode.call_count, 12 * 4)
        self.assertEqual(report["measurements"]["encodedClips"], 48)
        self.assertEqual([x["name"] for x in report["conditions"]], RECIPE["conditions"])
        for key in ("calibrated", "selectionPerformed", "productionEligible", "learnerFeedbackEligible"):
            self.assertIs(report[key], False)
        for condition in report["conditions"]:
            self.assertEqual([r["name"] for r in condition["runs"]], ["first", "second"])
            self.assertEqual(len(condition["waveforms"]), 12)
            self.assertEqual({x["split"] for x in condition["waveforms"]}, {"calibration", "test"})
        for directory, run in zip(self.directories, report["conditions"][0]["runs"]):
            saved = read_json(directory / "report.json")
            for split in ("calibration", "test"):
                self.assertEqual(run["splits"][split], saved["splits"][split])
        with self.assertRaisesRegex(ValueError, "Output exists"):
            self.run_report()

    def test_checkpoint_corruption_fails_before_encoder_load(self):
        path = self.directories[-1] / "head.pt"
        path.write_bytes(path.read_bytes()[:-1])
        with patch("stress.load_encoder") as loader:
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                self.run_report()
            loader.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_changed_holdout_membership_fails_before_encoder_load(self):
        changed = read_json(self.manifest)
        changed["items"] = [row for row in changed["items"] if row["id"] != "test-00"]
        path = self.manifest.parent / "changed.json"
        write_json(path, changed)
        third = self.root / "third"
        train(path, third, "spectral-engineering-v1", self.root / "cache", steps=2)
        self.runs[-1] = (third, path)
        with patch("stress.load_encoder") as loader:
            with self.assertRaisesRegex(ValueError, "identical test"):
                self.run_report()
            loader.assert_not_called()

    def test_modified_recipe_and_clean_recomputation_fail(self):
        changed = {**RECIPE, "noiseSeed": 18}
        write_json(self.recipe, changed)
        with patch("stress.load_encoder") as loader:
            with self.assertRaisesRegex(ValueError, "predeclared"):
                self.run_report()
            loader.assert_not_called()
        saved = read_json(self.directories[0] / "report.json")["splits"]["test"]
        for field in ("tokenEdits", "ctcLoss"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "differs"):
                check_original_metrics({**saved, field: saved[field] + 1}, saved)


if __name__ == "__main__":
    unittest.main()
