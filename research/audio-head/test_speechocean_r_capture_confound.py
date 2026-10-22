"""Focused cohort and speaker-leakage checks for the capture confound probe."""
import unittest

import numpy as np

from speechocean_r_capture_confound import METHODS, design_matrix, evaluate
from speechocean_train_cv import inner_validation_speakers, outer_speaker_folds


class CaptureControlTests(unittest.TestCase):
    def test_design_uses_fit_words_and_keeps_capture_columns_separate(self):
        rows = [{"targetWord": "RED", "ageBand": "child"},
                {"targetWord": "CAR", "ageBand": "adult"},
                {"targetWord": "NEW", "ageBand": "child"}]
        capture = np.asarray([[1.0, .01], [2.0, .02], [3.0, .03]])
        fit = np.asarray([0, 1])
        holdout = np.asarray([2])
        base_fit, base_holdout, words = design_matrix(rows, capture, fit, holdout, False)
        full_fit, full_holdout, full_words = design_matrix(rows, capture, fit, holdout, True)
        self.assertEqual(words, ["CAR", "RED"])
        self.assertEqual(words, full_words)
        self.assertEqual(base_fit.shape, (2, 3))
        self.assertTrue(np.array_equal(base_holdout, [[0, 0, 0]]))
        self.assertTrue(np.array_equal(full_fit[:, :3], base_fit))
        self.assertTrue(np.array_equal(full_holdout[0, -2:], capture[2]))

    def test_outer_holdout_ratings_cannot_change_own_predictions(self):
        rows, counts, capture = [], [], []
        for speaker in range(10):
            for clip in range(2):
                rows.append({"id": f"{speaker}-{clip}", "speaker": f"{speaker:04d}",
                             "targetWord": "RED" if clip else "CAR",
                             "ageBand": "child" if speaker < 5 else "adult"})
                counts.append([5, 0, 0] if speaker % 2 else [0, 0, 5])
                capture.append([1.0 + speaker / 10 + clip / 20, .01 + speaker / 100])
        counts = np.asarray(counts)
        assignment = outer_speaker_folds({row["speaker"] for row in rows}, 5, 20260923)
        saved = [{"outerFold": assignment[row["speaker"]]} for row in rows]
        pinned_folds = []
        for fold in range(5):
            fit = {speaker for speaker, number in assignment.items() if number != fold}
            pinned_folds.append({"holdoutSpeakerIds": sorted(set(assignment) - fit),
                                 "innerValidationSpeakerIds": sorted(
                                     inner_validation_speakers(fit, fold, .25, 20260923))})
        recipe = {"expectedTrainClips": len(rows), "outerFolds": 5, "outerSeed": 20260923,
                  "innerFractionOfOuterTrainSpeakers": .25,
                  "softmaxL2Candidates": [.01], "maxOptimizerIterations": 30,
                  "logLossEpsilon": 1e-12}
        original, original_oof, _ = evaluate(
            rows, counts, np.asarray(capture), saved, {"folds": pinned_folds}, recipe)
        changed = counts.copy()
        holdout = [i for i, row in enumerate(rows) if assignment[row["speaker"]] == 0]
        changed[holdout] = [0, 5, 0]
        _, changed_oof, _ = evaluate(
            rows, changed, np.asarray(capture), saved, {"folds": pinned_folds}, recipe)
        self.assertEqual(set(original["pooledOutOfFold"]), set(METHODS))
        for index in holdout:
            self.assertEqual(original_oof[index]["probabilities"],
                             changed_oof[index]["probabilities"])


if __name__ == "__main__":
    unittest.main()
