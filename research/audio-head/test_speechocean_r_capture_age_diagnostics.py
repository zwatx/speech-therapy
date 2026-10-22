"""Pairing, age-slice, metric, and within-band bootstrap checks."""
import copy
import unittest

import numpy as np

from speechocean_r_capture_age_diagnostics import load_recipe, summarize
from speechocean_r_oof_diagnostics import per_clip_scores


class CaptureAgeDiagnosticTests(unittest.TestCase):
    def test_locked_sources_and_settings(self):
        recipe = load_recipe()
        self.assertEqual(recipe["expectedBandClips"], {"child": 349, "adult": 417})
        self.assertEqual(recipe["bootstrap"]["unit"], "whole speaker within age band")
        self.assertEqual(recipe["bootstrap"]["resamples"], 2000)

    def test_paired_scores_recombine_and_age_resampling_stays_within_band(self):
        acoustic_rows, capture_rows = [], []
        ages = {"c1": 12, "c2": 13, "a1": 20, "a2": 21}
        for index, speaker in enumerate(ages):
            identity = {"id": f"clip-{index}", "speaker": speaker,
                        "outerFold": index, "fiveRaterCounts": [0, 0, 5]}

            def p(top):
                return [(1 - top) / 2, (1 - top) / 2, top]

            acoustic_rows.append({**identity, "probabilities": {
                "wav2vec2-base": p((.90, .85, .50, .55)[index]),
                "wavlm-base-plus": p((.85, .80, .55, .60)[index]),
                "trainPrior": p(.70), "targetWord": p(.70)}})
            capture_rows.append({**identity, "probabilities": {
                "wordAgeSoftmax": p(.70),
                "wordAgeDurationRmsSoftmax": p((.75, .78, .65, .62)[index])}})
        counts = np.asarray([row["fiveRaterCounts"] for row in acoustic_rows])

        def pooled(rows, names):
            return {name: dict(zip(("perRaterLogLoss", "perRaterBrier"),
                                   (float(value.mean()) for value in per_clip_scores(
                                       np.asarray([row["probabilities"][name] for row in rows]),
                                       counts, 1e-12)))) for name in names}

        acoustic_report = {"pooledOutOfFold": pooled(
            acoustic_rows, ("wav2vec2-base", "wavlm-base-plus"))}
        capture_report = {"pooledOutOfFold": pooled(
            capture_rows, ("wordAgeDurationRmsSoftmax",))}
        recipe = {"expectedClips": 4, "expectedSpeakers": 4,
                  "expectedBandClips": {"child": 2, "adult": 2},
                  "expectedBandSpeakers": {"child": 2, "adult": 2},
                  "logLossEpsilon": 1e-12,
                  "bootstrap": {"seed": 9, "resamples": 2000,
                                "percentiles": [2.5, 97.5]}}
        original = copy.deepcopy((acoustic_rows, capture_rows))
        bands = summarize(acoustic_rows, capture_rows, ages, recipe,
                          acoustic_report, capture_report)
        self.assertEqual((acoustic_rows, capture_rows), original)
        self.assertEqual(bands, summarize(acoustic_rows, capture_rows, ages, recipe,
                                          acoustic_report, capture_report))
        self.assertEqual((bands["child"]["speakers"], bands["adult"]["speakers"]),
                         (2, 2))
        self.assertEqual(bands["child"]["bootstrapDrawsSha256"],
                         bands["adult"]["bootstrapDrawsSha256"])
        comparison = "wordAgeDurationRmsSoftmax minus wav2vec2-base"
        self.assertGreater(bands["child"]["comparisons"]["perRaterLogLoss"]
                           [comparison]["pointDifference"], 0)
        self.assertLess(bands["adult"]["comparisons"]["perRaterLogLoss"]
                          [comparison]["pointDifference"], 0)
        for method, source in (("wordAgeDurationRmsSoftmax", capture_report),
                               ("wav2vec2-base", acoustic_report),
                               ("wavlm-base-plus", acoustic_report)):
            for metric in ("perRaterLogLoss", "perRaterBrier"):
                pooled_value = sum(bands[band]["clips"] * bands[band]["methods"][method][metric]
                                   for band in bands) / 4
                self.assertAlmostEqual(pooled_value,
                                       source["pooledOutOfFold"][method][metric])
        with self.assertRaisesRegex(ValueError, "Unexpected child age cohort"):
            summarize(acoustic_rows, capture_rows, {**ages, "c2": 20}, recipe,
                      acoustic_report, capture_report)
        altered = copy.deepcopy(capture_rows)
        altered[1]["outerFold"] = 4
        with self.assertRaisesRegex(ValueError, "rows differ"):
            summarize(acoustic_rows, altered, ages, recipe,
                      acoustic_report, capture_report)


if __name__ == "__main__":
    unittest.main()
