"""Once-only private artifact stages around frozen confirmation tools.

Supplied files only: no corpus reader, decoding, extraction, inference or fit.
The caller retains external hashes; this is a local lifecycle, not proof of global
chronology or authorization to access reserved outcomes or recordings.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import stat

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
SOURCE_PATHS = {"stages": HERE / "stages.py", "runPackageInit": HERE / "__init__.py",
                "locking": HERE.parent / "r_confirmatory/locking.py",
                "evaluate": HERE.parent / "r_confirmatory/evaluate.py",
                "evaluationAudit": HERE.parent / "r_confirmatory/evaluation_audit.py",
                "confirmatoryPackageInit": HERE.parent / "r_confirmatory/__init__.py",
                "verdict": HERE / "verdict.py", "prediction": HERE / "prediction.py"}
OPTIONAL_SOURCE_PATHS = {
    "execution": HERE / "execution.py", "requests": HERE / "requests.py", "outcomes": HERE / "outcomes.py",
    "structuralProjection": HERE.parent / "r_confirmatory/structural_projection_v2.py",
    "retainedLoader": HERE.parent / "ages_6_12_bundle/inference.py",
    "retainedPackageInit": HERE.parent / "ages_6_12_bundle/__init__.py",
    "retainedModelSource": HERE.parent / "multiphone_models.py",
    "calibrationPredict": HERE.parent / "r_confirmatory/calibrate.py",
    "calibrationPackageInit": HERE.parent / "r_confirmatory/__init__.py"}
INPUT_NAMES = {"preparedTokens", "candidate", "retained", "calibration", "policy", "frozenProtocol"}
PROFILE_FIELDS = {"schemaVersion", "mode", "expectedChildren", "children", "selectedTokens", "policy",
                  "inputBindings", "sourceBindings", "environment"}
FLAGS = {"researchOnly": True, "clinicalUseEligible": False,
         "learnerFeedbackEligible": False, "productionUseEligible": False}
THREADS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
           "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS", "OMP_DYNAMIC", "MKL_DYNAMIC")
PROTOCOL_SHA = "458872741505a761719ff29d6be48abc8e06d4b402566a8e0625612b259b9940"
POLICY_SHA = "62b206d0e3f1d95d6c61d9a6a3a4cd6725851465ac9208bf5eaa386ced1b553d"
POLICY_PATH = PROJECT / "docs/consumer-assessment/r-confirmatory-decisions-20261003.json"
PROTOCOL_PATH = PROJECT / "docs/consumer-assessment/r-confirmatory-frozen-protocol-20261003.json"
PURPOSE_PATHS = {
    "preparedTokens": "research/audio-head/outputs/r-confirmatory-preparation-20261003/metadata-v2/projection/selection.json",
    "candidate": "research/audio-head/outputs/percept-r-binary-head-20261002/v1/final/full-dev-candidate.npz",
    "retained": "research/audio-head/outputs/multiphone-20260927/ages-6-12-mixture-v1/bundle/manifest.json",
    "calibration": "research/audio-head/outputs/r-confirmatory-preparation-20261003/calibration-v1/fit/control.json",
    "policy": "docs/consumer-assessment/r-confirmatory-decisions-20261003.json"}


class RunStageError(ValueError):
    """Fixed safe lifecycle error; private supplied values are never echoed."""

    def __init__(self, code, failure=None, decision=None):
        super().__init__(code)
        self.failure, self.decision = failure, decision


def _require(condition, code):
    if not condition:
        raise RunStageError(code)


def _finite_json(value):
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_finite_json(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _finite_json(item) for key, item in value.items())
    return False


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _anchor(value):
    _require(type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None, "invalid_external_anchor")


def _path(value):
    path = Path(value)
    _require(path.is_absolute() and path == path.resolve(), "noncanonical_absolute_path")
    return path


def _directory(path, private=False):
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        info = os.fstat(fd)
        _require(not private or (info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700),
                 "unsafe_private_directory")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _fresh(path):
    parent_fd = _directory(path.parent)
    fd = None
    try:
        os.mkdir(path.name, 0o700, dir_fd=parent_fd)
        fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        os.fchmod(fd, 0o700)
        os.fsync(parent_fd)
        return fd
    except BaseException:
        if fd is not None:
            os.close(fd)
        raise
    finally:
        os.close(parent_fd)


def _read(path, private=False):
    directory_fd = _directory(path.parent, private=private)
    fd = None
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.getuid()
                 and (not private or stat.S_IMODE(before.st_mode) == 0o600), "unsafe_file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read()
        after = os.fstat(fd)
        _require((before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                 == (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "file_changed_during_read")
        return raw
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory_fd)


def _binding_shape(binding):
    _require(type(binding) is dict and set(binding) == {"path", "sha256"}
             and type(binding["path"]) is str, "invalid_binding")
    _anchor(binding["sha256"])
    return _path(binding["path"])


def _binding(binding, private=False):
    path = _binding_shape(binding)
    raw = _read(path, private)
    _require(_digest(raw) == binding["sha256"], "binding_hash_mismatch")
    return raw


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _constant(_):
    raise RunStageError("nonfinite_json_constant")


def _json(raw):
    result = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    _require(_finite_json(result), "invalid_finite_json")
    return result


def _write(fd, directory, name, value):
    raw = _bytes(value)
    file_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    with os.fdopen(file_fd, "wb") as destination:
        os.fchmod(destination.fileno(), 0o600)
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())
    os.fsync(fd)
    return {"path": str(directory / name), "sha256": _digest(raw)}


def _environment():
    return {"python": platform.python_version(), "numpy": importlib.metadata.version("numpy"),
            "platform": platform.platform(), "threadEnvironment": {name: os.environ.get(name) for name in THREADS}}


def _verify_profile(profile):
    sources = profile["sourceBindings"]
    allowed = {**SOURCE_PATHS, **OPTIONAL_SOURCE_PATHS}
    _require(type(sources) is dict and set(SOURCE_PATHS) <= set(sources) <= set(allowed), "invalid_source_set")
    if profile["mode"] == "reserved_test":
        _require(set(sources) == set(allowed), "reserved_source_set_incomplete")
    # Validate every role/path before opening even the first supplied source.
    for name, binding in sources.items():
        _require(type(binding) is dict and binding.get("path") == str(allowed[name]), "source_path_mismatch")
        _binding_shape(binding)
    inputs = profile["inputBindings"]
    _require(type(inputs) is dict and set(inputs) == INPUT_NAMES, "invalid_input_set")
    for binding in inputs.values():
        _binding_shape(binding)
    _require(inputs["policy"] == {"path": str(POLICY_PATH), "sha256": POLICY_SHA}, "frozen_policy_binding_mismatch")
    if profile["mode"] == "reserved_test":
        _require(inputs["frozenProtocol"] == {"path": str(PROTOCOL_PATH), "sha256": PROTOCOL_SHA},
                 "frozen_protocol_binding_mismatch")
        # Only the fixed public protocol is read to authorize private purposes.
        protocol = _json(_binding({"path": str(PROTOCOL_PATH), "sha256": PROTOCOL_SHA}))
        for purpose, relative in PURPOSE_PATHS.items():
            _require(inputs[purpose] == {"path": str(PROJECT / relative),
                                        "sha256": protocol["bindings"][relative]["sha256"]},
                     "reserved_purpose_binding_mismatch")
        frozen_sources = {"locking", "evaluate", "evaluationAudit", "confirmatoryPackageInit", "structuralProjection",
                          "retainedLoader", "retainedPackageInit", "retainedModelSource", "calibrationPredict", "calibrationPackageInit"}
        for name in frozen_sources:
            relative = str(allowed[name].relative_to(PROJECT))
            _require(sources[name]["sha256"] == protocol["bindings"][relative]["sha256"],
                     "frozen_scientific_source_mismatch")
    for binding in sources.values():
        _binding(binding)
    _require(profile["environment"] == _environment(), "environment_changed")
    raw = {name: _binding(binding) for name, binding in inputs.items()}
    policy = _json(raw["policy"])
    _require(_bytes(policy) == _bytes(profile["policy"]), "policy_changed")
    protocol = _json(raw["frozenProtocol"])
    _require(_bytes(protocol["selectedResearchPolicy"]) == _bytes(policy), "protocol_policy_mismatch")
    if profile["mode"] == "synthetic":
        _require(protocol.get("synthetic") is True, "synthetic_protocol_label_required")
    prepared = _json(raw["preparedTokens"])
    ids = [row["childId"] for row in prepared["children"]]
    _require(len(ids) == len(set(ids)) and sorted(ids) == [row["childId"] for row in profile["children"]],
             "prepared_children_mismatch")
    selected = [{"childId": row["childId"], "tokenId": row["tokenId"]}
                for row in prepared["tokens"] if row["disposition"] == "selected"]
    _require(sorted(selected, key=lambda row: (row["childId"], row["tokenId"])) == profile["selectedTokens"],
             "prepared_selection_mismatch")


def _profile(profile):
    _require(type(profile) is dict and PROFILE_FIELDS <= set(profile) <= PROFILE_FIELDS | {"executionInputs"}
             and _finite_json(profile), "invalid_profile")
    _require(type(profile["schemaVersion"]) is int and profile["schemaVersion"] == 1,
             "invalid_profile_version")
    _require(profile["mode"] in ("synthetic", "reserved_test") and type(profile["expectedChildren"]) is int
             and 1 <= profile["expectedChildren"] <= 80, "invalid_profile_mode_or_denominator")
    if "executionInputs" in profile:
        _binding_shape(profile["executionInputs"])
    children = profile["children"]
    _require(type(children) is list and len(children) == profile["expectedChildren"], "invalid_full_child_roster")
    seen = set()
    for row in children:
        _require(type(row) is dict and {"childId"} <= set(row) <= {"childId", "descriptors"}, "invalid_child_fields")
        child = row["childId"]
        _require(type(child) is str and child.isascii() and child.isdecimal() and child[0] != "0"
                 and child not in seen, "invalid_numeric_child_identity")
        _require("descriptors" not in row or type(row["descriptors"]) is dict, "invalid_child_descriptors")
        seen.add(child)
    _require(type(profile["selectedTokens"]) is list, "invalid_selected_roster")
    tokens = set()
    for row in profile["selectedTokens"]:
        _require(type(row) is dict and set(row) == {"childId", "tokenId"} and row["childId"] in seen
                 and type(row["tokenId"]) is str and row["tokenId"] == row["tokenId"].strip()
                 and bool(row["tokenId"]), "invalid_selected_identity")
        key = row["childId"], row["tokenId"]
        _require(key not in tokens, "duplicate_selected_identity")
        tokens.add(key)
    if profile["mode"] == "reserved_test":
        _require("executionInputs" in profile, "reserved_execution_input_binding_required")
        _require(profile["expectedChildren"] == 80 and len(tokens) == 3066, "reserved_denominator_mismatch")
    canonical = copy.deepcopy(profile)
    canonical["children"].sort(key=lambda row: row["childId"])
    canonical["selectedTokens"].sort(key=lambda row: (row["childId"], row["tokenId"]))
    return canonical


def declare_run(profile, freshroot):
    """Bind a complete explicit roster under a fresh private declaration root."""
    fd = None
    started = False
    try:
        profile = _profile(profile)
        root = _path(freshroot)
        fd = _fresh(root)
        _write(fd, root, "started.json", {"schemaVersion": 1, "phase": "declare", "status": "started", **FLAGS})
        started = True
        _verify_profile(profile)
        membership = {"childIds": [row["childId"] for row in profile["children"]],
                      "selectedTokens": profile["selectedTokens"]}
        return _write(fd, root, "declaration.json", {"schemaVersion": 1, "artifactType": "confirmation_run_declaration",
                      "root": str(root), "profile": profile, "membershipSha256": _digest(_bytes(membership)),
                      "localOnceOnlyScope": True, "syntheticFixture": profile["mode"] == "synthetic", **FLAGS})
    except BaseException as error:
        interrupted = not isinstance(error, Exception)
        code = "declaration_interrupted" if interrupted else str(error) if isinstance(error, RunStageError) else "declaration_failed"
        if started:
            try:
                _write(fd, root, "failure.json", {"schemaVersion": 1, "phase": "declare",
                       "status": "interrupted" if interrupted else "failed", "code": code, **FLAGS})
            except Exception:
                pass
        if interrupted:
            raise
        raise RunStageError(code) from None
    finally:
        if fd is not None:
            os.close(fd)


def _declaration(root, digest):
    _anchor(digest)
    root = _path(root)
    binding = {"path": str(root / "declaration.json"), "sha256": digest}
    declaration = _json(_binding(binding, private=True))
    _require(type(declaration) is dict and set(declaration) == {"schemaVersion", "artifactType", "root", "profile",
             "membershipSha256", "localOnceOnlyScope", "syntheticFixture", *FLAGS}
             and type(declaration["schemaVersion"]) is int and declaration["schemaVersion"] == 1
             and declaration["artifactType"] == "confirmation_run_declaration" and declaration["root"] == str(root)
             and all(declaration[key] is value for key, value in FLAGS.items()), "invalid_declaration")
    profile = _profile(declaration["profile"])
    membership = {"childIds": [row["childId"] for row in profile["children"]], "selectedTokens": profile["selectedTokens"]}
    _require(declaration["membershipSha256"] == _digest(_bytes(membership))
             and declaration["localOnceOnlyScope"] is True
             and declaration["syntheticFixture"] is (profile["mode"] == "synthetic"), "declaration_membership_mismatch")
    return root, declaration, binding


def _phase(root, digest, phase, callback, precheck=None):
    fd = None
    started = False
    try:
        root, declaration, declaration_pin = _declaration(root, digest)
        previous = precheck(root, declaration, declaration_pin) if precheck else None
        phase_root = root / phase
        fd = _fresh(phase_root)
        started_pin = _write(fd, phase_root, "started.json", {"schemaVersion": 1, "phase": phase,
                              "status": "started", "declaration": declaration_pin, **FLAGS})
        started = True
        _verify_profile(declaration["profile"])
        artifacts = callback(root, declaration, declaration_pin, phase_root, previous)
        _binding(declaration_pin, private=True)
        _binding(started_pin, private=True)
        _verify_profile(declaration["profile"])
        for binding in artifacts.values():
            _binding(binding, private=True)
        completion = _write(fd, phase_root, "completion.json", {"schemaVersion": 1, "artifactType": "phase_completion",
                             "phase": phase, "status": "completed", "declaration": declaration_pin,
                             "started": started_pin, "artifacts": artifacts,
                             "syntheticFixture": declaration["syntheticFixture"], **FLAGS})
        return {**artifacts, "completion": completion}
    except BaseException as error:
        interrupted = not isinstance(error, Exception)
        code = "phase_interrupted" if interrupted else str(error) if isinstance(error, RunStageError) else "phase_failed"
        failure = decision = None
        if started:
            try:
                failure = _write(fd, phase_root, "failure.json", {"schemaVersion": 1, "phase": phase,
                       "status": "interrupted" if interrupted else "failed",
                       "code": code, "declaration": declaration_pin, **FLAGS})
            except Exception:
                pass
            if phase == "audit":
                try:
                    decision = _write(fd, phase_root, "invalid-decision.json", {"schemaVersion": 1,
                               "verdict": "invalid", "reasons": ["integrity_failure"], "coverage": None,
                               "auditVerified": False, "syntheticFixture": declaration["syntheticFixture"], **FLAGS})
                except Exception:
                    pass
        if interrupted:
            raise
        raise RunStageError(code, failure, decision) from None
    finally:
        if fd is not None:
            os.close(fd)


def _matching_roster(payload, profile):
    _require(type(payload) is dict and set(payload) == {"children", "selectedTokens", "arms"}, "invalid_prediction_payload")
    _require(sorted(payload["children"], key=lambda row: row["childId"]) == profile["children"]
             and sorted(payload["selectedTokens"], key=lambda row: (row["childId"], row["tokenId"])) == profile["selectedTokens"],
             "prediction_membership_mismatch")


def lock_predictions(root, declsha, predictions_binding, external_prediction_completion_sha256):
    """Lock only fixed output from an externally anchored prediction completion."""
    _anchor(external_prediction_completion_sha256)
    def predecessor(root, declaration, declaration_pin):
        return _completion(root, "prediction-output", declaration_pin, external_prediction_completion_sha256,
                           verify_artifacts=False)
    def lock(root, declaration, declaration_pin, phase_root, previous):
        produced, completion_pin = _completion(root, "prediction-output", declaration_pin,
                                                external_prediction_completion_sha256)
        _require(predictions_binding == produced["predictions"]
                 and predictions_binding["path"] == str(root / "prediction-output/predictions.json")
                 and produced["receipt"]["path"] == str(root / "prediction-output/receipt.json"),
                 "prediction_output_relation_mismatch")
        supplied = _json(_binding(predictions_binding, private=True))
        profile = declaration["profile"]
        receipt = _json(_binding(produced["receipt"], private=True))
        receipt_fields = {"schemaVersion", "executionSource", "predictionSource", "inputBindings", "executionInputs",
                          "productionBound", "terminalTokens", "syntheticFixture", "extractorCompletions", "predictorProvenance", *FLAGS}
        _require(type(receipt) is dict and set(receipt) == receipt_fields and type(receipt["schemaVersion"]) is int
                 and receipt["schemaVersion"] == 1 and receipt["executionSource"] == profile["sourceBindings"].get("execution")
                 and receipt["predictionSource"] == profile["sourceBindings"]["prediction"]
                 and receipt["inputBindings"] == profile["inputBindings"]
                 and receipt["executionInputs"] == produced["executionInputs"]
                 and ("executionInputs" not in profile or produced["executionInputs"] == profile["executionInputs"])
                 and ("executionInputs" in profile or profile["mode"] == "synthetic")
                 and receipt["productionBound"] is (profile["mode"] == "reserved_test")
                 and receipt["syntheticFixture"] is declaration["syntheticFixture"]
                 and type(receipt["terminalTokens"]) is int and receipt["terminalTokens"] == len(profile["selectedTokens"])
                 and type(receipt["extractorCompletions"]) is list and type(receipt["predictorProvenance"]) is dict
                 and all(receipt[key] is flag for key, flag in FLAGS.items()), "invalid_prediction_execution_receipt")
        _require(type(supplied) is dict and set(supplied) == {"schemaVersion", "declaration", "predictionSource", "inputBindings", "payload"}
                 and type(supplied["schemaVersion"]) is int and supplied["schemaVersion"] == 1
                 and supplied["declaration"] == declaration_pin
                 and supplied["predictionSource"] == profile["sourceBindings"]["prediction"]
                 and supplied["inputBindings"] == profile["inputBindings"], "invalid_prediction_envelope")
        _matching_roster(supplied["payload"], profile)
        locking = importlib.import_module("r_confirmatory.locking")
        result = locking.create_prediction_lock(supplied["payload"], phase_root / "artifact")
        return {"lock": {"path": result["lockPath"], "sha256": result["lockSha256"]},
                "predictions": copy.deepcopy(predictions_binding), "predictionCompletion": completion_pin}
    return _phase(root, declsha, "lock", lock, predecessor)


ARTIFACT_NAMES = {"prediction-output": {"predictions", "executionInputs", "receipt"},
                  "lock": {"lock", "predictions", "predictionCompletion"},
                  "outcome-access": {"joinedInput", "receipt", "ratings", "lock", "claim", "lockCompletion"},
                  "evaluate": {"report", "joinedInput", "joinCompletion"},
                  "audit": {"audit", "decision", "report", "evaluationCompletion"}}


def _local_pin(path):
    raw = _read(path, private=True)
    return {"path": str(path), "sha256": _digest(raw)}


def _completion(root, phase, declaration_pin, anchor=None, verify_artifacts=True):
    completion_pin = {"path": str(root / phase / "completion.json"), "sha256": anchor} if anchor else _local_pin(root / phase / "completion.json")
    value = _json(_binding(completion_pin, private=True))
    fields = {"schemaVersion", "artifactType", "phase", "status", "declaration", "started", "artifacts", "syntheticFixture", *FLAGS}
    _require(type(value) is dict and set(value) == fields and type(value["schemaVersion"]) is int
             and value["schemaVersion"] == 1 and value["artifactType"] == "phase_completion" and value["phase"] == phase
             and value["status"] == "completed" and value["declaration"] == declaration_pin
             and all(value[key] is flag for key, flag in FLAGS.items())
             and type(value["artifacts"]) is dict and set(value["artifacts"]) == ARTIFACT_NAMES[phase],
             "invalid_phase_completion")
    _require(value["started"]["path"] == str(root / phase / "started.json"), "started_path_mismatch")
    started = _json(_binding(value["started"], private=True))
    _require(started == {"schemaVersion": 1, "phase": phase, "status": "started", "declaration": declaration_pin, **FLAGS},
             "invalid_started_marker")
    directory_fd = _directory(root / phase, private=True)
    try:
        _require("failure.json" not in os.listdir(directory_fd), "contradictory_phase_failure")
    finally:
        os.close(directory_fd)
    if verify_artifacts:
        for binding in value["artifacts"].values():
            _binding(binding, private=True)
        predecessors = {"predictionCompletion": "prediction-output", "lockCompletion": "lock", "joinCompletion": "outcome-access", "evaluationCompletion": "evaluate"}
        for name, prior in predecessors.items():
            if name in value["artifacts"]:
                pin = value["artifacts"][name]
                _require(pin["path"] == str(root / prior / "completion.json"), "predecessor_path_mismatch")
                _completion(root, prior, declaration_pin, pin["sha256"])
    return value["artifacts"], completion_pin


def _locked_predecessor(root, declaration, declaration_pin, externallocksha, mode):
    _require(declaration["profile"]["mode"] == mode, "outcome_entry_point_mode_mismatch")
    artifacts, completion_pin = _completion(root, "lock", declaration_pin)
    expected = {"path": str(root / "lock/artifact/prediction-lock.json"), "sha256": externallocksha}
    _require(artifacts["lock"] == expected, "external_lock_mismatch")
    lock = _json(_binding(expected, private=True))
    _matching_roster(lock["input"], declaration["profile"])
    _require(lock["membershipSha256"] == declaration["membershipSha256"]
             and lock["sourceFiles"] == {"locking.py": declaration["profile"]["sourceBindings"]["locking"]["sha256"]},
             "lock_declaration_mismatch")
    return expected, completion_pin


def _join_ratings(phase_root, previous, supplied_ratings, ratings_binding):
    lock_pin, completion_pin = previous
    locking = importlib.import_module("r_confirmatory.locking")
    result = locking.join_locked_outcomes(lock_pin["path"], lock_pin["sha256"], supplied_ratings, phase_root / "artifact")
    return {"joinedInput": {"path": result["joinedInputPath"], "sha256": result["joinedInputSha256"]},
            "receipt": {"path": result["receiptPath"], "sha256": result["receiptSha256"]},
            "claim": _local_pin(Path(result["claimPath"])), "lock": lock_pin,
            "ratings": copy.deepcopy(ratings_binding), "lockCompletion": completion_pin}


def join_outcomes(root, declsha, externallocksha, ratings_binding):
    """Synthetic fixtures only: claim access before reading supplied ratings."""
    _anchor(externallocksha)
    def predecessor(root, declaration, declaration_pin):
        return _locked_predecessor(root, declaration, declaration_pin, externallocksha, "synthetic")
    def join(root, declaration, declaration_pin, phase_root, previous):
        supplied_ratings = _json(_binding(ratings_binding, private=True))
        return _join_ratings(phase_root, previous, supplied_ratings, ratings_binding)
    return _phase(root, declsha, "outcome-access", join, predecessor)


def join_reserved_outcomes(root, declsha, externallocksha):
    """Project fixed reserved outcomes only after the exclusive access claim."""
    _anchor(externallocksha)
    def predecessor(root, declaration, declaration_pin):
        return _locked_predecessor(root, declaration, declaration_pin, externallocksha, "reserved_test")
    def join(root, declaration, declaration_pin, phase_root, previous):
        outcomes = importlib.import_module("r_confirmatory_run.outcomes")
        supplied_ratings = outcomes.project_reserved_outcomes(declaration["profile"])
        ratings_binding = _save(phase_root, "ratings.json", supplied_ratings)
        return _join_ratings(phase_root, previous, supplied_ratings, ratings_binding)
    return _phase(root, declsha, "outcome-access", join, predecessor)


def _save(directory, name, value):
    fd = _directory(directory, private=True)
    try:
        return _write(fd, directory, name, value)
    finally:
        os.close(fd)


def evaluate_run(root, declsha, externaljoincompletionsha):
    """Evaluate a complete externally anchored join after exclusive phase start."""
    _anchor(externaljoincompletionsha)
    def predecessor(root, declaration, declaration_pin):
        return _completion(root, "outcome-access", declaration_pin, externaljoincompletionsha, verify_artifacts=False)
    def evaluate(root, declaration, declaration_pin, phase_root, previous):
        joined, completion_pin = _completion(root, "outcome-access", declaration_pin, externaljoincompletionsha)
        payload = _json(_binding(joined["joinedInput"], private=True))
        _matching_roster({key: payload[key] for key in ("children", "selectedTokens", "arms")}, declaration["profile"])
        evaluator = importlib.import_module("r_confirmatory.evaluate")
        report = evaluator.evaluate(payload)
        report_pin = _save(phase_root, "report.json", report)
        _completion(root, "outcome-access", declaration_pin, externaljoincompletionsha)
        return {"report": report_pin, "joinedInput": joined["joinedInput"], "joinCompletion": completion_pin}
    return _phase(root, declsha, "evaluate", evaluate, predecessor)


def audit_run(root, declsha, externalevalcompletionsha):
    """Save independent numerical audit before invoking the pinned policy kernel."""
    _anchor(externalevalcompletionsha)
    def predecessor(root, declaration, declaration_pin):
        return _completion(root, "evaluate", declaration_pin, externalevalcompletionsha, verify_artifacts=False)
    def audit(root, declaration, declaration_pin, phase_root, previous):
        evaluated, completion_pin = _completion(root, "evaluate", declaration_pin, externalevalcompletionsha)
        payload = _json(_binding(evaluated["joinedInput"], private=True))
        report = _json(_binding(evaluated["report"], private=True))
        auditor = importlib.import_module("r_confirmatory.evaluation_audit")
        checked = auditor.audit_evaluation(payload, report)
        profile = declaration["profile"]
        _require(checked["outcome"] == "verified" and checked["reportSha256"] == evaluated["report"]["sha256"]
                 and checked["inputSha256"] == evaluated["joinedInput"]["sha256"]
                 and checked["auditorSourceSha256"] == profile["sourceBindings"]["evaluationAudit"]["sha256"]
                 and checked["numpyVersion"] == profile["environment"]["numpy"], "audit_binding_mismatch")
        audit_pin = _save(phase_root, "audit.json", checked)
        saved_audit = _json(_binding(audit_pin, private=True))
        _completion(root, "evaluate", declaration_pin, externalevalcompletionsha)
        _verify_profile(profile)
        verdict = importlib.import_module("r_confirmatory_run.verdict")
        decision = verdict.decide_outcome(report, saved_audit, profile["policy"], expected_children=profile["expectedChildren"])
        _require(type(decision) is dict and all(decision[key] is value for key, value in FLAGS.items()), "unsafe_decision_flags")
        decision = {**decision, "syntheticFixture": declaration["syntheticFixture"], "executionMode": profile["mode"]}
        decision_pin = _save(phase_root, "decision.json", decision)
        _completion(root, "evaluate", declaration_pin, externalevalcompletionsha)
        return {"audit": audit_pin, "decision": decision_pin, "report": evaluated["report"], "evaluationCompletion": completion_pin}
    return _phase(root, declsha, "audit", audit, predecessor)
