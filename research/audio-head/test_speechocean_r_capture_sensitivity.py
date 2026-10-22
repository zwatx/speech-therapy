"""Numerical and boundary tests without loading models or any corpus audio."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

import speechocean_r_capture_sensitivity as sensitivity


class SensitivityTests(unittest.TestCase):
    def test_analytic_probability_movement_and_argmax_tie_rule(self):
        clean = np.asarray([[1., 0., 0.], [0., 1., 0.]])
        changed = np.asarray([[0., 0., 1.], [0.5, 0.5, 0.]])
        result = sensitivity.summarize(clean, changed)
        self.assertEqual(result["clips"], 2)
        self.assertEqual(result["meanTotalVariation"], 0.75)
        self.assertEqual(result["maxTotalVariation"], 1)
        self.assertEqual(result["meanExpectedRatingShift"], 0.75)
        self.assertEqual(result["meanAbsoluteExpectedRatingShift"], 1.25)
        self.assertEqual(result["maxAbsoluteExpectedRatingShift"], 2)
        self.assertEqual(result["argmaxClassChanges"], 2)

    def test_identity_has_zero_movement_and_order_is_paired(self):
        probabilities = np.asarray([[0.1, 0.2, 0.7], [0.6, 0.3, 0.1]])
        result = sensitivity.summarize(probabilities, probabilities.copy())
        self.assertEqual(result["meanTotalVariation"], 0)
        self.assertEqual(result["argmaxClassChanges"], 0)
        self.assertGreater(sensitivity.summarize(probabilities, probabilities[::-1])[
            "meanTotalVariation"], 0)

    def test_invalid_simplexes_or_pairing_fail(self):
        valid = np.asarray([[0.1, 0.2, 0.7]])
        for bad in (np.empty((0, 3)), np.asarray([0.1, 0.2, 0.7]),
                    np.asarray([[0.2, 0.8]]), np.asarray([[0.1, 0.2, 0.6]]),
                    np.asarray([[-0.1, 0.2, 0.9]]), np.asarray([[np.nan, 0., 1.]]),
                    np.asarray([[np.inf, 0., 1.]])):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sensitivity.summarize(valid, bad)
        with self.assertRaisesRegex(ValueError, "shapes differ"):
            sensitivity.summarize(valid, np.vstack([valid, valid]))

    def test_strata_keep_correct_denominators_and_missing_stratum_fails(self):
        rows = [{"stratum": value} for value in sensitivity.sample.STRATA for _ in range(2)]
        clean = np.tile([0.1, 0.2, 0.7], (8, 1))
        changed = clean.copy()
        changed[0] = [0.7, 0.2, 0.1]
        result = sensitivity.group_summaries(clean, changed, rows)
        self.assertEqual(result["all"]["clips"], 8)
        self.assertEqual(result["all"]["argmaxClassChanges"], 1)
        self.assertEqual(result["child.ceiling"]["clips"], 2)
        self.assertEqual(result["child.ceiling"]["argmaxClassChanges"], 1)
        self.assertEqual(result["adult.ceiling"]["argmaxClassChanges"], 0)
        with self.assertRaisesRegex(ValueError, "four predeclared"):
            sensitivity.group_summaries(clean[:2], changed[:2], rows[:2])

    def test_recipe_changes_and_output_overwrite_fail_before_model_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "recipe.json"
            value = {**sensitivity.EXPECTED_RECIPE, "authorPartition": "test"}
            recipe.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "locked settings"):
                sensitivity.load_recipe(recipe)
        with patch.object(sensitivity.Path, "exists", return_value=True), \
                patch.object(sensitivity, "load_recipe") as load:
            with self.assertRaisesRegex(ValueError, "already exists"):
                sensitivity.run()
            load.assert_not_called()

    def test_bad_features_fail_before_head_prediction(self):
        for features in (torch.empty((0, 768)), torch.ones((3, 2)),
                         torch.full((3, 768), float("nan"))):
            with self.subTest(shape=features.shape), self.assertRaisesRegex(ValueError, "frames"):
                sensitivity.pooled_probabilities(lambda waveform: features, {}, torch.zeros(1600))

    def test_report_paths_cannot_escape_ignored_outputs(self):
        for output in (Path("/tmp/cadence-capture-report.json"),
                       sensitivity.HERE / "outputs/../../capture-report.json"):
            with self.subTest(output=output), \
                    patch.object(sensitivity, "load_recipe") as load:
                with self.assertRaisesRegex(ValueError, "ignored research outputs"):
                    sensitivity.run(output)
                load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
