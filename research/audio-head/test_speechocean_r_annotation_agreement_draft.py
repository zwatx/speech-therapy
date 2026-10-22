"""Synthetic-only tests for the draft descriptive reviewer agreement report."""

import copy
import json
import unittest

from speechocean_r_annotation_agreement_draft import validated_agreement_report
from speechocean_r_annotation_intake import load_schema


def interval(start, end):
    return {"startSeconds": start, "endSeconds": end}


class AnnotationAgreementDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = dict(load_schema())
        cls.schema["opaqueClips"] = 4
        cls.durations = {letter * 16: 2.0 for letter in "abcd"}

    def export(self):
        records = []
        for reviewer in self.schema["reviewers"]:
            for clip_id in self.durations:
                records.append({"clipId": clip_id, "reviewer": reviewer,
                                "targetPresence": "expected", "qualityReason": "none",
                                "wordInterval": interval(0.1, 0.8),
                                "rInterval": interval(0.3, 0.5)})
        return {"schemaVersion": 1, "records": records}

    def record(self, export, letter, reviewer):
        return next(record for record in export["records"]
                    if record["clipId"] == letter * 16 and
                    record["reviewer"] == reviewer)

    def test_disagreement_and_nullable_intervals_have_explicit_denominators(self):
        export = self.export()
        a_b = self.record(export, "a", "reviewer-b")
        a_b["wordInterval"] = interval(0.2, 0.9)
        a_b["rInterval"] = interval(0.4, 0.6)
        b_a = self.record(export, "b", "reviewer-a")
        b_a["targetPresence"] = "altered"
        b_b = self.record(export, "b", "reviewer-b")
        b_b["targetPresence"] = "omitted"
        b_b["rInterval"] = None
        b_b["qualityReason"] = "targetSoundOmitted"
        for reviewer in self.schema["reviewers"]:
            c = self.record(export, "c", reviewer)
            c["targetPresence"] = "indeterminate"
            c["wordInterval"] = None
            c["rInterval"] = None
            c["qualityReason"] = "timingIndeterminate"
        d_b = self.record(export, "d", "reviewer-b")
        d_b["targetPresence"] = "altered"
        d_b["wordInterval"] = None
        d_b["rInterval"] = None
        d_b["qualityReason"] = "captureNoise"

        report = validated_agreement_report(export, self.schema, self.durations)
        self.assertEqual((report["clips"], report["recordsValidated"]), (4, 8))
        presence = report["targetPresence"]
        self.assertEqual(presence["exactPairs"], 2)
        self.assertEqual(presence["exactFraction"], 0.5)
        self.assertEqual(presence["reviewerARowsReviewerBColumns"]["altered"]["omitted"], 1)
        self.assertEqual(report["qualityReason"]["exactPairs"], 2)
        word = report["wordInterval"]
        target = report["rInterval"]
        self.assertEqual((word["bothPresentPairs"], word["onePresentPairs"],
                          word["neitherPresentPairs"]), (2, 1, 1))
        self.assertEqual((target["bothPresentPairs"], target["onePresentPairs"],
                          target["neitherPresentPairs"]), (1, 2, 1))
        self.assertAlmostEqual(word["pairedMetrics"]["meanIntersectionOverUnion"], 0.875)
        self.assertAlmostEqual(target["pairedMetrics"]["meanIntersectionOverUnion"], 1 / 3)
        self.assertAlmostEqual(target["pairedMetrics"]["meanAbsoluteStartDifferenceSeconds"], 0.1)
        self.assertAlmostEqual(target["pairedMetrics"]["meanAbsoluteEndDifferenceSeconds"], 0.1)
        self.assertFalse(report["qualifiedSlpSignoff"])
        self.assertFalse(report["labelsApprovedForTraining"])
        self.assertFalse(report["clinicalUseEligible"])
        serialized = json.dumps(report, sort_keys=True)
        for clip_id in self.durations:
            self.assertNotIn(clip_id, serialized)
        self.assertNotIn("records", report)

    def test_no_paired_r_intervals_has_null_metrics(self):
        export = self.export()
        for record in export["records"]:
            record["targetPresence"] = "indeterminate"
            record["rInterval"] = None
            record["qualityReason"] = "timingIndeterminate"
        report = validated_agreement_report(export, self.schema, self.durations)
        self.assertEqual(report["rInterval"]["bothPresentPairs"], 0)
        self.assertEqual(report["rInterval"]["neitherPresentPairs"], 4)
        self.assertIsNone(report["rInterval"]["pairedMetrics"])

    def test_malformed_exports_are_rejected_before_reporting(self):
        cases = []
        unknown = self.export()
        unknown["records"][0]["clipId"] = "f" * 16
        cases.append(unknown)
        duplicate = self.export()
        duplicate["records"][1] = copy.deepcopy(duplicate["records"][0])
        cases.append(duplicate)
        incomplete = self.export()
        incomplete["records"].pop()
        cases.append(incomplete)
        disallowed = self.export()
        disallowed["records"][0]["sourceId"] = "private"
        cases.append(disallowed)
        forced = self.export()
        forced["records"][0]["targetPresence"] = "omitted"
        cases.append(forced)
        beyond_wav = self.export()
        beyond_wav["records"][0]["wordInterval"]["endSeconds"] = 3.0
        cases.append(beyond_wav)
        for submission in cases:
            with self.subTest(submission=submission), self.assertRaises(ValueError):
                validated_agreement_report(submission, self.schema, self.durations)


if __name__ == "__main__":
    unittest.main()
