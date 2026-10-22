from pathlib import Path
import copy
import json
import os
import time
import tempfile
import unittest

from review_service.audit import Audit
from review_service.auth import AuthStore
from review_service.fixtures import fixture_manifest
from workbench.domain import ValidationError, semantic_digest
from workbench.store import Store


class AuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "service"
        self.root.mkdir(mode=0o700)
        self.auth = AuthStore.create(self.root)
        shared_lock = self.auth.lock()
        shared_lock.__enter__()
        self.addCleanup(shared_lock.__exit__, None, None, None)
        self.store = Store.create(self.root / "project", fixture_manifest())
        self.audit = Audit.create(self.root, {"demo-review": self.head()["sha256"]})
        self.actor = {"accountId": "fixture-coordinator", "generation": 1}

    def head(self):
        return self.store.export_bundle()["events"][-1]

    def intent(self, participant="person-a", reason="Invented restriction."):
        payload = {"participantId": participant, "reason": reason}
        return self.audit.intent(self.actor, "demo-review", "coordinator", "withdraw", participant,
                                 self.head(), "withdrawal", payload)

    def replace_journal(self, records):
        previous = None
        for seq, record in enumerate(records):
            record.update(seq=seq, previousSha256=previous)
            record["sha256"] = semantic_digest({key: value for key, value in record.items() if key != "sha256"})
            previous = record["sha256"]
        (self.root / "access.jsonl").write_bytes(b"".join(
            json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
            for record in records))

    def test_invalid_append_leaves_journal_bytes_and_history_unchanged(self):
        journal = self.root / "access.jsonl"
        before = journal.read_bytes()
        payload = {"accountId": "fixture-coordinator", "projectId": "demo-review", "role": "unrecognized",
                   "action": "state_read", "objectId": None, "outcome": "authorized"}
        with self.assertRaises(ValidationError):
            self.audit.append("access", payload)
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual(len(self.audit.records()), 1)

    def test_malformed_schema_types_have_fixed_errors_and_no_append(self):
        intent = self.intent()
        access = {"accountId": None, "projectId": None, "role": None, "action": "access_denied",
                  "objectId": None, "outcome": "denied"}
        result = {"operationId": intent["operationId"], "status": "not_applied", "eventSha256": None, "recovered": False}
        variants = [("access", {**access, "role": []}), ("access", {**access, "action": {}}),
                    ("access", {**access, "outcome": []}), ("access", {**access, "accountId": float("nan")}),
                    ("access", {**access, "objectId": "\ud800"}), ("intent", {**intent, "role": []}),
                    ("intent", {**intent, "expectedKind": {}}), ("intent", {**intent, "generation": True}),
                    ("result", {**result, "operationId": []}), ("result", {**result, "status": []}),
                    ("result", {**result, "recovered": 1}), ([], access), ("access", None)]
        before = (self.root / "access.jsonl").read_bytes()
        for kind, payload in variants:
            with self.subTest(kind=kind, payload=payload):
                with self.assertRaises(ValidationError) as error:
                    self.audit.append(kind, payload)
                self.assertEqual(str(error.exception), "access_audit_invalid")
                self.assertEqual((self.root / "access.jsonl").read_bytes(), before)
                self.assertEqual(len(self.audit.records()), 2)

    def test_intent_without_store_append_recovers_not_applied_once(self):
        intent = self.intent()
        self.assertEqual(self.store.revision, 0)
        result = self.audit.reconcile({"demo-review": self.store})
        self.assertEqual(result, {"verified": True, "sourceRevisions": {"demo-review": 0},
                                  "authenticityEstablished": False})
        receipts = [record["payload"] for record in self.audit.records() if record["kind"] == "result"]
        self.assertEqual(receipts, [{"operationId": intent["operationId"], "status": "not_applied",
                                    "eventSha256": None, "recovered": True}])
        before = (self.root / "access.jsonl").read_bytes()
        self.audit.reconcile({"demo-review": self.store})
        self.assertEqual((self.root / "access.jsonl").read_bytes(), before)

    def test_committed_store_append_without_result_recovers_applied_exactly_once(self):
        intent = self.intent()
        self.store.withdraw("person-a", "Invented restriction.")
        event = self.head()
        self.assertEqual(self.audit.reconcile({"demo-review": self.store})["sourceRevisions"], {"demo-review": 1})
        receipts = [record["payload"] for record in self.audit.records() if record["kind"] == "result"]
        self.assertEqual(receipts, [{"operationId": intent["operationId"], "status": "applied",
                                    "eventSha256": event["sha256"], "recovered": True}])
        before = (self.root / "access.jsonl").read_bytes()
        Audit(self.root).reconcile({"demo-review": Store.open(self.store.path)})
        self.assertEqual((self.root / "access.jsonl").read_bytes(), before)
        self.assertEqual(self.store.revision, 1)

    def test_unexpected_source_event_quarantines_without_inferred_receipt(self):
        self.intent()
        self.store.withdraw("person-b", "Foreign source event.")
        before = (self.root / "access.jsonl").read_bytes()
        with self.assertRaisesRegex(ValidationError, "^project_quarantined$"):
            self.audit.reconcile({"demo-review": self.store})
        self.assertEqual((self.root / "access.jsonl").read_bytes(), before)

    def test_foreign_event_after_expected_commit_quarantines_before_recovery_append(self):
        self.intent()
        self.store.withdraw("person-a", "Invented restriction.")
        self.store.withdraw("person-b", "Foreign source event.")
        before = (self.root / "access.jsonl").read_bytes()
        with self.assertRaisesRegex(ValidationError, "^project_quarantined$"):
            self.audit.reconcile({"demo-review": self.store})
        self.assertEqual((self.root / "access.jsonl").read_bytes(), before)

    def test_partial_receipt_quarantines_without_changing_source_or_audit_bytes(self):
        self.intent()
        self.store.withdraw("person-a", "Invented restriction.")
        journal = self.root / "access.jsonl"
        with journal.open("ab") as stream:
            stream.write(b'{"seq":2')
        before = journal.read_bytes()
        with self.assertRaisesRegex(ValidationError, "^project_quarantined$"):
            self.audit.reconcile({"demo-review": self.store})
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual(self.store.revision, 1)

    def test_fifo_journal_fails_without_waiting_for_peer(self):
        journal = self.root / "access.jsonl"
        journal.unlink()
        os.mkfifo(journal, 0o600)
        started = time.monotonic()
        with self.assertRaisesRegex(ValidationError, "^access_audit_invalid$"):
            self.audit.records()
        self.assertLess(time.monotonic() - started, 1)

    def test_utf16_receipt_bytes_are_not_accepted_as_a_utf8_journal(self):
        header = self.audit.records()[0]
        (self.root / "access.jsonl").write_bytes(json.dumps(header).encode("utf-16") + b"\n")
        with self.assertRaisesRegex(ValidationError, "^access_audit_invalid$"):
            self.audit.records()

    def test_completed_history_including_aborted_intent_stays_exact_and_idempotent(self):
        aborted = self.intent()
        self.audit.result(aborted)
        for participant in ("person-a", "person-b"):
            intent = self.intent(participant)
            self.store.withdraw(participant, "Invented restriction.")
            self.audit.result(intent, self.head())
        self.audit.access(self.actor, "demo-review", "coordinator", "state_read", allowed=True)
        before = (self.root / "access.jsonl").read_bytes()
        result = self.audit.reconcile({"demo-review": self.store})
        self.assertEqual(result["sourceRevisions"], {"demo-review": 2})
        self.assertFalse(result["authenticityEstablished"])
        self.assertEqual((self.root / "access.jsonl").read_bytes(), before)
        receipts = [record["payload"] for record in self.audit.records() if record["kind"] == "result"]
        self.assertEqual([record["status"] for record in receipts], ["not_applied", "applied", "applied"])
        self.assertTrue(all(record["recovered"] is False for record in receipts))

    def test_hash_valid_completed_receipt_and_intent_forgery_cannot_match_source_history(self):
        intent = self.intent()
        self.store.withdraw("person-a", "Invented restriction.")
        self.audit.result(intent, self.head())
        original = self.audit.records()
        mutations = [(1, "priorSha256", "0" * 64), (1, "expectedKind", "content_review"),
                     (1, "expectedPayloadSha256", "0" * 64), (2, "eventSha256", "0" * 64)]
        for index, field, value in mutations:
            with self.subTest(field=field):
                altered = copy.deepcopy(original)
                altered[index]["payload"][field] = value
                self.replace_journal(altered)
                # The hash-linked JSON schema remains valid, but source correspondence fails.
                self.assertEqual(len(self.audit.records()), 3)
                before = (self.root / "access.jsonl").read_bytes()
                with self.assertRaisesRegex(ValidationError, "^project_quarantined$"):
                    self.audit.reconcile({"demo-review": self.store})
                self.assertEqual((self.root / "access.jsonl").read_bytes(), before)

    def test_corrupt_receipt_types_or_source_journal_quarantine_fail_closed(self):
        intent = self.intent()
        self.store.withdraw("person-a", "Invented restriction.")
        self.audit.result(intent, self.head())
        original = self.audit.records()
        for changes in ({"status": []}, {"operationId": {}}, {"recovered": 1}):
            altered = copy.deepcopy(original)
            altered[-1]["payload"].update(changes)
            self.replace_journal(altered)
            with self.subTest(changes=changes), self.assertRaisesRegex(ValidationError, "^project_quarantined$"):
                self.audit.reconcile({"demo-review": self.store})
        self.replace_journal(original)
        source = self.store.path / "events.jsonl"
        source.write_bytes(source.read_bytes()[:-1])
        before = (self.root / "access.jsonl").read_bytes()
        with self.assertRaisesRegex(ValidationError, "^project_quarantined$"):
            self.audit.reconcile({"demo-review": self.store})
        self.assertEqual((self.root / "access.jsonl").read_bytes(), before)

    def test_duplicate_or_unbound_result_is_rejected_before_write(self):
        intent = self.intent()
        result = self.audit.result(intent)
        before = (self.root / "access.jsonl").read_bytes()
        for payload in (result["payload"], {**result["payload"], "operationId": "unknown-operation"}):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValidationError, "^access_audit_invalid$"):
                self.audit.append("result", payload)
            self.assertEqual((self.root / "access.jsonl").read_bytes(), before)

    def test_source_project_roster_and_initial_digest_must_match(self):
        with self.assertRaisesRegex(ValidationError, "^project_quarantined$"):
            self.audit.reconcile({"another-project": self.store})
        manifest = fixture_manifest()
        manifest["title"] = "Changed source project"
        other = Store.create(self.root / "other-project", manifest)
        with self.assertRaisesRegex(ValidationError, "^project_quarantined$"):
            self.audit.reconcile({"demo-review": other})

    def test_private_journal_symlinks_hardlinks_and_modes_are_denied(self):
        journal = self.root / "access.jsonl"
        original = self.root / "original-audit.jsonl"
        journal.rename(original)
        journal.symlink_to(original)
        with self.assertRaisesRegex(ValidationError, "^access_audit_invalid$"):
            self.audit.records()
        journal.unlink()
        os.link(original, journal)
        with self.assertRaisesRegex(ValidationError, "^access_audit_invalid$"):
            self.audit.records()
        journal.unlink()
        original.rename(journal)
        for mode in (0o644, 0o400, 0o1600):
            journal.chmod(mode)
            with self.subTest(mode=mode), self.assertRaisesRegex(ValidationError, "^access_audit_invalid$"):
                self.audit.records()
        journal.chmod(0o600)
        self.assertEqual(len(self.audit.records()), 1)


if __name__ == "__main__":
    unittest.main()
