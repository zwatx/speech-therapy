import copy
import unittest

import numpy as np

from speechocean_r_oof_diagnostics import per_clip_scores, speaker_bootstrap
from speechocean_r_word_age_paired_bootstrap import (COMPARISONS, compare_rows,
                                                     load_recipe)


class WordAgePairedBootstrapTests(unittest.TestCase):
    def test_locked_recipe(self):
        recipe = load_recipe()
        self.assertEqual(recipe["bootstrap"]["comparisons"], COMPARISONS)
        self.assertEqual(recipe["bootstrap"]["unit"], "speaker")

    def test_pairing_checks_identity_and_saved_metrics(self):
        counts = [0, 0, 5]
        original = []
        categorical = []
        for index, sound in enumerate((0.85, 0.55)):
            side = (1 - sound) / 2
            base = {"id": f"clip-{index}", "speaker": f"spk-{index}",
                    "outerFold": index, "fiveRaterCounts": counts}
            original.append({**base, "probabilities": {
                "wav2vec2-base": [side, side, sound],
                "wavlm-base-plus": [side, side, sound],
                "trainPrior": [0.15, 0.15, 0.7],
                "targetWord": [0.15, 0.15, 0.7]}})
            categorical.append({**base, "probabilities": [0.15, 0.15, 0.7]})
        rating_counts = np.asarray([counts, counts])

        def mean_loss(probabilities):
            return float(per_clip_scores(np.asarray(probabilities), rating_counts, 1e-12)[0].mean())

        acoustic = mean_loss([row["probabilities"]["wav2vec2-base"] for row in original])
        word_age = mean_loss([row["probabilities"] for row in categorical])
        reference = {"pooledOutOfFold": {
            "wav2vec2-base": {"perRaterLogLoss": acoustic},
            "wavlm-base-plus": {"perRaterLogLoss": acoustic}}}
        control = {"pooledOutOfFold": {"perRaterLogLoss": word_age}}
        recipe = {"expectedClips": 2, "expectedSpeakers": 2,
                  "logLossEpsilon": 1e-12}
        loss, speakers = compare_rows(original, categorical, reference, control, recipe)
        self.assertEqual(speakers, ["spk-0", "spk-1"])
        self.assertAlmostEqual(float(loss["wordAge"].mean()), word_age)
        bootstrap, _ = speaker_bootstrap(loss, speakers, COMPARISONS, 17, 2000,
                                         [2.5, 97.5])
        self.assertAlmostEqual(bootstrap["wav2vec2-base minus wordAge"]["pointDifference"],
                               acoustic - word_age)
        bad = copy.deepcopy(categorical)
        bad[1]["speaker"] = "other"
        with self.assertRaisesRegex(ValueError, "rows differ"):
            compare_rows(original, bad, reference, control, recipe)
        bad = copy.deepcopy(control)
        bad["pooledOutOfFold"]["perRaterLogLoss"] += 0.1
        with self.assertRaisesRegex(ValueError, "loss differs"):
            compare_rows(original, categorical, reference, bad, recipe)


if __name__ == "__main__":
    unittest.main()
