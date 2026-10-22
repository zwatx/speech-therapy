"""Synthetic checks of the paired speaker-and-word-purged incremental fit."""
import copy
import unittest

import numpy as np

from speechocean_r_incremental_audio_word_purged import METHODS, evaluate, load_recipe
from speechocean_r_speaker_word_purged import fold_split
from speechocean_train_cv import outer_speaker_folds


class IncrementalWordPurgeTests(unittest.TestCase):
    def test_recipe_pins_upstream_feature_recipe_bytes(self):
        recipe = load_recipe()
        self.assertEqual(recipe["featureRecipeSha256"],
                         "f17a024acb7837679a0818d7fbd5f617c0b1ba0ec3cb56c127531adabe22c5f5")

    def test_paired_fits_use_word_and_speaker_disjoint_splits(self):
        rows, counts, capture = [], [], []
        for speaker in range(10):
            for clip, word in enumerate(("COMMON", f"UNIQUE{speaker}")):
                rows.append({"id": f"{speaker}-{clip}", "speaker": str(speaker),
                             "targetWord": word,
                             "ageBand": "child" if speaker < 5 else "adult"})
                counts.append([5, 0, 0] if speaker % 2 else [0, 0, 5])
                capture.append([1 + speaker / 10 + clip / 20, .01 + speaker / 100])
        counts = np.asarray(counts)
        capture = np.asarray(capture)
        audio = {"wav2vec2-base": np.tile(np.arange(768, dtype=float), (20, 1)) / 768,
                 "wavlm-base-plus": np.tile(np.arange(768, dtype=float)[::-1],
                                              (20, 1)) / 768}
        assignments = outer_speaker_folds({row["speaker"] for row in rows}, 5, 20260923)
        reference_oof = [{"outerFold": assignments[row["speaker"]]} for row in rows]
        recipe = {"expectedTrainClips": 20, "expectedTrainSpeakers": 10,
                  "outerFolds": 5, "outerSeed": 20260923,
                  "innerFractionOfOuterTrainSpeakers": .25,
                  "softmaxL2Candidates": [.01], "maxOptimizerIterations": 20,
                  "logLossEpsilon": 1e-12}
        pinned = []
        for fold in range(5):
            split = fold_split(rows, assignments, fold, recipe)
            for fit, validation in ((split["outerFit"], split["outerHoldout"]),
                                     (split["innerFit"], split["innerValidation"])):
                self.assertFalse({rows[i]["speaker"] for i in fit} &
                                 {rows[i]["speaker"] for i in validation})
                self.assertFalse({rows[i]["targetWord"] for i in fit} &
                                 {rows[i]["targetWord"] for i in validation})
            pinned.append({"holdoutClips": len(split["outerHoldout"]),
                           "outerCandidateClips": len(split["outerCandidates"]),
                           "outerPurgedClips": len(split["outerRemoved"]),
                           "outerFitClips": len(split["outerFit"]),
                           "innerCandidateClips": len(split["innerCandidates"]),
                           "innerPurgedClips": len(split["innerRemoved"]),
                           "innerFitClips": len(split["innerFit"]),
                           "innerValidationClips": len(split["innerValidation"])})
        report = {"folds": pinned}
        summary, oof, _ = evaluate(rows, counts, capture, audio, reference_oof,
                                   report, recipe)
        self.assertEqual(summary["outOfFoldClips"], 20)
        self.assertEqual(set(oof[0]["probabilities"]), set(METHODS))
        changed = counts.copy()
        held = [i for i, row in enumerate(rows) if assignments[row["speaker"]] == 0]
        changed[held] = [0, 5, 0]
        _, changed_oof, _ = evaluate(rows, changed, capture, audio, reference_oof,
                                     report, recipe)
        for i in held:
            self.assertEqual(oof[i]["probabilities"], changed_oof[i]["probabilities"])
        tampered = copy.deepcopy(report)
        tampered["folds"][0]["outerPurgedClips"] += 1
        with self.assertRaisesRegex(ValueError, "Pinned word-purge"):
            evaluate(rows, counts, capture, audio, reference_oof, tampered, recipe)


if __name__ == "__main__":
    unittest.main()
