import unittest

import numpy as np

from speechocean_train_cv import (choose_ridge, evaluate, inner_validation_speakers,
                                  load_recipe, outer_speaker_folds)


class TrainOnlyCrossValidationTests(unittest.TestCase):
    def test_predeclared_recipe_uses_train_only_and_research_flags(self):
        recipe = load_recipe()
        self.assertEqual(recipe["authorPartition"], "train")
        self.assertFalse(recipe["authorTestUsedForSettings"])
        self.assertEqual(recipe["outerFolds"], 5)
        self.assertTrue(all(recipe[key] is False for key in (
            "productionEligible", "calibrationEligible", "learnerFeedbackEligible", "clinicalUseEligible")))

    def test_outer_and_inner_speaker_assignments_are_deterministic_and_disjoint(self):
        speakers = {f"{number:04d}" for number in range(124)}
        first = outer_speaker_folds(speakers, 5, 20260923)
        self.assertEqual(first, outer_speaker_folds(set(reversed(sorted(speakers))), 5, 20260923))
        self.assertEqual(sorted(set(first.values())), list(range(5)))
        for fold in range(5):
            train = {speaker for speaker, assigned in first.items() if assigned != fold}
            holdout = speakers - train
            inner = inner_validation_speakers(train, fold, 0.2, 20260923)
            self.assertTrue(inner <= train)
            self.assertFalse(inner & holdout)
            self.assertTrue(train - inner)

    def test_inner_alpha_selection_does_not_read_outer_holdout_label(self):
        x = np.arange(12, dtype=float).reshape(6, 2)
        y = np.asarray([0.2, 0.6, 1.0, 1.4, 1.8, 2.0])
        fit = np.asarray([0, 1, 2])
        validation = np.asarray([3, 4])
        before = choose_ridge(x, y, fit, validation, [1.0, 10.0])
        changed = y.copy()
        changed[5] = -1000.0
        self.assertEqual(before, choose_ridge(x, changed, fit, validation, [1.0, 10.0]))

    def test_nested_oof_covers_each_train_clip_once_without_speaker_overlap(self):
        recipe = load_recipe()
        rows = []
        for speaker_index in range(124):
            for utterance_index in range(6 + (speaker_index < 22)):
                rows.append({"id": f"{speaker_index:04d}-{utterance_index}",
                             "speaker": f"{speaker_index:04d}",
                             "rating": float([0.4, 1.0, 1.6, 2.0][(speaker_index + utterance_index) % 4]),
                             "targetWord": ["RED", "AROUND", "CAR"][speaker_index % 3],
                             "text": ["SAY RED", "SAY CAR"][utterance_index % 2]})
        self.assertEqual(len(rows), 766)
        values = np.asarray([row["rating"] for row in rows])
        features = np.column_stack([values, np.arange(len(rows)) % 7]).astype(float)
        matrices = {"wav2vec2-base": features,
                    "wavlm-base-plus": features[:, ::-1].copy()}
        summary, oof = evaluate(rows, matrices, recipe)
        self.assertEqual(len(oof), 766)
        self.assertEqual(len({row["id"] for row in oof}), 766)
        self.assertEqual(sum(fold["holdoutClips"] for fold in summary["folds"]), 766)
        for fold in summary["folds"]:
            self.assertFalse(set(fold["holdoutSpeakerIds"]) & set(fold["outerTrainSpeakerIds"]))
            self.assertFalse(set(fold["innerFitSpeakerIds"]) & set(fold["innerValidationSpeakerIds"]))
            self.assertEqual(fold["outerTrainSpeakers"], len(fold["outerTrainSpeakerIds"]))
            self.assertEqual(fold["holdoutSpeakers"], len(fold["holdoutSpeakerIds"]))
        error = np.mean([abs(row["predictions"]["constantTwo"] - row["rating"]) for row in oof])
        self.assertAlmostEqual(error, summary["pooledOutOfFold"]["constantTwo"]["mae"])


if __name__ == "__main__":
    unittest.main()
