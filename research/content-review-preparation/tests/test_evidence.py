import unittest
import copy
import tempfile
from pathlib import Path

from content_review import evidence
from content_review.packet import compile_packet, load_pack_bytes, source_manifest
from workbench.domain import semantic_digest
from workbench.store import Store
from workbench.demo import make_manifest


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.packet = compile_packet(load_pack_bytes())

    def complete_declarations(self, mode="invented_exercise"):
        declarations = evidence.evidence_template(self.packet)
        declarations["mode"] = mode
        for prompt in declarations["prompts"]:
            prompt["decision"] = "engineering_prepared"
            prompt["fields"] = {code: "Invented declaration; not verified." for code in prompt["fields"]}
            for variant in prompt["variants"]:
                for occurrence in variant["occurrences"]:
                    occurrence["rule"] = "Invented rule for this retained occurrence."
        return declarations

    def test_template_retains_every_variant_and_target_occurrence_as_pending(self):
        template = evidence.evidence_template(self.packet)
        self.assertEqual(set(template), {"schemaVersion", "kind", "sourcePackSha256", "packetSha256", "mode", "claimLimits", "prompts"})
        self.assertEqual(template["packetSha256"], semantic_digest(self.packet))
        self.assertEqual(template["mode"], "preparation")
        self.assertEqual(len(template["prompts"]), 15)
        self.assertTrue(all(prompt["decision"] == "pending" and prompt["notes"] == ""
                            and all(value is None for value in prompt["fields"].values())
                            for prompt in template["prompts"]))
        variants = [variant for prompt in template["prompts"] for variant in prompt["variants"]]
        occurrences = [occurrence for variant in variants for occurrence in variant["occurrences"]]
        self.assertEqual((len(variants), len(occurrences), sum(occurrence["isSelectedPosition"] for occurrence in occurrences)), (17, 23, 18))
        self.assertTrue(all(occurrence["rule"] is None for occurrence in occurrences))
        banana = next(prompt for prompt in template["prompts"] if prompt["promptId"] == "n-middle-banana")
        self.assertEqual(banana["variants"][0]["occurrences"], [
            {"index": 2, "isSelectedPosition": True, "rule": None},
            {"index": 4, "isSelectedPosition": True, "rule": None}])
        self.assertTrue(all(value is False for value in template["claimLimits"].values()))

    def test_pending_declarations_report_missing_fields_and_every_occurrence(self):
        template = evidence.evidence_template(self.packet)
        result = evidence.check_evidence(self.packet, template)
        self.assertEqual(result["status"], "pending_declarations")
        self.assertEqual(result["counts"], {"prompts": 15, "variants": 17, "allTargetOccurrences": 23,
                                           "selectedPositionOccurrences": 18, "completePromptDeclarations": 0,
                                           "pendingPromptDeclarations": 15})
        banana = next(prompt for prompt in result["promptResults"] if prompt["promptId"] == "n-middle-banana")
        self.assertEqual(banana["missingOccurrenceRules"], [{"variantId": "variant-1", "index": 2},
                                                           {"variantId": "variant-1", "index": 4}])
        self.assertEqual(len(banana["missingFields"]), 11)
        self.assertFalse(banana["declarationComplete"])
        self.assertTrue(all(value is False for value in result["claimLimits"].values()))

    def test_complete_invented_or_unsafe_declarations_never_establish_approval_rights_or_reference_bytes(self):
        for mode, status in (("invented_exercise", "complete_invented_declaration_exercise"),
                             ("preparation", "complete_unverified_preparation_declarations")):
            declarations = self.complete_declarations(mode)
            for prompt in declarations["prompts"]:
                prompt["fields"]["reference_rights"] = "Rights denied or unknown; no use authorized."
                prompt["fields"]["reference_provenance"] = "PRIVATE_REFERENCE_PATH; declaration only, do not open."
            unsupported = next(prompt for prompt in declarations["prompts"] if prompt["promptId"] == "zh-middle-treasure")
            unsupported["fields"]["reference_scope"] = "Unsupported target; reference scope unavailable."
            result = evidence.check_evidence(self.packet, declarations)
            self.assertEqual(result["status"], status)
            self.assertEqual(result["counts"]["completePromptDeclarations"], 15)
            self.assertTrue(all(value is False for value in result["claimLimits"].values()))
            self.assertNotIn("PRIVATE_REFERENCE_PATH", str(result))

    def test_prepared_decision_does_not_hide_missing_field_or_occurrence_rule(self):
        declarations = self.complete_declarations()
        declarations["prompts"][0]["fields"]["adult_support"] = None
        declarations["prompts"][0]["variants"][0]["occurrences"][0]["rule"] = None
        result = evidence.check_evidence(self.packet, declarations)
        self.assertEqual(result["status"], "pending_declarations")
        self.assertEqual(result["counts"]["pendingPromptDeclarations"], 1)
        self.assertEqual(result["promptResults"][0]["missingFields"], ["adult_support"])
        self.assertEqual(result["promptResults"][0]["missingOccurrenceRules"], [{"variantId": "variant-1", "index": 0}])

    def test_full_text_with_pending_or_revision_decision_remains_incomplete(self):
        declarations = self.complete_declarations("preparation")
        for decision in ("pending", "needs_revision"):
            declarations["prompts"][0]["decision"] = decision
            result = evidence.check_evidence(self.packet, declarations)
            first = result["promptResults"][0]
            self.assertEqual(first["missingFields"], [])
            self.assertEqual(first["missingOccurrenceRules"], [])
            self.assertFalse(first["declarationComplete"])
            self.assertEqual(result["status"], "pending_declarations")

    def test_declared_approval_or_rights_flags_and_stale_packet_pins_are_rejected(self):
        template = evidence.evidence_template(self.packet)
        for changes in ({"packetSha256": "0" * 64}, {"sourcePackSha256": "0" * 64},
                        {"schemaVersion": True}, {"schemaVersion": 2}, {"mode": "approved"},
                        {"kind": "qualified-content"}, {"unknown": True},
                        {"claimLimits": {**template["claimLimits"], "rightsVerified": True}},
                        {"claimLimits": {**template["claimLimits"], "qualifiedApprovalEstablished": True}}):
            with self.subTest(changes=changes), self.assertRaises(evidence.EvidenceError):
                evidence.check_evidence(self.packet, {**template, **changes})

    def test_exact_prompt_variant_occurrence_rosters_and_identities_cannot_be_substituted(self):
        original = evidence.evidence_template(self.packet)
        mutations = []
        missing = copy.deepcopy(original)
        missing["prompts"].pop()
        mutations.append(missing)
        duplicate = copy.deepcopy(original)
        duplicate["prompts"][-1] = copy.deepcopy(duplicate["prompts"][0])
        mutations.append(duplicate)
        unknown = copy.deepcopy(original)
        unknown["prompts"][0]["promptId"] = "PRIVATE_FOREIGN_PROMPT"
        mutations.append(unknown)
        for changes in ({"variantId": "unknown"}, {"phonesSha256": "0" * 64}, {"extra": "PRIVATE_PATH"}):
            changed = copy.deepcopy(original)
            changed["prompts"][0]["variants"][0].update(changes)
            mutations.append(changed)
        missing_variant = copy.deepcopy(original)
        missing_variant["prompts"][0]["variants"].pop()
        mutations.append(missing_variant)
        duplicate_variant = copy.deepcopy(original)
        duplicate_variant["prompts"][0]["variants"][1] = copy.deepcopy(duplicate_variant["prompts"][0]["variants"][0])
        mutations.append(duplicate_variant)
        for changes in ({"index": True}, {"index": 999}, {"isSelectedPosition": 1},
                        {"isSelectedPosition": False}, {"extra": "PRIVATE_PATH"}):
            changed = copy.deepcopy(original)
            changed["prompts"][0]["variants"][0]["occurrences"][0].update(changes)
            mutations.append(changed)
        missing_rule = copy.deepcopy(original)
        next(prompt for prompt in missing_rule["prompts"] if prompt["promptId"] == "n-middle-banana")["variants"][0]["occurrences"].pop()
        mutations.append(missing_rule)
        duplicate_rule = copy.deepcopy(original)
        banana = next(prompt for prompt in duplicate_rule["prompts"] if prompt["promptId"] == "n-middle-banana")
        banana["variants"][0]["occurrences"][1] = copy.deepcopy(banana["variants"][0]["occurrences"][0])
        mutations.append(duplicate_rule)
        for index, changed in enumerate(mutations):
            with self.subTest(case=index), self.assertRaises(evidence.EvidenceError):
                evidence.check_evidence(self.packet, changed)

    def preparation_bundle(self, records=()):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store.create(Path(temporary) / "prepared", source_manifest())
            for prompt_id, record in records:
                store.record_content_review(prompt_id, record)
            return store.export_bundle()

    def test_real_preparation_export_retains_original_decisions_without_approval_or_authentication(self):
        accepted = {"reviewerId": "fictional-coordinator", "decision": "accepted",
                    "notes": "Invented engineering review; no professional approval.",
                    "reference": {"id": "invented-reference", "version": "v1", "sha256": "0" * 64, "rights": "unknown"}}
        revised = {**accepted, "decision": "revise", "reference": {**accepted["reference"], "rights": "denied"}}
        pending = {**accepted, "decision": "pending", "reference": None}
        bundle = self.preparation_bundle((("r-beginning-rabbit", accepted),
                                          ("r-beginning-rabbit", revised), ("zh-middle-treasure", pending)))
        original = copy.deepcopy(bundle)
        result = evidence.import_preparation_export(self.packet, bundle)
        self.assertEqual(set(result), {"sourcePackSha256", "packetSha256", "projectId", "sourceRevision",
                                       "sourceExportSha256", "replayVerified", "authenticationEstablished",
                                       "qualifiedApprovalEstablished", "records"})
        self.assertEqual(result["sourceRevision"], 3)
        self.assertEqual(result["sourceExportSha256"], bundle["sha256"])
        self.assertTrue(result["replayVerified"])
        self.assertFalse(result["authenticationEstablished"])
        self.assertFalse(result["qualifiedApprovalEstablished"])
        self.assertEqual([record["engineeringDecision"] for record in result["records"]], ["accepted", "revise", "pending"])
        self.assertEqual([record["referenceDeclaration"] for record in result["records"]],
                         [accepted["reference"], revised["reference"], None])
        self.assertTrue(all(record["recordedByAccount"] == "fictional-coordinator" for record in result["records"]))
        result["records"][0]["referenceDeclaration"]["rights"] = "allowed"
        self.assertEqual(bundle, original)
        empty = evidence.import_preparation_export(self.packet, self.preparation_bundle())
        self.assertEqual(empty["records"], [])
        self.assertEqual(empty["sourceRevision"], 0)

    def test_declaration_roster_order_does_not_change_source_order_diagnostics(self):
        original = evidence.evidence_template(self.packet)
        reordered = copy.deepcopy(original)
        reordered["prompts"].reverse()
        for prompt in reordered["prompts"]:
            prompt["variants"].reverse()
            for variant in prompt["variants"]:
                variant["occurrences"].reverse()
        self.assertEqual(evidence.check_evidence(self.packet, reordered),
                         evidence.check_evidence(self.packet, original))

    def test_export_rejects_valid_demo_foreign_source_and_irrelevant_empty_seal_history(self):
        foreign = source_manifest()
        foreign["title"] = "Foreign preparation manifest"
        manifests = (make_manifest(), foreign)
        for index, manifest in enumerate(manifests):
            with tempfile.TemporaryDirectory() as temporary:
                store = Store.create(Path(temporary) / "project", manifest)
                bundle = store.export_bundle()
            with self.subTest(case=index), self.assertRaises(evidence.EvidenceError) as error:
                evidence.import_preparation_export(self.packet, bundle)
            self.assertEqual(error.exception.code, "invalid_preparation_export")
        with tempfile.TemporaryDirectory() as temporary:
            store = Store.create(Path(temporary) / "project", source_manifest())
            store.seal_reviews("reviewer-a")
            bundle = store.export_bundle()
        with self.assertRaises(evidence.EvidenceError):
            evidence.import_preparation_export(self.packet, bundle)

    def test_export_tampering_cannot_replace_initial_manifest_or_evade_frozen_replay(self):
        record = {"reviewerId": "fictional-coordinator", "decision": "pending", "notes": "Unverified.", "reference": None}
        original = self.preparation_bundle((("r-beginning-rabbit", record),))
        mutations = []
        changed = copy.deepcopy(original)
        changed["events"][0]["payload"]["title"] = "PRIVATE_FOREIGN_SOURCE"
        mutations.append(changed)
        changed = copy.deepcopy(original)
        changed["aggregate"]["manifest"]["attempts"] = [{"recording": {"path": "PRIVATE_MEDIA_PATH"}}]
        mutations.append(changed)
        changed = copy.deepcopy(original)
        changed["aggregate"]["contentReviews"][0]["record"]["decision"] = "accepted"
        mutations.append(changed)
        changed = copy.deepcopy(original)
        changed["events"][1]["payload"]["record"]["notes"] = "Rehashed event but inconsistent aggregate"
        changed["events"][1]["sha256"] = semantic_digest({key: value for key, value in changed["events"][1].items() if key != "sha256"})
        mutations.append(changed)
        changed = copy.deepcopy(original)
        changed["report"]["PRIVATE_UNKNOWN_REPORT"] = True
        mutations.append(changed)
        for changes in ({"kind": "review"}, {"seq": True}, {"payload": {"promptId": "unknown", "record": record}},
                        {"payload": {"promptId": "r-beginning-rabbit", "record": {**record, "qualified": True}}},
                        {"payload": {"promptId": "r-beginning-rabbit", "record": {**record, "decision": "approved"}}},
                        {"payload": {"promptId": "r-beginning-rabbit", "record": {**record, "reference": {"path": "PRIVATE_MEDIA_PATH"}}}}):
            changed = copy.deepcopy(original)
            changed["events"][1].update(changes)
            mutations.append(changed)
        for index, changed in enumerate(mutations):
            changed["sha256"] = semantic_digest({key: value for key, value in changed.items() if key != "sha256"})
            with self.subTest(case=index), self.assertRaises(evidence.EvidenceError) as error:
                evidence.import_preparation_export(self.packet, changed)
            self.assertEqual(str(error.exception), "invalid_preparation_export")
            self.assertNotIn("PRIVATE", str(error.exception))

    def test_export_exact_schema_types_and_stale_packet_reject_without_raw_errors(self):
        original = self.preparation_bundle()
        mutations = [None, [], {}, {**original, "schemaVersion": True}, {**original, "events": []},
                     {**original, "events": {}}, {**original, "extra": "PRIVATE_UNKNOWN"},
                     {**original, "aggregate": []}, {**original, "sha256": []}]
        for changes in ({"reviews": None}, {"contentReviews": {}}, {"seals": {"reviewer-a": 0, "reviewer-b": False}}):
            mutations.append({**original, "aggregate": {**original["aggregate"], **changes}})
        for index, changed in enumerate(mutations):
            with self.subTest(case=index), self.assertRaises(evidence.EvidenceError) as error:
                evidence.import_preparation_export(self.packet, changed)
            self.assertEqual(error.exception.code, "invalid_preparation_export")
        stale = copy.deepcopy(self.packet)
        stale["sourceManifestSha256"] = "0" * 64
        for operation in (lambda: evidence.evidence_template(stale),
                          lambda: evidence.check_evidence(stale, evidence.evidence_template(self.packet)),
                          lambda: evidence.import_preparation_export(stale, original)):
            with self.assertRaises(evidence.EvidenceError) as error:
                operation()
            self.assertEqual(error.exception.code, "invalid_packet")

    def test_notes_fields_and_rules_must_be_bounded_unambiguous_storable_text(self):
        original = evidence.evidence_template(self.packet)
        mutations = []
        for value in ("", "  ", "x" * 1001, True, 10, [], "\ud800", "embedded\x00control"):
            for location in ("field", "rule"):
                changed = copy.deepcopy(original)
                if location == "field":
                    changed["prompts"][0]["fields"]["reference_rights"] = value
                else:
                    changed["prompts"][0]["variants"][0]["occurrences"][0]["rule"] = value
                mutations.append(changed)
        for value in ("x" * 2001, None, True, [], "\ud800", "embedded\x00control"):
            changed = copy.deepcopy(original)
            changed["prompts"][0]["notes"] = value
            mutations.append(changed)
        for changes in ({"decision": "approved"}, {"decision": []}, {"qualified": True}):
            changed = copy.deepcopy(original)
            changed["prompts"][0].update(changes)
            mutations.append(changed)
        for index, changed in enumerate(mutations):
            with self.subTest(case=index), self.assertRaises(evidence.EvidenceError):
                evidence.check_evidence(self.packet, changed)


if __name__ == "__main__":
    unittest.main()
