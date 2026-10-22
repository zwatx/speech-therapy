"""Exact metric examples and synthetic artifact tampering checks."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

import multiphone_verify as verify


class WeightedMetricTests(unittest.TestCase):
    def test_weighted_auc_and_ap_have_exact_tie_aware_values(self):
        value = verify.weighted_binary_metrics([0.8, 0.2], [2, 1], [0, 2])
        self.assertAlmostEqual(value["auroc"], 5 / 6)
        self.assertAlmostEqual(value["averagePrecision"], 13 / 15)
        self.assertAlmostEqual(value["prevalence"], 3 / 5)
        tied = verify.weighted_binary_metrics([0.4, 0.4], [2, 1], [0, 2])
        self.assertEqual(tied["auroc"], 0.5)
        self.assertEqual(tied["averagePrecision"], 0.6)

    def test_auc_matches_expanded_individual_rater_pairs(self):
        scores = np.array([0.3, 0.1, 0.3, 0.9])
        positive, negative = np.array([2, 0, 1, 3]), np.array([3, 5, 4, 2])
        a, b = np.repeat(scores, positive), np.repeat(scores, negative)
        expected = np.mean((a[:, None] > b).astype(float) + 0.5 * (a[:, None] == b))
        value = verify.weighted_binary_metrics(scores, positive, negative)
        self.assertAlmostEqual(value["auroc"], expected)
        order = [2, 3, 0, 1]
        reordered = verify.weighted_binary_metrics(scores[order], positive[order], negative[order])
        self.assertEqual(value, reordered)

    def test_absent_class_is_explicitly_undefined(self):
        no_positive = verify.weighted_binary_metrics([0.2, 0.7], [0, 0], [5, 5])
        self.assertIsNone(no_positive["auroc"])
        self.assertIsNone(no_positive["averagePrecision"])
        self.assertEqual(no_positive["prevalence"], 0)
        all_positive = verify.weighted_binary_metrics([0.2, 0.7], [5, 5], [0, 0])
        self.assertIsNone(all_positive["auroc"])
        self.assertEqual(all_positive["averagePrecision"], 1)

    def test_class_nll_and_recall_use_counts_without_majority_relabeling(self):
        p = np.array([[0.6, 0.2, 0.2], [0.1, 0.8, 0.1]])
        c = np.array([[3, 0, 2], [0, 5, 0]])
        value = verify.discrimination(p, c)
        self.assertAlmostEqual(value["classes"]["0"]["conditionalNLL"], -math.log(0.6))
        self.assertAlmostEqual(value["classes"]["1"]["conditionalNLL"], -math.log(0.8))
        self.assertAlmostEqual(value["classes"]["2"]["conditionalNLL"], -math.log(0.2))
        self.assertEqual([value["classes"][str(i)]["argmaxRecall"] for i in range(3)], [1, 1, 0])
        self.assertAlmostEqual(value["balancedArgmaxRecall"], 2 / 3)
        expected = -(3 * math.log(0.6) + 2 * math.log(0.2) + 5 * math.log(0.8)) / 10
        self.assertAlmostEqual(value["perRaterLogLoss"], expected)
        self.assertEqual(value["ratingBelow2"]["positiveRaterWeight"], 8)

    def test_row_weights_match_explicit_replication(self):
        p = np.array([[0.8, 0.1, 0.1], [0.2, 0.2, 0.6], [0.1, 0.2, 0.7]])
        c = np.array([[3, 1, 1], [0, 2, 3], [1, 0, 4]])
        weighted = verify.discrimination(p, c, [2, 0, 1])
        repeated = verify.discrimination(p[[0, 0, 2]], c[[0, 0, 2]])
        for key, value in verify.scalar_metrics(weighted).items():
            self.assertAlmostEqual(value, verify.scalar_metrics(repeated)[key])

    def test_speaker_bootstrap_is_deterministic_and_paired(self):
        p = np.array([[0.8, 0.1, 0.1]] * 2 + [[0.1, 0.1, 0.8]] * 2)
        c = np.array([[5, 0, 0]] * 2 + [[0, 0, 5]] * 2)
        speakers = ["a", "a", "b", "b"]
        result = verify.clustered_bootstrap(p, c, speakers, replicates=80, seed=7, reference=p, phones=["B"] * 4)
        repeated = verify.clustered_bootstrap(p, c, speakers, replicates=80, seed=7, reference=p, phones=["B"] * 4)
        self.assertEqual(result, repeated)
        self.assertEqual(result["speakers"], 2)
        self.assertEqual(result["model"]["class0.prevalence"]["percentile95"], [0, 1])
        self.assertLess(result["model"]["rating0.auroc"]["validReplicates"], 80)
        self.assertIn("macroTarget.rating0.auroc", result["model"])
        for row in result["pairedModelMinusPrior"].values():
            if row["validReplicates"]:
                self.assertEqual(row["percentile95"], [0, 0])

    def test_macro_phone_ranking_separates_phone_prevalence_from_within_phone_signal(self):
        p = np.array([[0.8, 0.1, 0.1]] * 2 + [[0.2, 0.1, 0.7]] * 2 + [[0.01, 0.01, 0.98]])
        c = np.array([[4, 0, 1]] * 2 + [[1, 0, 4]] * 2 + [[0, 0, 5]])
        phones = ["A", "A", "B", "B", "C"]
        pooled = verify.discrimination(p, c)
        result = verify.target_discrimination(p, c, phones)
        self.assertGreater(pooled["rating0"]["auroc"], 0.5)
        macro = result["macroTarget"]["rating0"]
        self.assertEqual(macro["auroc"], 0.5)
        self.assertEqual(macro["averagePrecision"], 0.5)
        self.assertEqual(macro["definedTargets"], 2)
        self.assertEqual(macro["undefinedTargets"], 1)
        self.assertEqual(macro["excludedPhones"], ["C"])
        absent = verify.target_discrimination(p, c, phones, [0, 0, 1, 1, 1])
        self.assertEqual(absent["macroTarget"]["rating0"]["excludedPhones"], ["A", "C"])

    def test_invalid_probability_count_and_weight_inputs_fail(self):
        for p, c in (([[0.4, 0.4, 0.4]], [[0, 0, 5]]),
                     ([[0.2, 0.2, 0.6]], [[-1, 0, 6]]),
                     ([[0.2, 0.2, 0.6]], [[0.5, 0.5, 4]]),
                     ([[float("nan"), 0, 1]], [[0, 0, 5]])):
            with self.assertRaises(ValueError):
                verify.discrimination(p, c)
        with self.assertRaises(ValueError):
            verify.discrimination([[0.2, 0.2, 0.6]], [[0, 0, 5]], [0])
        with self.assertRaises(ValueError):
            verify.clustered_bootstrap([[0.2, 0.2, 0.6]], [[0, 0, 5]], ["one"], replicates=2)


class ArtifactVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cadence-verify-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.recipe = verify.load_recipe()
        self.expected = next(verify.matrix_runs(self.recipe))
        self.config = {key: self.expected[key] for key in ("head", "fold", "seed", "lr")}
        self.config.update({
            "phase": "inner", "device": "cpu", "hidden": 128, "dropout": 0.1,
            "weight_decay": 0.01, "batch_size": 16, "epochs": 100, "patience": 15,
            "threads": 4, "cohortSha256": self.recipe["cohortSha256"],
            "splitsSha256": self.recipe["splitsSha256"], "cacheIndexSha256": "cache-index-pin",
            "sourceSha256": copy.deepcopy(verify.SOURCE_SHA256), "authorPartition": "train",
            "clinicalUseEligible": False, "learnerFeedbackEligible": False,
            "cohort": str(self.base / "cohort.json"), "splits": str(self.base / "splits.json"),
            "cache": str(self.base / "wav2vec-frames"), "output": str(self.base / self.expected["name"]),
        })

    def check(self, config):
        verify.verify_config(config, self.expected, self.recipe, self.base, "cache-index-pin")

    def test_recipe_hash_is_fixed_not_recomputed_as_expectation(self):
        path = self.base / "recipe.json"
        path.write_bytes(verify.RECIPE.read_bytes())
        self.assertEqual(verify.load_recipe(path), self.recipe)
        path.write_text(path.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "recipe changed"):
            verify.load_recipe(path)

    def test_expected_matrix_has_120_unique_inner_runs(self):
        expected = list(verify.matrix_runs(self.recipe))
        self.assertEqual(len(expected), 120)
        self.assertEqual(len({row["name"] for row in expected}), 120)
        self.assertTrue(all(row["name"].startswith("inner-") for row in expected))

    def test_changed_settings_cache_paths_or_sources_are_rejected(self):
        self.check(self.config)
        mutations = {"hidden": 64, "dropout": 0.2, "weight_decay": 0.02,
                     "batch_size": 8, "epochs": 99, "patience": 14, "phase": "outer",
                     "cacheIndexSha256": "changed", "threads": 2, "clinicalUseEligible": True,
                     "cohortSha256": "changed", "cache": str(self.base / "wavlm-frames")}
        for key, value in mutations.items():
            changed = copy.deepcopy(self.config)
            changed[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.check(changed)
        changed = copy.deepcopy(self.config)
        changed["sourceSha256"]["multiphone_models.py"] = "changed"
        with self.assertRaises(ValueError):
            self.check(changed)

    def test_thread_exception_is_limited_to_first_recorded_run(self):
        expected = dict(self.expected, name="inner-wav2vec-mean-f0-s7-lr0003", lr=0.0003)
        config = dict(self.config, lr=0.0003, output=str(self.base / expected["name"]), threads=2)
        verify.verify_config(config, expected, self.recipe, self.base, "cache-index-pin")
        config["threads"] = 4
        with self.assertRaises(ValueError):
            verify.verify_config(config, expected, self.recipe, self.base, "cache-index-pin")

    def test_checkpoint_tampering_and_internal_linkage_are_rejected(self):
        run = self.base / "run"
        run.mkdir()
        (run / "config.json").write_text(json.dumps(self.config))
        saved = {"configSha256": verify.digest(run / "config.json"), "epoch": 1, "bestEpoch": 1,
                 "model": {"weight": torch.ones(2)}, "mean": torch.zeros(768), "std": torch.ones(768)}
        torch.save(saved, run / "best.pt")
        report = {"configSha256": saved["configSha256"], "checkpointSha256": verify.digest(run / "best.pt"),
                  "bestEpoch": 1}
        verify.checked_checkpoint(run, report)
        saved["epoch"] = 2
        torch.save(saved, run / "best.pt")
        with self.assertRaisesRegex(ValueError, "digest"):
            verify.checked_checkpoint(run, report)
        report["checkpointSha256"] = verify.digest(run / "best.pt")
        with self.assertRaisesRegex(ValueError, "linkage"):
            verify.checked_checkpoint(run, report)

    def test_inner_best_epoch_and_stopping_are_reconstructed(self):
        recipe = dict(self.recipe, patienceEpochs=2)
        history = [{"epoch": i, "trainPerRaterLogLoss": 0.1,
                    "validation": {"macroTargetLogLoss": loss}}
                   for i, loss in enumerate([0.4, 0.3, 0.35, 0.4], 1)]
        report = {"epochsRun": 4, "bestEpoch": 2, "evaluation": {"macroTargetLogLoss": 0.3}}
        self.assertEqual(verify.verify_history(history, report, recipe), (2, 0.3))
        with self.assertRaises(ValueError):
            verify.verify_history(history, dict(report, bestEpoch=4), recipe)
        with self.assertRaises(ValueError):
            verify.verify_history(history[:2], dict(report, epochsRun=2), recipe)

    def test_prediction_rows_and_reported_loss_are_checked(self):
        rows = [{"trainingEligible": True, "raterCounts": [0, 0, 5], "targetPhone": "B"},
                {"trainingEligible": True, "raterCounts": [5, 0, 0], "targetPhone": "P"}]
        prediction = {"rowIndices": [0, 1], "probabilities": [[0.1, 0.1, 0.8], [0.8, 0.1, 0.1]]}
        evaluation = {"perRaterLogLoss": -math.log(0.8), "macroTargetLogLoss": -math.log(0.8)}
        verify.checked_predictions(prediction, [1, 0], rows, evaluation)
        changed = dict(prediction, rowIndices=[1, 0])
        with self.assertRaises(ValueError):
            verify.checked_predictions(changed, [0, 1], rows, evaluation)
        changed = dict(prediction, probabilities=[[0.1, 0.1, 0.8], [0.1, 0.1, 0.8]])
        with self.assertRaisesRegex(ValueError, "proper scores"):
            verify.checked_predictions(changed, [0, 1], rows, evaluation)

    def test_supplied_prior_must_reconstruct_from_exact_inner_fit_counts(self):
        directory = self.base / "controls" / "fold-0-inner"
        directory.mkdir(parents=True)
        rows = [{"targetPhone": "B", "raterCounts": [5, 0, 0]},
                {"targetPhone": "P", "raterCounts": [0, 0, 5]},
                {"targetPhone": "B", "raterCounts": [0, 0, 5]},
                {"targetPhone": "P", "raterCounts": [5, 0, 0]}]
        fold = {"innerFitRows": [0, 1], "innerValidationRows": [2, 3]}
        config = {"phase": "inner", "fold": 0, "fitRows": [0, 1], "validationRows": [2, 3],
                  "binding": {key: self.recipe[key] for key in ("cohortSha256", "splitsSha256")}}
        (directory / "config.json").write_text(json.dumps(config))
        state = {"family": "prior", "priorPseudocountPerClass": 1.0,
                 "phonePriors": {"B": [0.75, 0.125, 0.125], "P": [0.125, 0.125, 0.75]}}

        def save_prior():
            (directory / "prior.json").write_text(json.dumps(state))
            selection = {"configSha256": verify.digest(directory / "config.json"), "outerOutcomesUsed": False,
                         "selected": {"prior": {"statePath": "prior.json",
                                                "stateSha256": verify.digest(directory / "prior.json")}}}
            (directory / "selection.json").write_text(json.dumps(selection))

        save_prior()
        p, _ = verify.supplied_prior(directory.parent, 0, {"rows": rows}, {"folds": [fold]}, self.recipe)
        np.testing.assert_array_equal(p, [state["phonePriors"]["B"], state["phonePriors"]["P"]])
        # Re-signing the changed artifact cannot hide that it used different counts.
        state["phonePriors"]["B"] = [0.125, 0.125, 0.75]
        save_prior()
        with self.assertRaisesRegex(ValueError, "inner-fit count"):
            verify.supplied_prior(directory.parent, 0, {"rows": rows}, {"folds": [fold]}, self.recipe)


if __name__ == "__main__":
    torch.set_num_threads(2)
    unittest.main()
