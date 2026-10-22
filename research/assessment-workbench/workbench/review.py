"""Pure independent review boundaries for the local research workbench."""

import copy
import hashlib
import math
import re

from .domain import ValidationError, semantic_digest, validate_manifest


ANSWER_ENUMS = {
    "speech": {"present", "absent", "uncertain", "unavailable"},
    "promptMatch": {"matched", "mismatched", "uncertain", "unavailable"},
    "occurrence": {"resolved", "ambiguous", "unavailable"},
    "target": {"expected", "altered", "omitted", "indeterminate", "unscorable"},
    "quality": {"usable", "limited", "unusable"},
}
REVIEWERS = ("reviewer-a", "reviewer-b")
PREDICTION_REASONS = {
    "unavailable": {"recording_unavailable", "permission_denied", "permission_unknown", "withdrawn",
                    "unsupported", "unsupported_target", "model_unavailable", "context_unavailable",
                    "synthetic_unavailable"},
    "failed": {"processing_failed", "model_failed", "invalid_input"},
}


def _fail(code):
    raise ValidationError(code)


def _exact(value, fields, code):
    if type(value) is not dict or set(value) != set(fields):
        _fail(code)


def validate_answer(answer):
    """Return an isolated answer with only explicit human observations."""
    _exact(answer, (*ANSWER_ENUMS, "notes"), "review_answer_fields")
    for key, choices in ANSWER_ENUMS.items():
        if type(answer[key]) is not str or answer[key] not in choices:
            _fail("review_answer_value")
    if type(answer["notes"]) is not str or len(answer["notes"]) > 2000:
        _fail("review_notes")
    semantic_digest(answer)
    return copy.deepcopy(answer)


def item_id(manifest, reviewerId, attemptId):
    """Return an opaque local demo item identifier, without claiming authentication."""
    if type(reviewerId) is not str or reviewerId not in REVIEWERS:
        _fail("reviewer_id")
    if type(attemptId) is not str or not any(attempt["id"] == attemptId for attempt in manifest["attempts"]):
        _fail("attempt_id")
    return _opaque_item_id(manifest["projectId"], reviewerId, attemptId)


def _opaque_item_id(project_id, reviewer_id, attempt_id):
    return hashlib.sha256(
        f"{project_id}|{reviewer_id}|{attempt_id}".encode("utf-8")
    ).hexdigest()[:24]


def _project(manifest):
    return copy.deepcopy({
        "title": manifest["title"], "mode": manifest["mode"],
        "task": {key: manifest["task"][key] for key in
                 ("id", "version", "referenceVariety", "definitionSource")},
    })


def recording_available(aggregate, attempt):
    permissions = attempt["permissions"]
    withdrawn = any(record["participantId"] == attempt["participantId"]
                    for record in aggregate["withdrawals"])
    return bool(attempt["recording"] is not None and permissions["review"] == "allowed"
                and permissions["withdrawn"] is False and not withdrawn)


def _prompt_context(prompt, attempt):
    variant = next(value for value in prompt["variants"] if value["id"] == attempt["variantId"])
    return {"word": prompt["word"], "targetPhone": prompt["targetPhone"],
            "variantId": variant["id"], "phones": copy.deepcopy(variant["phones"]),
            "occurrenceIndex": attempt["occurrenceIndex"]}


def reviewer_projection(aggregate, reviewerId):
    """Construct the independent reviewer view from an explicit nested allowlist."""
    if type(reviewerId) is not str or reviewerId not in REVIEWERS:
        _fail("reviewer_id")
    manifest = aggregate["manifest"]
    prompts = {prompt["id"]: prompt for prompt in manifest["prompts"]}
    items = []
    for attempt in manifest["attempts"]:
        prompt = prompts[attempt["promptId"]]
        own = aggregate["reviews"][reviewerId].get(attempt["id"])
        items.append({
            "itemId": _opaque_item_id(manifest["projectId"], reviewerId, attempt["id"]),
            "prompt": _prompt_context(prompt, attempt),
            "recordingAvailable": recording_available(aggregate, attempt),
            "synthetic": (attempt["recording"]["origin"] == "synthetic"
                          if attempt["recording"] is not None else manifest["mode"] == "synthetic"),
            "review": validate_answer(own["answer"]) if own is not None else None,
        })
    return {"project": _project(manifest), "reviewerId": reviewerId, "sealed": aggregate["seals"].get(reviewerId) is True, "items": items}


def _sha(value, code):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _fail(code)


def _original(record):
    _exact(record, ("answer", "sha256"), "review_record")
    validated = validate_answer(record["answer"])
    _sha(record["sha256"], "review_digest")
    if record["sha256"] != semantic_digest(validated):
        _fail("review_digest")
    return {"answer": validated, "sha256": record["sha256"]}


def _sealed(aggregate):
    return all(aggregate["seals"].get(reviewer) is True for reviewer in REVIEWERS)


def adjudicator_projection(aggregate):
    """Expose both immutable originals only after both independent batches seal."""
    manifest = aggregate["manifest"]
    result = {"project": _project(manifest), "items": [],
              "seals": {reviewer: aggregate["seals"].get(reviewer) is True for reviewer in REVIEWERS}}
    if not _sealed(aggregate):
        return result
    prompts = {prompt["id"]: prompt for prompt in manifest["prompts"]}
    for attempt in manifest["attempts"]:
        prompt = prompts[attempt["promptId"]]
        originals = [aggregate["reviews"][reviewer].get(attempt["id"]) for reviewer in REVIEWERS]
        adjudication = aggregate["adjudications"].get(attempt["id"])
        if adjudication is not None:
            _exact(adjudication, ("answer", "sha256"), "adjudication_record")
            decision = validate_adjudication(aggregate, attempt["id"], adjudication["answer"])
            _sha(adjudication["sha256"], "adjudication_digest")
            if semantic_digest(decision) != adjudication["sha256"]:
                _fail("adjudication_digest")
            adjudication = {"answer": decision, "sha256": adjudication["sha256"]}
        result["items"].append({
            "attemptId": attempt["id"], "prompt": _prompt_context(prompt, attempt),
            "reviewA": _original(originals[0]) if originals[0] is not None else None,
            "reviewB": _original(originals[1]) if originals[1] is not None else None,
            "adjudication": adjudication,
        })
    return result


def validate_adjudication(aggregate, attemptId, answer):
    """Bind an explicit target decision to the two sealed, stored originals."""
    if type(attemptId) is not str or not any(
        attempt["id"] == attemptId for attempt in aggregate["manifest"]["attempts"]
    ):
        _fail("attempt_id")
    if not _sealed(aggregate):
        _fail("reviews_not_sealed")
    _exact(answer, ("target", "notes", "reviewedOriginals"), "adjudication_fields")
    if type(answer["target"]) is not str or answer["target"] not in ANSWER_ENUMS["target"]:
        _fail("adjudication_target")
    if (type(answer["notes"]) is not str or not answer["notes"].strip()
            or len(answer["notes"]) > 2000):
        _fail("adjudication_notes")
    pins = answer["reviewedOriginals"]
    if type(pins) is not list or len(pins) != 2:
        _fail("adjudication_originals")
    for pin in pins:
        _sha(pin, "adjudication_originals")
    originals = [_original(aggregate["reviews"][reviewer].get(attemptId)) for reviewer in REVIEWERS]
    if pins != [record["sha256"] for record in originals]:
        _fail("adjudication_originals")
    semantic_digest(answer)
    return copy.deepcopy(answer)


def validate_prediction_lock(manifest, payload, expectedSha):
    """Validate a caller-pinned import; a digest does not prove authenticity."""
    manifest = validate_manifest(manifest)
    _sha(expectedSha, "prediction_expected_digest")
    digest = semantic_digest(payload)
    if digest != expectedSha:
        _fail("prediction_digest_mismatch")
    _exact(payload, ("schemaVersion", "model", "rows"), "prediction_fields")
    if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1:
        _fail("prediction_schema_version")
    model = payload["model"]
    _exact(model, ("id", "version", "manifestSha256", "preprocessingSha256", "meaning"),
           "prediction_model_fields")
    if type(model["id"]) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model["id"]) is None:
        _fail("prediction_model_id")
    if type(model["version"]) is not str or not model["version"].strip():
        _fail("prediction_model_version")
    _sha(model["manifestSha256"], "prediction_manifest_digest")
    _sha(model["preprocessingSha256"], "prediction_preprocessing_digest")
    if model["meaning"] != "subjective_corpus_classes":
        _fail("prediction_meaning")
    if model["manifestSha256"] != semantic_digest(manifest):
        _fail("prediction_manifest_mismatch")
    rows = payload["rows"]
    if type(rows) is not list:
        _fail("prediction_rows")
    attempts = {attempt["id"]: attempt for attempt in manifest["attempts"]}
    seen = set()
    for row in rows:
        if type(row) is not dict:
            _fail("prediction_row_fields")
        attempt_id = row.get("attemptId")
        if type(attempt_id) is not str or attempt_id not in attempts or attempt_id in seen:
            _fail("prediction_roster")
        seen.add(attempt_id)
        if row.get("contextSha256") != semantic_digest(attempts[attempt_id]["context"]):
            _fail("prediction_context_mismatch")
        status = row.get("status")
        if type(status) is not str or status not in ("processed", *PREDICTION_REASONS):
            _fail("prediction_status")
        _exact(row, ("attemptId", "contextSha256", "status",
                     "probabilities" if status == "processed" else "reason"), "prediction_row_fields")
        if status == "processed":
            probabilities = row["probabilities"]
            if (type(probabilities) is not list or len(probabilities) != 3
                    or any(type(value) not in (int, float) or not 0 <= value <= 1
                           or not math.isfinite(value) for value in probabilities)
                    or not math.isclose(sum(probabilities), 1, rel_tol=0, abs_tol=1e-9)):
                _fail("prediction_probabilities")
        elif type(row["reason"]) is not str or row["reason"] not in PREDICTION_REASONS[status]:
            _fail("prediction_reason")
    if seen != set(attempts):
        _fail("prediction_roster")
    return {"payload": copy.deepcopy(payload), "sha256": digest}
