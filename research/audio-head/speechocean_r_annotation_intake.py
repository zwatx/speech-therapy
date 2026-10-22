"""Provisional, local-only validator for future blinded /R/ reviewer exports.

This script never collects labels or writes a validated label artifact. It
rejects any export outside the locked 40-clip, two-reviewer draft contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import wave


HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "experiments/speechocean-r-annotation-intake-draft-v1.json"
OPAQUE_ID = re.compile(r"[0-9a-f]{16}\Z")
FALSE_FLAGS = ("sourceIdentifiersInExport", "freeTextInExport", "rawAudioInExport",
               "adjudicationInExport", "productionEligible", "calibrationEligible",
               "learnerFeedbackEligible", "clinicalUseEligible", "trainingEligible")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path: Path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON field: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def checked_file(path: Path, expected: str):
    require(digest(path) == expected, f"Pinned file SHA-256 mismatch: {path.name}")
    return read_json(path)


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    require(path.resolve() == SCHEMA_PATH.resolve(), "Intake schema path differs from locked draft")
    schema = read_json(path)
    require(schema.get("schemaVersion") == 1 and
            schema.get("name") == "speechocean-r-annotation-intake-draft-v1" and
            schema.get("sourcePartition") == "author-train" and
            schema.get("sampleDirectory") == "outputs/speechocean-r-annotation-sample-v1" and
            schema.get("opaqueClips") == 40 and
            schema.get("reviewers") == ["reviewer-a", "reviewer-b"] and
            schema.get("completeExportRequiresAllClipReviewerPairs") is True and
            schema.get("recordFields") == ["clipId", "reviewer", "targetPresence",
                                            "wordInterval", "rInterval", "qualityReason"] and
            schema.get("targetPresenceValues") == ["expected", "altered", "omitted",
                                                    "indeterminate"] and
            schema.get("qualityReasonValues") == ["none", "targetWordOmitted",
                                                   "targetSoundOmitted", "captureNoise",
                                                   "overlap", "timingIndeterminate"] and
            schema.get("intervalFields") == ["startSeconds", "endSeconds"] and
            schema.get("intervalsMayBeNull") is True and
            schema.get("rIntervalMustLieWithinWordIntervalWhenBothPresent") is True and
            schema.get("missingIntervalRequiresQualityReason") is True and
            schema.get("omittedOrIndeterminateRIntervalMustBeNull") is True and
            all(schema.get(flag) is False for flag in FALSE_FLAGS),
            "Intake schema differs from locked provisional contract")
    return schema


def verified_wav_duration(path: Path, expected_sha256: str) -> float:
    require(path.is_file() and digest(path) == expected_sha256,
            "Reviewer WAV bytes differ from verified source")
    with wave.open(str(path), "rb") as source:
        require((source.getnchannels(), source.getsampwidth(), source.getframerate(),
                 source.getcomptype()) == (1, 2, 16000, "NONE") and
                source.getnframes() > 0, "Reviewer WAV format differs from verified PCM")
        return source.getnframes() / source.getframerate()


def load_verified_pack_context(schema: dict, base: Path = HERE
                               ) -> tuple[dict[str, float], dict[str, tuple[str, ...]]]:
    """Verify the pinned sample and WAVs, retaining each blinded pack's order."""
    sample = base / schema["sampleDirectory"]
    report = checked_file(sample / "report.json", schema["sampleReportSha256"])
    manifest = checked_file(sample / "internal-manifest.json",
                            schema["internalManifestSha256"])
    queue = checked_file(sample / "reviewer-queue.json", schema["reviewerQueueSha256"])
    packs = sample / "local-reviewer-packs"
    pack_report = checked_file(packs / "report.json", schema["packReportSha256"])
    require(report.get("authorPartition") == "train" and
            report.get("internalManifestSha256") == schema["internalManifestSha256"] and
            report.get("reviewerQueueSha256") == schema["reviewerQueueSha256"] and
            report.get("selectedClips") == 40 and
            pack_report.get("sampleReportSha256") == schema["sampleReportSha256"] and
            pack_report.get("notDistributed") is True and
            queue.get("annotationComplete") is False,
            "Sample or pack provenance mismatch")
    items = queue.get("items")
    clips = manifest.get("clips")
    require(type(items) is list and type(clips) is list and len(items) == len(clips) == 40,
            "Expected forty pinned queue and manifest entries")
    queue_by_id = {item["reviewerId"]: item for item in items}
    manifest_by_id = {clip["reviewerId"]: clip for clip in clips}
    require(len(queue_by_id) == len(manifest_by_id) == 40 and
            set(queue_by_id) == set(manifest_by_id) and
            all(OPAQUE_ID.fullmatch(clip_id) for clip_id in queue_by_id),
            "Invalid or duplicate opaque queue IDs")
    public_fields = ("targetPrompt", "targetWord", "wordIndexZeroBased",
                     "phoneIndexWithinWordZeroBased")
    for clip_id, item in queue_by_id.items():
        require(set(item) == {"reviewerId", *public_fields} and
                all(item[field] == manifest_by_id[clip_id][field] for field in public_fields),
                "Queue target differs from verified internal mapping")
    durations = {}
    pack_orders = {}
    for reviewer in schema["reviewers"]:
        pack_queue = checked_file(packs / reviewer / "queue.json",
                                  schema["reviewerPackQueueSha256"][reviewer])
        require(pack_queue.get("reviewer") == reviewer and
                pack_report.get("reviewerPackQueueSha256", {}).get(reviewer) ==
                schema["reviewerPackQueueSha256"][reviewer] and
                len(pack_queue.get("items", [])) == 40,
                "Reviewer pack provenance mismatch")
        seen = set()
        order = []
        for item in pack_queue["items"]:
            clip_id = item.get("reviewerId")
            require(clip_id in queue_by_id and clip_id not in seen and
                    item.get("audioFile") == f"media/{clip_id}.wav" and
                    set(item) == {"reviewerId", "audioFile", *public_fields} and
                    all(item[field] == queue_by_id[clip_id][field] for field in public_fields),
                    "Pack queue differs from pinned opaque queue")
            seen.add(clip_id)
            order.append(clip_id)
            duration = verified_wav_duration(packs / reviewer / "media" /
                                             f"{clip_id}.wav",
                                             manifest_by_id[clip_id]["wavSha256"])
            if clip_id in durations:
                require(duration == durations[clip_id], "Reviewer WAV durations differ")
            durations[clip_id] = duration
        require(seen == set(queue_by_id), "Reviewer pack does not cover all clips")
        pack_orders[reviewer] = tuple(order)
    return durations, pack_orders


def load_verified_durations(schema: dict, base: Path = HERE) -> dict[str, float]:
    return load_verified_pack_context(schema, base)[0]


def validate_interval(value, duration: float, label: str) -> tuple[float, float] | None:
    if value is None:
        return None
    require(type(value) is dict and set(value) == {"startSeconds", "endSeconds"},
            f"{label} must have only startSeconds/endSeconds or null")
    start, end = value["startSeconds"], value["endSeconds"]
    require(type(start) in (int, float) and type(end) in (int, float) and
            0 <= start < end <= duration and math.isfinite(start) and
            math.isfinite(end), f"{label} outside verified WAV duration")
    return float(start), float(end)


def validate_export_shape(submission: dict) -> list:
    require(type(submission) is dict and set(submission) == {"schemaVersion", "records"} and
            type(submission["schemaVersion"]) is int and submission["schemaVersion"] == 1 and
            type(submission["records"]) is list,
            "Export must contain only schemaVersion and records")
    return submission["records"]


def validate_records(records: list, schema: dict, durations: dict[str, float],
                     expected_pairs: set[tuple[str, str]]) -> None:
    require(len(records) == len(expected_pairs), "Export has missing or extra records")
    seen = set()
    for index, record in enumerate(records):
        require(type(record) is dict and set(record) == set(schema["recordFields"]),
                f"Record {index} contains missing or disallowed fields")
        clip_id, reviewer = record["clipId"], record["reviewer"]
        require(type(clip_id) is str and clip_id in durations and
                type(reviewer) is str and reviewer in schema["reviewers"],
                f"Record {index} has unknown clip/reviewer")
        pair = (clip_id, reviewer)
        require(pair in expected_pairs, f"Record {index} has wrong reviewer")
        require(pair not in seen, f"Duplicate clip/reviewer record: {index}")
        seen.add(pair)
        presence, reason = record["targetPresence"], record["qualityReason"]
        require(type(presence) is str and presence in schema["targetPresenceValues"] and
                type(reason) is str and reason in schema["qualityReasonValues"],
                f"Record {index} has unsupported closed response")
        word = validate_interval(record["wordInterval"], durations[clip_id],
                                 f"Record {index} wordInterval")
        target = validate_interval(record["rInterval"], durations[clip_id],
                                   f"Record {index} rInterval")
        require(presence not in ("omitted", "indeterminate") or target is None,
                f"Record {index} cannot force an /R/ interval")
        require(word is not None and target is not None or reason != "none",
                f"Record {index} missing interval requires a closed reason")
        require(word is None or target is None or reason == "none",
                f"Record {index} complete intervals require no missing-interval reason")
        omission_reasons = ("targetWordOmitted", "targetSoundOmitted")
        require((presence == "omitted") == (reason in omission_reasons),
                f"Record {index} omission judgment/reason mismatch")
        require(reason != "targetWordOmitted" or word is None,
                f"Record {index} omitted word cannot have a word interval")
        require(word is None or target is None or
                (word[0] <= target[0] < target[1] <= word[1]),
                f"Record {index} /R/ interval outside target word")
    require(seen == expected_pairs, "Export omits a clip/reviewer pair")


def validation_summary(clips: int, reviewers: list[str]) -> dict:
    return {"schemaVersion": 1, "status": "provisional structure only",
            "recordsValidated": clips * len(reviewers), "opaqueClips": clips,
            "reviewers": reviewers,
            "qualifiedSlpSignoff": False, "labelsApprovedForTraining": False,
            "clinicalUseEligible": False}


def validate_submission(submission: dict, schema: dict,
                        durations: dict[str, float]) -> dict:
    records = validate_export_shape(submission)
    require(len(durations) == schema["opaqueClips"] and
            len(records) == len(durations) * len(schema["reviewers"]),
            "Complete export requires one record per clip and reviewer")
    validate_records(records, schema, durations,
                     {(clip_id, reviewer) for clip_id in durations
                      for reviewer in schema["reviewers"]})
    return validation_summary(len(durations), list(schema["reviewers"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path,
                        help="Local, future JSON export; no labels are saved by this validator")
    args = parser.parse_args()
    schema = load_schema()
    durations = load_verified_durations(schema)
    summary = validate_submission(read_json(args.submission), schema, durations)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
