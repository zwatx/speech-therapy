import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from comparison import compare_runs, load_run
from data import digest, make_fixtures, read_json, write_json
from pipeline import train
from encoders import SpectralEncoder, Wav2VecEncoder


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = make_fixtures(self.root / "data")
        self.first, self.second = self.root / "first", self.root / "second"
        for seed, directory in enumerate((self.first, self.second)):
            train(self.manifest, directory, "spectral-engineering-v1", self.root / "cache", steps=2, seed=seed)

    def compare(self):
        return compare_runs([(self.first, self.manifest), (self.second, self.manifest)])

    def test_comparison_keeps_input_order_and_never_selects(self):
        report = self.compare()
        self.assertEqual([row["name"] for row in report["runs"]], ["first", "second"])
        self.assertFalse(report["selectionPerformed"])
        self.assertFalse(report["productionEligible"])
        self.assertFalse(report["learnerFeedbackEligible"])
        first, second = report["runs"]
        self.assertEqual(first["partitionSha256"], second["partitionSha256"])
        self.assertIsNone(first["headInitializationSeed"])
        self.assertEqual(first["initialHeadSha256"], read_json(self.first / "report.json")["initialHeadSha256"])
        self.assertAlmostEqual(second["differenceFromFirst"]["test"]["tokenErrorRatePercentagePoints"],
                               100 * (second["splits"]["test"]["tokenErrorRate"] - first["splits"]["test"]["tokenErrorRate"]))

    def test_changed_holdout_identity_is_rejected_even_with_matching_counts(self):
        changed = read_json(self.manifest)
        for row in changed["items"]:
            if row["split"] == "test":
                row["speakerHash"] = digest(("different-" + row["id"]).encode())
        alternative = self.manifest.parent / "changed.json"
        write_json(alternative, changed)
        third = self.root / "third"
        train(alternative, third, "spectral-engineering-v1", self.root / "cache", steps=2)
        with self.assertRaisesRegex(ValueError, "identical test"):
            compare_runs([(self.first, self.manifest), (third, alternative)])

    def test_arithmetic_tampering_is_rejected(self):
        report = read_json(self.second / "report.json")
        for field, value in (("tokenErrorRate", 0.123456789), ("ctcLoss", float("inf")), ("exactSequenceMatches", 1000)):
            modified = copy.deepcopy(report)
            modified["splits"]["test"][field] = value
            # JSON writer rightly rejects nonfinite numbers; exercise parser tolerance explicitly.
            import json
            (self.second / "report.json").write_text(json.dumps(modified))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.compare()

    def test_manifest_and_checkpoint_tampering_are_rejected(self):
        wrong = make_fixtures(self.root / "other-data", seed=11)
        with self.assertRaisesRegex(ValueError, "different manifest"):
            load_run(self.first, wrong)
        weights = self.second / "head.pt"
        weights.write_bytes(weights.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.compare()

    def test_duplicate_run_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            compare_runs([(self.first, self.manifest), (self.first, self.manifest)])

    def test_explicit_head_initialization_provenance_is_preserved(self):
        paired = self.root / "paired"
        train(self.manifest, paired, "spectral-engineering-v1", self.root / "cache",
              steps=2, seed=11, head_seed=7)
        report = compare_runs([(self.first, self.manifest), (paired, self.manifest)])
        recorded = read_json(paired / "report.json")
        self.assertEqual(report["runs"][1]["headInitializationSeed"], 7)
        self.assertEqual(report["runs"][1]["initialHeadSha256"], recorded["initialHeadSha256"])

    def test_encoder_contrast_requires_explicit_opt_in_and_preserves_holdout_checks(self):
        class PaddedTestEncoder(SpectralEncoder):
            # A test double avoids downloading speech weights; the stored head
            # has the real declared width so normal checkpoint validation runs.
            identity = Wav2VecEncoder.identity

            def __call__(self, samples):
                from torch.nn.functional import pad
                return pad(super().__call__(samples), (0, 768 - 65))

        third = self.root / "other-encoder"
        with patch("pipeline.load_encoder", return_value=PaddedTestEncoder()):
            train(self.manifest, third, "wav2vec2-base", self.root / "cache", steps=2)
        runs = [(self.first, self.manifest), (third, self.manifest)]
        with self.assertRaisesRegex(ValueError, "explicitly enable encoder comparison"):
            compare_runs(runs)
        report = compare_runs(runs, allow_encoder_comparison=True)
        self.assertTrue(report["encoderComparisonEnabled"])
        self.assertTrue(report["encodersDiffer"])
        self.assertFalse(report["selectionPerformed"])
        self.assertEqual(report["runs"][1]["encoder"], Wav2VecEncoder.identity)

        # Permission to compare encoders never relaxes holdout membership.
        altered = read_json(self.manifest)
        for row in altered["items"]:
            if row["split"] == "test":
                row["speakerHash"] = digest(("changed-" + row["id"]).encode())
        different_manifest = self.manifest.parent / "different.json"
        write_json(different_manifest, altered)
        fourth = self.root / "other-holdout"
        with patch("pipeline.load_encoder", return_value=PaddedTestEncoder()):
            train(different_manifest, fourth, "wav2vec2-base", self.root / "cache", steps=2)
        with self.assertRaisesRegex(ValueError, "identical test"):
            compare_runs([(self.first, self.manifest), (fourth, different_manifest)],
                         allow_encoder_comparison=True)


if __name__ == "__main__":
    unittest.main()
