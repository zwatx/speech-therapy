"""Synthetic records and read-only real-pack preflight for single-reviewer exports."""

import copy
from contextlib import redirect_stderr
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speechocean_r_annotation_intake import (
    load_schema, load_verified_pack_context, read_json,
)
from speechocean_r_annotation_reviewer_export import main, validate_reviewer_export


class ReviewerExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = dict(load_schema())
        cls.schema["opaqueClips"] = 2
        cls.order = ("a" * 16, "b" * 16)
        cls.durations = {cls.order[0]: 1.0, cls.order[1]: 1.0}

    def export(self, reviewer="reviewer-a"):
        return {"schemaVersion": 1, "records": [
            {"clipId": clip_id, "reviewer": reviewer,
             "targetPresence": "expected",
             "wordInterval": {"startSeconds": 0.1, "endSeconds": 0.8},
             "rInterval": {"startSeconds": 0.3, "endSeconds": 0.5},
             "qualityReason": "none"}
            for clip_id in self.order]}

    def validate(self, export, reviewer="reviewer-a", order=None):
        return validate_reviewer_export(export, reviewer, self.schema,
                                        self.durations, self.order if order is None else order)

    def test_accepts_one_complete_reviewer_and_reports_only_aggregate_flags(self):
        export = self.export()
        original = copy.deepcopy(export)
        summary = self.validate(export)
        self.assertEqual(export, original)
        self.assertEqual(summary["recordsValidated"], 2)
        self.assertEqual(summary["reviewers"], ["reviewer-a"])
        self.assertFalse(summary["labelsApprovedForTraining"])
        self.assertNotIn("records", summary)
        self.assertNotIn(self.order[0], json.dumps(summary))
        other = self.export("reviewer-b")
        other["records"].reverse()
        self.assertEqual(self.validate(other, "reviewer-b", tuple(reversed(self.order)))
                         ["reviewers"], ["reviewer-b"])

    def test_rejects_wrong_order_reviewer_ids_duplicates_and_missing_records(self):
        mutations = [
            lambda e: e["records"].reverse(),
            lambda e: e["records"][0].update(reviewer="reviewer-b"),
            lambda e: e["records"][0].update(clipId="c" * 16),
            lambda e: e["records"].__setitem__(1, copy.deepcopy(e["records"][0])),
            lambda e: e["records"].pop(),
            lambda e: e["records"].append(copy.deepcopy(e["records"][0])),
        ]
        for mutate in mutations:
            export = self.export()
            mutate(export)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.validate(export)
        with self.assertRaisesRegex(ValueError, "pack order"):
            self.validate(self.export(), order=(self.order[0], self.order[0]))
        with self.assertRaisesRegex(ValueError, "pack order"):
            self.validate(self.export(), order=("source-id", self.order[1]))
        with self.assertRaisesRegex(ValueError, "Unknown reviewer"):
            self.validate(self.export(), reviewer="reviewer-c")

    def test_rejects_extra_or_missing_fields_and_unstructured_content(self):
        for field, value in (("sourceId", "source"), ("speakerId", "speaker"),
                             ("notes", "free text"), ("audioBytes", "AAA"),
                             ("otherReviewer", {})):
            export = self.export()
            export["records"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "disallowed"):
                self.validate(export)
        export = self.export()
        del export["records"][0]["qualityReason"]
        with self.assertRaisesRegex(ValueError, "missing"):
            self.validate(export)
        for field in ("sourceId", "reviewerNotes"):
            export = self.export()
            export[field] = "private"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(export)

    def test_reuses_locked_interval_and_closed_response_rules(self):
        changes = [
            lambda row: row["rInterval"].update(endSeconds=1.1),
            lambda row: row["rInterval"].update(startSeconds=-0.1),
            lambda row: row["rInterval"].update(endSeconds=float("nan")),
            lambda row: row["rInterval"].update(endSeconds=0.1),
            lambda row: row["rInterval"].update(startSeconds=0.79, endSeconds=0.9),
            lambda row: row.update(targetPresence="omitted"),
            lambda row: row.update(qualityReason="free text"),
            lambda row: row.update(rInterval=None),
        ]
        for change in changes:
            export = self.export()
            change(export["records"][0])
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate(export)

    def test_cli_uses_verified_context_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps(self.export()))
            with patch("speechocean_r_annotation_reviewer_export.load_schema",
                       return_value=self.schema), \
                 patch("speechocean_r_annotation_reviewer_export.load_verified_pack_context",
                       return_value=(self.durations, {"reviewer-a": self.order})), \
                 patch("builtins.print") as printed:
                main(["reviewer-a", str(path)])
            self.assertEqual(list(Path(directory).iterdir()), [path])
            self.assertEqual(read_json(path), self.export())
            self.assertEqual(json.loads(printed.call_args.args[0])["recordsValidated"], 2)
            path.write_text('{"schemaVersion":1,"records":[],"records":[]}')
            error = io.StringIO()
            with patch("speechocean_r_annotation_reviewer_export.load_schema",
                       return_value=self.schema), \
                 patch("speechocean_r_annotation_reviewer_export.load_verified_pack_context",
                       return_value=(self.durations, {"reviewer-a": self.order})), \
                 redirect_stderr(error), self.assertRaises(SystemExit) as failed:
                main(["reviewer-a", str(path)])
            self.assertEqual(failed.exception.code, 2)
            self.assertNotIn(self.order[0], error.getvalue())
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_real_pack_preflight_without_labels(self):
        schema = load_schema()
        durations, orders = load_verified_pack_context(schema)
        self.assertEqual(len(durations), 40)
        self.assertEqual(set(orders), set(schema["reviewers"]))
        for reviewer in schema["reviewers"]:
            self.assertEqual(len(orders[reviewer]), 40)
            self.assertEqual(set(orders[reviewer]), set(durations))
        self.assertNotEqual(orders["reviewer-a"], orders["reviewer-b"])


if __name__ == "__main__":
    unittest.main()
