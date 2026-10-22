"""Synthetic fixtures only: no public corpus audio or held-out labels are read."""
import contextlib
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_train as trainer


def canonical_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cadence-training-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # train() hashes its three implementation sources, including at completion.
        for name in ("multiphone_train.py", "multiphone_models.py", "multiphone_cache.py"):
            (self.root / name).write_bytes((trainer.HERE / name).read_bytes())
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.cohort = {"clips": [], "rows": []}
        for clip_index, frame_count in enumerate((3, 5, 4)):
            clip_id = f"synthetic-{clip_index}"
            speaker = f"speaker-{clip_index}"
            self.cohort["clips"].append({
                "id": clip_id, "speakerId": speaker,
                "audioSha256": hashlib.sha256(clip_id.encode()).hexdigest(),
            })
            for target in (0, 1):
                self.cohort["rows"].append({
                    "clipIndex": clip_index, "clipId": clip_id, "speakerId": speaker,
                    "targetId": target, "targetPhone": ("B", "P")[target],
                    "trainingEligible": True, "age": 8 + 6 * clip_index,
                    "raterCounts": [4, 1, 0] if target == 0 else [0, 1, 4],
                })
        self.fold = {"outerFitRows": [0, 1, 2, 3], "outerHoldoutRows": [4, 5],
                     "innerFitRows": [0, 1], "innerValidationRows": [2, 3]}
        self.cohort_path = self.root / "cohort.json"
        self.splits_path = self.root / "splits.json"
        self.persist_sources()
        self.build_cache()

    def persist_sources(self):
        trainer.atomic_json(self.cohort_path, self.cohort)
        trainer.atomic_json(self.splits_path, {"folds": [self.fold],
                            "cohortCanonicalSha256": canonical_hash(self.cohort)})

    def build_cache(self):
        trainer.atomic_json(self.cache / "config.json", {
            "purpose": "synthetic test fixture", "cohortSha256": trainer.digest(self.cohort_path),
        })
        config_hash = trainer.digest(self.cache / "config.json")
        entries = {}
        for clip_index, frame_count in enumerate((3, 5, 4)):
            clip = self.cohort["clips"][clip_index]
            # Different clip means make accidental normalization leakage observable.
            frames = np.broadcast_to(np.arange(frame_count, dtype=np.float32)[:, None]
                                     + clip_index * 10, (frame_count, 768)).copy()
            path = self.cache / f"{clip['id']}.npz"
            np.savez(path, frames=frames, audio_sha256=clip["audioSha256"], config_sha256=config_hash)
            entries[clip["id"]] = {"path": path.name, "sha256": trainer.digest(path)}
        trainer.atomic_json(self.cache / "index.json", {
            "complete": True, "configSha256": config_hash, "entries": entries,
        })

    def args(self, phase="inner", epochs=4):
        return SimpleNamespace(
            cohort=self.cohort_path, splits=self.splits_path, cache=self.cache,
            output=self.root / "outputs" / phase, head="mean", phase=phase, fold=0,
            device="cpu", seed=7, hidden=8, dropout=0.0, lr=0.001,
            weight_decay=0.01, epochs=epochs, patience=2, batch_size=2, threads=2,
        )

    def run_training(self, args):
        with patch.object(trainer, "HERE", self.root), contextlib.redirect_stdout(io.StringIO()):
            return trainer.train(args)

    def test_metrics_use_all_raters_and_expected_rater_brier(self):
        probabilities = np.array([[0.6, 0.2, 0.2], [0.1, 0.8, 0.1]])
        counts = np.array([[3, 0, 2], [0, 5, 0]])
        metrics = trainer.distribution_metrics(probabilities, counts)
        expected_nll = -((3 * math.log(0.6) + 2 * math.log(0.2)) / 5 + math.log(0.8)) / 2
        self.assertAlmostEqual(metrics["perRaterLogLoss"], expected_nll)
        self.assertAlmostEqual(metrics["perRaterBrier"], 0.31)
        self.assertAlmostEqual(metrics["meanRatingMSE"], 0.02)
        self.assertAlmostEqual(metrics["meanRatingMAE"], 0.1)

    def test_invalid_counts_are_rejected_before_training_or_metrics(self):
        for counts in ([-1, 0, 6], [0.5, 0.5, 4], [0, 0, 4], [0, 0, float("nan")], [0, 5]):
            with self.subTest(counts=counts):
                cohort = copy.deepcopy(self.cohort)
                cohort["rows"][0]["raterCounts"] = counts
                with self.assertRaises(ValueError):
                    trainer.StudyData(cohort, self.cache, [0])
                with self.assertRaises(ValueError):
                    trainer.distribution_metrics(np.array([[0.2, 0.2, 0.6]]), np.asarray([counts]))

    def test_duplicate_rows_speakers_clips_and_incomplete_inner_split_rejected(self):
        trainer.verify_partitions(self.cohort, self.fold)
        for key in ("speakerId", "clipId"):
            cohort = copy.deepcopy(self.cohort)
            cohort["rows"][2][key] = cohort["rows"][0][key]
            with self.assertRaisesRegex(ValueError, "crosses"):
                trainer.verify_partitions(cohort, self.fold)
        duplicate = copy.deepcopy(self.fold)
        duplicate["outerHoldoutRows"].append(4)
        with self.assertRaises(ValueError):
            trainer.verify_partitions(self.cohort, duplicate)
        incomplete = copy.deepcopy(self.fold)
        incomplete["innerValidationRows"] = [2]
        with self.assertRaisesRegex(ValueError, "subdivide"):
            trainer.verify_partitions(self.cohort, incomplete)

    def test_normalization_is_fit_only_and_batch_masks_preserve_row_order(self):
        data = trainer.StudyData(self.cohort, self.cache, list(range(6)))
        mean, std = data.normalization([0])
        torch.testing.assert_close(mean, torch.ones(768))
        torch.testing.assert_close(std, torch.full((768,), math.sqrt(2/3)))
        changed = data.features[2].clone()
        data.features[2].fill_(1e6)
        again = data.normalization([0])
        torch.testing.assert_close(again[0], mean)
        torch.testing.assert_close(again[1], std)
        data.features[2] = changed
        features, frame_mask, phones, target_mask, targets, row_ids = data.batch(
            [1, 0], {0, 1, 3}, mean, std, "cpu")
        self.assertEqual(row_ids, [3, 0, 1])
        self.assertEqual(phones.tolist(), [[1, -1], [0, 1]])
        self.assertEqual(target_mask.tolist(), [[True, False], [True, True]])
        self.assertEqual(frame_mask.tolist(), [[True] * 5, [True, True, True, False, False]])
        self.assertEqual(features[1, 3:].count_nonzero(), 0)
        torch.testing.assert_close(targets[target_mask].sum(-1), torch.ones(3))
        self.assertEqual(targets[~target_mask].count_nonzero(), 0)

    def test_cache_binding_and_modified_feature_files_are_rejected(self):
        config = self.cache / "config.json"
        config.write_text(config.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "config changed"):
            trainer.StudyData(self.cohort, self.cache, [0, 1])
        self.build_cache()
        path = self.cache / "synthetic-0.npz"
        path.write_bytes(path.read_bytes() + b"modified")
        with self.assertRaisesRegex(ValueError, "digest"):
            trainer.StudyData(self.cohort, self.cache, [0, 1])

    def test_missing_or_stale_split_cohort_binding_is_rejected(self):
        for split in ({"folds": [self.fold]}, {"folds": [self.fold], "cohortCanonicalSha256": "0" * 64}):
            trainer.atomic_json(self.splits_path, split)
            with self.assertRaises((ValueError, KeyError)):
                self.run_training(self.args())

    def test_inner_selection_uses_validation_only_and_restores_best_epoch(self):
        args = self.args(epochs=6)
        # An inner run must never load outer labels or feature files.
        self.cohort["rows"][4]["raterCounts"] = [-1, 0, 6]
        self.persist_sources()
        self.build_cache()
        (self.cache / "synthetic-2.npz").unlink()
        calls = []
        validation_losses = iter([3.0, 1.0, 2.0, 2.5, 1.0])

        def validation(model, data, selected, *unused):
            model.eval()
            calls.append(list(selected))
            self.assertEqual(selected, self.fold["innerValidationRows"])
            return {"macroTargetLogLoss": next(validation_losses)}, {"rowIndices": selected}

        with patch.object(trainer, "evaluate", side_effect=validation):
            report = self.run_training(args)
        self.assertEqual(report["bestEpoch"], 2)
        self.assertEqual(report["epochsRun"], 4)
        self.assertEqual(len(calls), 5)  # Four selection calls and the restored checkpoint.
        best = torch.load(args.output / "best.pt", weights_only=True)
        last = torch.load(args.output / "last.pt", weights_only=True)
        self.assertEqual(best["epoch"], 2)
        self.assertEqual(last["epoch"], 4)
        self.assertEqual(best["configSha256"], trainer.digest(args.output / "config.json"))
        torch.testing.assert_close(best["mean"], torch.ones(768))

    def test_outer_run_evaluates_only_after_all_fixed_epochs(self):
        args = self.args(phase="outer", epochs=3)
        args.patience = 1
        calls = []

        def final_evaluation(model, data, selected, *unused):
            calls.append(list(selected))
            self.assertEqual(selected, self.fold["outerHoldoutRows"])
            history = (args.output / "history.jsonl").read_text().splitlines()
            self.assertEqual(len(history), 3)
            self.assertTrue(all("validation" not in json.loads(line) for line in history))
            return {"macroTargetLogLoss": 1000.0}, {"rowIndices": selected}

        with patch.object(trainer, "evaluate", side_effect=final_evaluation):
            report = self.run_training(args)
        self.assertEqual(calls, [self.fold["outerHoldoutRows"]])
        self.assertEqual((report["bestEpoch"], report["epochsRun"]), (3, 3))
        saved = torch.load(args.output / "best.pt", weights_only=True)
        self.assertEqual(saved["epoch"], 3)

    def test_real_evaluation_preserves_all_rows_and_macro_target_average(self):
        args = self.args(epochs=1)
        report = self.run_training(args)
        predictions = json.loads((args.output / "predictions.json").read_text())
        self.assertEqual(predictions["rowIndices"], [2, 3])
        np.testing.assert_allclose(np.asarray(predictions["probabilities"]).sum(-1), 1, atol=1e-6)
        result = report["evaluation"]
        self.assertEqual(set(result["perTarget"]), {"B", "P"})
        self.assertAlmostEqual(result["macroTargetLogLoss"], np.mean(
            [row["perRaterLogLoss"] for row in result["perTarget"].values()]))
        self.assertIsNone(result["ages6to12"])
        self.assertEqual(result["ages13plus"]["examples"], 2)


if __name__ == "__main__":
    torch.set_num_threads(2)
    unittest.main()
