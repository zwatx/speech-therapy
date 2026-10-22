"""Declaration completeness and pinned preparation-export inspection."""

from copy import deepcopy
import re

from workbench.domain import semantic_digest
from workbench.store import verify_export

from .packet import PacketError, source_manifest, validate_packet


class EvidenceError(PacketError):
    """Fixed safe declaration or preparation-export validation code."""


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise EvidenceError("invalid_evidence")


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise EvidenceError("invalid_evidence")


def _text(value, limit, required=False):
    if (type(value) is not str or len(value) > limit
            or (required and not value.strip())
            or any((ord(char) < 32 and char not in "\t\n\r") or 127 <= ord(char) < 160 for char in value)):
        raise EvidenceError("invalid_evidence")
    value.encode("utf-8")


def _roster(value, key, expected, fields):
    if type(value) is not list or len(value) != len(expected):
        raise EvidenceError("invalid_evidence")
    result = {}
    for record in value:
        _exact(record, fields)
        identity = record[key]
        if (type(identity) is not (int if key == "index" else str)
                or identity not in expected or identity in result):
            raise EvidenceError("invalid_evidence")
        result[identity] = record
    return result


def _packet(packet):
    try:
        validate_packet(packet)
        return deepcopy(packet)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise EvidenceError("invalid_packet") from None


def evidence_template(packet):
    """Retain every source identity and occurrence with pending declarations."""
    packet = _packet(packet)
    return {
        "schemaVersion": 1, "kind": "content-preparation-declarations",
        "sourcePackSha256": packet["sourcePackSha256"], "packetSha256": semantic_digest(packet),
        "mode": "preparation", "claimLimits": deepcopy(packet["claimLimits"]),
        "prompts": [{
            "promptId": prompt["id"], "decision": "pending", "notes": "",
            "fields": {requirement: None for requirement in prompt["requirements"]},
            "variants": [{
                "variantId": variant["id"], "phonesSha256": semantic_digest(variant["phones"]),
                "occurrences": [{"index": index, "isSelectedPosition": index in variant["selectedPositionIndexes"],
                                 "rule": None} for index in variant["allTargetIndexes"]],
            } for variant in prompt["variants"]],
        } for prompt in packet["prompts"]],
    }


def check_evidence(packet, evidence):
    """Describe declaration completeness without validating their truth or rights."""
    packet = _packet(packet)
    evidence = _validate_declarations(packet, evidence)
    declarations = {prompt["promptId"]: prompt for prompt in evidence["prompts"]}
    results = []
    for prompt in packet["prompts"]:
        declaration = declarations[prompt["id"]]
        missing_fields = [code for code in prompt["requirements"] if declaration["fields"][code] is None]
        rules = {variant["variantId"]: {occurrence["index"]: occurrence["rule"]
                                        for occurrence in variant["occurrences"]}
                 for variant in declaration["variants"]}
        missing_rules = [{"variantId": variant["id"], "index": index}
                         for variant in prompt["variants"] for index in variant["allTargetIndexes"]
                         if rules[variant["id"]][index] is None]
        results.append({"promptId": prompt["id"],
                        "declarationComplete": not missing_fields and not missing_rules and declaration["decision"] == "engineering_prepared",
                        "missingFields": missing_fields, "missingOccurrenceRules": missing_rules,
                        "decision": declaration["decision"]})
    complete = sum(result["declarationComplete"] for result in results)
    status = "pending_declarations"
    if complete == len(results):
        status = ("complete_invented_declaration_exercise" if evidence["mode"] == "invented_exercise"
                  else "complete_unverified_preparation_declarations")
    return {"schemaVersion": 1, "sourcePackSha256": packet["sourcePackSha256"],
            "packetSha256": semantic_digest(packet), "mode": evidence["mode"], "status": status,
            "counts": {key: packet["counts"][key] for key in
                       ("prompts", "variants", "allTargetOccurrences", "selectedPositionOccurrences")} |
                      {"completePromptDeclarations": complete, "pendingPromptDeclarations": len(results) - complete},
            "promptResults": results, "claimLimits": deepcopy(packet["claimLimits"]),
            "meaning": "Completeness of declarations only; no bytes, rights, identity, qualification or clinical validity verified"}


def _validate_declarations(packet, evidence):
    try:
        semantic_digest(evidence)
        _exact(evidence, ("schemaVersion", "kind", "sourcePackSha256", "packetSha256", "mode", "claimLimits", "prompts"))
        if (type(evidence["schemaVersion"]) is not int or evidence["schemaVersion"] != 1
                or evidence["kind"] != "content-preparation-declarations"
                or evidence["sourcePackSha256"] != packet["sourcePackSha256"]
                or evidence["packetSha256"] != semantic_digest(packet)):
            raise EvidenceError("invalid_evidence")
        _enum(evidence["mode"], ("preparation", "invented_exercise"))
        _exact(evidence["claimLimits"], packet["claimLimits"])
        if not all(value is False for value in evidence["claimLimits"].values()):
            raise EvidenceError("invalid_evidence")
        source_prompts = {prompt["id"]: prompt for prompt in packet["prompts"]}
        prompts = _roster(evidence["prompts"], "promptId", source_prompts,
                          ("promptId", "decision", "notes", "fields", "variants"))
        for prompt_id, prompt in prompts.items():
            source = source_prompts[prompt_id]
            _enum(prompt["decision"], ("pending", "needs_revision", "engineering_prepared"))
            _text(prompt["notes"], 2000)
            _exact(prompt["fields"], source["requirements"])
            for value in prompt["fields"].values():
                if value is not None:
                    _text(value, 1000, required=True)
            source_variants = {variant["id"]: variant for variant in source["variants"]}
            variants = _roster(prompt["variants"], "variantId", source_variants,
                               ("variantId", "phonesSha256", "occurrences"))
            for variant_id, variant in variants.items():
                source_variant = source_variants[variant_id]
                if variant["phonesSha256"] != semantic_digest(source_variant["phones"]):
                    raise EvidenceError("invalid_evidence")
                indexes = {index: index in source_variant["selectedPositionIndexes"]
                           for index in source_variant["allTargetIndexes"]}
                occurrences = _roster(variant["occurrences"], "index", indexes,
                                     ("index", "isSelectedPosition", "rule"))
                if any(type(occurrence["isSelectedPosition"]) is not bool
                       or occurrence["isSelectedPosition"] != indexes[index]
                       for index, occurrence in occurrences.items()):
                    raise EvidenceError("invalid_evidence")
                for occurrence in occurrences.values():
                    if occurrence["rule"] is not None:
                        _text(occurrence["rule"], 1000, required=True)
        return deepcopy(evidence)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise EvidenceError("invalid_evidence") from None


def _identifier(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) is None:
        raise EvidenceError("invalid_preparation_export")


def _sha(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise EvidenceError("invalid_preparation_export")


def _content_record(payload, prompt_ids):
    _exact(payload, ("promptId", "record"))
    if type(payload["promptId"]) is not str or payload["promptId"] not in prompt_ids:
        raise EvidenceError("invalid_preparation_export")
    record = payload["record"]
    _exact(record, ("reviewerId", "decision", "notes", "reference"))
    _identifier(record["reviewerId"])
    _enum(record["decision"], ("accepted", "revise", "pending"))
    _text(record["notes"], 2000)
    reference = record["reference"]
    if reference is not None:
        _exact(reference, ("id", "version", "sha256", "rights"))
        _identifier(reference["id"])
        _identifier(reference["version"])
        _sha(reference["sha256"])
        _enum(reference["rights"], ("allowed", "unknown", "denied"))


def _preflight_export(bundle, manifest):
    """Limit replay to the exact zero-attempt manifest and content declarations."""
    _exact(bundle, ("schemaVersion", "aggregate", "events", "report", "splitDiagnostics", "sha256"))
    if type(bundle["schemaVersion"]) is not int or bundle["schemaVersion"] != 1:
        raise EvidenceError("invalid_preparation_export")
    _sha(bundle["sha256"])
    aggregate = bundle["aggregate"]
    _exact(aggregate, ("manifest", "reviews", "seals", "adjudications", "contentReviews", "predictionLock", "withdrawals"))
    # Check both manifest copies before the frozen verifier can create a Store.
    expected_manifest_sha = semantic_digest(manifest)
    if semantic_digest(aggregate["manifest"]) != expected_manifest_sha:
        raise EvidenceError("invalid_preparation_export")
    inactive = {"reviews": {"reviewer-a": {}, "reviewer-b": {}},
                "seals": {"reviewer-a": False, "reviewer-b": False},
                "adjudications": {}, "predictionLock": None, "withdrawals": []}
    if semantic_digest({key: aggregate[key] for key in inactive}) != semantic_digest(inactive):
        raise EvidenceError("invalid_preparation_export")
    events = bundle["events"]
    if type(events) is not list or not events:
        raise EvidenceError("invalid_preparation_export")
    first = events[0]
    _exact(first, ("seq", "previousSha256", "kind", "payload", "sha256"))
    if (type(first["seq"]) is not int or first["seq"] != 0 or first["previousSha256"] is not None
            or first["kind"] != "project" or semantic_digest(first["payload"]) != expected_manifest_sha):
        raise EvidenceError("invalid_preparation_export")
    _sha(first["sha256"])
    prompt_ids = {prompt["id"] for prompt in manifest["prompts"]}
    previous = first["sha256"]
    for seq, event in enumerate(events[1:], 1):
        _exact(event, ("seq", "previousSha256", "kind", "payload", "sha256"))
        if (type(event["seq"]) is not int or event["seq"] != seq or event["kind"] != "content_review"
                or event["previousSha256"] != previous):
            raise EvidenceError("invalid_preparation_export")
        _sha(event["sha256"])
        _content_record(event["payload"], prompt_ids)
        previous = event["sha256"]
    if type(aggregate["contentReviews"]) is not list:
        raise EvidenceError("invalid_preparation_export")
    for payload in aggregate["contentReviews"]:
        _content_record(payload, prompt_ids)


def import_preparation_export(packet, bundle):
    """Replay a pinned preparation history; retain records as declarations only."""
    packet = _packet(packet)
    try:
        semantic_digest(bundle)
        bundle = deepcopy(bundle)
        manifest = source_manifest()
        _preflight_export(bundle, manifest)
        verified = verify_export(bundle)
        records = [{"promptId": payload["promptId"], "recordedByAccount": payload["record"]["reviewerId"],
                    "engineeringDecision": payload["record"]["decision"], "notes": payload["record"]["notes"],
                    "referenceDeclaration": deepcopy(payload["record"]["reference"])}
                   for payload in bundle["aggregate"]["contentReviews"]]
        return {"sourcePackSha256": packet["sourcePackSha256"], "packetSha256": semantic_digest(packet),
                "projectId": manifest["projectId"], "sourceRevision": verified["revision"],
                "sourceExportSha256": bundle["sha256"], "replayVerified": True,
                "authenticationEstablished": False, "qualifiedApprovalEstablished": False, "records": records}
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError, OSError):
        raise EvidenceError("invalid_preparation_export") from None
