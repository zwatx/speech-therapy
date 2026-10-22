"""Pairing, tamper, and speaker-cluster checks for fixed incremental OOF intervals."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np

from speechocean_r_incremental_audio import METHODS
from speechocean_r_incremental_audio_paired_bootstrap import (COMPARISONS, RUNS,
                                                               load_inputs, load_recipe,
                                                               score_run, validate_rows)
from speechocean_r_oof_diagnostics import per_clip_scores, sha256_file, speaker_bootstrap
from speechocean_train_cv import outer_speaker_folds


class IncrementalPairedBootstrapTests(unittest.TestCase):
    def test_recipe_locks_both_runs_and_whole_speaker_draws(self):
        recipe = load_recipe()
        self.assertEqual(recipe["runs"], RUNS)
        self.assertEqual(recipe["comparisons"], COMPARISONS)
        self.assertEqual(recipe["bootstrap"]["resamples"], 10000)
        self.assertEqual(recipe["bootstrap"]["unit"], "whole speaker")

    def test_hash_tamper_is_rejected_before_reading_source(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for name in ("recipe.json", "report.json", "oof.json"):
                (base / name).write_text("{}\n")
            pins = {"recipe": "recipe.json", "report": "report.json",
                    "outOfFold": "oof.json"}
            for key in ("recipe", "report", "outOfFold"):
                pins[key + "Sha256"] = sha256_file(base / pins[key])
            recipe = {"runs": {"speakerOnly": pins}}
            (base / "oof.json").write_text("[]\n")
            with self.assertRaisesRegex(ValueError, "Pinned speakerOnly outOfFold SHA-256"):
                load_inputs(recipe, base)

    def test_exact_row_order_fold_and_rating_pairing(self):
        speakers = {f"{speaker:04d}" for speaker in range(10)}
        assignment = outer_speaker_folds(speakers, 5, 20260923)
        rows = []
        for speaker in sorted(speakers):
            for clip in range(2):
                rows.append({"id": f"{int(speaker) * 2 + clip:09d}",
                             "speaker": speaker, "outerFold": assignment[speaker],
                             "fiveRaterCounts": [0, 0, 5],
                             "probabilities": {name: [.05, .05, .9] for name in METHODS}})
        digest = hashlib.sha256(("\n".join(sorted(row["id"] for row in rows)) + "\n")
                                .encode()).hexdigest()
        recipe = {"expectedClips": 20, "expectedSpeakers": 10,
                  "outerFolds": 5, "outerSeed": 20260923,
                  "selectedTrainIdsSha256": digest}
        loaded = {"speakerOnly": (rows, {}),
                  "speakerAndWordPurged": (copy.deepcopy(rows), {})}
        self.assertEqual(len(validate_rows(loaded, recipe)), 20)
        changed = copy.deepcopy(loaded)
        changed["speakerAndWordPurged"][0][0], changed["speakerAndWordPurged"][0][1] = (
            changed["speakerAndWordPurged"][0][1],
            changed["speakerAndWordPurged"][0][0])
        with self.assertRaisesRegex(ValueError, "ordering"):
            validate_rows(changed, recipe)
        changed = copy.deepcopy(loaded)
        changed["speakerAndWordPurged"][0][0]["fiveRaterCounts"] = [1, 0, 4]
        with self.assertRaisesRegex(ValueError, "ratings"):
            validate_rows(changed, recipe)
        changed = copy.deepcopy(loaded)
        changed["speakerAndWordPurged"][0][0]["outerFold"] = 4
        with self.assertRaisesRegex(ValueError, "fold"):
            validate_rows(changed, recipe)

    def test_whole_speaker_draws_keep_unequal_clip_clusters_together(self):
        scores = {"wav2vec2Combined": np.asarray([2., 2., 0.]),
                  "captureOnly": np.asarray([1., 1., 1.])}
        args = (scores, ["a", "a", "b"], [COMPARISONS[0]], 11, 1000, [2.5, 97.5])
        result, draws = speaker_bootstrap(*args)
        repeated, repeated_draws = speaker_bootstrap(*args)
        np.testing.assert_array_equal(draws, repeated_draws)
        self.assertEqual(result, repeated)
        differences = result["wav2vec2Combined minus captureOnly"]["replicateDifferences"]
        self.assertEqual(set(differences), {-1.0, 1.0 / 3.0, 1.0})

    def test_probability_simplex_and_saved_scores_are_replayed(self):
        rows = [{"outerFold": 0, "fiveRaterCounts": [0, 0, 5],
                 "probabilities": {name: [.05, .05, .9] for name in METHODS}},
                {"outerFold": 0, "fiveRaterCounts": [5, 0, 0],
                 "probabilities": {name: [.8, .1, .1] for name in METHODS}}]
        counts = np.asarray([row["fiveRaterCounts"] for row in rows])
        p = np.asarray([row["probabilities"]["captureOnly"] for row in rows])
        loss, brier = per_clip_scores(p, counts, 1e-12)
        metrics = {"perRaterLogLoss": float(loss.mean()),
                   "perRaterBrier": float(brier.mean())}
        report = {"pooledOutOfFold": {name: metrics for name in METHODS},
                  "folds": [{"fold": 0, "holdoutClips": 2,
                             "models": {name: {"metrics": metrics} for name in METHODS}}]}
        recipe = {"metrics": ["perRaterLogLoss", "perRaterBrier"],
                  "logLossEpsilon": 1e-12, "outerFolds": 1}
        scores, _ = score_run(rows, report, recipe)
        self.assertAlmostEqual(float(scores["perRaterBrier"]["captureOnly"].mean()),
                               metrics["perRaterBrier"])
        changed = copy.deepcopy(rows)
        changed[0]["probabilities"]["wavlmCombined"] = [.1, .1, .9]
        with self.assertRaisesRegex(ValueError, "Invalid probabilities"):
            score_run(changed, report, recipe)
        changed = copy.deepcopy(rows)
        changed[0]["probabilities"]["wavlmCombined"] = [.1, .1, .8]
        with self.assertRaisesRegex(ValueError, "differs from OOF"):
            score_run(changed, report, recipe)


if __name__ == "__main__":
    unittest.main()
