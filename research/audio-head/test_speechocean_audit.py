import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import speechocean_audit as audit


def example_metadata():
    aggregate, detail, splits, ages, genders = {}, {}, {}, {}, {}
    for part, offset in (("train", 0), ("test", 125)):
        splits[part] = {}
        ages[part] = {}
        genders[part] = {}
        for speaker_number in range(offset, offset + 125):
            speaker = f"{speaker_number:04d}"
            ages[part][speaker] = "12"
            genders[part][speaker] = "f"
            for index in range(20):
                utterance = f"{speaker_number:04d}{index:05d}"
                splits[part][utterance] = speaker
                aggregate[utterance] = {
                    "accuracy": 8, "completeness": 10, "fluency": 8, "prosodic": 8, "total": 8,
                    "text": "BAT", "words": [{"text": "BAT", "phones": ["B", "AE1", "T"],
                                             "phones-accuracy": [2, 1.8, 2],
                                             "accuracy": 8, "stress": 10, "total": 8}],
                }
                detail[utterance] = {
                    "accuracy": [8] * 5, "completeness": [1] * 5, "fluency": [8] * 5,
                    "prosodic": [8] * 5, "total": [8] * 5, "text": "BAT",
                    "words": [{"text": "BAT", "ref-phones": "B AE1 T",
                               "phones": ["B AE1 T"] * 4 + ["B {AE1} T"],
                               "accuracy": [8] * 5, "stress": [10] * 5, "total": [8] * 5}],
                }
    return aggregate, detail, splits, ages, genders


class SpeechOceanAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = example_metadata()

    def fields(self):
        return copy.deepcopy(self.fixture)

    def test_accepts_distinct_canonical_and_five_rater_scores(self):
        result = audit.validate_scores(*self.fields())
        self.assertEqual(result["utterances"], 5000)
        self.assertEqual(result["canonicalPhonePositions"], 15000)
        self.assertEqual(result["speakers"], {"train": 125, "test": 125})
        # Every fixture has unanimous B/T, but one of five raters marks AE1 as accented.
        self.assertEqual(result["unanimousFiveRaterPhonePositions"], 10000)
        self.assertEqual(result["nonUnanimousFiveRaterPhonePositions"], 5000)
        self.assertEqual(result["fiveRaterScoreRangeCounts"], {"0": 10000, "1": 5000, "2": 0})
        self.assertEqual(sum(result["fiveRaterScoreRangeCounts"].values()),
                         result["canonicalPhonePositions"])

    def test_full_zero_to_two_rater_disagreement_has_range_two(self):
        aggregate, detail, splits, ages, genders = self.fields()
        next(iter(detail.values()))["words"][0]["phones"][0] = "B (AE1) T"
        next(iter(aggregate.values()))["words"][0]["phones-accuracy"][1] = 1.4
        result = audit.validate_scores(aggregate, detail, splits, ages, genders)
        self.assertEqual(result["fiveRaterScoreRangeCounts"], {"0": 10000, "1": 4999, "2": 1})
        self.assertEqual(result["unanimousFiveRaterPhonePositions"] +
                         result["nonUnanimousFiveRaterPhonePositions"],
                         result["canonicalPhonePositions"])

    def test_canonical_phones_cannot_be_relabelled_as_produced_ctc_targets(self):
        aggregate, detail, splits, ages, genders = self.fields()
        first = next(iter(aggregate.values()))
        first["words"][0]["producedPhones"] = first["words"][0]["phones"]
        with self.assertRaisesRegex(ValueError, "cannot present ratings as CTC training labels"):
            audit.validate_scores(aggregate, detail, splits, ages, genders)

    def test_speaker_or_utterance_leakage_is_rejected(self):
        for kind in ("speaker", "utterance"):
            with self.subTest(kind=kind):
                aggregate, detail, splits, ages, genders = self.fields()
                if kind == "speaker":
                    test_speaker = next(iter(splits["test"].values()))
                    splits["test"] = {key: ("0000" if value == test_speaker else value)
                                      for key, value in splits["test"].items()}
                    ages["test"]["0000"] = ages["test"].pop(test_speaker)
                    genders["test"]["0000"] = genders["test"].pop(test_speaker)
                else:
                    key = next(iter(splits["test"]))
                    copied = next(iter(splits["train"]))
                    splits["test"][copied] = splits["test"].pop(key)
                with self.assertRaisesRegex(ValueError, "both splits"):
                    audit.validate_scores(aggregate, detail, splits, ages, genders)

    def test_rater_values_and_aggregate_must_agree(self):
        aggregate, detail, splits, ages, genders = self.fields()
        next(iter(aggregate.values()))["words"][0]["phones-accuracy"][1] = 2
        with self.assertRaisesRegex(ValueError, "differs from five raters"):
            audit.validate_scores(aggregate, detail, splits, ages, genders)
        aggregate, detail, splits, ages, genders = self.fields()
        next(iter(detail.values()))["words"][0]["phones"][0] = "B [K] AE1 T"
        # Insertion stays distinct; the five original canonical phones still match.
        next(iter(aggregate.values()))["words"][0]["phones-accuracy"][1] = 1.8
        result = audit.validate_scores(aggregate, detail, splits, ages, genders)
        self.assertEqual(result["annotatedInsertionsAcrossRaters"], 1)
        next(iter(detail.values()))["words"][0]["phones"][0] = "B (AE1) T"
        with self.assertRaisesRegex(ValueError, "differs from five raters"):
            audit.validate_scores(aggregate, detail, splits, ages, genders)

    def test_bad_annotation_or_selective_note_is_rejected(self):
        aggregate, detail, splits, ages, genders = self.fields()
        next(iter(detail.values()))["words"][0]["phones"][0] = "B K T"
        with self.assertRaisesRegex(ValueError, "differs from canonical phones"):
            audit.validate_scores(aggregate, detail, splits, ages, genders)
        aggregate, detail, splits, ages, genders = self.fields()
        next(iter(aggregate.values()))["words"][0]["mispronunciations"] = [
            {"canonical-phone": "AE", "index": 1, "pronounced-phone": "EH"}]
        with self.assertRaisesRegex(ValueError, "lacks low expert rating"):
            audit.validate_scores(aggregate, detail, splits, ages, genders)
        next(iter(aggregate.values()))["words"][0]["mispronunciations"] = None
        with self.assertRaisesRegex(ValueError, "notes must be a list"):
            audit.validate_scores(aggregate, detail, splits, ages, genders)

    def test_pin_mismatch_and_budget_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "probe").write_bytes(b"abc")
            with patch.dict(audit.FILES, {"probe": (3, audit.sha256(b"abc"))}, clear=True):
                self.assertEqual(audit.pinned_bytes(root, "probe"), b"abc")
                (root / "probe").write_bytes(b"abd")
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    audit.pinned_bytes(root, "probe")
            with patch.dict(audit.FILES, {"probe": (audit.LIMIT_BYTES + 1, "0" * 64)}, clear=True):
                with patch("urllib.request.urlopen") as request:
                    with self.assertRaisesRegex(ValueError, "30 MB"):
                        audit.fetch_metadata(root / "fetch")
                    request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
