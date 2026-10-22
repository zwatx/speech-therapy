"""Project a binary XML stream to allowlisted structural metadata only.

No filesystem, archive, model, or device access occurs in this module. XML
co-resident outcome bytes necessarily stream through Expat; their text is never
accumulated, interpreted, retained, logged, or exposed by the projection.
"""
from __future__ import annotations

import math
import re
from xml.parsers import expat


class ProjectionError(ValueError):
    """A fixed diagnostic code, with no source values or snippets."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


MAX_ENTRY_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 128
MAX_RECORDS = 20000
MAX_PHONES_PER_RECORD = 512
MAX_ALLOWED_TEXT = 4096
READ_CHUNK_BYTES = 65536

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_FOLDER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*_[1-9][0-9]*")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_STRUCTURAL_NAMES = {"session", "participants", "transcript", "participant", "age", "r", "segment", "userTiers", "userTier", "tierData", "tw"}
_STRUCTURAL_ATTRS = {"participant": {"id"}, "r": {"id"}, "segment": {"start", "end", "unit"}, "userTier": {"name"}}


def _split_name(name):
    parts = name.rsplit("|", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", name)


def _timing(attrs):
    if attrs.get("unit") != "s":
        raise ProjectionError("invalid_segment")
    values = []
    for key in ("start", "end"):
        value = attrs.get(key)
        if not isinstance(value, str) or not _NUMBER.fullmatch(value):
            raise ProjectionError("invalid_segment")
        number = float(value)
        if not math.isfinite(number):
            raise ProjectionError("invalid_segment")
        values.append(number)
    if values[0] < 0 or values[1] <= values[0]:
        raise ProjectionError("invalid_segment")
    return values


class _Projection:
    def __init__(self):
        self.stack = []
        self.namespace = None
        self.containers = {"participants": 0, "transcript": 0}
        self.records = []
        self.record = None
        self.record_depth = None
        self.chi_depth = None
        self.chi_count = 0
        self.age_count = 0
        self.age = None
        self.record_ids = set()
        self.segment_count = 0
        self.wrapper_count = 0
        self.capture = None
        self.capture_size = 0
        self.capture_kind = None
        self.capture_depth = None
        self.target_depth = None
        self.tier_data_depth = None
        self.target_count = 0
        self.tier_data_count = 0
        self.opaque_depth = None

    def start(self, qualified_name, attrs):
        namespace, name = _split_name(qualified_name)
        if self.namespace is None:
            self.namespace = namespace
        depth = len(self.stack) + 1
        parent = self.stack[-1] if self.stack else None
        if depth == 1 and name != "session":
            raise ProjectionError("invalid_root")
        if depth > MAX_DEPTH:
            raise ProjectionError("nesting_limit")
        if self.capture is not None:
            code = "invalid_age" if self.capture_kind == "age" else "invalid_target_structure"
            raise ProjectionError(code)
        self.stack.append(name)
        # Other user tiers are opaque after their name selects this branch.
        # Do not inspect any values or semantic attributes within them.
        if self.opaque_depth is not None:
            return
        if depth > 1 and name == "session":
            raise ProjectionError("invalid_root")
        if name == "r" and self.record is not None:
            raise ProjectionError("invalid_record_structure")
        if name in _STRUCTURAL_NAMES:
            if namespace != self.namespace:
                raise ProjectionError("namespace_ambiguity")
            for attr in attrs:
                attr_namespace, attr_name = _split_name(attr)
                if attr_name in _STRUCTURAL_ATTRS.get(name, ()):
                    if attr_namespace:
                        raise ProjectionError("namespace_ambiguity")
                    if len(attrs[attr]) > MAX_ALLOWED_TEXT:
                        raise ProjectionError("allowed_text_limit")
        if name in self.containers:
            if self.stack != ["session", name]:
                raise ProjectionError("invalid_session_structure")
            self.containers[name] += 1
            if self.containers[name] != 1:
                raise ProjectionError("invalid_session_structure")
        if self.stack[:-1] == ["session", "transcript"] and name not in {"r", "comment", "gem"}:
            raise ProjectionError("invalid_record_structure")
        if name == "participant" and self.stack != ["session", "participants", "participant"]:
            raise ProjectionError("invalid_participant_structure")
        if name == "age" and self.chi_depth is not None and depth != self.chi_depth + 1:
            raise ProjectionError("invalid_age")
        if name == "r" and self.stack != ["session", "transcript", "r"]:
            raise ProjectionError("invalid_record_structure")
        if self.target_depth is not None:
            if name == "tierData" and parent == "userTier" and depth == self.target_depth + 1:
                self.tier_data_count += 1
                if self.tier_data_count > 1:
                    raise ProjectionError("invalid_target_structure")
                self.tier_data_depth = depth
            elif name == "tw" and parent == "tierData" and self.tier_data_depth is not None and depth == self.tier_data_depth + 1:
                if len(self.record["phones"]) >= MAX_PHONES_PER_RECORD:
                    raise ProjectionError("phone_limit")
                self._capture("phone", depth)
            else:
                raise ProjectionError("invalid_target_structure")
        elif name == "participant" and attrs.get("id") == "CHI":
            self.chi_count += 1
            if self.chi_count > 1:
                raise ProjectionError("duplicate_chi_participant")
            if self.record is not None:
                raise ProjectionError("invalid_record_structure")
            self.chi_depth = depth
        elif name == "age" and parent == "participant" and depth == (self.chi_depth or -1) + 1:
            self.age_count += 1
            if self.age_count > 1:
                raise ProjectionError("duplicate_chi_age")
            self._capture("age", depth)
        elif name == "r":
            if len(self.records) >= MAX_RECORDS:
                raise ProjectionError("record_limit")
            self.record_depth = depth
            record_id = attrs.get("id")
            if not isinstance(record_id, str) or not _SAFE_ID.fullmatch(record_id):
                raise ProjectionError("invalid_record_id")
            if record_id in self.record_ids:
                raise ProjectionError("duplicate_record_id")
            self.record_ids.add(record_id)
            self.record = {"recordId": record_id, "phones": []}
            self.target_count = self.segment_count = self.wrapper_count = 0
        elif name == "segment" and self.record is not None:
            if depth != self.record_depth + 1:
                raise ProjectionError("invalid_segment_structure")
            self.segment_count += 1
            if self.segment_count > 1:
                raise ProjectionError("duplicate_segment")
            self.record["startSeconds"], self.record["endSeconds"] = _timing(attrs)
        elif name == "userTiers" and self.record is not None:
            if depth != self.record_depth + 1:
                raise ProjectionError("invalid_target_structure")
            self.wrapper_count += 1
            if self.wrapper_count > 1:
                raise ProjectionError("invalid_target_structure")
        elif name == "userTier" and self.record is not None:
            direct = depth == self.record_depth + 1
            wrapped = parent == "userTiers" and depth == self.record_depth + 2
            if not (direct or wrapped):
                raise ProjectionError("invalid_target_structure")
            if attrs.get("name") == "ARPABET Target":
                self.target_count += 1
                if self.target_count > 1:
                    raise ProjectionError("duplicate_target_tier")
                self.target_depth = depth
                self.tier_data_count = 0
            else:
                self.opaque_depth = depth

    def _capture(self, kind, depth):
        self.capture = []
        self.capture_size = 0
        self.capture_kind = kind
        self.capture_depth = depth

    def text(self, data):
        if self.capture is not None:
            self.capture_size += len(data)
            if self.capture_size > MAX_ALLOWED_TEXT:
                raise ProjectionError("allowed_text_limit")
            self.capture.append(data)

    def end(self, qualified_name):
        depth = len(self.stack)
        if self.opaque_depth is not None:
            if depth == self.opaque_depth:
                self.opaque_depth = None
        elif self.capture is not None and depth == self.capture_depth:
            value = "".join(self.capture)
            if self.capture_kind == "age":
                value = value.strip()
                match = re.fullmatch(r"P([0-9]+)Y(?:([0-9]+)M)?(?:([0-9]+)D)?", value)
                if not match or (match[2] is not None and int(match[2]) > 11):
                    raise ProjectionError("invalid_age")
                self.age = int(match[1])
            else:
                self.record["phones"].append(value)
            self.capture = self.capture_kind = self.capture_depth = None
        elif depth == self.target_depth:
            if self.tier_data_count != 1:
                raise ProjectionError("unresolved_target_metadata")
            self.target_depth = self.tier_data_depth = None
        elif depth == self.tier_data_depth:
            self.tier_data_depth = None
        elif depth == self.chi_depth:
            self.chi_depth = None
        elif depth == self.record_depth:
            if self.target_count != 1:
                raise ProjectionError("unresolved_target_metadata")
            if self.segment_count != 1:
                raise ProjectionError("missing_segment")
            self.records.append(self.record)
            self.record = self.record_depth = None
        self.stack.pop()

    def result(self):
        if any(count != 1 for count in self.containers.values()):
            raise ProjectionError("missing_session_structure")
        if self.age is None:
            raise ProjectionError("missing_chi_age")
        return {"ageYears": self.age, "records": self.records,
                "counts": {"records": len(self.records), "phones": sum(len(r["phones"]) for r in self.records)},
                "flags": {"coResidentXML": True, "outcomeValuesExtracted": False,
                          "outcomeValuesInterpreted": False, "outcomeValuesRetained": False,
                          "outcomeValuesLogged": False, "outcomeValuesExposed": False}}


def _reject_declaration(*_):
    raise ProjectionError("forbidden_xml_declaration")


def project_session(stream, folder, session):
    """Return completed CHI age and every record's timing and target phones."""
    if (not isinstance(folder, str) or len(folder) > MAX_ALLOWED_TEXT or not _FOLDER_ID.fullmatch(folder)
            or not isinstance(session, str) or len(session) > MAX_ALLOWED_TEXT or not _SAFE_ID.fullmatch(session)):
        raise ProjectionError("invalid_identity")
    projection = _Projection()
    parser = expat.ParserCreate(namespace_separator="|")
    parser.StartElementHandler = projection.start
    parser.CharacterDataHandler = projection.text
    parser.EndElementHandler = projection.end
    parser.StartDoctypeDeclHandler = _reject_declaration
    parser.EntityDeclHandler = _reject_declaration
    parser.ExternalEntityRefHandler = _reject_declaration
    parser.SkippedEntityHandler = _reject_declaration
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    entry_bytes = 0
    try:
        while True:
            requested = min(READ_CHUNK_BYTES, MAX_ENTRY_BYTES - entry_bytes + 1)
            try:
                chunk = stream.read(requested)
            except Exception:
                raise ProjectionError("stream_read_failed") from None
            if not isinstance(chunk, bytes) or len(chunk) > requested:
                raise ProjectionError("invalid_stream")
            if not chunk:
                break
            entry_bytes += len(chunk)
            if entry_bytes > MAX_ENTRY_BYTES:
                raise ProjectionError("entry_bytes_limit")
            parser.Parse(chunk, False)
        parser.Parse(b"", True)
    except expat.ExpatError:
        raise ProjectionError("malformed_xml") from None
    return projection.result()
