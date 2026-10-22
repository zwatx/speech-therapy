"""Manual proper/rank scores and speaker-cluster inference invariants."""
from copy import deepcopy
import json
import math
import unittest

import numpy as np

import multiphone_outer_statistics as stats
from multiphone_train import distribution_metrics
from multiphone_verify import target_discrimination, weighted_binary_metrics


def row(identity, speaker, phone, counts, age=8, clip=None):
    return {"id": identity, "speakerId": speaker, "clipId": clip or speaker + "-clip", "age": age,
            "targetPhone": phone, "raterCounts": counts}


class OuterStatisticsTests(unittest.TestCase):
    def test_manual_proper_scores_and_per_rater_brier(self):
        rows = [row("a", "A", "B", [5, 0, 0]), row("b", "B", "B", [0, 0, 5])]
        p = np.array([[.8, .1, .1], [.1, .2, .7]])
        result = stats.compute_statistics({"model": p}, rows, [0, 0], replicates=100)
        values = result["slices"]["allAges"]["models"]["model"]["point"]
        self.assertAlmostEqual(values["macroTargetLogLoss"], -(math.log(.8) + math.log(.7)) / 2)
        self.assertAlmostEqual(values["perRaterLogLoss"], values["macroTargetLogLoss"])
        self.assertAlmostEqual(values["perRaterBrier"], .1)
        self.assertAlmostEqual(values["meanRatingMAE"], .35)
        self.assertEqual(values["macroTarget.rating0.auroc"], 1)
        self.assertEqual(values["macroTarget.rating0.averagePrecision"], 1)
        mixed = [row("a", "A", "B", [2, 1, 2]), row("b", "B", "B", [2, 1, 2])]
        p = np.array([[.4, .2, .4]] * 2)
        proper = stats.compute_statistics({"model": p}, mixed, [0, 0], replicates=10)
        self.assertAlmostEqual(proper["slices"]["allAges"]["models"]["model"]["point"]["perRaterBrier"], .64)
        self.assertEqual(np.square(p - np.array([r["raterCounts"] for r in mixed]) / 5).sum(), 0)

    def test_ties_grouped_average_precision_and_weighted_auc_match_manual(self):
        scores, positive, negative = [.2, .2, .8], [1, 2, 1], [2, 0, 1]
        grouped = stats.RankGroups(scores, positive, negative, [0, 1, 2])
        auc, ap = grouped.evaluate([[1, 1, 1]])
        self.assertAlmostEqual(auc[0], 5.5 / 12)
        self.assertAlmostEqual(ap[0], (.5 + 12 / 7) / 4)
        reference = weighted_binary_metrics(scores, positive, negative)
        self.assertAlmostEqual(auc[0], reference["auroc"])
        self.assertAlmostEqual(ap[0], reference["averagePrecision"])
        equal = stats.RankGroups([.4] * 3, positive, negative, [0, 1, 2])
        auc, ap = equal.evaluate([[1, 1, 1]])
        self.assertEqual(auc[0], .5)
        self.assertAlmostEqual(ap[0], 4 / 7)

    def test_point_estimates_match_existing_metrics_for_all_age_slices(self):
        rows, folds = [], []
        for i, age in enumerate((8, 10, 14, 15, 18, 30)):
            for j, phone in enumerate(("B", "P", "S")):
                rows.append(row(f"r{i}-{j}", f"speaker{i}", phone, [j, 1, 4-j], age))
                folds.append(i // 2)
        p = np.random.default_rng(42).dirichlet([1, 2, 4], len(rows))
        result = stats.compute_statistics({"m": p}, rows, folds, replicates=25)
        for age, section in result["slices"].items():
            keep = np.asarray([age == "allAges" or stats.age_slice(r["age"]) == age for r in rows])
            selected = [r for r, ok in zip(rows, keep) if ok]
            counts = np.asarray([r["raterCounts"] for r in selected])
            expected = distribution_metrics(p[keep], counts)
            point = section["models"]["m"]["point"]
            for name in ("perRaterLogLoss", "perRaterBrier", "meanRatingMAE"):
                self.assertAlmostEqual(point[name], expected[name], places=13)
            phone = np.asarray([r["targetPhone"] for r in selected])
            macro = np.mean([distribution_metrics(p[keep][phone == q], counts[phone == q])["perRaterLogLoss"] for q in np.unique(phone)])
            self.assertAlmostEqual(point["macroTargetLogLoss"], macro, places=13)
            ranks = target_discrimination(p[keep], counts, phone)["macroTarget"]
            for event in stats.EVENTS:
                for metric in ("auroc", "averagePrecision"):
                    self.assertAlmostEqual(point[f"macroTarget.{event}.{metric}"], ranks[event][metric], places=13)

    def test_bootstrap_preserves_speaker_cluster_and_fold_age_strata(self):
        rows = [row("aB", "A", "B", [1, 1, 3]), row("aP", "A", "P", [1, 1, 3]),
                row("bB", "B", "B", [1, 1, 3]), row("c", "C", "B", [1, 1, 3], 14),
                row("d", "D", "B", [1, 1, 3], 20)]
        folds = [0, 0, 0, 1, 1]
        _, _, metadata = stats.validate_inputs({"m": np.tile([.2, .2, .6], (len(rows), 1))}, rows, folds, {})
        speakers, multiplicities, strata = stats.speaker_bootstrap(metadata, 100, 7)
        mapping = {speaker: i for i, speaker in enumerate(speakers)}
        row_weights = multiplicities[:, [mapping[r["speakerId"]] for r in rows]]
        np.testing.assert_array_equal(row_weights[:, 0], row_weights[:, 1])
        np.testing.assert_array_equal(multiplicities[:, [mapping["A"], mapping["B"]]].sum(1), 2)
        np.testing.assert_array_equal(multiplicities[:, mapping["C"]], 1)
        np.testing.assert_array_equal(multiplicities[:, mapping["D"]], 1)
        self.assertEqual(sum(x["speakers"] for x in strata), 4)
        np.testing.assert_array_equal(multiplicities, stats.speaker_bootstrap(metadata, 100, 7)[1])
        self.assertFalse(np.array_equal(multiplicities, stats.speaker_bootstrap(metadata, 100, 8)[1]))

    def test_fixed_phone_support_marks_replicate_missing_instead_of_changing_macro(self):
        rows = [row("a", "A", "B", [1, 1, 3]), row("b", "B", "P", [1, 1, 3])]
        result = stats.compute_statistics({"m": [[.2, .2, .6]] * 2}, rows, [0, 0], replicates=200)
        section = result["slices"]["allAges"]
        self.assertEqual(section["fixedProperPhones"], ["B", "P"])
        self.assertEqual(section["fixedRankingPhones"]["rating0"], ["B", "P"])
        intervals = section["models"]["m"]["intervals"]
        for metric in ("macroTargetLogLoss", "macroTarget.rating0.auroc", "macroTarget.rating0.averagePrecision"):
            self.assertGreater(intervals[metric]["validReplicates"], 0)
            self.assertLess(intervals[metric]["validReplicates"], 190)
            self.assertIsNone(intervals[metric]["percentile95"])
        self.assertEqual(intervals["perRaterLogLoss"]["validReplicates"], 200)
        self.assertFalse(intervals["perRaterLogLoss"]["intervalWithheld"])
        self.assertTrue(stats.interval(.5, [.5] * 18 + [np.nan] * 2)["intervalWithheld"])
        self.assertFalse(stats.interval(.5, [.5] * 19 + [np.nan])["intervalWithheld"])

    def test_class_absence_and_empty_age_slices_are_explicit(self):
        rows = [row("a", "A", "B", [0, 0, 5]), row("b", "B", "B", [0, 0, 5])]
        result = stats.compute_statistics({"m": [[.1, .1, .8]] * 2}, rows, [0, 0], replicates=20)
        section = result["slices"]["allAges"]
        self.assertEqual(section["fixedRankingPhones"]["rating0"], [])
        self.assertEqual(section["excludedRankingPhones"]["rating0"], ["B"])
        self.assertIsNone(section["models"]["m"]["point"]["macroTarget.rating0.auroc"])
        self.assertEqual(section["models"]["m"]["intervals"]["macroTarget.rating0.auroc"]["validReplicates"], 0)
        self.assertEqual(result["slices"]["ages13to15"]["support"]["speakers"], 0)
        self.assertIsNone(result["slices"]["ages13to15"]["models"]["m"]["point"]["macroTargetLogLoss"])
        json.dumps(result, allow_nan=False)

    def test_all_positive_and_all_negative_ranking_both_return_undefined(self):
        for counts in ([5, 0, 0], [0, 0, 5]):
            rows = [row("a", "A", "B", counts), row("b", "B", "B", counts)]
            result = stats.compute_statistics({"m": [[.2, .2, .6]] * 2}, rows, [0, 0], replicates=20)
            phone = result["slices"]["allAges"]["models"]["m"]["perPhone"]["B"]
            for event in stats.EVENTS:
                self.assertIsNone(phone[event]["auroc"])
                self.assertIsNone(phone[event]["averagePrecision"])

    def test_identical_paired_models_zero_differences_and_batch_determinism(self):
        rows = [row("a", "A", "B", [1, 1, 3]), row("b", "B", "B", [2, 1, 2])]
        p = np.array([[.3, .1, .6], [.4, .2, .4]])
        original = p.copy()
        kwargs = {"model_probabilities": {"m": p, "prior": p.copy()}, "rows": rows, "row_folds": [0, 0],
                  "reference_pairs": {"m": ["prior"]}, "replicates": 51, "seed": 42}
        a, b = stats.compute_statistics(**kwargs, batch_size=1), stats.compute_statistics(**kwargs, batch_size=64)
        self.assertEqual(a, b)
        for metric in stats.METRICS:
            value = a["slices"]["allAges"]["pairedDeltas"]["m"]["prior"][metric]
            self.assertEqual(value["pointEstimate"], 0)
            self.assertEqual(value["percentile95"], [0, 0])
            self.assertEqual(value["validReplicates"], 51)
        np.testing.assert_array_equal(p, original)

    def test_negative_nonfinite_misaligned_and_cross_fold_inputs_rejected(self):
        rows = [row("a", "A", "B", [1, 1, 3]), row("b", "B", "B", [2, 1, 2])]
        p = np.array([[.3, .1, .6], [.4, .2, .4]])
        for changed in (p[:1], p * 2, np.array([[-.1, .5, .6], [.4, .2, .4]]), np.full((2, 3), np.nan)):
            with self.assertRaises(ValueError):
                stats.compute_statistics({"m": changed}, rows, [0, 0], replicates=10)
        changed = deepcopy(rows)
        changed[0]["raterCounts"] = [-1, 1, 5]
        with self.assertRaises(ValueError):
            stats.compute_statistics({"m": p}, changed, [0, 0], replicates=10)
        changed = deepcopy(rows)
        changed[1]["speakerId"] = "A"
        with self.assertRaisesRegex(ValueError, "spans outer folds"):
            stats.compute_statistics({"m": p}, changed, [0, 1], replicates=10)
        with self.assertRaisesRegex(ValueError, "Unknown or duplicate reference"):
            stats.compute_statistics({"m": p}, rows, [0, 0], {"m": ["absent"]}, replicates=10)
        with self.assertRaises(ValueError):
            stats.RankGroups([.5], [-1], [5], [0])
        with self.assertRaises(ValueError):
            stats.RankGroups([.5], [1], [4], [0]).evaluate([[-1]])


if __name__ == "__main__":
    unittest.main()
