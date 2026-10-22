"""Pairing and fixed-prediction checks for the capture-control bootstrap."""
import copy
import unittest

import numpy as np

from speechocean_r_capture_paired_bootstrap import COMPARISONS, compare_rows, load_recipe
from speechocean_r_oof_diagnostics import per_clip_scores, speaker_bootstrap


class CapturePairedBootstrapTests(unittest.TestCase):
    def test_locked_recipe(self):
        recipe = load_recipe()
        self.assertEqual(recipe["bootstrap"]["comparisons"], COMPARISONS)
        self.assertEqual(recipe["bootstrap"]["resamples"], 2000)
        self.assertEqual(recipe["bootstrap"]["unit"], "speaker")

    def test_exact_pairing_and_metric_replay(self):
        acoustic, capture = [], []
        for index, top in enumerate((.9, .5)):
            identity = {"id": f"clip-{index}", "speaker": f"speaker-{index}",
                        "outerFold": index, "fiveRaterCounts": [0, 0, 5]}
            p = [(1 - top) / 2, (1 - top) / 2, top]
            acoustic.append({**identity, "probabilities": {
                "wav2vec2-base": p, "wavlm-base-plus": p,
                "trainPrior": p, "targetWord": p}})
            capture.append({**identity, "probabilities": {
                "wordAgeSoftmax": [.1, .1, .8],
                "wordAgeDurationRmsSoftmax": [.15, .15, .7]}})
        counts = np.asarray([[0, 0, 5], [0, 0, 5]])

        def mean_loss(probabilities):
            return float(per_clip_scores(np.asarray(probabilities), counts, 1e-12)[0].mean())

        acoustic_loss = mean_loss([row["probabilities"]["wav2vec2-base"] for row in acoustic])
        capture_loss = mean_loss([row["probabilities"]["wordAgeDurationRmsSoftmax"]
                                  for row in capture])
        acoustic_report = {"pooledOutOfFold": {
            "wav2vec2-base": {"perRaterLogLoss": acoustic_loss},
            "wavlm-base-plus": {"perRaterLogLoss": acoustic_loss}}}
        capture_report = {"pooledOutOfFold": {
            "wordAgeDurationRmsSoftmax": {"perRaterLogLoss": capture_loss}}}
        recipe = {"expectedClips": 2, "expectedSpeakers": 2, "logLossEpsilon": 1e-12}
        scores, speakers = compare_rows(acoustic, capture, acoustic_report, capture_report, recipe)
        self.assertEqual(speakers, ["speaker-0", "speaker-1"])
        results, _ = speaker_bootstrap(scores, speakers, COMPARISONS, 7, 2000, [2.5, 97.5])
        self.assertAlmostEqual(results["wordAgeDurationRmsSoftmax minus wav2vec2-base"]
                               ["pointDifference"], capture_loss - acoustic_loss)
        bad = copy.deepcopy(capture)
        bad[1]["outerFold"] = 4
        with self.assertRaisesRegex(ValueError, "rows differ"):
            compare_rows(acoustic, bad, acoustic_report, capture_report, recipe)
        bad_report = copy.deepcopy(capture_report)
        bad_report["pooledOutOfFold"]["wordAgeDurationRmsSoftmax"]["perRaterLogLoss"] += .1
        with self.assertRaisesRegex(ValueError, "loss differs"):
            compare_rows(acoustic, capture, acoustic_report, bad_report, recipe)


if __name__ == "__main__":
    unittest.main()
