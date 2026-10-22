"""Synthetic global refit boundaries; no corpus encoder or holdout inference."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

from encoders import WavLMEncoder
import multiphone_global_outer as outer
import multiphone_train as trainer
import multiphone_verify as verify
import test_multiphone_train as fixtures


class GlobalOuterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.TrainingTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        for name in outer.SOURCES:
            (self.root / name).write_bytes((outer.HERE / name).read_bytes())
        self.fixture.cache.rename(self.root / "wavlm-frames")
        self.fixture.cache = self.root / "wavlm-frames"
        self.recipe = self.root / "recipe.json"
        self.original_recipe = outer.read_json(outer.RECIPE)
        self.patchers = [patch.object(outer, "HERE", self.root), patch.object(outer, "RECIPE", self.recipe)]
        for item in self.patchers:
            item.start()
            self.addCleanup(item.stop)
        self.prepare()
        self.args = SimpleNamespace(candidates=self.candidates, output=self.root / "outputs/refit")

    def prepare(self):
        fixture = self.fixture
        fixture.persist_sources()
        fixture.build_cache()
        config = outer.read_json(fixture.cache / "config.json")
        config.update(encoder=WavLMEncoder.identity, sourceSha256=verify.CACHE_SOURCE_SHA256,
                      dtype="float32", device="mps", authorPartition="train")
        outer.atomic_json(fixture.cache / "config.json", config)
        index = outer.read_json(fixture.cache / "index.json")
        index["configSha256"] = outer.digest(fixture.cache / "config.json")
        index["clipCount"] = len(fixture.cohort["clips"])
        for clip in fixture.cohort["clips"]:
            entry = index["entries"][clip["id"]]
            path = fixture.cache / entry["path"]
            with np.load(path) as saved:
                frames = saved["frames"].copy()
            np.savez(path, frames=frames, audio_sha256=clip["audioSha256"], config_sha256=index["configSha256"])
            entry.update(sha256=outer.digest(path), frames=len(frames), audioSha256=clip["audioSha256"])
        outer.atomic_json(fixture.cache / "index.json", index)
        recipe = {**self.original_recipe, "cohortSha256": outer.digest(fixture.cohort_path),
                  "splitsSha256": outer.digest(fixture.splits_path), "hiddenWidth": 8,
                  "dropout": 0., "maximumEpochs": 4, "patienceEpochs": 2, "batchSizeClips": 2}
        outer.atomic_json(self.recipe, recipe)
        if hasattr(self, "recipe_patch"):
            self.recipe_patch.stop()
        self.recipe_patch = patch.object(verify, "RECIPE_SHA256", outer.digest(self.recipe))
        self.recipe_patch.start()
        self.addCleanup(self.recipe_patch.stop)
        self.candidates = []
        for rate, suffix in ((.001, "001"), (.0003, "0003")):
            args = fixture.args()
            args.lr = rate
            args.output = self.root / f"inner-wavlm-mean-f0-s7-lr{suffix}"
            # Fixture training confines outputs beneath its own outputs directory.
            temporary = self.root / "outputs" / f"inner-{suffix}"
            args.output = temporary
            fixture.run_training(args)
            destination = self.root / f"inner-wavlm-mean-f0-s7-lr{suffix}"
            temporary.rename(destination)
            self.rebind_output(destination)
            self.candidates.append(destination)

    def rebind_output(self, directory):
        config = outer.read_json(directory / "config.json")
        config["output"] = str(directory)
        outer.atomic_json(directory / "config.json", config)
        checkpoint = torch.load(directory / "best.pt", weights_only=True)
        checkpoint["configSha256"] = outer.digest(directory / "config.json")
        trainer.save_checkpoint(directory / "best.pt", checkpoint)
        report = outer.read_json(directory / "report.json")
        report.update(configSha256=outer.digest(directory / "config.json"), checkpointSha256=outer.digest(directory / "best.pt"))
        outer.atomic_json(directory / "report.json", report)

    def evaluate_args(self):
        return SimpleNamespace(input=self.args.output, output=self.root / "outputs/evaluation")

    def test_both_candidates_replay_and_fixed_refit_never_loads_or_predicts_holdout(self):
        real_init, real_evaluate = trainer.StudyData.__init__, trainer.evaluate
        requested = []
        def init(data, cohort, cache, indices):
            requested.extend(indices)
            self.assertTrue(set(indices).isdisjoint(self.fixture.fold["outerHoldoutRows"]))
            real_init(data, cohort, cache, indices)
        def evaluate(model, data, indices, *rest):
            self.assertEqual(indices, self.fixture.fold["innerValidationRows"])
            return real_evaluate(model, data, indices, *rest)
        with patch.object(trainer.StudyData, "__init__", init), patch.object(trainer, "evaluate", side_effect=evaluate) as evaluated:
            result = outer.run_refit(self.args)
        self.assertEqual(evaluated.call_count, 2)
        self.assertFalse(result["holdoutPredictionsComputed"])
        self.assertFalse((self.args.output / "predictions.json").exists())
        config = outer.read_json(self.args.output / "config.json")
        choice = min(config["trials"], key=lambda x: (x["loss"], x["lr"], x["epochs"]))
        self.assertEqual(config["selected"], choice)
        self.assertEqual(result["epochsRun"], choice["epochs"])
        args = outer.original_args(outer.read_json(Path(choice["directory"]) / "config.json"))
        data, fold, mean, std, _ = outer.outer_data(args, outer.read_json(self.recipe))
        saved = torch.load(self.args.output / "checkpoint.pt", weights_only=True)
        self.assertTrue(torch.equal(saved["mean"], mean))
        self.assertTrue(torch.equal(saved["std"], std))
        # A fresh repeat starts from the same seed, not from an inner checkpoint.
        repeated, _ = outer.fit_epochs(args, data, fold["outerFitRows"], mean, std, choice["epochs"], lambda _: None)
        self.assertTrue(all(torch.equal(saved["model"][k], v) for k, v in repeated.state_dict().items()))

    def test_evaluation_exact_replay_same_fit_prior_and_row_coverage(self):
        outer.run_refit(self.args)
        before = outer.digest(self.args.output / "checkpoint.pt")
        args = self.evaluate_args()
        report = outer.run_evaluate(args)
        saved = torch.load(self.args.output / "checkpoint.pt", weights_only=True)
        config = outer.read_json(self.args.output / "config.json")
        original = outer.original_args(outer.read_json(Path(config["innerConfigPath"])))
        data, fold, mean, std, prior = outer.outer_data(original, outer.read_json(self.recipe), True)
        model = trainer.HEADS["mean"](hidden_dim=original.hidden, dropout=original.dropout)
        model.load_state_dict(saved["model"])
        _, predictions = trainer.evaluate(model, data, fold["outerHoldoutRows"], mean, std, "cpu", original.batch_size)
        self.assertEqual(predictions, outer.read_json(args.output / "predictions.json"))
        self.assertEqual(report["evaluationRows"], sorted(fold["outerHoldoutRows"]))
        expected = [prior[data.rows[i]["targetPhone"]]["probabilities"] for i in predictions["rowIndices"]]
        self.assertEqual(expected, outer.read_json(args.output / "prior.json")["probabilities"])
        self.assertEqual(before, outer.digest(self.args.output / "checkpoint.pt"))

    def test_rehashed_loser_prediction_cannot_change_selection(self):
        reports = [outer.read_json(p / "report.json") for p in self.candidates]
        loser = self.candidates[int(reports[1]["evaluation"]["macroTargetLogLoss"] >= reports[0]["evaluation"]["macroTargetLogLoss"])]
        saved = outer.read_json(loser / "predictions.json")
        saved["probabilities"][0] = [1., 0., 0.]
        outer.atomic_json(loser / "predictions.json", saved)
        with self.assertRaisesRegex(ValueError, "exactly replay"):
            outer.run_refit(self.args)
        self.assertFalse(self.args.output.exists())

    def test_rehashed_fit_moments_and_incomplete_history_rejected(self):
        directory = self.candidates[0]
        saved = torch.load(directory / "best.pt", weights_only=True)
        saved["mean"] += 1
        trainer.save_checkpoint(directory / "best.pt", saved)
        report = outer.read_json(directory / "report.json")
        report["checkpointSha256"] = outer.digest(directory / "best.pt")
        outer.atomic_json(directory / "report.json", report)
        with self.assertRaisesRegex(ValueError, "fit-only"):
            outer.run_refit(self.args)
        saved["mean"] -= 1
        trainer.save_checkpoint(directory / "best.pt", saved)
        report["checkpointSha256"] = outer.digest(directory / "best.pt")
        outer.atomic_json(directory / "report.json", report)
        history = directory / "history.jsonl"
        history.write_text("\n".join(history.read_text().splitlines()[:-1]) + "\n")
        with self.assertRaisesRegex(ValueError, "epoch count"):
            outer.run_refit(self.args)

    def test_outer_label_changes_cannot_change_refit(self):
        outer.run_refit(self.args)
        before = torch.load(self.args.output / "checkpoint.pt", weights_only=True)
        # Rebind synthetic metadata and inner artifacts without changing any fit/validation labels.
        for index in self.fixture.fold["outerHoldoutRows"]:
            self.fixture.cohort["rows"][index]["raterCounts"] = [5, 0, 0]
        import shutil
        for path in self.candidates:
            shutil.rmtree(path)
        self.prepare()
        args = SimpleNamespace(candidates=self.candidates, output=self.root / "outputs/changed-refit")
        outer.run_refit(args)
        after = torch.load(args.output / "checkpoint.pt", weights_only=True)
        self.assertTrue(torch.equal(before["mean"], after["mean"]))
        self.assertTrue(all(torch.equal(before["model"][key], value) for key, value in after["model"].items()))

    def test_mutation_during_refit_blocks_frozen_completion(self):
        real_fit = outer.fit_epochs
        def mutate(*args):
            result = real_fit(*args)
            self.recipe.write_text(self.recipe.read_text() + " ")
            return result
        with patch.object(outer, "fit_epochs", side_effect=mutate), self.assertRaisesRegex(ValueError, "changed"):
            outer.run_refit(self.args)
        self.assertFalse((self.args.output / "frozen.json").exists())

    def test_mid_evaluation_history_mutation_blocks_report(self):
        outer.run_refit(self.args)
        real_evaluate = trainer.evaluate
        def mutate(*args):
            result = real_evaluate(*args)
            path = self.args.output / "history.json"
            path.write_text(path.read_text() + " ")
            return result
        with patch.object(trainer, "evaluate", side_effect=mutate), self.assertRaisesRegex(ValueError, "changed"):
            outer.run_evaluate(self.evaluate_args())
        self.assertFalse((self.evaluate_args().output / "report.json").exists())

    def test_missing_candidate_source_and_existing_output_fail_before_holdout(self):
        with self.assertRaisesRegex(ValueError, "two distinct"):
            outer.run_refit(SimpleNamespace(candidates=self.candidates[:1], output=self.args.output))
        outer.run_refit(self.args)
        evaluation = self.evaluate_args()
        evaluation.output.mkdir()
        with patch.object(trainer, "evaluate", side_effect=AssertionError("Holdout accessed")):
            with self.assertRaisesRegex(ValueError, "fresh directory"):
                outer.run_evaluate(evaluation)
            with patch.object(outer, "source_hashes", return_value={}):
                with self.assertRaisesRegex(ValueError, "changed"):
                    outer.run_evaluate(evaluation)


if __name__ == "__main__":
    unittest.main()
