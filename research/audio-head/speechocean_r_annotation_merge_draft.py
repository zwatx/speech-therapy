"""Combine two future local reviewer exports under the provisional intake contract.

This is a structural draft, not adjudication or approval of reviewer labels.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import wave

from speechocean_r_annotation_intake import (
    load_schema, load_verified_pack_context, read_json, require, validate_submission,
)
from speechocean_r_annotation_reviewer_export import validate_reviewer_export


def merge_reviewers(first: dict, second: dict, schema: dict,
                    durations: dict[str, float],
                    pack_orders: dict[str, tuple[str, ...]]) -> tuple[dict, dict]:
    """Preserve both reviewers' records and validate the complete 80-record export."""
    records = []
    for submission, reviewer in zip((first, second), schema["reviewers"], strict=True):
        require(reviewer in pack_orders, "Missing reviewer pack order")
        validate_reviewer_export(submission, reviewer, schema, durations,
                                 pack_orders[reviewer])
        records.extend(submission["records"])
    combined = {"schemaVersion": 1, "records": records}
    summary = validate_submission(combined, schema, durations)
    return combined, summary


def write_new_local_json(path: Path, value: dict) -> None:
    """Publish complete JSON in the same directory without replacing any path."""
    require(path.is_absolute() and not str(path).startswith("//") and
            path.parent.is_dir() and path.parent.resolve(strict=True) == path.parent and
            not path.exists() and not path.is_symlink(),
            "Output must be a new local path in a real directory")
    payload = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".annotation-merge-", suffix=".tmp",
                                               dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviewer_a", type=Path, help="Local reviewer-a JSON export")
    parser.add_argument("reviewer_b", type=Path, help="Local reviewer-b JSON export")
    parser.add_argument("output", type=Path, help="New absolute local JSON output path")
    args = parser.parse_args(argv)
    try:
        schema = load_schema()
        durations, pack_orders = load_verified_pack_context(schema)
        combined, summary = merge_reviewers(read_json(args.reviewer_a),
                                            read_json(args.reviewer_b), schema, durations,
                                            pack_orders)
        write_new_local_json(args.output, combined)
    except (OSError, ValueError, KeyError, TypeError, wave.Error):
        parser.error("Reviewer exports or output failed locked intake validation")
    print(json.dumps({**summary, "status": "provisional merged structure only",
                      "outputWritten": True}, sort_keys=True))


if __name__ == "__main__":
    main()
