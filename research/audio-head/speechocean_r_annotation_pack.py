"""Prepare two local, blinded media packs for the /R/ annotation pilot.

This copies only public author-train WAVs into ignored output. It does not
collect labels, contact reviewers, or authorize a clinical use.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import tempfile

from speechocean_r_annotation_sample import (
    ARCHIVE, ARCHIVE_SHA256, AUDIO, OUTPUT, RECIPE, AUTHORITY,
    blinded_queue, build_candidates, load_recipe, require_real_generated_path, select_sample,
    private_directory, sha256_file, verify_selected_wavs, write_json,
)


PACK_ROOT = OUTPUT / "local-reviewer-packs"
PACK_NAMES = ("reviewer-a", "reviewer-b")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def source_rows() -> tuple[list[dict], bytes]:
    """Rebuild the locked sample and check the existing private mapping."""
    recipe = load_recipe()
    manifest_path = OUTPUT / "internal-manifest.json"
    queue_path = OUTPUT / "reviewer-queue.json"
    report = json.loads((OUTPUT / "report.json").read_text())
    require(report.get("internalManifestSha256") == sha256_file(manifest_path)
            and report.get("reviewerQueueSha256") == sha256_file(queue_path)
            and report.get("recipeSha256") == sha256_file(RECIPE)
            and report.get("sourceArchiveSha256") == ARCHIVE_SHA256,
            "Annotation sample provenance differs from locked report")
    manifest = json.loads(manifest_path.read_text())
    require(all(manifest.get(name) is False for name in AUTHORITY)
            and manifest.get("recipeSha256") == sha256_file(RECIPE)
            and manifest.get("sourceArchiveSha256") == ARCHIVE_SHA256,
            "Internal manifest has unexpected authority or source")
    key = bytes.fromhex(manifest["blindingKeyHex"])
    require(len(key) == 32, "Invalid local blinding key")
    selected = select_sample(build_candidates(), recipe)
    expected_queue = blinded_queue(selected, key)
    require(json.loads(queue_path.read_text()) == expected_queue,
            "Blinded queue differs from locked sample")
    saved = manifest.get("clips")
    require(type(saved) is list and len(saved) == 40,
            "Expected forty internal source mappings")
    for actual, expected in zip(saved, selected, strict=True):
        require(all(actual.get(name) == value for name, value in expected.items()),
                "Internal source mapping differs from locked train selection")
        require(set(actual) == set(expected) | {"wavPath", "wavSha256"},
                "Internal source mapping has unexpected fields")
        expected_path = AUDIO / f"WAVE/SPEAKER{expected['speakerId']}/{expected['sourceId']}.WAV"
        require(actual["wavPath"] == str(expected_path), "Internal WAV path differs from author split")
    # Recheck extracted bytes against the official pinned archive immediately
    # before they become reviewer-facing media.
    recorded_digests = {row["sourceId"]: row["wavSha256"] for row in saved}
    archive_hashes = verify_selected_wavs([dict(row) for row in saved], ARCHIVE, AUDIO)
    for row in saved:
        member = f"speechocean762/WAVE/SPEAKER{row['speakerId']}/{row['sourceId']}.WAV"
        require(archive_hashes[member] == recorded_digests[row["sourceId"]],
                "Selected WAV digest differs from internal manifest")
    return saved, key


def reviewer_order(rows: list[dict], key: bytes, reviewer: str) -> list[dict]:
    require(reviewer in PACK_NAMES and len(key) == 32, "Invalid local reviewer order")
    return sorted(rows, key=lambda row: hmac.new(
        key, f"{reviewer}:{row['sourceId']}".encode(), hashlib.sha256).digest())


def copy_private_wav(source: Path, target: Path, expected_sha256: str) -> None:
    """Copy through a private temporary file before replacing a generated WAV."""
    descriptor, temporary = tempfile.mkstemp(prefix=".annotation-wav-", suffix=".tmp",
                                             dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as destination, source.open("rb") as original:
            shutil.copyfileobj(original, destination)
            destination.flush()
            os.fsync(destination.fileno())
        require(sha256_file(Path(temporary)) == expected_sha256,
                "WAV changed while preparing blinded pack")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare_packs() -> dict:
    require_real_generated_path(PACK_ROOT, OUTPUT.parent)
    rows, key = source_rows()
    PACK_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    orders = []
    pack_hashes = {}
    for reviewer in PACK_NAMES:
        destination = PACK_ROOT / reviewer
        media = destination / "media"
        require(not destination.is_symlink() and not media.is_symlink(),
                "Reviewer pack directory cannot be a symlink")
        media.mkdir(parents=True, exist_ok=True, mode=0o700)
        ordered = reviewer_order(rows, key, reviewer)
        orders.append([row["reviewerId"] for row in ordered])
        expected_media = {f"{row['reviewerId']}.wav" for row in ordered}
        require(len(expected_media) == len(rows) and
                {path.name for path in media.iterdir() if path.suffix == ".wav"} <= expected_media,
                "Existing reviewer pack contains stale or unexpected WAVs")
        items = []
        for row in ordered:
            source = Path(row["wavPath"])
            target = media / f"{row['reviewerId']}.wav"
            require(not target.is_symlink(), "Reviewer WAV cannot be a symlink")
            if (not target.exists() or target.stat().st_nlink > 1 or
                    sha256_file(target) != row["wavSha256"]):
                copy_private_wav(source, target, row["wavSha256"])
            require(sha256_file(target) == row["wavSha256"],
                  "Reviewer WAV differs from pinned archive")
            target.chmod(0o600)
            items.append({
                "reviewerId": row["reviewerId"],
                "audioFile": f"media/{row['reviewerId']}.wav",
                "targetPrompt": row["targetPrompt"],
                "targetWord": row["targetWord"],
                "wordIndexZeroBased": row["wordIndexZeroBased"],
                "phoneIndexWithinWordZeroBased": row["phoneIndexWithinWordZeroBased"],
            })
        require({path.name for path in media.iterdir() if path.suffix == ".wav"} == expected_media,
                "Reviewer pack media set differs from locked sample")
        pack = {
            "schemaVersion": 1,
            "purpose": "local blinded public-speech annotation feasibility",
            "reviewer": reviewer,
            "source": "SpeechOcean762: An Open-Source Non-native English Speech Corpus For Pronunciation Assessment",
            "sourceAuthors": "Junbo Zhang, Zhiwen Zhang, Yongqing Wang, Zhiyong Yan, Qiong Song, Yukai Huang, Ke Li, Daniel Povey, Yujun Wang (2021)",
            "sourceUrl": "https://openslr.org/101/",
            "licenseUrl": "https://creativecommons.org/licenses/by/4.0/",
            "changes": "WAV bytes unchanged; local filenames replaced with opaque IDs and presentation order changed",
            "annotationComplete": False,
            "items": items,
        }
        path = destination / "queue.json"
        write_json(path, pack)
        pack_hashes[reviewer] = sha256_file(path)
        private_directory(media)
        private_directory(destination)
    require(orders[0] != orders[1], "Reviewer presentation orders are identical")
    report = {
        "schemaVersion": 1,
        "purpose": "local-only blinded media preparation for qualified review",
        "sampleReportSha256": sha256_file(OUTPUT / "report.json"),
        "sourceArchiveSha256": ARCHIVE_SHA256,
        "reviewerPackQueueSha256": pack_hashes,
        "clipsPerReviewer": len(rows),
        "independentPresentationOrders": True,
        "audioFilesCopiedPerReviewer": len(rows),
        "notDistributed": True,
        **AUTHORITY,
    }
    write_json(PACK_ROOT / "report.json", report)
    private_directory(PACK_ROOT)
    return report


if __name__ == "__main__":
    result = prepare_packs()
    print(json.dumps({"clipsPerReviewer": result["clipsPerReviewer"],
                      "independentPresentationOrders": result["independentPresentationOrders"]}))
