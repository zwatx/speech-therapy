import copy
import math
import unittest

import numpy as np

from speechocean_r_speaker_word_purged import (
    evaluate, fold_split, load_recipe, purge_split,
)
from speechocean_r_rater_cv import prior_probabilities
from speechocean_train_cv import inner_validation_speakers, outer_speaker_folds


class PurgedSplitTests(unittest.TestCase):
    def test_purge_removes_every_fit_clip_with_a_holdout_word(self):
        rows = [
            {"speaker": "a", "targetWord": "CAR"},
            {"speaker": "b", "targetWord": "RED"},
            {"speaker": "b", "targetWord": "CAR"},
            {"speaker": "c", "targetWord": "RED"},
            {"speaker": "c", "targetWord": "TREE"},
        ]
        retained, removed = purge_split(rows, np.asarray([1, 2, 3, 4]), np.asarray([0]))
        self.assertEqual(retained.tolist(), [1, 3, 4])
        self.assertEqual(removed.tolist(), [2])

    def test_purge_rejects_speaker_overlap_and_empty_fit(self):
        rows = [{"speaker": "a", "targetWord": "CAR"},
                {"speaker": "a", "targetWord": "RED"},
                {"speaker": "b", "targetWord": "CAR"}]
        with self.assertRaisesRegex(ValueError, "share speakers"):
            purge_split(rows, np.asarray([1]), np.asarray([0]))
        with self.assertRaisesRegex(ValueError, "Purge did not create"):
            purge_split(rows, np.asarray([2]), np.asarray([0]))

    def test_nested_folds_keep_speakers_and_words_disjoint(self):
        recipe = load_recipe()
        rows = []
        for speaker in range(10):
            rows.extend([{"id": f"{speaker}-common", "speaker": str(speaker),
                          "targetWord": "COMMON"},
                         {"id": f"{speaker}-unique", "speaker": str(speaker),
                          "targetWord": f"WORD{speaker}"}])
        assignments = outer_speaker_folds({row["speaker"] for row in rows}, 5,
                                          recipe["outerSeed"])
        coverage = np.zeros(len(rows), dtype=int)
        for fold in range(5):
            split = fold_split(rows, assignments, fold, recipe)
            coverage[split["outerHoldout"]] += 1
            self.assertEqual(len(split["outerRemoved"]), 8)
            self.assertEqual(len(split["outerFit"]), 8)
            for fit_name, holdout_name in (("outerFit", "outerHoldout"),
                                           ("innerFit", "innerValidation")):
                fit = split[fit_name]
                holdout = split[holdout_name]
                self.assertFalse({rows[i]["speaker"] for i in fit} &
                                 {rows[i]["speaker"] for i in holdout})
                self.assertFalse({rows[i]["targetWord"] for i in fit} &
                                 {rows[i]["targetWord"] for i in holdout})
        self.assertTrue(np.all(coverage == 1))

    def test_inner_fit_purges_word_shared_with_validation_speaker(self):
        recipe = load_recipe()
        speakers = {str(i) for i in range(10)}
        assignments = outer_speaker_folds(speakers, 5, recipe["outerSeed"])
        outer_speakers = {speaker for speaker in speakers if assignments[speaker] != 0}
        inner_speakers = inner_validation_speakers(
            outer_speakers, 0, recipe["innerFractionOfOuterTrainSpeakers"], recipe["outerSeed"])
        validation_speaker = sorted(inner_speakers)[0]
        fit_speaker = sorted(outer_speakers - inner_speakers)[0]
        rows = [{"id": speaker, "speaker": speaker, "targetWord": f"WORD{speaker}"}
                for speaker in sorted(speakers)]
        rows.extend([{"id": "validation-shared", "speaker": validation_speaker,
                      "targetWord": "INNER_SHARED"},
                     {"id": "fit-shared", "speaker": fit_speaker,
                      "targetWord": "INNER_SHARED"}])
        split = fold_split(rows, assignments, 0, recipe)
        self.assertIn(next(i for i, row in enumerate(rows) if row["id"] == "fit-shared"),
                      split["innerRemoved"])
        self.assertNotIn(next(i for i, row in enumerate(rows) if row["id"] == "fit-shared"),
                         split["innerFit"])


class PurgedEvaluationTests(unittest.TestCase):
    def test_oof_is_complete_and_prior_uses_purged_fit_only(self):
        recipe = copy.deepcopy(load_recipe())
        recipe["softmaxL2Candidates"] = [0.1]
        recipe["maxOptimizerIterations"] = 5
        rows = []
        counts = []
        features = []
        for speaker in range(10):
            for clip, word in enumerate(("COMMON", f"WORD{speaker}")):
                rows.append({"id": f"{speaker}-{clip}", "speaker": str(speaker),
                             "targetWord": word})
                label = (speaker + clip) % 3
                counts.append([5 * (label == value) for value in range(3)])
                features.append([float(speaker % 4), float(clip), float(label)])
        counts = np.asarray(counts)
        x = np.asarray(features)
        matrices = {"wav2vec2-base": x, "wavlm-base-plus": x[:, ::-1].copy()}
        summary, oof, heads = evaluate(rows, matrices, counts, recipe)
        self.assertEqual(len(oof), 20)
        self.assertEqual(len({row["id"] for row in oof}), 20)
        self.assertEqual(sum(fold["holdoutClips"] for fold in summary["folds"]), 20)
        self.assertTrue(heads)
        assignments = outer_speaker_folds({row["speaker"] for row in rows}, 5,
                                          recipe["outerSeed"])
        for fold in range(5):
            split = fold_split(rows, assignments, fold, recipe)
            expected_prior = prior_probabilities(counts[split["outerFit"]], 1.0)
            for i in split["outerHoldout"]:
                self.assertTrue(np.allclose(oof[i]["probabilities"]["trainPrior"], expected_prior))
                for probability in oof[i]["probabilities"].values():
                    self.assertAlmostEqual(sum(probability), 1)
                    self.assertTrue(all(math.isfinite(value) for value in probability))
        self.assertEqual(summary["outOfFoldRaterScores"], 100)

    def test_duplicate_clip_id_is_rejected_before_fitting(self):
        recipe = load_recipe()
        rows = [{"id": "same", "speaker": str(i), "targetWord": f"WORD{i}"}
                for i in range(10)]
        rows[1]["id"] = "same"
        counts = np.tile([0, 0, 5], (10, 1))
        x = np.ones((10, 2))
        with self.assertRaisesRegex(ValueError, "Invalid paired author-train input"):
            evaluate(rows, {"wav2vec2-base": x, "wavlm-base-plus": x}, counts, recipe)


if __name__ == "__main__":
    unittest.main()
