import copy
import unittest

from speechocean_r_age_bootstrap import COMPARISONS, load_recipe, summarize


class AgeBootstrapTests(unittest.TestCase):
    def test_locked_recipe(self):
        recipe = load_recipe()
        self.assertEqual(recipe["bootstrap"]["comparisons"], COMPARISONS)
        self.assertEqual(recipe["bootstrap"]["resamples"], 2000)

    def test_speaker_resamples_are_paired_and_age_specific(self):
        def row(speaker, predicted):
            side = (1 - predicted) / 2
            return {"speaker": speaker, "fiveRaterCounts": [0, 0, 5],
                    "probabilities": {"wav2vec2-base": [side, side, predicted],
                                      "wavlm-base-plus": [side, side, predicted],
                                      "trainPrior": [0.15, 0.15, 0.70]}}

        rows = [row("c1", 0.90), row("c2", 0.85),
                row("a1", 0.50), row("a2", 0.55)]
        recipe = {"expectedBandClips": {"child": 2, "adult": 2},
                  "expectedBandSpeakers": {"child": 2, "adult": 2},
                  "logLossEpsilon": 1e-12,
                  "bootstrap": {"seed": 9, "resamples": 2000,
                                "percentiles": [2.5, 97.5]}}
        original = copy.deepcopy(rows)
        bands = summarize(rows, {"c1": 12, "c2": 13, "a1": 20, "a2": 21}, recipe)
        self.assertEqual(bands, summarize(rows,
                                          {"c1": 12, "c2": 13, "a1": 20, "a2": 21},
                                          recipe))
        self.assertEqual(rows, original)
        key = "wav2vec2-base minus trainPrior"
        self.assertLess(bands["child"]["comparisons"][key]["pointDifference"], 0)
        self.assertGreater(bands["adult"]["comparisons"][key]["pointDifference"], 0)
        self.assertEqual((bands["child"]["speakers"], bands["adult"]["speakers"]),
                         (2, 2))
        with self.assertRaisesRegex(ValueError, "Unexpected child age cohort"):
            summarize(rows, {"c1": 12, "c2": 20, "a1": 20, "a2": 21}, recipe)


if __name__ == "__main__":
    unittest.main()
