"""Preparation-only prediction locks and local, single-attempt outcome joins.

Accepts supplied data only. No corpus access, model execution or scientific
execution authority. A caller must record the returned exact-byte digest in a
trusted external anchor before supplying outcomes. Generic descriptors may
contain caller-provided outcomes: this tool cannot establish blinding.

The join claim applies to one physical lock directory. Copies, rewritten
external anchors, authentication, signatures, trusted time, global transactions
and independent chronology are outside this API's guarantees.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path

ARM_NAMES = ("candidate", "retained", "calibration")
FLAGS = {"researchOnly": True, "clinicalUseEligible": False,
         "learnerFeedbackEligible": False, "productionUseEligible": False}
STATUS = "preparation_not_declaration"
MAX_LOCK_BYTES = 10 * 1024 * 1024
CLAIM_NAME = "outcome-join-claim.json"


def _bytes(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, OverflowError, UnicodeError, RecursionError) as error:
        raise ValueError("invalid_json_encoding") from error


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _key(row):
    return row["childId"], row["tokenId"]


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def _finite_json(value, active=None):
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) not in (list, dict):
        return False
    active = set() if active is None else active
    if id(value) in active:
        return False
    active.add(id(value))
    try:
        if type(value) is dict:
            return all(type(key) is str and _finite_json(item, active) for key, item in value.items())
        return all(_finite_json(item, active) for item in value)
    finally:
        active.remove(id(value))


def _identifier(value):
    return type(value) is str and bool(value) and value == value.strip()


def _roster(rows, child_ids):
    _require(type(rows) is list, "invalid_roster")
    seen = set()
    for row in rows:
        _require(type(row) is dict and _identifier(row.get("childId"))
                 and _identifier(row.get("tokenId")), "invalid_identity")
        key = _key(row)
        _require(key[0] in child_ids and key not in seen, "invalid_roster_membership")
        seen.add(key)
    return seen


def _validate_predictions(payload):
    try:
        _require(type(payload) is dict and _finite_json(payload), "invalid_prediction_json")
        _require(set(payload) == {"children", "selectedTokens", "arms"}, "invalid_prediction_fields")
        _require(type(payload["children"]) is list, "invalid_children")
        child_ids = set()
        for child in payload["children"]:
            _require(type(child) is dict and _identifier(child.get("childId")), "invalid_child_identity")
            _require(set(child) <= {"childId", "descriptors"}, "invalid_child_fields")
            _require("descriptors" not in child or type(child["descriptors"]) is dict, "invalid_descriptors")
            _require(child["childId"] not in child_ids, "duplicate_child")
            child_ids.add(child["childId"])
        selected = _roster(payload["selectedTokens"], child_ids)
        _require(all(set(row) == {"childId", "tokenId"} for row in payload["selectedTokens"]), "invalid_selected_fields")
        _require(type(payload["arms"]) is dict and set(payload["arms"]) == set(ARM_NAMES), "invalid_arms")
        for name in ARM_NAMES:
            _require(_roster(payload["arms"][name], child_ids) == selected, "incomplete_arm_roster")
            for row in payload["arms"][name]:
                if row.get("status") == "processed":
                    probability = row.get("probability")
                    _require(type(probability) in (int, float) and 0 <= probability <= 1
                             and math.isfinite(probability), "invalid_probability")
                    _require(set(row) == {"childId", "tokenId", "status", "probability"}, "invalid_processed_fields")
                else:
                    _require(row.get("status") in ("unavailable", "failed"), "invalid_prediction_status")
                    _require(type(row.get("reason")) is str and bool(row["reason"].strip()), "invalid_prediction_reason")
                    _require(set(row) == {"childId", "tokenId", "status", "reason"}, "invalid_terminal_fields")
        _bytes(payload)
    except (OverflowError, RecursionError, UnicodeError) as error:
        raise ValueError("invalid_prediction_json") from error
    return child_ids, selected


def _canonical_input(payload):
    result = copy.deepcopy(payload)
    result["children"].sort(key=lambda row: row["childId"])
    result["selectedTokens"].sort(key=_key)
    for rows in result["arms"].values():
        rows.sort(key=_key)
        for row in rows:
            if row["status"] == "processed":
                row["probability"] = float(row["probability"]) or 0.0
    return result


def _artifact(payload):
    membership = {"childIds": [row["childId"] for row in payload["children"]],
                  "selectedTokens": payload["selectedTokens"]}
    coverage = {"fullChildDenominator": len(payload["children"]),
                "selectedTokenDenominator": len(payload["selectedTokens"]), "children": []}
    for child in payload["children"]:
        child_id = child["childId"]
        coverage["children"].append({"childId": child_id,
            "selectedTokens": sum(row["childId"] == child_id for row in payload["selectedTokens"]),
            "arms": {arm: {status: sum(row["childId"] == child_id and row["status"] == status
                                       for row in payload["arms"][arm])
                           for status in ("processed", "unavailable", "failed")} for arm in ARM_NAMES}})
    sources = {"locking.py": _digest(Path(__file__).read_bytes())}
    return {"schemaVersion": 1, "artifactType": "prediction_lock", "status": STATUS,
            **FLAGS, "input": payload, "inputSha256": _digest(_bytes(payload)),
            "membership": membership, "membershipSha256": _digest(_bytes(membership)),
            "coverage": coverage, "sourceFiles": sources, "sourceSha256": _digest(_bytes(sources))}


class OutcomeJoinError(ValueError):
    """A failed attempt with fixed safe diagnostics and retained local paths."""
    def __init__(self, code, receipt_path=None, claim_path=None):
        super().__init__(code)
        self.code = code
        self.receipt_path = receipt_path
        self.claim_path = claim_path


def _path(value):
    try:
        path = Path(value)
        _require(".." not in path.parts, "unsafe_path")
        _require("\x00" not in str(path), "invalid_path")
        return path.absolute()
    except (TypeError, OSError) as error:
        raise ValueError("invalid_path") from error


def _open_directory(path):
    """Traverse directories without following any caller-supplied symlink."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _private_directory(fd):
    info = os.fstat(fd)
    _require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
             "unsafe_lock_directory")


def _fresh_directory(path):
    parent_fd = _open_directory(path.parent)
    fd = None
    try:
        os.mkdir(path.name, mode=0o700, dir_fd=parent_fd)
        fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        os.fchmod(fd, 0o700)
        return parent_fd, fd
    except BaseException:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)
        raise


def _cleanup_empty_directory(path, parent_fd, fd):
    """Only remove our own newly reserved, still-empty directory on claim conflict."""
    try:
        actual = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        held = os.fstat(fd)
        if (actual.st_dev, actual.st_ino) == (held.st_dev, held.st_ino):
            os.rmdir(path.name, dir_fd=parent_fd)
    except OSError:
        pass


def _write_new(directory_fd, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, "wb") as destination:
        os.fchmod(destination.fileno(), 0o600)
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())
    os.fsync(directory_fd)


def create_prediction_lock(payload, output_directory):
    """Freeze a full supplied roster; return its path and external-anchor digest.

    output_directory must be fresh. Existing directories are never merged or
    deleted; filesystem errors leave any newly created evidence in place.
    """
    _validate_predictions(payload)
    canonical = _canonical_input(payload)
    raw = _bytes(_artifact(canonical))
    _require(len(raw) <= MAX_LOCK_BYTES, "lock_too_large")
    directory = _path(output_directory)
    parent_fd = directory_fd = None
    try:
        parent_fd, directory_fd = _fresh_directory(directory)
        _write_new(directory_fd, "prediction-lock.json", raw)
        return {"lockPath": str(directory / "prediction-lock.json"), "lockSha256": _digest(raw)}
    except OSError as error:
        raise ValueError("lock_output_unavailable") from error
    finally:
        for fd in (directory_fd, parent_fd):
            if fd is not None:
                os.close(fd)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("nonfinite_lock_json")


def _read_lock(directory_fd, name, expected_sha256):
    _require(name == "prediction-lock.json", "invalid_lock_filename")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    try:
        initial = os.fstat(fd)
        _require(stat.S_ISREG(initial.st_mode) and initial.st_nlink == 1
                 and initial.st_uid == os.getuid() and stat.S_IMODE(initial.st_mode) == 0o600,
                 "unsafe_lock_file")
        _require(initial.st_size <= MAX_LOCK_BYTES, "lock_too_large")
        chunks = []
        length = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_LOCK_BYTES + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
            _require(length <= MAX_LOCK_BYTES, "lock_too_large")
        final = os.fstat(fd)
        _require((initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns)
                 == (final.st_size, final.st_mtime_ns, final.st_ctime_ns), "lock_changed_during_read")
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    _require(_digest(raw) == expected_sha256, "lock_anchor_mismatch")
    try:
        artifact = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
        _require(type(artifact) is dict and _finite_json(artifact), "invalid_lock_json")
        _validate_predictions(artifact.get("input"))
        canonical = _canonical_input(artifact["input"])
        _require(raw == _bytes(_artifact(canonical)), "invalid_lock_bindings")
    except (UnicodeError, RecursionError, OverflowError, json.JSONDecodeError) as error:
        raise ValueError("invalid_lock_json") from error
    return artifact


def _canonical_ratings(ratings, payload):
    try:
        _require(_finite_json(ratings), "invalid_rating_json")
        children = {row["childId"] for row in payload["children"]}
        selected = {_key(row) for row in payload["selectedTokens"]}
        _require(_roster(ratings, children) == selected, "incomplete_rating_roster")
        for row in ratings:
            if row.get("status") == "available":
                _require(set(row) == {"childId", "tokenId", "status", "positiveVotes", "negativeVotes"},
                         "invalid_available_rating_fields")
                counts = (row["positiveVotes"], row["negativeVotes"])
                _require(all(type(count) is int and count >= 0 for count in counts)
                         and sum(counts) > 0, "invalid_rating_votes")
                try:
                    _require(math.isfinite(sum(counts)), "invalid_rating_votes")
                except OverflowError:
                    raise ValueError("invalid_rating_votes") from None
            else:
                _require(row.get("status") == "unavailable", "invalid_rating_status")
                _require(type(row.get("reason")) is str and bool(row["reason"].strip()), "invalid_rating_reason")
                _require(set(row) == {"childId", "tokenId", "status", "reason"}, "invalid_unavailable_rating_fields")
        canonical = sorted(copy.deepcopy(ratings), key=_key)
        _bytes(canonical)
        return canonical
    except (OverflowError, RecursionError, UnicodeError) as error:
        raise ValueError("invalid_rating_json") from error


def _attempted_rating_digest(ratings):
    """Hash serializable supplied JSON in as-given array order, after the claim."""
    try:
        if _finite_json(ratings):
            return _digest(_bytes(ratings))
    except (ValueError, OverflowError, RecursionError, UnicodeError):
        pass
    return None


def _receipt(artifact, digest, status, attempted_digest, ratings_digest=None, joined_digest=None, code=None):
    return {"schemaVersion": 1, "artifactType": "outcome_join_receipt", **FLAGS,
            "status": status, "preparationStatus": STATUS, "lockSha256": digest,
            "inputSha256": artifact["inputSha256"], "membershipSha256": artifact["membershipSha256"],
            "sourceFiles": artifact["sourceFiles"], "sourceSha256": artifact["sourceSha256"],
            "attemptedRatingsSha256": attempted_digest, "ratingsSha256": ratings_digest,
            "joinedInputSha256": joined_digest, "failureCode": code}


def _set_claim(fd, digest, status, receipt_digest=None):
    raw = _bytes({"schemaVersion": 1, "artifactType": "outcome_join_claim", **FLAGS,
                  "preparationStatus": STATUS, "lockSha256": digest,
                  "status": status, "receiptSha256": receipt_digest})
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    view = memoryview(raw)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("claim_write_failed")
        view = view[written:]
    os.fsync(fd)


def join_locked_outcomes(lock_path, expected_sha256, ratings, output_directory):
    """Consume one local claim, including invalid ratings or interruption.

    Anchor/lock/output checks precede claim creation. Rating validation follows
    it, so invalid ratings leave a failed claim and failure receipt; no joined
    payload is written. A started/interrupted claim also prohibits retry.
    An output conflict does not consume a claim. A claim conflict removes only
    this call's still-empty output reservation. Existing caller files survive.
    """
    _require(type(expected_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_sha256),
             "invalid_external_anchor")
    path, output = _path(lock_path), _path(output_directory)
    lock_fd = output_fd = parent_fd = claim_fd = None
    claimed = False
    try:
        lock_fd = _open_directory(path.parent)
        _private_directory(lock_fd)
        artifact = _read_lock(lock_fd, path.name, expected_sha256)
        parent_fd, output_fd = _fresh_directory(output)
        try:
            claim_fd = os.open(CLAIM_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                               0o600, dir_fd=lock_fd)
        except FileExistsError as error:
            _cleanup_empty_directory(output, parent_fd, output_fd)
            raise OutcomeJoinError("join_already_claimed", claim_path=str(path.parent / CLAIM_NAME)) from error
        claimed = True
        os.fchmod(claim_fd, 0o600)
        _set_claim(claim_fd, expected_sha256, "started")
        os.fsync(lock_fd)
        attempted_digest = _attempted_rating_digest(ratings)
        try:
            canonical_ratings = _canonical_ratings(ratings, artifact["input"])
        except ValueError as error:
            # Fixed validation codes only; supplied probabilities/votes never enter diagnostics.
            code = str(error) if str(error).startswith("invalid_") or str(error) in ("incomplete_rating_roster", "invalid_roster_membership") else "invalid_rating_json"
            receipt_raw = _bytes(_receipt(artifact, expected_sha256, "failed", attempted_digest, code=code))
            _write_new(output_fd, "outcome-join-receipt.json", receipt_raw)
            _set_claim(claim_fd, expected_sha256, "failed", _digest(receipt_raw))
            raise OutcomeJoinError(code, str(output / "outcome-join-receipt.json"), str(path.parent / CLAIM_NAME)) from None
        joined = {**artifact["input"], "ratings": canonical_ratings}
        joined_raw = _bytes(joined)
        joined_digest = _digest(joined_raw)
        receipt_raw = _bytes(_receipt(artifact, expected_sha256, "succeeded", attempted_digest,
                                    _digest(_bytes(canonical_ratings)), joined_digest))
        _write_new(output_fd, "joined-input.json", joined_raw)
        _write_new(output_fd, "outcome-join-receipt.json", receipt_raw)
        _set_claim(claim_fd, expected_sha256, "succeeded", _digest(receipt_raw))
        os.fsync(lock_fd)
        return {"joinedInputPath": str(output / "joined-input.json"),
                "joinedInputSha256": joined_digest,
                "receiptPath": str(output / "outcome-join-receipt.json"),
                "receiptSha256": _digest(receipt_raw), "claimPath": str(path.parent / CLAIM_NAME)}
    except OSError as error:
        raise OutcomeJoinError("join_io_failure_after_claim" if claimed else "join_io_failure_before_claim",
                               claim_path=str(path.parent / CLAIM_NAME) if claimed else None) from error
    finally:
        for fd in (claim_fd, output_fd, parent_fd, lock_fd):
            if fd is not None:
                os.close(fd)
