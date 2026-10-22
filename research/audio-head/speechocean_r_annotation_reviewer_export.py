"""Read-only structural validation of one future blinded reviewer export.

The draft contract remains provisional; this does not collect or approve labels.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import wave

from speechocean_r_annotation_intake import (
    OPAQUE_ID, load_schema, load_verified_pack_context, read_json, require,
    validate_export_shape, validate_records, validation_summary,
)


def validate_reviewer_export(submission: dict, reviewer: str, schema: dict,
                             durations: dict[str, float],
                             pack_order: tuple[str, ...]) -> dict:
    """Check one complete export against the chosen reviewer's verified pack."""
    require(type(reviewer) is str and reviewer in schema["reviewers"],
            "Unknown reviewer")
    require(len(durations) == schema["opaqueClips"] and
            type(pack_order) is tuple and len(pack_order) == len(durations) and
            all(type(clip_id) is str and OPAQUE_ID.fullmatch(clip_id)
                for clip_id in pack_order) and
            len(set(pack_order)) == len(pack_order) and
            set(pack_order) == set(durations),
            "Reviewer pack order or opaque IDs differ from verified sample")
    records = validate_export_shape(submission)
    validate_records(records, schema, durations,
                     {(clip_id, reviewer) for clip_id in pack_order})
    require(tuple(record["clipId"] for record in records) == pack_order,
            "Export records differ from reviewer pack order")
    return validation_summary(len(durations), [reviewer])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviewer", choices=("reviewer-a", "reviewer-b"))
    parser.add_argument("submission", type=Path,
                        help="Future local JSON export; validation writes nothing")
    args = parser.parse_args(argv)
    try:
        schema = load_schema()
        durations, orders = load_verified_pack_context(schema)
        summary = validate_reviewer_export(read_json(args.submission), args.reviewer,
                                           schema, durations, orders[args.reviewer])
    except (OSError, ValueError, KeyError, TypeError, wave.Error):
        parser.error("Reviewer export failed locked intake validation")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
