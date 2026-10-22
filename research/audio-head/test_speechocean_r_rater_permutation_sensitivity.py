import unittest

from speechocean_r_rater_permutation_sensitivity import (
    PREDICTORS, SEEDS, load_sensitivity_recipe, summarize_replicates)


class PermutationSensitivityTests(unittest.TestCase):
    def test_recipe_pins_existing_train_only_evaluation(self):
        recipe, cv_recipe, reference = load_sensitivity_recipe()
        self.assertEqual(recipe["permutationSeeds"], SEEDS)
        self.assertEqual(len(SEEDS), 20)
        self.assertEqual(cv_recipe["authorPartition"], "train")
        self.assertEqual(reference["outOfFoldClips"], 766)
        self.assertFalse(recipe["clinicalUseEligible"])

    def test_summary_reports_range_median_and_exploratory_rank(self):
        def scores(value):
            return {name: {"perRaterLogLoss": value, "perRaterBrier": value / 2}
                    for name in PREDICTORS}

        reference = scores(0.5)
        replicates = [
            {"seed": seed,
             "permutation": {"sourceMappingSha256": f"mapping-{index}",
                             "fiveScoreVectorsChanged": 200 + index},
             "pooledOutOfFold": scores(index / 20)}
            for index, seed in enumerate(SEEDS)]
        summary = summarize_replicates(replicates, reference)
        metric = summary["wav2vec2-base"]["perRaterLogLoss"]
        self.assertEqual(metric["minimum"], 0.0)
        self.assertEqual(metric["median"], 0.475)
        self.assertEqual(metric["maximum"], 0.95)
        self.assertEqual(metric["replicatesBelowReference"], 10)
        self.assertEqual(metric["replicatesEqualReference"], 1)
        self.assertEqual(metric["replicatesAboveReference"], 9)
        self.assertEqual(summary["fiveScoreVectorsChanged"],
                         {"minimum": 200, "median": 209.5, "maximum": 219})

    def test_rejects_duplicate_mapping_even_with_distinct_seeds(self):
        replicates = [
            {"seed": seed,
             "permutation": {"sourceMappingSha256": "duplicate",
                             "fiveScoreVectorsChanged": 200},
             "pooledOutOfFold": {name: {"perRaterLogLoss": 0.5,
                                          "perRaterBrier": 0.25}
                                 for name in PREDICTORS}}
            for seed in SEEDS]
        with self.assertRaisesRegex(ValueError, "distinct ordered permutation"):
            summarize_replicates(replicates, replicates[0]["pooledOutOfFold"])

    def test_rank_ignores_roundoff_at_machine_precision(self):
        reference = {name: {"perRaterLogLoss": 0.5, "perRaterBrier": 0.25}
                     for name in PREDICTORS}
        replicates = [
            {"seed": seed,
             "permutation": {"sourceMappingSha256": f"mapping-{index}",
                             "fiveScoreVectorsChanged": 230},
             "pooledOutOfFold": {name: {"perRaterLogLoss": 0.5 + 1e-14,
                                          "perRaterBrier": 0.25 - 1e-14}
                                 for name in PREDICTORS}}
            for index, seed in enumerate(SEEDS)]
        metric = summarize_replicates(replicates, reference)["trainPrior"]["perRaterLogLoss"]
        self.assertEqual(metric["replicatesEqualReference"], 20)
        self.assertEqual(metric["replicatesAboveReference"], 0)


if __name__ == "__main__":
    unittest.main()
