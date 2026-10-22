"""Synthetic ablation invariance, provenance, age-support and exact replay tests."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_local_ablation as ablation
import multiphone_local_train as local
from test_multiphone_local_train import fixture, save


class LocalAblationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=local.HERE / "outputs", prefix="test-ablation-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.args = fixture(self.root)
        self.args.variant = "target-posterior"
        self.args.full_models = self.root / "full"
        self.recipe = self.root / "ablation-recipe.json"
        self.patcher = patch.object(ablation, "RECIPE_PATH", self.recipe)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        torch.set_num_threads(2)
        self.bind_recipe(self.args)

    def load(self, args=None):
        args = args or self.args
        return local.load_inputs(args.cohort, args.splits, args.features)

    def bind_recipe(self, args):
        evidence = self.load(args)[-1]
        save(self.recipe, {"training": ablation.TRAINING_RECIPE, "authorPartition": "train",
                           "binding": {key: evidence[key] for key in
                               ("cohortSha256", "splitsSha256", "featuresSha256", "scalarSha256")}})

    def full_model(self, args=None):
        args = args or self.args
        full_args = SimpleNamespace(**vars(args))
        full_args.output = args.full_models / f"fold-{args.fold}-inner"
        with contextlib.redirect_stdout(io.StringIO()):
            return local.run_inner(full_args)

    def run_model(self, args=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return ablation.run_inner(args or self.args)

    def test_declared_masks_zero_only_excluded_columns_without_mutating_source(self):
        values = np.arange(52, dtype=np.float32).reshape(4, 13)
        original = values.copy()
        self.assertEqual([len(names) for names in ablation.VARIANTS.values()], [1, 11, 2])
        self.assertEqual(ablation.mask_for("target-posterior")["retainedScalars"], ["targetMeanPosterior"])
        for variant in ablation.VARIANTS:
            with self.subTest(variant=variant):
                mask = np.asarray(ablation.mask_for(variant)["keepMask"])
                result = ablation.masked_copy(values, variant)
                np.testing.assert_array_equal(result[:, mask], values[:, mask])
                np.testing.assert_array_equal(result[:, ~mask], 0)
                self.assertFalse(np.shares_memory(values, result))
                np.testing.assert_array_equal(values, original)

    def test_fit_only_scaling_and_ablated_feature_invariance(self):
        cohort, splits, values, _, _ = self.load()
        fit_ids = splits["folds"][0]["innerFitRows"]
        val_ids = splits["folds"][0]["innerValidationRows"]
        rows, validation = [[cohort["rows"][i] for i in indices] for indices in (fit_ids, val_ids)]
        design = local.design_for(cohort)
        for variant in ablation.VARIANTS:
            with self.subTest(variant=variant):
                state, _ = ablation.fit_ablation(design, rows, values[fit_ids], .01, variant)
                matrix = local.transform(design, rows, ablation.masked_copy(values[fit_ids], variant))
                np.testing.assert_array_equal(state["head"]["featureMean"], matrix.mean(0))
                np.testing.assert_array_equal(state["head"]["featureScale"], np.where(matrix.std(0) < 1e-6, 1, matrix.std(0)))
                keep = np.asarray(ablation.mask_for(variant)["keepMask"])
                changed = np.array(values)
                changed[:, ~keep] = 1e8
                other, _ = ablation.fit_ablation(design, rows, changed[fit_ids], .01, variant)
                self.assertEqual(state, other)
                p = ablation.predict_ablation(state, validation, values[val_ids], variant)
                np.testing.assert_array_equal(p, ablation.predict_ablation(other, validation, changed[val_ids], variant))
                zero_columns = np.all(matrix == 0, axis=0)
                np.testing.assert_array_equal(np.asarray(state["head"]["featureMean"])[zero_columns], 0)
                np.testing.assert_array_equal(np.asarray(state["head"]["featureScale"])[zero_columns], 1)
                frozen = deepcopy(state)
                ablation.predict_ablation(state, validation, np.full((len(validation), 13), 1e9), variant)
                self.assertEqual(state, frozen)

    def test_all_variants_all_trials_and_checkpoint_replay(self):
        self.full_model()
        source_digest = local.digest(self.root / "scalars.npy")
        cohort, splits, _, _, _ = self.load()
        for variant in ablation.VARIANTS:
            with self.subTest(variant=variant):
                self.args.variant, self.args.output = variant, self.root / variant
                report = self.run_model()
                self.assertEqual(len(report["trials"]), 4)
                self.assertEqual(report["selected"], local.choose_trial(report["trials"]))
                self.assertFalse(report["outerOutcomesUsed"])
                for trial in report["trials"]:
                    replay = ablation.replay_checkpoint(self.args.output / trial["checkpointPath"],
                                                        self.args.cohort, self.args.splits, self.args.features)
                    self.assertEqual(replay, local.read_json(self.args.output / trial["predictionsPath"]))
                prior = local.read_json(self.args.output / "prior.json")
                self.assertEqual(prior["rowIndices"], splits["folds"][0]["innerValidationRows"])
                for phone, counts in prior["observedFitCounts"].items():
                    expected = np.asarray([cohort["rows"][i]["raterCounts"] for i in prior["fitRows"]
                                           if cohort["rows"][i]["targetPhone"] == phone]).sum(0)
                    np.testing.assert_array_equal(counts, expected)
                    np.testing.assert_array_equal(prior["state"]["phonePriors"][phone], (expected + 1)/(expected.sum() + 3))
                self.assertTrue(report["fullFeatureComparator"]["sameValidationRows"])
        self.assertEqual(local.digest(self.root / "scalars.npy"), source_digest)

    def test_outer_labels_cannot_change_inner_fit_selection_or_metrics(self):
        self.full_model()
        report = self.run_model()
        cohort, splits, _, _, _ = self.load()
        changed_cohort = deepcopy(cohort)
        for index in splits["folds"][0]["outerHoldoutRows"]:
            changed_cohort["rows"][index]["raterCounts"] = [5, 0, 0]
        changed = fixture(self.root / "changed-outer", changed_cohort)
        changed.variant, changed.full_models = self.args.variant, self.root / "changed-full"
        self.bind_recipe(changed)
        self.full_model(changed)
        other = self.run_model(changed)
        self.assertEqual(report["selected"]["alpha"], other["selected"]["alpha"])
        for first, second in zip(report["trials"], other["trials"], strict=True):
            self.assertEqual(first["metrics"], second["metrics"])
            first_state = local.read_json(self.args.output / first["checkpointPath"])["state"]
            second_state = local.read_json(changed.output / second["checkpointPath"])["state"]
            self.assertEqual(first_state, second_state)

    def test_partial_coverage_lineage_and_recipe_changes_refused_before_output(self):
        original = local.read_json(self.args.features)
        for key, value in (("fullCohortCoverage", False), ("failedRows", [0]),
                           ("manifestSha256", "0" * 64), ("authorTestInferencePerformed", True)):
            with self.subTest(key=key):
                metadata = deepcopy(original)
                metadata[key] = value
                save(self.args.features, metadata)
                with self.assertRaises(ValueError):
                    self.run_model()
                self.assertFalse(self.args.output.exists())
        save(self.args.features, original)
        recipe = local.read_json(self.recipe)
        recipe["binding"]["featuresSha256"] = "0" * 64
        save(self.recipe, recipe)
        with self.assertRaisesRegex(ValueError, "recipe/data binding"):
            self.run_model()

    def test_full_comparator_metric_or_selection_tampering_refused(self):
        self.full_model()
        path = self.args.full_models / "fold-0-inner/selection.json"
        original = local.read_json(path)
        changed = deepcopy(original)
        changed["trials"][0]["metrics"]["macroTargetLogLoss"] += .1
        save(path, changed)
        with self.assertRaisesRegex(ValueError, "comparator metrics"):
            self.run_model()
        changed = deepcopy(original)
        changed["selected"]["alpha"] = 999
        save(path, changed)
        with self.assertRaisesRegex(ValueError, "selection does not follow"):
            self.run_model()
        self.assertFalse(self.args.output.exists())

    def test_checkpoint_and_prediction_tampering_refused(self):
        self.full_model()
        report = self.run_model()
        trial = report["selected"]
        checkpoint = self.args.output / trial["checkpointPath"]
        original_checkpoint = checkpoint.read_bytes()
        saved = local.read_json(checkpoint)
        saved["state"]["head"]["intercept"][0] += .1
        save(checkpoint, saved)
        with self.assertRaisesRegex(ValueError, "Checkpoint digest"):
            ablation.replay_checkpoint(checkpoint, self.args.cohort, self.args.splits, self.args.features)
        checkpoint.write_bytes(original_checkpoint)
        predictions_path = self.args.output / trial["predictionsPath"]
        predictions = local.read_json(predictions_path)
        predictions["probabilities"][0] = [.1, .2, .7]
        save(predictions_path, predictions)
        with self.assertRaisesRegex(ValueError, "Prediction digest"):
            ablation.replay_checkpoint(checkpoint, self.args.cohort, self.args.splits, self.args.features)

    def test_rehashed_full_comparator_predictions_cannot_change_selection(self):
        self.full_model()
        directory = self.args.full_models / "fold-0-inner"
        report = local.read_json(directory / "selection.json")
        trial = next(item for item in report["trials"] if item["alpha"] != report["selected"]["alpha"])
        cohort, splits, _, _, _ = self.load()
        rows = [cohort["rows"][i] for i in splits["folds"][0]["innerValidationRows"]]
        predictions_path = directory / trial["predictionsPath"]
        saved = local.read_json(predictions_path)
        p = np.asarray([row["raterCounts"] for row in rows], dtype=float) / 5
        saved["probabilities"] = p.tolist()
        save(predictions_path, saved)
        trial["predictionsSha256"] = local.digest(predictions_path)
        trial["metrics"] = local.score_predictions(p, rows)
        report["selected"] = local.choose_trial(report["trials"])
        save(directory / "selection.json", report)
        with self.assertRaisesRegex(ValueError, "checkpoint/prediction binding"):
            self.run_model()
        self.assertFalse(self.args.output.exists())

    def test_age_metrics_preserve_undefined_support_and_all_age_selection(self):
        cohort, _, _, _, _ = self.load()
        rows = deepcopy(cohort["rows"][:4])
        for row, age in zip(rows, [6, 12, 13, 15]):
            row["age"], row["raterCounts"] = age, [0, 0, 5]
        p = np.tile([.1, .1, .8], (4, 1))
        metrics = ablation.metrics_for(p, rows)
        child = metrics["ageGroups"]["ages6to12"]
        self.assertEqual(child["positions"], 2)
        self.assertEqual(child["observedRaterCounts"], [0, 0, 10])
        self.assertIsNone(child["targetDiscrimination"]["macroTarget"]["rating0"]["auroc"])
        trials = [{"alpha": alpha, "metrics": {"macroTargetLogLoss": all_age,
                    "ageGroups": {"ages6to12": {"macroTargetLogLoss": child_nll}}}}
                  for alpha, all_age, child_nll in zip(ablation.TRAINING_RECIPE["l2Candidates"],
                                                      [.5, .4, .4, .6], [.1, .9, .9, .8])]
        self.assertEqual(local.choose_trial(trials)["alpha"], .01)


if __name__ == "__main__":
    unittest.main()
