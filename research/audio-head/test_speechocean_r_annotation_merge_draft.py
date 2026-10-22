"""Synthetic-only tests for the provisional two-reviewer merge."""

import copy
from contextlib import redirect_stderr
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speechocean_r_annotation_intake import load_schema, load_verified_pack_context, read_json
from speechocean_r_annotation_merge_draft import (
    main, merge_reviewers, write_new_local_json,
)


class AnnotationMergeDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = dict(load_schema())
        cls.schema["opaqueClips"] = 2
        cls.durations = {"a" * 16: 1.0, "b" * 16: 1.0}
        cls.orders = {reviewer: tuple(cls.durations) for reviewer in cls.schema["reviewers"]}

    def reviewer_export(self, reviewer, durations=None, order=None):
        durations = self.durations if durations is None else durations
        order = tuple(durations) if order is None else order
        return {"schemaVersion": 1, "records": [
            {"clipId": clip_id, "reviewer": reviewer,
             "targetPresence": "expected",
             "wordInterval": {"startSeconds": 0.1, "endSeconds": 0.8},
             "rInterval": {"startSeconds": 0.3, "endSeconds": 0.5},
             "qualityReason": "none"}
            for clip_id in order]}

    def test_merge_preserves_disagreements_and_original_records(self):
        first = self.reviewer_export("reviewer-a")
        second = self.reviewer_export("reviewer-b")
        second["records"][0].update(targetPresence="omitted", rInterval=None,
                                    qualityReason="targetSoundOmitted")
        original_first, original_second = copy.deepcopy(first), copy.deepcopy(second)
        combined, summary = merge_reviewers(first, second, self.schema, self.durations,
                                            self.orders)
        self.assertEqual(combined["records"], first["records"] + second["records"])
        self.assertEqual((first, second), (original_first, original_second))
        self.assertEqual(summary["recordsValidated"], 4)
        self.assertFalse(summary["labelsApprovedForTraining"])

    def test_rejects_wrong_reviewers_duplicates_unknown_ids_and_extra_data(self):
        base_first = self.reviewer_export("reviewer-a")
        base_second = self.reviewer_export("reviewer-b")
        mutations = [
            lambda a, b: a["records"][0].update(reviewer="reviewer-b"),
            lambda a, b: a["records"].__setitem__(1, copy.deepcopy(a["records"][0])),
            lambda a, b: b["records"][0].update(clipId="c" * 16),
            lambda a, b: a["records"][0].update(sourceId="sensitive"),
            lambda a, b: a.update(sourceId="sensitive"),
            lambda a, b: b["records"].pop(),
            lambda a, b: a.update(schemaVersion=True),
            lambda a, b: b["records"][0]["rInterval"].update(endSeconds=2.0),
        ]
        for mutate in mutations:
            first, second = copy.deepcopy(base_first), copy.deepcopy(base_second)
            mutate(first, second)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                merge_reviewers(first, second, self.schema, self.durations, self.orders)

    def test_rejects_a_reviewers_reordered_export(self):
        first = self.reviewer_export("reviewer-a")
        second = self.reviewer_export("reviewer-b")
        first["records"].reverse()
        with self.assertRaisesRegex(ValueError, "pack order"):
            merge_reviewers(first, second, self.schema, self.durations, self.orders)

    def test_write_is_new_private_file_and_rejects_existing_or_symlink_output(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            root = Path(directory)
            destination = root / "merged.json"
            value = {"schemaVersion": 1, "records": []}
            write_new_local_json(destination, value)
            self.assertEqual(read_json(destination), value)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                write_new_local_json(destination, {"replaced": True})
            self.assertEqual(read_json(destination), value)
            link = root / "link.json"
            link.symlink_to(destination)
            with self.assertRaises(ValueError):
                write_new_local_json(link, value)
            directory_link = root / "linked-directory"
            directory_link.symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                write_new_local_json(directory_link / "new.json", value)
            with self.assertRaises(ValueError):
                write_new_local_json(Path("relative.json"), value)
            self.assertEqual(list(root.glob(".annotation-merge-*")), [])

    def test_main_writes_only_after_validation_and_prints_aggregate_summary(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            root = Path(directory)
            first, second = self.reviewer_export("reviewer-a"), self.reviewer_export("reviewer-b")
            a_path, b_path, output = root / "a.json", root / "b.json", root / "merged.json"
            a_path.write_text(json.dumps(first))
            b_path.write_text(json.dumps(second))
            with patch("speechocean_r_annotation_merge_draft.load_schema", return_value=self.schema), \
                 patch("speechocean_r_annotation_merge_draft.load_verified_pack_context",
                       return_value=(self.durations, self.orders)), \
                 patch("builtins.print") as printed:
                main([str(a_path), str(b_path), str(output)])
            self.assertEqual(read_json(output)["records"], first["records"] + second["records"])
            summary = json.loads(printed.call_args.args[0])
            self.assertEqual(summary["recordsValidated"], 4)
            self.assertNotIn("records", summary)
            self.assertNotIn("clipId", summary)
            self.assertFalse(summary["clinicalUseEligible"])

            output.unlink()
            second["records"][0]["clipId"] = "unknown"
            b_path.write_text(json.dumps(second))
            error = io.StringIO()
            with patch("speechocean_r_annotation_merge_draft.load_schema", return_value=self.schema), \
                 patch("speechocean_r_annotation_merge_draft.load_verified_pack_context",
                       return_value=(self.durations, self.orders)), \
                 redirect_stderr(error), self.assertRaises(SystemExit) as failed:
                main([str(a_path), str(b_path), str(output)])
            self.assertEqual(failed.exception.code, 2)
            self.assertFalse(output.exists())
            self.assertNotIn("unknown", error.getvalue())

    def test_real_pinned_pack_accepts_only_complete_synthetic_shape(self):
        schema = load_schema()
        durations, orders = load_verified_pack_context(schema)
        self.assertEqual(len(durations), 40)
        first = self.reviewer_export("reviewer-a", durations, orders["reviewer-a"])
        second = self.reviewer_export("reviewer-b", durations, orders["reviewer-b"])
        combined, summary = merge_reviewers(first, second, schema, durations, orders)
        self.assertEqual(len(combined["records"]), 80)
        self.assertEqual(summary["recordsValidated"], 80)


if __name__ == "__main__":
    unittest.main()
