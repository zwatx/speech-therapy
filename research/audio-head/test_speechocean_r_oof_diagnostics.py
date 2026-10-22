"""Focused tests for read-only, speaker-clustered rater OOF diagnostics."""

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

import speechocean_r_oof_diagnostics as diagnostics


class AgreementAndMetricTests(unittest.TestCase):
    def test_agreement_groups_and_malformed_counts(self):
        self.assertEqual(diagnostics.agreement_group(np.array([0, 0, 5])), "unanimousTwo")
        self.assertEqual(diagnostics.agreement_group(np.array([5, 0, 0])), "unanimousZero")
        self.assertEqual(diagnostics.agreement_group(np.array([0, 5, 0])), "unanimousOne")
        self.assertEqual(diagnostics.agreement_group(np.array([2, 1, 2])), "mixed")
        for counts in ([2, 2, 2], [-1, 1, 5], [0.0, 0.0, 5.0]):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                diagnostics.agreement_group(np.asarray(counts))

    def test_per_rater_scores_average_all_five_judgments(self):
        probabilities = np.array([[0.2, 0.3, 0.5]])
        counts = np.array([[2, 1, 2]])
        loss, brier = diagnostics.per_clip_scores(probabilities, counts, 1e-12)
        expected_loss = -(2 * math.log(0.2) + math.log(0.3) +
                          2 * math.log(0.5)) / 5
        expected_brier = (2 * (0.8**2 + 0.3**2 + 0.5**2) +
                          (0.2**2 + 0.7**2 + 0.5**2) +
                          2 * (0.2**2 + 0.3**2 + 0.5**2)) / 5
        self.assertAlmostEqual(loss[0], expected_loss)
        self.assertAlmostEqual(brier[0], expected_brier)
        with self.assertRaises(ValueError):
            diagnostics.per_clip_scores(np.array([[0.2, 0.3, 0.6]]), counts, 1e-12)


class BootstrapTests(unittest.TestCase):
    def test_paired_draws_preserve_unbalanced_speaker_clusters(self):
        scores = {"first": np.array([2.0, 2.0, 0.0]),
                  "second": np.array([1.0, 1.0, 1.0]),
                  "same": np.array([2.0, 2.0, 0.0])}
        args = (scores, ["a", "a", "b"], [["first", "second"],
                                               ["same", "first"]], 7, 100, [2.5, 97.5])
        results, draws = diagnostics.speaker_bootstrap(*args)
        repeated, repeated_draws = diagnostics.speaker_bootstrap(*args)
        self.assertEqual(results, repeated)
        np.testing.assert_array_equal(draws, repeated_draws)
        first = results["first minus second"]
        self.assertAlmostEqual(first["pointDifference"], 1 / 3)
        self.assertEqual(set(first["replicateDifferences"]), {-1.0, 1 / 3, 1.0})
        self.assertEqual(set(results["same minus first"]["replicateDifferences"]), {0.0})

    def test_hash_pin_rejects_changed_saved_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            report = base / "report.json"
            oof = base / "oof.json"
            report.write_text(json.dumps({"experiment": "speechocean-r-rater-cv-convergence-v2"}))
            oof.write_text("[]\n")
            recipe = {"inputReport": "report.json",
                      "inputReportSha256": diagnostics.sha256_file(report),
                      "inputOutOfFold": "oof.json",
                      "inputOutOfFoldSha256": diagnostics.sha256_file(oof),
                      "expectedClips": 766}
            oof.write_text("[{}]\n")
            with self.assertRaisesRegex(ValueError, "OOF SHA-256 mismatch"):
                diagnostics.load_predictions(base, recipe)


if __name__ == "__main__":
    unittest.main()
