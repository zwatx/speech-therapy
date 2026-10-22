"""Aggregate, research-only draft agreement report for a validated reviewer export.

No reviewer labels exist in this repository. This command reads a future local
export, validates its pinned provenance and structure, and prints only aggregate
descriptive statistics. It never saves, merges, adjudicates, or approves labels.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, median
import wave

from speechocean_r_annotation_intake import (
    load_schema, load_verified_durations, read_json, validate_submission,
)


def category_agreement(pairs: list[tuple[dict, dict]], field: str,
                       values: list[str]) -> dict:
    confusion = {left: {right: 0 for right in values} for left in values}
    for first, second in pairs:
        confusion[first[field]][second[field]] += 1
    exact = sum(confusion[value][value] for value in values)
    return {"reviewerARowsReviewerBColumns": confusion,
            "exactPairs": exact, "exactFraction": exact / len(pairs)}


def interval_agreement(pairs: list[tuple[dict, dict]], field: str) -> dict:
    both = []
    one = neither = 0
    for first, second in pairs:
        left, right = first[field], second[field]
        if left is None and right is None:
            neither += 1
        elif left is None or right is None:
            one += 1
        else:
            both.append((left, right))
    result = {"bothPresentPairs": len(both), "onePresentPairs": one,
              "neitherPresentPairs": neither, "pairedMetrics": None}
    if not both:
        return result
    overlaps = []
    start_differences = []
    end_differences = []
    for left, right in both:
        left_start, left_end = left["startSeconds"], left["endSeconds"]
        right_start, right_end = right["startSeconds"], right["endSeconds"]
        intersection = max(0.0, min(left_end, right_end) - max(left_start, right_start))
        union = max(left_end, right_end) - min(left_start, right_start)
        overlaps.append(intersection / union)
        start_differences.append(abs(left_start - right_start))
        end_differences.append(abs(left_end - right_end))
    result["pairedMetrics"] = {
        "meanIntersectionOverUnion": mean(overlaps),
        "medianIntersectionOverUnion": median(overlaps),
        "meanAbsoluteStartDifferenceSeconds": mean(start_differences),
        "medianAbsoluteStartDifferenceSeconds": median(start_differences),
        "meanAbsoluteEndDifferenceSeconds": mean(end_differences),
        "medianAbsoluteEndDifferenceSeconds": median(end_differences),
    }
    return result


def validated_agreement_report(submission: dict, schema: dict,
                               durations: dict[str, float]) -> dict:
    """Validate the complete export before computing any paired statistics."""
    validation = validate_submission(submission, schema, durations)
    by_pair = {(record["clipId"], record["reviewer"]): record
               for record in submission["records"]}
    first, second = schema["reviewers"]
    pairs = [(by_pair[(clip_id, first)], by_pair[(clip_id, second)])
             for clip_id in durations]
    return {
        "reportVersion": 1,
        "status": "draft descriptive agreement only",
        "clips": validation["opaqueClips"],
        "recordsValidated": validation["recordsValidated"],
        "targetPresence": category_agreement(
            pairs, "targetPresence", schema["targetPresenceValues"]),
        "qualityReason": category_agreement(
            pairs, "qualityReason", schema["qualityReasonValues"]),
        "wordInterval": interval_agreement(pairs, "wordInterval"),
        "rInterval": interval_agreement(pairs, "rInterval"),
        "qualifiedSlpSignoff": False,
        "labelsApprovedForTraining": False,
        "clinicalUseEligible": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path, help="Future local reviewer export")
    args = parser.parse_args()
    try:
        schema = load_schema()
        durations = load_verified_durations(schema)
        submission = read_json(args.submission)
        report = validated_agreement_report(submission, schema, durations)
    except (OSError, ValueError, KeyError, TypeError, wave.Error):
        parser.error("Export failed pinned provenance or intake validation")
    print(json.dumps(report, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
