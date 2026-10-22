"""Synthetic-only tests for the provisional blinded annotation intake."""

import copy
import hashlib
import tempfile
import unittest
import wave
from pathlib import Path

from speechocean_r_annotation_intake import (
    checked_file, load_schema, load_verified_durations, read_json, validate_submission,
    verified_wav_duration,
)


class AnnotationIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = dict(load_schema())
        cls.schema["opaqueClips"] = 2
        cls.durations = {"a" * 16: 1.0, "b" * 16: 2.0}

    def export(self):
        records = []
        for reviewer in self.schema["reviewers"]:
            for clip_id in self.durations:
                records.append({"clipId": clip_id, "reviewer": reviewer,
                                "targetPresence": "expected",
                                "wordInterval": {"startSeconds": 0.1, "endSeconds": 0.8},
                                "rInterval": {"startSeconds": 0.3, "endSeconds": 0.5},
                                "qualityReason": "none"})
        return {"schemaVersion": 1, "records": records}

    def test_two_independent_complete_records_are_retained(self):
        export = self.export()
        first, second = export["records"][0], export["records"][2]
        first["targetPresence"] = "altered"
        second["targetPresence"] = "omitted"
        second["rInterval"] = None
        second["qualityReason"] = "targetSoundOmitted"
        result = validate_submission(export, self.schema, self.durations)
        self.assertEqual(result["recordsValidated"], 4)
        self.assertEqual(first["targetPresence"], "altered")
        self.assertEqual(second["targetPresence"], "omitted")
        self.assertFalse(result["labelsApprovedForTraining"])

    def test_rejects_unknown_duplicate_and_incomplete_pairs(self):
        cases = []
        unknown = self.export()
        unknown["records"][0]["clipId"] = "c" * 16
        cases.append(unknown)
        duplicate = self.export()
        duplicate["records"][1] = copy.deepcopy(duplicate["records"][0])
        cases.append(duplicate)
        missing = self.export()
        missing["records"].pop()
        cases.append(missing)
        for export in cases:
            with self.subTest(export=export), self.assertRaises(ValueError):
                validate_submission(export, self.schema, self.durations)

    def test_rejects_sensitive_or_unstructured_fields(self):
        for field, value in (("sourceId", "000010011"), ("age", 12),
                             ("modelOutput", 0.2), ("name", "Reviewer"),
                             ("comment", "free text"), ("audioBytes", "AAAA"),
                             ("adjudication", "overwritten")):
            export = self.export()
            export["records"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "disallowed"):
                validate_submission(export, self.schema, self.durations)
        export = self.export()
        export["speakerId"] = "0001"
        with self.assertRaises(ValueError):
            validate_submission(export, self.schema, self.durations)
        export = self.export()
        export["schemaVersion"] = True
        with self.assertRaises(ValueError):
            validate_submission(export, self.schema, self.durations)

    def test_rejects_invalid_or_forced_intervals(self):
        for start, end in ((-0.1, 0.2), (0.2, 2.0), (0.4, 0.4),
                           (float("nan"), 0.5), (0.1, float("inf")),
                           (True, 0.5)):
            export = self.export()
            export["records"][0]["rInterval"] = {
                "startSeconds": start, "endSeconds": end}
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                validate_submission(export, self.schema, self.durations)
        export = self.export()
        export["records"][0]["rInterval"] = {"startSeconds": 0.79,
                                               "endSeconds": 0.9}
        with self.assertRaisesRegex(ValueError, "outside target word"):
            validate_submission(export, self.schema, self.durations)
        export = self.export()
        export["records"][0]["targetPresence"] = "omitted"
        with self.assertRaisesRegex(ValueError, "cannot force"):
            validate_submission(export, self.schema, self.durations)

    def test_missing_interval_can_be_explicitly_indeterminate(self):
        export = self.export()
        record = export["records"][0]
        record["targetPresence"] = "indeterminate"
        record["wordInterval"] = None
        record["rInterval"] = None
        record["qualityReason"] = "timingIndeterminate"
        validate_submission(export, self.schema, self.durations)
        record["qualityReason"] = "none"
        with self.assertRaisesRegex(ValueError, "requires a closed reason"):
            validate_submission(export, self.schema, self.durations)

    def test_closed_reasons_match_missing_intervals_and_omissions(self):
        for presence, reason, word in (
            ("expected", "captureNoise", True),
            ("omitted", "captureNoise", True),
            ("omitted", "targetWordOmitted", True),
            ("indeterminate", "targetSoundOmitted", False),
        ):
            export = self.export()
            row = export["records"][0]
            row["targetPresence"] = presence
            row["qualityReason"] = reason
            if not word:
                row["wordInterval"] = None
                row["rInterval"] = None
            elif presence == "omitted":
                row["rInterval"] = None
            with self.subTest(presence=presence, reason=reason), self.assertRaises(ValueError):
                validate_submission(export, self.schema, self.durations)

    def test_verified_wav_duration_fails_closed_on_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 16000)
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(verified_wav_duration(path, expected), 1.0)
            path.write_bytes(path.read_bytes() + b"mutated")
            with self.assertRaisesRegex(ValueError, "bytes differ"):
                verified_wav_duration(path, expected)

    def test_pinned_queue_hash_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.json"
            path.write_text('{"items":[]}')
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(checked_file(path, expected), {"items": []})
            path.write_text('{"items":[{}]}')
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                checked_file(path, expected)

    def test_duplicate_json_key_is_rejected_before_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "future-export.json"
            path.write_text('{"schemaVersion":1,"schemaVersion":2,"records":[]}')
            with self.assertRaisesRegex(ValueError, "Duplicate JSON field"):
                read_json(path)

    def test_real_pinned_reference_durations_are_verified_without_labels(self):
        durations = load_verified_durations(load_schema())
        self.assertEqual(len(durations), 40)
        self.assertTrue(all(0 < duration < 30 for duration in durations.values()))


if __name__ == "__main__":
    unittest.main()
