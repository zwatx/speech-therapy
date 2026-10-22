import copy
import unittest

import numpy as np

from speechocean_r_word_age_negative_control import (
    categorical_probabilities, choose_smoothing, evaluate,
)
from speechocean_train_cv import outer_speaker_folds


class CategoricalControlTests(unittest.TestCase):
    def test_word_age_cell_and_unseen_backoff_use_fit_counts_only(self):
        fit_rows = [
            {"targetWord": "RED", "ageBand": "child"},
            {"targetWord": "RED", "ageBand": "adult"},
            {"targetWord": "CAR", "ageBand": "adult"},
        ]
        counts = np.asarray([[5, 0, 0], [0, 0, 5], [0, 0, 5]])
        query = [{"targetWord": "RED", "ageBand": "child"},
                 {"targetWord": "CAR", "ageBand": "child"},
                 {"targetWord": "NEW", "ageBand": "child"}]
        result = categorical_probabilities(fit_rows, counts, query, 5, 5, 5)
        self.assertTrue(np.allclose(result.sum(axis=1), 1))
        self.assertTrue(np.all(result > 0))
        self.assertGreater(result[0, 0], result[1, 0])
        self.assertGreater(result[1, 2], result[2, 2])
        changed = np.vstack([counts, [0, 0, 5]])
        with self.assertRaisesRegex(ValueError, "Invalid categorical"):
            categorical_probabilities(fit_rows, changed, query, 5, 5, 5)

    def test_inner_selection_ignores_rows_outside_inner_fit_and_validation(self):
        rows = [{"targetWord": "RED" if i % 2 else "CAR",
                 "ageBand": "child" if i < 4 else "adult"} for i in range(8)]
        counts = np.asarray([[5, 0, 0], [0, 0, 5], [4, 1, 0], [0, 1, 4],
                             [5, 0, 0], [0, 0, 5], [5, 0, 0], [0, 0, 5]])
        recipe = {"wordSmoothingCandidates": [1, 5],
                  "ageSmoothingCandidates": [1, 5],
                  "cellSmoothingCandidates": [5, 20],
                  "globalPriorPseudocountPerClass": 1,
                  "logLossEpsilon": 1e-12}
        original = choose_smoothing(rows, counts, np.asarray([0, 1, 2, 3]),
                                    np.asarray([4, 5]), recipe)
        altered = counts.copy()
        altered[6:] = [[0, 5, 0], [0, 5, 0]]
        self.assertEqual(original, choose_smoothing(rows, altered,
                                                    np.asarray([0, 1, 2, 3]),
                                                    np.asarray([4, 5]), recipe))

    def test_outer_holdout_scores_do_not_affect_own_fold_predictions(self):
        rows, counts = [], []
        for speaker in range(10):
            for clip in range(2):
                rows.append({"id": f"{speaker}-{clip}", "speaker": f"{speaker:04d}",
                             "targetWord": "RED" if clip else "CAR",
                             "ageBand": "child" if speaker < 5 else "adult"})
                counts.append([5, 0, 0] if speaker % 2 else [0, 0, 5])
        counts = np.asarray(counts)
        folds = outer_speaker_folds({row["speaker"] for row in rows}, 5, 20260923)
        reference_oof = [{"outerFold": folds[row["speaker"]]} for row in rows]
        recipe = {"expectedTrainClips": len(rows), "outerFolds": 5, "outerSeed": 20260923,
                  "innerFractionOfOuterTrainSpeakers": 0.25,
                  "wordSmoothingCandidates": [1, 5],
                  "ageSmoothingCandidates": [1, 5],
                  "cellSmoothingCandidates": [5, 20],
                  "globalPriorPseudocountPerClass": 1,
                  "logLossEpsilon": 1e-12}
        summary, original = evaluate(rows, counts, reference_oof, recipe)
        changed = counts.copy()
        held_out = [i for i, row in enumerate(rows) if folds[row["speaker"]] == 0]
        changed[held_out] = [0, 5, 0]
        _, repeated = evaluate(rows, changed, reference_oof, copy.deepcopy(recipe))
        self.assertEqual(len(summary["folds"]), 5)
        self.assertTrue(all(not (set(fold["holdoutSpeakerIds"]) &
                                 set(fold["outerTrainSpeakerIds"])) for fold in summary["folds"]))
        for i in held_out:
            self.assertEqual(original[i]["probabilities"], repeated[i]["probabilities"])


if __name__ == "__main__":
    unittest.main()
