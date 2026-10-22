"""Synthetic split isolation, fixed-budget refits and artifact replay checks."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_head_outer as outer
from test_multiphone_local_head import LocalHeadTests as LocalFixture
from test_multiphone_phonetic_head import PhoneticHeadTests as PhoneticFixture
from test_multiphone_local_train import save


class OuterHeadTests(unittest.TestCase):
    @contextmanager
    def study(self, kind="local", regime="all-age"):
        fixture = (LocalFixture if kind == "local" else PhoneticFixture)()
        fixture.setUp()
        try:
            for name in outer.SOURCES:
                (fixture.root / name).write_bytes((outer.HERE / name).read_bytes())
            if kind == "phonetic":
                fixture.bind()
            with fixture.environment(), patch.object(outer, "HERE", fixture.root):
                trainer = outer.TRAINERS[kind]
                candidates = []
                for lr in (.001, .0003):
                    output = fixture.root / "outputs" / f"inner-{lr}"
                    args = fixture.args(regime=regime, output=output, lr=lr)
                    trainer.train(args)
                    candidates.append(output)
                yield fixture, SimpleNamespace(kind=kind, candidates=candidates,
                                               output=fixture.root / "outputs/refit")
        finally:
            fixture.doCleanups()

    def test_both_kinds_and_age_regimes_refit_then_separately_evaluate(self):
        for kind in ("local", "phonetic"):
            for regime in ("all-age", "child-only"):
                with self.subTest(kind=kind, regime=regime), self.study(kind, regime) as (fixture, args):
                    fit_impl = outer.fit_epochs

                    def no_prediction_fit(*values, **keywords):
                        with patch.object(outer.local, "evaluate", side_effect=AssertionError("refit evaluated")):
                            return fit_impl(*values, **keywords)

                    with patch.object(outer, "fit_epochs", side_effect=no_prediction_fit):
                        frozen = outer.run_refit(args)
                    self.assertFalse(frozen["holdoutPredictionsComputed"])
                    self.assertFalse((args.output / "predictions.json").exists())
                    config = outer.read_json(args.output / "config.json")
                    self.assertEqual(frozen["epochsRun"], config["selected"]["epochs"])
                    expected = fixture.splits["folds"][0]["outerFitRows"]
                    if regime == "child-only":
                        expected = [i for i in expected if outer.is_child(fixture.cohort["rows"][i])]
                    self.assertEqual(config["fitRows"], expected)
                    destination = fixture.root / "outputs/evaluation"
                    result = outer.run_evaluate(SimpleNamespace(input=args.output, output=destination))
                    self.assertTrue(result["complete"])
                    predictions = outer.read_json(destination / "predictions.json")
                    self.assertEqual(predictions["rowIndices"], fixture.splits["folds"][0]["outerHoldoutRows"])
                    # Re-evaluating an immutable refit in a new destination is exact.
                    repeated = fixture.root / "outputs/evaluation-repeat"
                    outer.run_evaluate(SimpleNamespace(input=args.output, output=repeated))
                    self.assertEqual(predictions, outer.read_json(repeated / "predictions.json"))

    def test_holdout_values_and_labels_cannot_change_refit(self):
        with self.study(regime="child-only") as (fixture, args):
            _, _, _, original, data = outer.checked_candidates("local", args.candidates)
            first = outer.outer_data("local", original, data)
            changed = deepcopy(data)
            changed["values"] = np.array(data["values"], copy=True)
            for i in first["holdout"]:
                changed["values"][changed["positions"][i]] = 1e12
                changed["cohort"]["rows"][i]["raterCounts"] = [5, 0, 0]
            second = outer.outer_data("local", original, changed)
            self.assertTrue(torch.equal(first["mean"], second["mean"]))
            self.assertTrue(torch.equal(first["std"], second["std"]))
            self.assertEqual(first["priors"], second["priors"])
            left, left_history = outer.fit_epochs(original, first, 2)
            right, right_history = outer.fit_epochs(original, second, 2)
            self.assertEqual(left_history, right_history)
            for key, value in left.state_dict().items():
                self.assertTrue(torch.equal(value, right.state_dict()[key]))

    def test_rehashed_wrong_inner_predictions_rejected_before_refit(self):
        with self.study() as (_, args):
            directory = args.candidates[0]
            predictions = outer.read_json(directory / "predictions.json")
            predictions["probabilities"] = [[.2, .3, .5]] * len(predictions["rowIndices"])
            save(directory / "predictions.json", predictions)
            report = outer.read_json(directory / "report.json")
            report["predictionsSha256"] = outer.digest(directory / "predictions.json")
            save(directory / "report.json", report)
            with self.assertRaisesRegex(ValueError, "replay is not exact"):
                outer.run_refit(args)
            self.assertFalse(args.output.exists())

    def test_rehashed_wrong_stopping_history_rejected(self):
        with self.study() as (_, args):
            directory = args.candidates[0]
            history = outer.read_json(directory / "history.json")
            history[0]["epoch"] = 20
            save(directory / "history.json", history)
            report = outer.read_json(directory / "report.json")
            report["historySha256"] = outer.digest(directory / "history.json")
            save(directory / "report.json", report)
            with self.assertRaisesRegex(ValueError, "stopping rule"):
                outer.run_refit(args)

    def test_missing_lr_comparison_rejected(self):
        with self.study() as (_, args):
            args.candidates[1] = args.candidates[0]
            with self.assertRaisesRegex(ValueError, "two distinct"):
                outer.run_refit(args)

    def test_speaker_overlap_and_incorrect_nesting_rejected(self):
        with self.study("phonetic") as (_, args):
            _, _, _, original, data = outer.checked_candidates(args.kind, args.candidates)
            changed = deepcopy(data)
            fold = changed["splits"]["folds"][0]
            fold["outerHoldoutRows"].append(fold["outerFitRows"][0])
            with self.assertRaisesRegex(ValueError, "partition or inner nesting"):
                outer.outer_data(args.kind, original, changed)

    def test_existing_destination_refused_before_holdout_prediction(self):
        with self.study() as (fixture, args):
            outer.run_refit(args)
            destination = fixture.root / "outputs/already-exists"
            destination.mkdir()
            with patch.object(outer.local, "evaluate", side_effect=AssertionError("evaluated")):
                with self.assertRaisesRegex(ValueError, "fresh directory"):
                    outer.run_evaluate(SimpleNamespace(input=args.output, output=destination))

    def test_checkpoint_and_source_tampering_rejected(self):
        with self.study() as (fixture, args):
            outer.run_refit(args)
            checkpoint = args.output / "checkpoint.pt"
            original = checkpoint.read_bytes()
            checkpoint.write_bytes(original + b"changed")
            evaluation = SimpleNamespace(input=args.output, output=fixture.root / "outputs/evaluation")
            with self.assertRaisesRegex(ValueError, "Frozen refit differs"):
                outer.run_evaluate(evaluation)
            checkpoint.write_bytes(original)
            (fixture.root / "multiphone_head_outer.py").write_text("changed")
            with self.assertRaisesRegex(ValueError, "Pinned source"):
                outer.run_evaluate(evaluation)

    def test_mid_evaluation_frozen_input_mutation_rejected(self):
        with self.study() as (fixture, args):
            outer.run_refit(args)
            original_evaluate = outer.local.evaluate

            def mutate_after_prediction(*values, **keywords):
                result = original_evaluate(*values, **keywords)
                path = args.output / "history.json"
                path.write_text(path.read_text() + " ")
                return result

            destination = fixture.root / "outputs/evaluation"
            with patch.object(outer.local, "evaluate", side_effect=mutate_after_prediction):
                with self.assertRaisesRegex(ValueError, "Pinned source or inner artifacts"):
                    outer.run_evaluate(SimpleNamespace(input=args.output, output=destination))
            self.assertFalse((destination / "report.json").exists())

    def test_recipe_mutation_during_refit_rejected(self):
        with self.study() as (fixture, args):
            original_fit = outer.fit_epochs

            def mutate_after_fit(*values, **keywords):
                result = original_fit(*values, **keywords)
                fixture.recipe_path.write_text(fixture.recipe_path.read_text() + " ")
                return result

            with patch.object(outer, "fit_epochs", side_effect=mutate_after_fit):
                with self.assertRaisesRegex(ValueError, "Pinned source or inner artifacts"):
                    outer.run_refit(args)
            self.assertFalse((args.output / "frozen.json").exists())


if __name__ == "__main__":
    unittest.main()
