"""Exclusive saved-DEV calibration lifecycle; no corpus/model/audio discovery.

The caller supplies input/source byte pins and retains the returned declaration
hash externally. An entered fit or audit stage is terminal, including failure or
interruption. Matching pins prove byte identity, not scientific authenticity.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
SOURCE_PATHS = {
    "stage": HERE / "calibration_stage.py", "adapter": HERE / "dev_calibration_inputs.py",
    "fit": HERE / "calibrate.py", "auditor": HERE / "calibration_audit.py",
    "packageInit": HERE / "__init__.py",
    "policy": PROJECT / "docs/consumer-assessment/r-confirmatory-decisions-20261003.json",
    "policyDocument": PROJECT / "docs/consumer-assessment/r-confirmatory-decisions-20261003.md",
    "requirements": HERE.parent / "requirements.txt", "requirementsLock": HERE.parent / "requirements.lock.txt",
}
INPUT_NAMES = {"tokens", "extract", "predictions", "split", "selection", "closedDeclaration", "clips", "retention"}
DEFAULT_COUNTS = {"devChildren": 119, "completeTokens": 4534, "excludedTokens": 5,
                  "selectedTokens": 4539, "testChildren": 80}
FLAGS = {"researchOnly": True, "clinicalUseEligible": False,
         "learnerFeedbackEligible": False, "productionUseEligible": False}
THREAD_VARIABLES = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                    "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS", "OMP_DYNAMIC", "MKL_DYNAMIC")


class CalibrationStageError(ValueError):
    """A fixed error code; caller data and underlying exception text stay private."""


def _require(condition, code):
    if not condition:
        raise CalibrationStageError(code)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _path(value):
    path = Path(value)
    _require(path.is_absolute() and path == path.resolve(), "noncanonical_absolute_path")
    return path


def _binding(value):
    _require(type(value) is dict and set(value) == {"path", "sha256"}
             and type(value["path"]) is str and type(value["sha256"]) is str
             and re.fullmatch("[0-9a-f]{64}", value["sha256"]) is not None, "invalid_binding")
    return _path(value["path"])


def _read(path, directory_fd=None, private=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode), "nonregular_file")
        if private:
            _require(stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid(), "nonprivate_file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(fd)


def _verify_bindings(bindings, names, source=False):
    _require(type(bindings) is dict and set(bindings) == set(names), "invalid_binding_set")
    raw = {}
    for name in sorted(names):
        path = _binding(bindings[name])
        if source:
            _require(path == SOURCE_PATHS[name], "source_path_mismatch")
        raw[name] = _read(path)
        _require(_digest(raw[name]) == bindings[name]["sha256"], "binding_hash_mismatch")
    return raw


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(CalibrationStageError("nonfinite_json")))


def _environment():
    # Called only after all scientific/package source pins have been checked.
    numpy = importlib.import_module("numpy")
    scipy = importlib.import_module("scipy")
    versions = {name: importlib.metadata.version(name) for name in ("numpy", "scipy")}
    _require(versions == {"numpy": numpy.__version__, "scipy": scipy.__version__}, "dependency_version_mismatch")
    return {"python": platform.python_version(), "pythonImplementation": platform.python_implementation(),
            "pythonExecutable": sys.executable, "pythonBuild": list(platform.python_build()),
            "platform": platform.platform(), "machine": platform.machine(), "dependencies": versions,
            "numpyBuildConfiguration": numpy.__config__.show(mode="dicts"),
            "threadEnvironment": {name: os.environ.get(name) for name in THREAD_VARIABLES}}


def _directory(path, fresh=False):
    if fresh:
        os.mkdir(path, 0o700)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if fresh:
            os.fchmod(fd, 0o700)
        info = os.fstat(fd)
        _require(stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.getuid(), "nonprivate_directory")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _write(directory_fd, name, value, directory):
    raw = _bytes(value)
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(raw)
            handle.flush()
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory_fd)
    return {"path": str(directory / name), "sha256": _digest(raw)}


def _saved(directory_fd, name, directory, expected_sha=None):
    raw = _read(name, directory_fd, private=True)
    digest = _digest(raw)
    _require(expected_sha is None or digest == expected_sha, "saved_hash_mismatch")
    return _json(raw), {"path": str(directory / name), "sha256": digest}


def declare_calibration(bindings, source_bindings, fresh_root, expected=None):
    """Verify fixed sources/inputs, then exclusively publish a private declaration."""
    root_fd = None
    try:
        root = _path(fresh_root)
        _verify_bindings(source_bindings, SOURCE_PATHS, source=True)
        raw = _verify_bindings(bindings, INPUT_NAMES)
        environment = _environment()
        artifacts = {name: _json(raw[name]) for name in INPUT_NAMES - {"retention"}}
        adapter = importlib.import_module("r_confirmatory.dev_calibration_inputs")
        counts = dict(DEFAULT_COUNTS if expected is None else expected)
        prepared = adapter.prepare_dev_calibration_inputs(artifacts, bindings, counts)
        root_fd = _directory(root, fresh=True)
        payload_pin = _write(root_fd, "payload.json", prepared["payload"], root)
        receipt_pin = _write(root_fd, "input-receipt.json", prepared["receipt"], root)
        declaration = {"schemaVersion": 1, "artifactType": "saved_dev_calibration_declaration", **FLAGS,
                       "root": str(root), "expectedCounts": counts, "inputBindings": bindings,
                       "sourceBindings": source_bindings, "environment": environment,
                       "payload": payload_pin, "inputReceipt": receipt_pin,
                       "attemptPolicy": "exclusive_started_stage_is_terminal_no_retry"}
        declaration_pin = _write(root_fd, "declaration.json", declaration, root)
        return {"declarationPath": declaration_pin["path"], "declarationSha256": declaration_pin["sha256"],
                "payloadPath": payload_pin["path"], "receiptPath": receipt_pin["path"]}
    except CalibrationStageError:
        raise
    except Exception:
        raise CalibrationStageError("declaration_failed") from None
    finally:
        if root_fd is not None:
            os.close(root_fd)


def _load_declaration(root_fd, root, anchor):
    _require(type(anchor) is str and re.fullmatch("[0-9a-f]{64}", anchor) is not None, "invalid_external_anchor")
    declaration, pin = _saved(root_fd, "declaration.json", root, anchor)
    _require(declaration["schemaVersion"] == 1 and declaration["artifactType"] == "saved_dev_calibration_declaration"
             and declaration["root"] == str(root) and all(declaration[key] == value for key, value in FLAGS.items()),
             "invalid_declaration")
    return declaration, pin


def _validate_declared(declaration, root_fd, root):
    _verify_bindings(declaration["sourceBindings"], SOURCE_PATHS, source=True)
    raw = _verify_bindings(declaration["inputBindings"], INPUT_NAMES)
    _require(_environment() == declaration["environment"], "environment_changed")
    payload, payload_pin = _saved(root_fd, "payload.json", root, declaration["payload"]["sha256"])
    receipt, receipt_pin = _saved(root_fd, "input-receipt.json", root, declaration["inputReceipt"]["sha256"])
    _require(payload_pin == declaration["payload"] and receipt_pin == declaration["inputReceipt"], "saved_path_mismatch")
    adapter = importlib.import_module("r_confirmatory.dev_calibration_inputs")
    prepared = adapter.prepare_dev_calibration_inputs({name: _json(raw[name]) for name in INPUT_NAMES - {"retention"}},
                                                     declaration["inputBindings"], declaration["expectedCounts"])
    _require(_bytes(prepared["payload"]) == _bytes(payload) and _bytes(prepared["receipt"]) == _bytes(receipt),
             "saved_preparation_mismatch")
    return payload


def _execute_stage(root, anchor, stage, callback):
    root_fd = stage_fd = None
    started = False
    try:
        root = _path(root)
        root_fd = _directory(root)
        declaration, declaration_pin = _load_declaration(root_fd, root, anchor)
        os.mkdir(stage, 0o700, dir_fd=root_fd)
        stage_root = root / stage
        stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        os.fchmod(stage_fd, 0o700)
        started_pin = _write(stage_fd, "started.json", {"schemaVersion": 1, "stage": stage, "status": "started",
                                                      "declaration": declaration_pin, **FLAGS}, stage_root)
        started = True
        payload = _validate_declared(declaration, root_fd, root)
        return callback(root_fd, stage_fd, root, stage_root, declaration, declaration_pin, started_pin, payload)
    except Exception as error:
        code = str(error) if isinstance(error, CalibrationStageError) else "stage_execution_failed"
        if started:
            try:
                _write(stage_fd, "failure.json", {"schemaVersion": 1, "stage": stage, "status": "failed",
                                                 "code": code, "declarationSha256": anchor, **FLAGS}, stage_root)
            except Exception:
                pass  # The started marker remains terminal even if saving failure fails.
        raise CalibrationStageError(code) from None
    finally:
        for fd in (stage_fd, root_fd):
            if fd is not None:
                os.close(fd)


def run_calibration(root, externally_recorded_declaration_sha):
    """Consume this declaration's sole fit stage; failures/interruption forbid retry."""
    def fit(root_fd, stage_fd, root, stage_root, declaration, declaration_pin, started_pin, payload):
        fitter = importlib.import_module("r_confirmatory.calibrate")
        control = fitter.fit_calibration(payload)
        control_pin = _write(stage_fd, "control.json", control, stage_root)
        _saved(root_fd, "declaration.json", root, declaration_pin["sha256"])
        _saved(stage_fd, "started.json", stage_root, started_pin["sha256"])
        _validate_declared(declaration, root_fd, root)
        completion = {"schemaVersion": 1, "stage": "fit", "status": "completed", **FLAGS,
                      "calibrationFitPerformed": True,
                      "declaration": declaration_pin, "started": started_pin, "control": control_pin,
                      "payload": declaration["payload"], "environment": declaration["environment"]}
        completion_pin = _write(stage_fd, "completion.json", completion, stage_root)
        return {"controlPath": control_pin["path"], "controlSha256": control_pin["sha256"],
                "completionPath": completion_pin["path"], "completionSha256": completion_pin["sha256"]}
    return _execute_stage(root, externally_recorded_declaration_sha, "fit", fit)


def audit_calibration_stage(root, declaration_sha, externally_recorded_fit_completion_sha):
    """Replay saved control against external declaration and fit-completion anchors."""
    _require(type(externally_recorded_fit_completion_sha) is str
             and re.fullmatch("[0-9a-f]{64}", externally_recorded_fit_completion_sha) is not None,
             "invalid_external_completion_anchor")
    def audit(root_fd, stage_fd, root, stage_root, declaration, declaration_pin, started_pin, payload):
        fit_fd = _directory(root / "fit")
        try:
            _require(set(os.listdir(fit_fd)) == {"started.json", "control.json", "completion.json"},
                     "fit_stage_not_completed_exclusively")
            completion, fit_completion_pin = _saved(fit_fd, "completion.json", root / "fit",
                                                    externally_recorded_fit_completion_sha)
            fit_started, fit_started_pin = _saved(fit_fd, "started.json", root / "fit")
            _require(completion["status"] == "completed" and completion["declaration"] == declaration_pin
                     and completion["started"] == fit_started_pin and completion["payload"] == declaration["payload"]
                     and completion["environment"] == declaration["environment"]
                     and fit_started["declaration"] == declaration_pin, "invalid_fit_completion")
            control, control_pin = _saved(fit_fd, "control.json", root / "fit", completion["control"]["sha256"])
            _require(control_pin == completion["control"], "control_path_mismatch")
            _require(control["dependencies"] == {"python": declaration["environment"]["python"],
                     **declaration["environment"]["dependencies"], "dtype": "float64"}, "control_dependencies_mismatch")
            auditor = importlib.import_module("r_confirmatory.calibration_audit")
            report = auditor.audit_calibration(payload, control)
            audit_pin = _write(stage_fd, "audit.json", report, stage_root)
            _saved(root_fd, "declaration.json", root, declaration_pin["sha256"])
            _saved(fit_fd, "completion.json", root / "fit", externally_recorded_fit_completion_sha)
            _saved(fit_fd, "control.json", root / "fit", control_pin["sha256"])
            _saved(stage_fd, "started.json", stage_root, started_pin["sha256"])
            _validate_declared(declaration, root_fd, root)
            completion_pin = _write(stage_fd, "completion.json", {"schemaVersion": 1, "stage": "audit",
                                    "status": "completed", **FLAGS, "declaration": declaration_pin,
                                    "calibrationFitPerformed": True, "started": started_pin,
                                    "fitCompletion": fit_completion_pin,
                                    "control": control_pin, "audit": audit_pin}, stage_root)
            return {"auditPath": audit_pin["path"], "auditSha256": audit_pin["sha256"],
                    "completionPath": completion_pin["path"], "completionSha256": completion_pin["sha256"]}
        finally:
            os.close(fit_fd)
    return _execute_stage(root, declaration_sha, "audit", audit)
