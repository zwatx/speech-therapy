from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data import make_fixtures
from encoders import SpectralEncoder
from measure_runtime import measure, summary
from pipeline import train


class RuntimeMeasurementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest = make_fixtures(self.root / "data")
        self.checkpoint = self.root / "run"
        train(self.manifest, self.checkpoint, "spectral-engineering-v1", self.root / "cache", steps=2)

    def test_nearest_rank_percentile_and_median_use_all_observations(self):
        self.assertEqual(summary(list(range(20, 0, -1))), {
            "count": 20, "median": 10.5, "p95NearestRank": 19, "minimum": 1, "maximum": 20,
        })

    def test_reuse_measures_every_holdout_and_checks_repeat_outputs(self):
        with patch("measure_runtime.load_encoder", return_value=SpectralEncoder()) as loader:
            report = measure(self.checkpoint, self.manifest, self.root / "cache", repeats=2)
        loader.assert_called_once_with("spectral-engineering-v1", self.root / "cache", allow_download=False)
        self.assertEqual(len(report["measurements"]), 24)
        self.assertEqual(len({row["id"] for row in report["measurements"]}), 12)
        self.assertEqual({row["pass"] for row in report["measurements"]}, {1, 2})
        self.assertFalse(report["productionEligible"])
        self.assertFalse(report["learnerFeedbackEligible"])
        self.assertGreater(report["peakProcessResidentBytes"], 0)
        for row in report["measurements"]:
            self.assertGreater(row["frameCount"], 0)
            self.assertAlmostEqual(row["realTimeFactor"], row["inferenceMilliseconds"] / row["durationMilliseconds"])

    def test_changed_repeated_predictions_abort_the_report(self):
        class ChangingEncoder(SpectralEncoder):
            calls = 0

            def __call__(self, samples):
                self.calls += 1
                return super().__call__(samples) + self.calls * 0.1

        with patch("measure_runtime.load_encoder", return_value=ChangingEncoder()):
            with self.assertRaisesRegex(ValueError, "Repeated inference changed"):
                measure(self.checkpoint, self.manifest, self.root / "cache")

    def test_invalid_bounds_and_corrupt_checkpoint_fail_before_encoder_load(self):
        with patch("measure_runtime.load_encoder") as loader:
            for invalid in [0, 6, True, 1.5]:
                with self.subTest(repeats=invalid), self.assertRaises(ValueError):
                    measure(self.checkpoint, self.manifest, self.root / "cache", repeats=invalid)
            weights = self.checkpoint / "head.pt"
            weights.write_bytes(weights.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                measure(self.checkpoint, self.manifest, self.root / "cache")
            loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
