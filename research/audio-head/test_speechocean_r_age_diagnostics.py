import unittest

from speechocean_r_age_diagnostics import age_band, summarize


class AgeDiagnosticsTests(unittest.TestCase):
    def test_age_band_rejects_unassigned_and_bool(self):
        self.assertEqual(age_band(15), "child")
        self.assertEqual(age_band(19), "adult")
        for value in (True, -1, 16, 18):
            with self.subTest(value=value), self.assertRaises(ValueError):
                age_band(value)

    def test_two_slices_keep_five_ratings_and_speakers(self):
        def row(speaker, counts, probability):
            return {"speaker": speaker, "fiveRaterCounts": counts,
                    "probabilities": {method: probability for method in
                                      ("wav2vec2-base", "wavlm-base-plus",
                                       "trainPrior", "targetWord")}}

        rows = [row("c1", [0, 0, 5], [0.1, 0.1, 0.8]),
                row("c1", [0, 1, 4], [0.1, 0.2, 0.7]),
                row("a1", [5, 0, 0], [0.8, 0.1, 0.1]),
                row("a2", [1, 2, 2], [0.3, 0.3, 0.4])]
        recipe = {"expectedClips": 4, "expectedSpeakers": 3,
                  "expectedBandClips": {"child": 2, "adult": 2},
                  "logLossEpsilon": 1e-12}
        slices = summarize(rows, {"c1": 12, "a1": 19, "a2": 25}, recipe)
        self.assertEqual((slices["child"]["clips"], slices["child"]["speakers"],
                          slices["child"]["raterScores"]), (2, 1, 10))
        self.assertEqual((slices["adult"]["unanimousZeroClips"],
                          slices["adult"]["mixedClips"]), (1, 1))
        self.assertAlmostEqual(slices["child"]["wav2vecMinusPriorLogLoss"], 0)

        with self.assertRaisesRegex(ValueError, "clip count"):
            summarize(rows, {"c1": 12, "a1": 19, "a2": 25},
                      {**recipe, "expectedBandClips": {"child": 1, "adult": 3}})
        with self.assertRaisesRegex(ValueError, "OOF speakers"):
            summarize(rows, {"c1": 12, "a1": 19}, recipe)


if __name__ == "__main__":
    unittest.main()
