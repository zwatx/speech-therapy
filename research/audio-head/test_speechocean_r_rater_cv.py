import copy
import math
import unittest

import numpy as np

from speechocean_r_rater_cv import (choose_softmax, evaluate, fit_softmax,
                                   V2_RECIPE, load_recipe, predict_softmax, prior_probabilities,
                                   probabilistic_metrics, target_word_probabilities)


class ProbabilityTests(unittest.TestCase):
    def test_log_loss_and_brier_use_all_five_rater_scores(self):
        counts = np.asarray([[3, 0, 2], [0, 5, 0]])
        probabilities = np.asarray([[0.6, 0.2, 0.2], [0.1, 0.8, 0.1]])
        measured = probabilistic_metrics(probabilities, counts)
        expected_log = -((3 * math.log(0.6) + 2 * math.log(0.2)) / 5 + math.log(0.8)) / 2
        expected_brier = ((0.6**2 + 0.2**2 + 0.2**2 -
                           2 * (0.6 * 3/5 + 0.2 * 2/5) + 1) +
                          (0.1**2 + 0.8**2 + 0.1**2 - 2 * 0.8 + 1)) / 2
        self.assertAlmostEqual(measured["perRaterLogLoss"], expected_log)
        self.assertAlmostEqual(measured["perRaterBrier"], expected_brier)

    def test_train_prior_and_word_backoff_use_only_supplied_fit_rows(self):
        fit_rows = [{"targetWord": "RED"}, {"targetWord": "CAR"}]
        counts = np.asarray([[5, 0, 0], [0, 0, 5]])
        prior = prior_probabilities(counts, 1.0)
        self.assertTrue(np.allclose(prior, [6/13, 1/13, 6/13]))
        prediction = target_word_probabilities(fit_rows, counts,
                                               [{"targetWord": "RED"}, {"targetWord": "NEW"}],
                                               1.0, 1.0)
        self.assertGreater(prediction[0, 0], prior[0])
        self.assertTrue(np.allclose(prediction[1], prior))
        with self.assertRaisesRegex(ValueError, "Invalid probability"):
            probabilistic_metrics(np.asarray([[1.1, -0.1, 0.0]]), np.asarray([[5, 0, 0]]))

    def test_softmax_fit_is_finite_bounded_and_uses_soft_targets(self):
        x = np.asarray([[-2.0], [-1.0], [0.0], [1.0], [2.0], [3.0]])
        counts = np.asarray([[5, 0, 0], [4, 1, 0], [2, 2, 1],
                             [1, 2, 2], [0, 1, 4], [0, 0, 5]])
        head, diagnostic = fit_softmax(x, counts, 0.01, 40)
        probabilities = predict_softmax(head, x)
        self.assertTrue(np.allclose(probabilities.sum(axis=1), 1))
        self.assertTrue(np.all((probabilities > 0) & (probabilities < 1)))
        self.assertGreater(probabilities[-1, 2], probabilities[0, 2])
        self.assertTrue(math.isfinite(diagnostic["finalObjective"]))
        self.assertLessEqual(diagnostic["optimizerIterations"], 40)


class NestedSelectionTests(unittest.TestCase):
    def test_recipe_locks_train_only_source_and_false_flags(self):
        recipe = load_recipe()
        self.assertEqual(recipe["authorPartition"], "train")
        self.assertFalse(recipe["authorTestUsedForSettings"])
        self.assertTrue(all(recipe[key] is False for key in (
            "productionEligible", "calibrationEligible", "learnerFeedbackEligible",
            "clinicalUseEligible", "clinicalReliabilityEstablished")))

    def test_v2_recipe_changes_only_iteration_budget_and_identifiers(self):
        earlier = load_recipe()
        later = load_recipe(V2_RECIPE)
        changed = {key for key in earlier if earlier[key] != later[key]}
        self.assertEqual(changed, {"experiment", "optimizer", "maxOptimizerIterations", "outputDirectory"})
        self.assertEqual((earlier["maxOptimizerIterations"], later["maxOptimizerIterations"]), (80, 400))
        self.assertEqual(earlier["inputs"], later["inputs"])
        self.assertEqual(earlier["outerSeed"], later["outerSeed"])

    def test_inner_softmax_choice_ignores_outer_label(self):
        recipe = copy.deepcopy(load_recipe())
        recipe["softmaxL2Candidates"] = [0.01, 0.1]
        recipe["maxOptimizerIterations"] = 10
        x = np.arange(12, dtype=float).reshape(6, 2)
        counts = np.asarray([[5, 0, 0], [4, 1, 0], [3, 1, 1],
                             [2, 2, 1], [1, 2, 2], [0, 0, 5]])
        fit, validation = np.asarray([0, 1, 2]), np.asarray([3, 4])
        before = choose_softmax(x, counts, fit, validation, recipe)
        changed = counts.copy()
        changed[5] = [5, 0, 0]
        self.assertEqual(before, choose_softmax(x, changed, fit, validation, recipe))

    def test_nested_oof_has_one_simplex_per_clip_and_disjoint_speakers(self):
        recipe = copy.deepcopy(load_recipe())
        recipe["softmaxL2Candidates"] = [0.1]
        recipe["targetWordSmoothingCandidates"] = [1.0]
        recipe["maxOptimizerIterations"] = 5
        rows = []
        counts = []
        for speaker in range(124):
            for clip in range(6 + (speaker < 22)):
                rows.append({"id": f"{speaker:04d}-{clip}", "speaker": f"{speaker:04d}",
                             "targetWord": "RED" if clip % 2 else "CAR"})
                label = (speaker + clip) % 3
                counts.append([5 * (label == value) for value in range(3)])
        counts = np.asarray(counts)
        features = np.column_stack([np.arange(766) % 7, counts @ np.asarray([0, 1, 2])]).astype(float)
        matrices = {"wav2vec2-base": features, "wavlm-base-plus": features[:, ::-1].copy()}
        summary, oof, heads = evaluate(rows, matrices, counts, recipe)
        self.assertEqual(len(oof), 766)
        self.assertEqual(summary["outOfFoldRaterScores"], 3830)
        self.assertEqual(len(summary["folds"]), 5)
        self.assertTrue(heads)
        for fold in summary["folds"]:
            self.assertFalse(set(fold["holdoutSpeakerIds"]) & set(fold["outerTrainSpeakerIds"]))
            self.assertFalse(set(fold["innerFitSpeakerIds"]) & set(fold["innerValidationSpeakerIds"]))
        for row in oof:
            self.assertEqual(sum(row["fiveRaterCounts"]), 5)
            for probabilities in row["probabilities"].values():
                self.assertAlmostEqual(sum(probabilities), 1)
        self.assertTrue(all(value["expectedRatingsOutsideZeroToTwo"] == 0
                            for value in summary["probabilityBounds"].values()))


if __name__ == "__main__":
    unittest.main()
