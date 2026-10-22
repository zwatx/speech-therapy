"""Synthetic and provenance tests for the locked train-only final fit."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from speechocean_r_rater_final_fit import (
    fit_heads, load_recipe, verify_cv_selection,
)
from speechocean_train_cv import sha256_file


class FinalFitTests(unittest.TestCase):
    def test_recipe_reuses_v2_pins_and_fixed_alpha_without_search(self):
        recipe = load_recipe()
        self.assertEqual(recipe["fixedSoftmaxL2"],
                         {"wav2vec2-base": 0.1, "wavlm-base-plus": 0.1})
        self.assertEqual(recipe["authorPartition"], "train")
        self.assertFalse(recipe["selectionSearchPerformed"])
        self.assertFalse(recipe["authorTestInferencePerformed"])
        selection = verify_cv_selection(recipe)
        self.assertEqual(selection["selectedAlphaByFold"],
                         {"wav2vec2-base": [0.1] * 5,
                          "wavlm-base-plus": [0.1] * 5})

    def test_v2_selection_report_hash_fails_closed(self):
        recipe = copy.deepcopy(load_recipe())
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / recipe["selectionEvidence"]["reportPath"]
            path.parent.mkdir(parents=True)
            path.write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                verify_cv_selection(recipe, base)
            recipe["selectionEvidence"]["reportSha256"] = sha256_file(path)
            with self.assertRaisesRegex(ValueError, "fold selections"):
                verify_cv_selection(recipe, base)

    def test_synthetic_fixed_fit_has_simplex_and_bounded_expected_rating(self):
        recipe = copy.deepcopy(load_recipe())
        recipe["maxOptimizerIterations"] = 60
        x = np.asarray([[-2.0], [-1.0], [0.0], [1.0], [2.0], [3.0]])
        matrices = {"wav2vec2-base": x, "wavlm-base-plus": -x}
        counts = np.asarray([[5, 0, 0], [4, 1, 0], [2, 2, 1],
                             [1, 2, 2], [0, 1, 4], [0, 0, 5]])
        heads, diagnostics, bounds = fit_heads(matrices, counts, recipe)
        self.assertEqual(set(heads), set(matrices))
        for kind in matrices:
            self.assertEqual(heads[kind]["alpha"], 0.1)
            self.assertFalse(diagnostics[kind]["atIterationLimit"])
            self.assertLess(bounds[kind]["maximumSimplexDeviation"], 1e-10)
            self.assertEqual(bounds[kind]["expectedRatingsOutsideZeroToTwo"], 0)

    def test_rejects_missing_encoder_or_invalid_five_rater_targets(self):
        recipe = load_recipe()
        x = np.zeros((2, 1))
        matrices = {"wav2vec2-base": x, "wavlm-base-plus": x.copy()}
        counts = np.asarray([[5, 0, 0], [0, 0, 5]])
        with self.assertRaisesRegex(ValueError, "Invalid paired"):
            fit_heads({"wav2vec2-base": x}, counts, recipe)
        with self.assertRaisesRegex(ValueError, "Invalid paired"):
            fit_heads(matrices, np.asarray([[4, 0, 0], [0, 0, 5]]), recipe)
        matrices["wavlm-base-plus"][0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "Invalid paired"):
            fit_heads(matrices, counts, recipe)


if __name__ == "__main__":
    unittest.main()
