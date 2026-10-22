"""Synthetic masked-refit boundaries, candidate integrity and held-out replay."""
from copy import deepcopy
import contextlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import multiphone_scalar_variant_outer as outer
import multiphone_local_ablation as ablation
import multiphone_local_train as local
from test_multiphone_local_train import fixture, save


class ScalarVariantOuterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=local.HERE / "outputs", prefix="test-variant-outer-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.recipe = self.root / "ablation-recipe.json"
        self.patcher = patch.object(ablation, "RECIPE_PATH", self.recipe)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.study = self.build_study(self.root / "study")
        self.args = self.outer_args(self.study, "target-posterior")

    def build_study(self, directory, cohort=None):
        args = fixture(directory, cohort)
        binding = local.load_inputs(args.cohort, args.splits, args.features)[-1]
        save(self.recipe, {"training": ablation.TRAINING_RECIPE, "authorPartition": "train",
                           "binding": {key: binding[key] for key in
                                       ("cohortSha256", "splitsSha256", "featuresSha256", "scalarSha256")}})
        args.full_models = directory / "full"
        with contextlib.redirect_stdout(io.StringIO()):
            local.run_inner(SimpleNamespace(**{**vars(args), "output": args.full_models / "fold-0-inner"}))
            for variant in outer.VARIANTS:
                ablation.run_inner(SimpleNamespace(**{**vars(args), "variant": variant, "output": directory / variant}))
        return args

    def outer_args(self, study, variant):
        return SimpleNamespace(cohort=study.cohort, splits=study.splits, features=study.features, fold=0,
                               variant=variant, input=study.cohort.parent / variant,
                               output=study.cohort.parent / (variant + "-refit"))

    def evaluate_args(self, args=None):
        args = args or self.args
        return SimpleNamespace(**{**vars(args), "input": args.output,
                                  "output": args.output.parent / (args.variant + "-evaluation")})

    def test_both_variants_refit_without_holdout_prediction_with_exact_fit_moments(self):
        original = local.digest(self.study.features.parent / "scalars.npy")
        for variant in outer.VARIANTS:
            args = self.outer_args(self.study, variant)
            # Inner candidates legitimately replay; reject any call on holdout rows.
            original_predict = ablation.predict_ablation
            split = local.read_json(args.splits)["folds"][0]
            cohort = local.read_json(args.cohort)
            holdout_ids = {cohort["rows"][i]["id"] for i in split["outerHoldoutRows"]}
            def checked_predict(state, rows, *rest):
                self.assertTrue(holdout_ids.isdisjoint(row["id"] for row in rows))
                return original_predict(state, rows, *rest)
            with patch.object(ablation, "predict_ablation", side_effect=checked_predict):
                result = outer.run_refit(args)
            self.assertFalse(result["holdoutPredictionsComputed"])
            self.assertFalse((args.output / "predictions.json").exists())
            c, s, values, positions, _ = local.load_inputs(args.cohort, args.splits, args.features)
            state = local.read_json(args.output / "checkpoint.json")["state"]
            moments = outer.moments_for(c, s["folds"][0]["outerFitRows"], values, positions, variant)
            np.testing.assert_array_equal(state["head"]["featureMean"], moments[0])
            np.testing.assert_array_equal(state["head"]["featureScale"], moments[1])
            selected = local.read_json(args.input / "selection.json")["selected"]
            self.assertEqual(state["head"]["alpha"], selected["alpha"])
        self.assertEqual(original, local.digest(self.study.features.parent / "scalars.npy"))

    def test_both_variants_evaluate_only_outer_rows_and_replay_frozen_state(self):
        for variant in outer.VARIANTS:
            args = self.outer_args(self.study, variant)
            outer.run_refit(args)
            before = local.digest(args.output / "checkpoint.json")
            evaluation = self.evaluate_args(args)
            result = outer.run_evaluate(evaluation)
            c, s, values, positions, _ = local.load_inputs(args.cohort, args.splits, args.features)
            indices = s["folds"][0]["outerHoldoutRows"]
            self.assertEqual(result["evaluationRows"], indices)
            rows = [c["rows"][i] for i in indices]
            state = local.read_json(args.output / "checkpoint.json")["state"]
            p = ablation.predict_ablation(state, rows, values[[positions[i] for i in indices]], variant)
            self.assertEqual(local.read_json(evaluation.output / "predictions.json"),
                             {"rowIndices": indices, "probabilities": p.tolist()})
            self.assertEqual(result["evaluation"], outer.score_predictions(p, rows))
            self.assertEqual(before, local.digest(args.output / "checkpoint.json"))

    def test_changed_outer_labels_cannot_change_selected_alpha_or_fitted_state(self):
        outer.run_refit(self.args)
        before = local.read_json(self.args.output / "checkpoint.json")["state"]
        cohort = local.read_json(self.args.cohort)
        for i in local.read_json(self.args.splits)["folds"][0]["outerHoldoutRows"]:
            cohort["rows"][i]["raterCounts"] = [5, 0, 0]
        changed = self.build_study(self.root / "changed", cohort)
        args = self.outer_args(changed, self.args.variant)
        outer.run_refit(args)
        self.assertEqual(before, local.read_json(args.output / "checkpoint.json")["state"])

    def test_wrong_fold_variant_and_missing_candidate_fail_before_refit(self):
        for key, value in (("fold", 1), ("variant", "local-scalars"), ("variant", "utterance-context")):
            args = SimpleNamespace(**{**vars(self.args), key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                outer.run_refit(args)
            self.assertFalse(args.output.exists())
        path = self.args.input / "selection.json"
        report = local.read_json(path)
        report["trials"].pop()
        save(path, report)
        with self.assertRaisesRegex(ValueError, "Incomplete trial matrix"):
            outer.run_refit(self.args)

    def test_rehashed_loser_predictions_cannot_change_selected_checkpoint(self):
        path = self.args.input / "selection.json"
        report = local.read_json(path)
        trial = next(t for t in report["trials"] if t != report["selected"])
        prediction = self.args.input / trial["predictionsPath"]
        saved = local.read_json(prediction)
        rows = [local.read_json(self.args.cohort)["rows"][i] for i in saved["rowIndices"]]
        p = np.array([r["raterCounts"] for r in rows], dtype=float) / 5
        saved["probabilities"] = p.tolist()
        save(prediction, saved)
        trial["predictionsSha256"] = local.digest(prediction)
        trial["metrics"] = ablation.metrics_for(p, rows)
        report["selected"] = local.choose_trial(report["trials"])
        save(path, report)
        with self.assertRaisesRegex(ValueError, "exactly replay"):
            outer.run_refit(self.args)

    def test_frozen_mask_and_checkpoint_tampering_refused(self):
        outer.run_refit(self.args)
        checkpoint = self.args.output / "checkpoint.json"
        original = checkpoint.read_bytes()
        checkpoint.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "digest"):
            outer.run_evaluate(self.evaluate_args())
        checkpoint.write_bytes(original)
        value = local.read_json(checkpoint)
        value["mask"] = ablation.mask_for("local-scalars")
        save(checkpoint, value)
        frozen = local.read_json(self.args.output / "frozen.json")
        frozen["checkpointSha256"] = local.digest(checkpoint)
        save(self.args.output / "frozen.json", frozen)
        with self.assertRaisesRegex(ValueError, "design/mask"):
            outer.run_evaluate(self.evaluate_args())

    def test_mutation_during_refit_cannot_publish_completion(self):
        original = ablation.fit_ablation
        def changed(*args, **kwargs):
            state = original(*args, **kwargs)
            path = self.args.input / "selection.json"
            path.write_text(path.read_text() + " ")
            return state
        with patch.object(ablation, "fit_ablation", side_effect=changed), self.assertRaisesRegex(ValueError, "changed during"):
            outer.run_refit(self.args)
        self.assertFalse((self.args.output / "frozen.json").exists())

    def test_existing_destination_and_changed_source_prevent_holdout_prediction(self):
        outer.run_refit(self.args)
        args = self.evaluate_args()
        args.output.mkdir()
        with patch.object(ablation, "predict_ablation", side_effect=AssertionError("No holdout access")):
            with self.assertRaisesRegex(ValueError, "fresh directory"):
                outer.run_evaluate(args)
            with patch.object(outer, "source_hashes", return_value={"changed": "0" * 64}):
                with self.assertRaisesRegex(ValueError, "variant binding"):
                    outer.run_evaluate(args)


if __name__ == "__main__":
    unittest.main()
