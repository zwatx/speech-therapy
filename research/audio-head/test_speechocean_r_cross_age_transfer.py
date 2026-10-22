"""Focused leakage and provenance checks for the train-only age transfer run."""

import copy
import unittest

import numpy as np

from speechocean_r_cross_age_transfer import evaluate_transfer, group_indices, load_recipe


class CrossAgeTransferTests(unittest.TestCase):
    def test_recipe_has_fixed_alpha_and_author_train_only(self):
        recipe, source = load_recipe()
        self.assertEqual(recipe["fixedSoftmaxL2"], 0.1)
        self.assertEqual(source["fixedSoftmaxL2"],
                         {"wav2vec2-base": 0.1, "wavlm-base-plus": 0.1})
        self.assertEqual(recipe["directions"], [["adult", "child"], ["child", "adult"]])
        self.assertEqual(recipe["authorPartition"], "train")
        self.assertFalse(recipe["authorTestInferencePerformed"])
        self.assertFalse(recipe["selectionSearchPerformed"])

    def test_group_pin_rejects_changed_identity(self):
        recipe, _ = load_recipe()
        # Cohort counts alone cannot catch a substituted recording.
        rows = ([{"id": f"c{i}", "speaker": f"c{i}"} for i in range(57)] +
                [{"id": f"a{i}", "speaker": f"a{i}"} for i in range(67)])
        rows += [{"id": f"cx{i}", "speaker": "c0"} for i in range(349 - 57)]
        rows += [{"id": f"ax{i}", "speaker": "a0"} for i in range(417 - 67)]
        ages = {row["speaker"]: (12 if row["speaker"].startswith("c") else 25)
                for row in rows}
        with self.assertRaisesRegex(ValueError, "cohort differs from pin"):
            group_indices(rows, ages, recipe["groups"])

    def test_holdout_labels_do_not_enter_train_prior_or_fit(self):
        recipe, _ = load_recipe()
        recipe = copy.deepcopy(recipe)
        recipe["maxOptimizerIterations"] = 80
        x = np.asarray([[-2.0], [-1.0], [0.0], [1.0], [2.0], [3.0]])
        counts = np.asarray([[5, 0, 0], [4, 1, 0], [3, 1, 1],
                             [0, 0, 5], [0, 1, 4], [1, 1, 3]])
        source, heldout = np.asarray([0, 1, 2]), np.asarray([3, 4, 5])
        first = evaluate_transfer(x, counts, source, heldout, recipe)
        changed = counts.copy()
        changed[heldout] = np.asarray([[5, 0, 0]] * len(heldout))
        second = evaluate_transfer(x, changed, source, heldout, recipe)
        self.assertEqual(first["sourceTrainPrior"], second["sourceTrainPrior"])
        self.assertEqual(first["fitDiagnostics"], second["fitDiagnostics"])
        self.assertNotEqual(first["head"], second["head"])
        self.assertEqual(sum(first["sourceTrainPrior"]), 1.0)

    def test_overlapping_or_repeated_rows_fail(self):
        recipe, _ = load_recipe()
        x = np.asarray([[0.0], [1.0], [2.0]])
        counts = np.asarray([[5, 0, 0], [0, 5, 0], [0, 0, 5]])
        for source, heldout in [(np.asarray([0, 1]), np.asarray([1, 2])),
                                (np.asarray([0, 0]), np.asarray([2])),
                                (np.asarray([0, 1]), np.asarray([3]))]:
            with self.subTest(source=source, heldout=heldout), self.assertRaisesRegex(
                    ValueError, "Invalid or overlapping"):
                evaluate_transfer(x, counts, source, heldout, recipe)


if __name__ == "__main__":
    unittest.main()
