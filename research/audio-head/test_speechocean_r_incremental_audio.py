"""Synthetic fit-only and speaker-leakage checks for the incremental probe."""
import unittest

import numpy as np

from speechocean_r_incremental_audio import METHODS, design, evaluate
from speechocean_train_cv import inner_validation_speakers, outer_speaker_folds


class IncrementalAudioTests(unittest.TestCase):
    def test_combined_uses_only_fit_words_and_the_requested_encoder(self):
        rows = [{"targetWord": "RED", "ageBand": "child"},
                {"targetWord": "CAR", "ageBand": "adult"},
                {"targetWord": "UNSEEN", "ageBand": "child"}]
        capture = np.asarray([[1, .01], [2, .02], [3, .03]], dtype=float)
        audio = {"wav2vec2-base": np.full((3, 768), 7.0),
                 "wavlm-base-plus": np.full((3, 768), 11.0)}
        fit, holdout = np.asarray([0, 1]), np.asarray([2])
        x_fit, x_holdout, words = design(rows, capture, audio, fit, holdout,
                                          "wavlmCombined")
        self.assertEqual(words, ["CAR", "RED"])
        self.assertTrue(np.array_equal(x_holdout[0, :2], [0, 0]))
        self.assertTrue(np.array_equal(x_holdout[0, 2:5], [0, 3, .03]))
        self.assertTrue(np.all(x_holdout[0, 5:] == 11))
        self.assertEqual(x_fit.shape, (2, 773))
        acoustic_fit, acoustic_holdout, vocabulary = design(
            rows, capture, audio, fit, holdout, "wav2vec2AudioOnly")
        self.assertEqual(vocabulary, [])
        self.assertTrue(np.all(acoustic_fit == 7))
        self.assertTrue(np.all(acoustic_holdout == 7))

    def test_outer_holdout_labels_cannot_change_own_predictions(self):
        rows, counts, capture = [], [], []
        for speaker in range(10):
            for clip in range(2):
                rows.append({"id": f"{speaker}-{clip}", "speaker": f"{speaker:04d}",
                             "targetWord": "RED" if clip else "CAR",
                             "ageBand": "child" if speaker < 5 else "adult"})
                counts.append([5, 0, 0] if speaker % 2 else [0, 0, 5])
                capture.append([1 + speaker / 10 + clip / 20, .01 + speaker / 100])
        counts = np.asarray(counts)
        capture = np.asarray(capture)
        base = np.arange(len(rows) * 768, dtype=float).reshape(len(rows), 768)
        audio = {"wav2vec2-base": np.sin(base / 97),
                 "wavlm-base-plus": np.cos(base / 101)}
        assignments = outer_speaker_folds({row["speaker"] for row in rows}, 5, 20260923)
        reference_oof = [{"outerFold": assignments[row["speaker"]]} for row in rows]
        folds = []
        for fold in range(5):
            fit_speakers = {speaker for speaker, number in assignments.items()
                            if number != fold}
            folds.append({"fold": fold,
                          "holdoutSpeakerIds": sorted(set(assignments) - fit_speakers),
                          "innerValidationSpeakerIds": sorted(inner_validation_speakers(
                              fit_speakers, fold, .25, 20260923))})
        recipe = {"expectedTrainClips": len(rows), "outerFolds": 5,
                  "outerSeed": 20260923, "innerFractionOfOuterTrainSpeakers": .25,
                  "softmaxL2Candidates": [.01], "maxOptimizerIterations": 20,
                  "logLossEpsilon": 1e-12}
        _, original, _ = evaluate(rows, counts, capture, audio, {"folds": folds},
                                  reference_oof, recipe)
        changed = counts.copy()
        held = [i for i, row in enumerate(rows) if assignments[row["speaker"]] == 0]
        changed[held] = [0, 5, 0]
        _, perturbed, _ = evaluate(rows, changed, capture, audio, {"folds": folds},
                                   reference_oof, recipe)
        for i in held:
            self.assertEqual(set(original[i]["probabilities"]), set(METHODS))
            self.assertEqual(original[i]["probabilities"], perturbed[i]["probabilities"])


if __name__ == "__main__":
    unittest.main()
