import copy
import json
import math
import unittest

from workbench import review
from workbench.domain import ValidationError, bind_manifest, semantic_digest


def answer(**changes):
    result = {
        "speech": "present", "promptMatch": "matched", "occurrence": "resolved",
        "target": "expected", "quality": "usable", "notes": "Invented review.",
    }
    result.update(changes)
    return result


def aggregate():
    manifest = {
        "schemaVersion": 1, "projectId": "demo", "title": "Invented study", "mode": "synthetic",
        "task": {"id": "task", "version": "1", "referenceVariety": "synthetic-en",
                 "controlledReviewRecord": {"notes": "PRIVATE_COORDINATOR"}, "definitionSource": "synthetic"},
        "policy": {"id": "policy", "version": "1", "allowedAges": [6, 12], "intendedLanguage": "en"},
        "prompts": [{"id": "prompt", "version": "1", "word": "sun", "lexicalGroup": "PRIVATE_GROUP",
                     "language": "en", "targetPhone": "S", "variants": [
                         {"id": "variant", "phones": ["S", "AH1", "N"], "occurrenceIndexes": [0]}],
                     "source": {"kind": "synthetic", "sha256": "a" * 64}, "engineeringStatus": "accepted"}],
        "participants": [{"id": "PRIVATE_PARTICIPANT", "householdId": "PRIVATE_HOUSEHOLD", "ageYears": 8,
                          "languageVariety": "synthetic-en", "identityLinkage": "declared"}],
        "attempts": [{"id": "attempt", "participantId": "PRIVATE_PARTICIPANT", "promptId": "prompt",
                      "variantId": "variant", "occurrenceIndex": 0, "sessionId": "PRIVATE_SESSION",
                      "conditionId": "quiet", "plannedRepeatOf": None, "retryOf": None, "split": "evaluation",
                      "terminal": "processed_unverified", "recording": {
                          "assetId": "PRIVATE_FILENAME", "sha256": "b" * 64, "durationMs": 900,
                          "origin": "synthetic"}, "permissions": {"version": "1", "recordSha256": "c" * 64,
                          "review": "allowed", "research": "allowed", "withdrawn": False}, "context": {
                              "taskSha256": "0" * 64, "policySha256": "0" * 64,
                              "promptSha256": "0" * 64, "permissionSha256": "0" * 64}}],
    }
    return {"manifest": bind_manifest(manifest), "reviews": {"reviewer-a": {}, "reviewer-b": {}},
            "seals": {"reviewer-a": False, "reviewer-b": False}, "adjudications": {},
            "contentReviews": [], "predictionLock": None, "withdrawals": []}


def predictions(manifest):
    return {"schemaVersion": 1, "model": {"id": "invented", "version": "1",
            "manifestSha256": semantic_digest(manifest), "preprocessingSha256": "f" * 64,
            "meaning": "subjective_corpus_classes"}, "rows": [
                {"attemptId": attempt["id"], "contextSha256": semantic_digest(attempt["context"]),
                 "status": "processed", "probabilities": [0.5, 0.25, 0.25]}
                for attempt in manifest["attempts"]]}


class AnswerTests(unittest.TestCase):
    def test_rejects_inferred_labels_and_unrecognized_fields(self):
        with self.assertRaises(ValueError):
            review.validate_answer(answer(score=0.99))

    def test_validated_answer_is_independent_and_failure_errors_are_fixed(self):
        original = answer()
        validated = review.validate_answer(original)
        validated["notes"] = "Changed"
        self.assertEqual(original["notes"], "Invented review.")
        for invalid in (answer(speech="PRIVATE_SOURCE"), answer(quality=[]), answer(notes="x" * 2001),
                        answer(notes=None), None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError) as error:
                    review.validate_answer(invalid)
                self.assertNotIn("PRIVATE_SOURCE", str(error.exception))

    def test_review_notes_must_have_valid_json_utf8_semantics(self):
        with self.assertRaises(ValidationError):
            review.validate_answer(answer(notes="\ud800"))

    def test_unavailable_observations_remain_explicit_without_model_evidence(self):
        unavailable = answer(speech="unavailable", promptMatch="unavailable", occurrence="unavailable",
                             target="unscorable", quality="unusable", notes="")
        self.assertEqual(review.validate_answer(unavailable), unavailable)


class ProjectionTests(unittest.TestCase):
    def test_reviewer_sees_only_prompt_and_own_answer_with_role_specific_ids(self):
        state = aggregate()
        own_answer, other_answer = answer(), answer(notes="PRIVATE_OTHER_REVIEW")
        state["reviews"]["reviewer-a"]["attempt"] = {"answer": own_answer, "sha256": semantic_digest(own_answer)}
        state["reviews"]["reviewer-b"]["attempt"] = {"answer": other_answer, "sha256": semantic_digest(other_answer)}
        state["coordinatorNotes"] = "PRIVATE_COORDINATOR_NOTES"
        state["predictionLock"] = {"scores": "PRIVATE_SCORES"}
        result = review.reviewer_projection(state, "reviewer-a")
        self.assertEqual(set(result), {"project", "reviewerId", "sealed", "items"})
        self.assertEqual(set(result["project"]["task"]), {"id", "version", "referenceVariety", "definitionSource"})
        item = result["items"][0]
        self.assertEqual(item["itemId"], "465919fce6a8028b70dd8a9b")
        self.assertEqual(set(item), {"itemId", "prompt", "recordingAvailable", "synthetic", "review"})
        self.assertEqual(item["prompt"], {"word": "sun", "targetPhone": "S", "variantId": "variant",
                                          "phones": ["S", "AH1", "N"], "occurrenceIndex": 0})
        self.assertTrue(item["recordingAvailable"])
        self.assertTrue(item["synthetic"])
        self.assertEqual(item["review"], answer())
        self.assertNotIn("PRIVATE_", json.dumps(result))
        other = review.reviewer_projection(state, "reviewer-b")
        self.assertNotEqual(item["itemId"], other["items"][0]["itemId"])
        result["items"][0]["prompt"]["phones"].append("T")
        result["items"][0]["review"]["notes"] = "Mutated"
        self.assertEqual(state["manifest"]["prompts"][0]["variants"][0]["phones"], ["S", "AH1", "N"])
        self.assertEqual(state["reviews"]["reviewer-a"]["attempt"]["answer"]["notes"], "Invented review.")

    def test_missing_permissions_and_current_withdrawal_block_recording_access(self):
        for restriction in ("denied", "unknown", "manifest-withdrawn", "current-withdrawn", "no-recording"):
            with self.subTest(restriction=restriction):
                state = aggregate()
                attempt = state["manifest"]["attempts"][0]
                if restriction in {"denied", "unknown"}:
                    attempt["permissions"]["review"] = restriction
                elif restriction == "manifest-withdrawn":
                    attempt["permissions"]["withdrawn"] = True
                elif restriction == "current-withdrawn":
                    state["withdrawals"] = [{"participantId": "PRIVATE_PARTICIPANT", "reason": "PRIVATE_REASON"}]
                else:
                    attempt["recording"] = None
                result = review.reviewer_projection(state, "reviewer-a")
                self.assertFalse(result["items"][0]["recordingAvailable"])
                self.assertIsNone(result["items"][0]["review"])
                self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_unknown_reviewer_never_gets_coordinator_state_or_private_error(self):
        with self.assertRaises(ValidationError) as error:
            review.reviewer_projection(aggregate(), "PRIVATE_SOURCE_PATH")
        self.assertEqual(str(error.exception), "reviewer_id")

    def test_adjudicator_receives_originals_only_after_both_batches_are_sealed(self):
        state = aggregate()
        first, second = answer(), answer(target="altered")
        state["reviews"]["reviewer-a"]["attempt"] = {"answer": first, "sha256": semantic_digest(first)}
        state["reviews"]["reviewer-b"]["attempt"] = {"answer": second, "sha256": semantic_digest(second)}
        state["seals"]["reviewer-a"] = True
        before = review.adjudicator_projection(state)
        self.assertEqual(before["items"], [])
        state["seals"]["reviewer-b"] = True
        result = review.adjudicator_projection(state)
        self.assertEqual(set(result), {"project", "items", "seals"})
        self.assertEqual(result["items"], [{"attemptId": "attempt", "prompt": {
                                          "word": "sun", "targetPhone": "S", "variantId": "variant",
                                          "phones": ["S", "AH1", "N"], "occurrenceIndex": 0},
                                          "reviewA": state["reviews"]["reviewer-a"]["attempt"],
                                          "reviewB": state["reviews"]["reviewer-b"]["attempt"], "adjudication": None}])
        self.assertNotIn("PRIVATE_", json.dumps(result))
        result["items"][0]["reviewA"]["answer"]["notes"] = "Changed"
        result["seals"]["reviewer-a"] = False
        self.assertEqual(first["notes"], "Invented review.")
        self.assertTrue(state["seals"]["reviewer-a"])

    def test_adjudicator_distinguishes_both_r_occurrences_and_preserves_unresolved_selection(self):
        state = aggregate()
        prompt = state["manifest"]["prompts"][0]
        prompt.update(word="rural", targetPhone="R", variants=[{
            "id": "rural-variant", "phones": ["R", "UH1", "R", "AH0", "L"], "occurrenceIndexes": [0, 2]}])
        first = state["manifest"]["attempts"][0]
        first.update(variantId="rural-variant", occurrenceIndex=0)
        second = {**copy.deepcopy(first), "id": "second-r", "occurrenceIndex": 2}
        unresolved = {**copy.deepcopy(first), "id": "unresolved-r", "occurrenceIndex": None}
        state["manifest"]["attempts"] = [first, second, unresolved]
        state["manifest"] = bind_manifest(state["manifest"])
        for reviewer in ("reviewer-a", "reviewer-b"):
            for attempt_id in ("attempt", "second-r", "unresolved-r"):
                original = answer()
                state["reviews"][reviewer][attempt_id] = {"answer": original, "sha256": semantic_digest(original)}
            state["seals"][reviewer] = True
        result = review.adjudicator_projection(state)
        self.assertEqual([item["prompt"] for item in result["items"]], [
            {"word": "rural", "targetPhone": "R", "variantId": "rural-variant",
             "phones": ["R", "UH1", "R", "AH0", "L"], "occurrenceIndex": occurrence}
            for occurrence in (0, 2, None)])
        self.assertNotIn("PRIVATE_", json.dumps(result))
        result["items"][0]["prompt"]["phones"][0] = "T"
        self.assertEqual(state["manifest"]["prompts"][0]["variants"][0]["phones"], ["R", "UH1", "R", "AH0", "L"])
        self.assertEqual(result["items"][1]["prompt"]["phones"][0], "R")


class AdjudicationTests(unittest.TestCase):
    def test_adjudication_names_the_exact_unchanged_originals(self):
        state = aggregate()
        first, second = answer(), answer(target="altered")
        state["reviews"]["reviewer-a"]["attempt"] = {"answer": first, "sha256": semantic_digest(first)}
        state["reviews"]["reviewer-b"]["attempt"] = {"answer": second, "sha256": semantic_digest(second)}
        decision = {"target": "altered", "notes": "Invented adjudication after replay.",
                    "reviewedOriginals": [semantic_digest(first), semantic_digest(second)]}
        with self.assertRaises(ValidationError):
            review.validate_adjudication(state, "attempt", decision)
        state["seals"] = {"reviewer-a": True, "reviewer-b": True}
        before = copy.deepcopy(state)
        validated = review.validate_adjudication(state, "attempt", decision)
        self.assertEqual(validated, decision)
        self.assertEqual(state, before)
        validated["reviewedOriginals"][0] = "0" * 64
        self.assertEqual(decision["reviewedOriginals"][0], semantic_digest(first))
        for bad in ({**decision, "reviewedOriginals": list(reversed(decision["reviewedOriginals"]))},
                    {**decision, "notes": " "}, {**decision, "notes": "x" * 2001},
                    {**decision, "target": "correct"}, {**decision, "reviewerId": "reviewer-a"},
                    {**decision, "reviewedOriginals": [decision["reviewedOriginals"][0]]}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                review.validate_adjudication(state, "attempt", bad)

    def test_missing_or_forged_original_digest_has_no_inferred_fallback(self):
        state = aggregate()
        state["seals"] = {"reviewer-a": True, "reviewer-b": True}
        first = answer()
        decision = {"target": "expected", "notes": "Invented adjudication.",
                    "reviewedOriginals": [semantic_digest(first), semantic_digest(first)]}
        state["reviews"]["reviewer-a"]["attempt"] = {"answer": first, "sha256": semantic_digest(first)}
        for record in (None, {"answer": first}, {"answer": first, "sha256": "0" * 64}):
            if record is None:
                state["reviews"]["reviewer-b"] = {}
            else:
                state["reviews"]["reviewer-b"]["attempt"] = record
            with self.subTest(record=record), self.assertRaises(ValidationError):
                review.validate_adjudication(state, "attempt", decision)

    def test_adjudicator_projection_retains_decision_and_rejects_record_metadata(self):
        state = aggregate()
        original = answer()
        for reviewer in ("reviewer-a", "reviewer-b"):
            state["reviews"][reviewer]["attempt"] = {"answer": original, "sha256": semantic_digest(original)}
            state["seals"][reviewer] = True
        decision = {"target": "expected", "notes": "Invented resolution.",
                    "reviewedOriginals": [semantic_digest(original), semantic_digest(original)]}
        state["adjudications"]["attempt"] = {"answer": decision, "sha256": semantic_digest(decision)}
        result = review.adjudicator_projection(state)
        result["items"][0]["adjudication"]["answer"]["notes"] = "Changed"
        self.assertEqual(decision["notes"], "Invented resolution.")
        state["adjudications"]["attempt"]["sourcePath"] = "PRIVATE_SOURCE_PATH"
        with self.assertRaises(ValidationError) as error:
            review.adjudicator_projection(state)
        self.assertEqual(str(error.exception), "adjudication_record")


class PredictionTests(unittest.TestCase):
    def test_locked_payload_keeps_every_attempt_including_recording_absence(self):
        manifest = aggregate()["manifest"]
        absent = copy.deepcopy(manifest["attempts"][0])
        absent.update(id="absent", recording=None, terminal="cancelled")
        manifest["attempts"].append(absent)
        manifest = bind_manifest(manifest)
        payload = predictions(manifest)
        payload["rows"][1] = {"attemptId": "absent", "contextSha256": semantic_digest(absent["context"]),
                              "status": "unavailable", "reason": "recording_unavailable"}
        original = copy.deepcopy(payload)
        digest = semantic_digest(payload)
        locked = review.validate_prediction_lock(manifest, payload, digest)
        self.assertEqual(locked, {"payload": original, "sha256": digest})
        locked["payload"]["rows"][0]["probabilities"][0] = 0.9
        self.assertEqual(payload, original)
        with self.assertRaises(ValidationError):
            review.validate_prediction_lock(manifest, payload, "0" * 64)

    def test_prediction_import_rejects_roster_and_semantic_context_substitution(self):
        manifest = aggregate()["manifest"]
        original = predictions(manifest)
        variants = []
        for replacement in ([], [original["rows"][0], original["rows"][0]],
                            [{**original["rows"][0], "attemptId": "extra"}],
                            [{**original["rows"][0], "contextSha256": "0" * 64}]):
            variants.append({**original, "rows": replacement})
        variants.append({**original, "model": {**original["model"], "manifestSha256": "0" * 64}})
        for payload in variants:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                review.validate_prediction_lock(manifest, payload, semantic_digest(payload))

    def test_prediction_vectors_and_failure_rows_are_strict_and_finite(self):
        manifest = aggregate()["manifest"]
        original = predictions(manifest)
        for vector in ([True, 0, 0], [1, 0], [1.1, 0, -0.1], [0.4, 0.2, 0.2], ["1", 0, 0],
                       [float("nan"), 0, 0], [float("inf"), 0, 0]):
            payload = copy.deepcopy(original)
            payload["rows"][0]["probabilities"] = vector
            with self.subTest(vector=vector), self.assertRaises(ValidationError):
                review.validate_prediction_lock(manifest, payload, "a" * 64 if any(
                    type(value) is float and not math.isfinite(value) for value in vector
                ) else semantic_digest(payload))
        for changes in ({"status": "invented"}, {"reason": "PRIVATE_SOURCE_PATH"},
                        {"status": "failed", "reason": "PRIVATE_SOURCE_PATH"}, {"score": 0.99}):
            payload = copy.deepcopy(original)
            payload["rows"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                review.validate_prediction_lock(manifest, payload, semantic_digest(payload))
        for status, reason in (("failed", "processing_failed"), ("unavailable", "permission_denied")):
            payload = copy.deepcopy(original)
            payload["rows"][0].pop("probabilities")
            payload["rows"][0].update(status=status, reason=reason)
            self.assertEqual(review.validate_prediction_lock(manifest, payload, semantic_digest(payload))["payload"], payload)

    def test_prediction_schema_and_model_do_not_claim_other_output_meanings(self):
        manifest = aggregate()["manifest"]
        original = predictions(manifest)
        payloads = [{**original, "schemaVersion": True}, {**original, "schemaVersion": 2},
                    {**original, "filename": "PRIVATE_FILENAME"}]
        for changes in ({"meaning": "pronunciation_accuracy"}, {"id": "../PRIVATE_MODEL"},
                        {"version": ""}, {"preprocessingSha256": "invalid"}, {"qualified": True}):
            payloads.append({**original, "model": {**original["model"], **changes}})
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError) as error:
                    review.validate_prediction_lock(manifest, payload, semantic_digest(payload))
                self.assertNotIn("PRIVATE_", str(error.exception))
        for expected in (None, "", "PRIVATE_SOURCE_PATH", True):
            with self.subTest(expected=expected), self.assertRaises(ValidationError):
                review.validate_prediction_lock(manifest, original, expected)


if __name__ == "__main__":
    unittest.main()
