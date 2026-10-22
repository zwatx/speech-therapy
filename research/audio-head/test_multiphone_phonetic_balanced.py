"""Synthetic weighted-objective correctness and fit-only/replay checks."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_phonetic_balanced as trainer
import test_multiphone_phonetic_head as fixtures
from test_multiphone_controls import synthetic_study
from test_multiphone_local_train import save


def observed_all_classes():
    cohort, splits = synthetic_study()
    for row in cohort["rows"]:
        n = row["clipIndex"] % 2
        row["raterCounts"] = [1 + n, 1, 3 - n]
    return cohort, splits


class BalancedPhoneticTests(unittest.TestCase):
    @contextmanager
    def study(self):
        fixture = fixtures.PhoneticHeadTests()
        with patch.object(fixtures, "synthetic_study", side_effect=observed_all_classes):
            fixture.setUp()
        try:
            fixture.bind()
            recipe = trainer.read_json(trainer.RECIPE)
            recipe.update(baselineRecipeSha256=trainer.digest(fixture.head_recipe_path),
                          featureBindingSha256=trainer.digest(fixture.binding_path))
            recipe_path = fixture.root / "weighted-recipe.json"
            save(recipe_path, recipe)
            with fixture.environment(), patch.object(trainer, "HERE", fixture.root), patch.object(trainer, "RECIPE", recipe_path):
                yield fixture
        finally:
            fixture.doCleanups()

    def args(self, fixture, regime="all-age", **updates):
        return fixture.args(family="target-scalars", regime=regime, **updates)

    def test_both_fit_populations_train_and_exactly_replay_corrected_predictions(self):
        with self.study() as fixture:
            binding_sha = trainer.digest(fixture.binding_path)
            for regime in ("all-age", "child-only"):
                args = self.args(fixture, regime)
                report = trainer.train(args)
                replay = trainer.replay(args.output)
                self.assertTrue(replay["exact"])
                self.assertEqual(replay["evaluation"], report["evaluation"])
                config = trainer.read_json(args.output / "config.json")
                expected = fixture.splits["folds"][0]["innerFitRows"]
                if regime == "child-only":
                    expected = [i for i in expected if 6 <= fixture.cohort["rows"][i]["age"] <= 12]
                self.assertEqual(config["fitRows"], expected)
                self.assertEqual(config["validationRows"], fixture.splits["folds"][0]["innerValidationRows"])
                self.assertFalse(config["outerOutcomesUsed"])
                self.assertFalse(config["empiricalCalibrationEstablished"])
            self.assertEqual(trainer.digest(fixture.binding_path), binding_sha)

    def test_actual_fit_counts_determine_weights_without_validation_or_older_child_fit_labels(self):
        with self.study() as fixture:
            args = self.args(fixture, "child-only")
            data = trainer.setup(args)
            counts = np.asarray([data["cohort"]["rows"][i]["raterCounts"] for i in data["fit"]]).sum(0)
            np.testing.assert_array_equal(data["classWeightState"]["observedRaterCounts"], counts)
            self.assertAlmostEqual(np.dot(counts / counts.sum(), data["classWeightState"]["weights"]), 1.)
            changed = deepcopy(data)
            for i, row in enumerate(changed["cohort"]["rows"]):
                if i not in data["fit"]:
                    row["raterCounts"] = [5, 0, 0]
            with patch.object(trainer.baseline, "setup", return_value=changed):
                second = trainer.setup(args)
            self.assertEqual(second["classWeightState"], data["classWeightState"])

    def test_global_weight_correction_recovers_population_optimum_without_row_renormalization(self):
        q = torch.tensor([[.1, .2, .7]], dtype=torch.float64)
        weights = torch.tensor([3., 2., 1.], dtype=torch.float64)
        logits = (q * weights).log()
        torch.testing.assert_close(trainer.corrected_probabilities(logits, weights), q, atol=1e-15, rtol=1e-15)
        loss = trainer.weighted_loss(torch.zeros_like(logits), q, weights)
        self.assertAlmostEqual(loss.item(), 1.4 * np.log(3))

    def test_absent_fit_rating_class_is_rejected_without_pseudolabels(self):
        with self.study() as fixture:
            args = self.args(fixture)
            data = trainer.baseline.setup(args)
            for i in data["fit"]:
                data["cohort"]["rows"][i]["raterCounts"] = [0, 0, 5]
            with patch.object(trainer.baseline, "setup", return_value=data):
                with self.assertRaisesRegex(ValueError, "every class"):
                    trainer.setup(args)

    def test_rehashed_wrong_class_state_or_predictions_rejected(self):
        with self.study() as fixture:
            args = self.args(fixture)
            trainer.train(args)
            path = args.output / "predictions.json"
            value = trainer.read_json(path)
            value["probabilities"] = [[.1, .2, .7]] * len(value["rowIndices"])
            save(path, value)
            report = trainer.read_json(args.output / "report.json")
            report["predictionsSha256"] = trainer.digest(path)
            save(args.output / "report.json", report)
            with self.assertRaisesRegex(ValueError, "replay is not exact"):
                trainer.replay(args.output)

    def test_configuration_mutation_before_publication_rejected(self):
        with self.study() as fixture:
            args = self.args(fixture)
            original = trainer.evaluate

            def mutate(*values, **keywords):
                result = original(*values, **keywords)
                path = args.output / "config.json"
                path.write_text(path.read_text() + " ")
                return result

            with patch.object(trainer, "evaluate", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "Immutable run configuration"):
                    trainer.train(args)
            self.assertFalse((args.output / "report.json").exists())

    def test_undeclared_feature_family_rejected(self):
        with self.study() as fixture:
            args = self.args(fixture)
            args.family = "global-scalars"
            with self.assertRaisesRegex(ValueError, "fixed weighted-objective"):
                trainer.setup(args)


if __name__ == "__main__":
    unittest.main()
