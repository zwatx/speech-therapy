"""Strict local engineering manifest and PCM reader. No application data access."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import re
import wave

import numpy as np
import torch

SAMPLE_RATE = 16_000
BLANK = "<blank>"
AUTHORITY = {"productionEligible": False, "learnerFeedbackEligible": False}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    result = json.loads(path.read_text(), object_pairs_hook=pairs)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    return result


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def load_pcm(path: Path, expected_hash: str | None = None) -> torch.Tensor:
    if not path.is_file() or path.stat().st_size > 200_000:
        raise ValueError("Audio must be a local WAV of at most 200 KB")
    data = path.read_bytes()
    if expected_hash is not None and digest(data) != expected_hash:
        raise ValueError("Audio SHA-256 mismatch")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, SAMPLE_RATE, "NONE"):
                raise ValueError("Audio requires mono 16 kHz, 16-bit PCM WAV")
            n = wav.getnframes()
            if not 2400 <= n <= 80_000:
                raise ValueError("Audio duration must be 150 ms to 5 seconds")
            raw = wav.readframes(n)
            if len(raw) != n * 2:
                raise ValueError("Truncated PCM payload")
    except (wave.Error, EOFError) as exc:
        raise ValueError("Malformed WAV") from exc
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if not np.isfinite(samples).all() or np.max(np.abs(samples)) >= 0.999:
        raise ValueError("Audio must be finite and not clipped")
    if float(np.sqrt(np.mean(samples * samples))) < 1e-5:
        raise ValueError("Audio is silent")
    return torch.from_numpy(samples)


def validate_vocabulary(value) -> list[str]:
    if (not isinstance(value, list) or not 2 <= len(value) <= 512
            or any(not isinstance(v, str) or not v.strip() or len(v) > 64 for v in value)
            or len(set(value)) != len(value) or value[0] != BLANK):
        raise ValueError("Vocabulary must have a unique blank at index 0 and nonempty phone tokens")
    return value


def load_manifest(path: Path) -> tuple[dict, list[dict]]:
    manifest = read_json(path)
    required = {"schemaVersion", "purpose", "labelSource", "vocabulary", "items", *AUTHORITY}
    public_alignment = manifest.get("schemaVersion") == 2
    if public_alignment:
        required |= {"splitIdentityBasis", "sourceLockSha256"}
    if set(manifest) != required or manifest["schemaVersion"] not in (1, 2):
        raise ValueError("Unsupported manifest fields or version")
    if any(manifest[k] is not False for k in AUTHORITY):
        raise ValueError("Manifest must be ineligible for production and learner feedback")
    if public_alignment:
        if (manifest["purpose"] != "public-speech-engineering"
                or manifest["labelSource"] != "automatic-phone-alignment"
                or manifest["splitIdentityBasis"] != "speaker-disjoint-households-unknown"):
            raise ValueError("Version 2 requires explicit automatic labels and unknown households")
        lock_path = path.resolve().parent / "source-lock.json"
        if digest(lock_path.read_bytes()) != manifest["sourceLockSha256"]:
            raise ValueError("Public corpus source-lock SHA-256 mismatch")
        source_lock = read_json(lock_path)
        if (source_lock.get("corpus") != "cmu-arctic-0.95"
                or source_lock.get("labelSource") != "automatic-phone-alignment"
                or not isinstance(source_lock.get("files"), dict)
                or not isinstance(source_lock.get("selected"), list)):
            raise ValueError("Unsupported public corpus source lock")
        if "profile" in source_lock:
            from arctic_profiles import validate_profile_selection
            validate_profile_selection(source_lock["selected"], source_lock["profile"])
        source_selection = {}
        for selected in source_lock["selected"]:
            if (not isinstance(selected, dict) or set(selected) != {"speaker", "utterance", "split"}
                    or selected["speaker"] not in {"bdl", "rms", "slt", "awb", "clb", "jmk"}
                    or not isinstance(selected["utterance"], str)
                    or not re.fullmatch(r"arctic_a\d{4}", selected["utterance"])
                    or selected["split"] not in {"train", "calibration", "test"}):
                raise ValueError("Invalid source-lock selection")
            key = f"{selected['speaker']}/{selected['utterance']}.wav"
            if key in source_selection:
                raise ValueError("Duplicate source-lock selection")
            source_selection[key] = selected
        if len(source_selection) != len(manifest["items"]):
            raise ValueError("Manifest must contain exactly the locked corpus selection")
    else:
        if manifest["purpose"] not in {"synthetic-engineering", "permitted-engineering"}:
            raise ValueError("Only non-patient engineering fixtures are supported")
        if manifest["labelSource"] != "produced-phones":
            raise ValueError("Targets must describe produced phones, not the expected prompt")
    vocabulary = validate_vocabulary(manifest["vocabulary"])
    if not isinstance(manifest["items"], list) or not 3 <= len(manifest["items"]) <= 10_000:
        raise ValueError("Manifest requires 3–10000 items")
    seen_ids, audio_hashes, pcm_hashes = set(), set(), set()
    partitions = {"speakerHash": {}, "householdHash": {}}
    splits, rows = set(), []
    root = path.resolve().parent
    for item in manifest["items"]:
        fields = {"id", "audioPath", "audioSha256", "speakerHash", "householdHash", "split", "producedPhones", "provenance"}
        if public_alignment:
            fields.remove("producedPhones")
            fields |= {"pseudoPhones", "alignmentPath", "alignmentSha256"}
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError("Invalid manifest item fields")
        if public_alignment:
            selected = source_selection.get(item["audioPath"])
            if (selected is None or item["split"] != selected["split"]
                    or item["speakerHash"] != digest(f"cmu-arctic-speaker:{selected['speaker']}".encode())
                    or item["alignmentPath"] != f"{selected['speaker']}/{selected['utterance']}.lab"
                    or item["id"] != f"cmu-{selected['speaker']}-{selected['utterance']}"):
                raise ValueError("Manifest identity, split, or file pairing differs from source lock")
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in seen_ids:
            raise ValueError("Duplicate or invalid item ID")
        if not isinstance(item["provenance"], str) or not item["provenance"].strip():
            raise ValueError("Each fixture requires a permitted-use provenance reference")
        if item["split"] not in {"train", "calibration", "test"}:
            raise ValueError("Invalid split")
        for field in ("audioSha256", "speakerHash", "householdHash"):
            if public_alignment and field == "householdHash":
                if item[field] is not None:
                    raise ValueError("Public corpus households are unknown, not inferred from speakers")
                continue
            if not isinstance(item[field], str) or not re.fullmatch(r"[a-f0-9]{64}", item[field]):
                raise ValueError(f"Invalid {field}")
        if item["audioSha256"] in audio_hashes:
            raise ValueError("Duplicate audio hash, including across splits")
        for key, mapping in partitions.items():
            if public_alignment and key == "householdHash":
                continue
            identity = item[key]
            if identity in mapping and mapping[identity] != item["split"]:
                raise ValueError(f"{key} split overlap")
            mapping[identity] = item["split"]
        phones = item["pseudoPhones" if public_alignment else "producedPhones"]
        if (not isinstance(phones, list) or not 1 <= len(phones) <= 100
                or any(not isinstance(p, str) or p not in vocabulary[1:] for p in phones)):
            raise ValueError("Unsupported phone, blank target, or empty produced-phone target")
        if not isinstance(item["audioPath"], str) or Path(item["audioPath"]).is_absolute():
            raise ValueError("Audio paths must be relative to the manifest")
        audio = (root / item["audioPath"]).resolve()
        if not audio.is_relative_to(root):
            raise ValueError("Audio path escapes manifest directory")
        samples = load_pcm(audio, item["audioSha256"])
        if public_alignment:
            from labels import parse_alignment
            alignment_path = item["alignmentPath"]
            if not isinstance(alignment_path, str) or Path(alignment_path).is_absolute():
                raise ValueError("Alignment paths must be relative")
            alignment = (root / alignment_path).resolve()
            if not alignment.is_relative_to(root) or alignment.stat().st_size > 20_000:
                raise ValueError("Invalid alignment path or size")
            label_bytes = alignment.read_bytes()
            if digest(label_bytes) != item["alignmentSha256"]:
                raise ValueError("Alignment SHA-256 mismatch")
            for local, expected_hash in [(item["audioPath"], item["audioSha256"]),
                                         (alignment_path, item["alignmentSha256"])]:
                if source_lock["files"].get(local, {}).get("sha256") != expected_hash:
                    raise ValueError("Manifest file digest differs from corpus source lock")
            if parse_alignment(label_bytes, len(samples) / SAMPLE_RATE) != phones:
                raise ValueError("Pseudo-phone targets differ from source alignment")
        # RIFF metadata can change a file hash without changing the recording.
        # Float32 represents every normalized PCM16 value exactly; use a fixed byte order.
        pcm_hash = digest(samples.numpy().astype("<f4").tobytes())
        if pcm_hash in pcm_hashes:
            raise ValueError("Duplicate decoded PCM, including across splits")
        pcm_hashes.add(pcm_hash)
        rows.append({**item, "targetPhones": phones, "samples": samples})
        seen_ids.add(item["id"])
        audio_hashes.add(item["audioSha256"])
        splits.add(item["split"])
    if splits != {"train", "calibration", "test"}:
        raise ValueError("All three identity-disjoint splits are required")
    return manifest, rows


def make_fixtures(directory: Path, seed: int = 7) -> Path:
    """Tones are engineering symbols, never simulated clinical speech."""
    directory.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(seed)
    items = []
    patterns = [["tone-a"], ["tone-b"], ["tone-a", "tone-b"],
                ["tone-b", "tone-a"], ["tone-a", "tone-a"], ["tone-b", "tone-b"]]
    for split, count in [("train", 18), ("calibration", 6), ("test", 6)]:
        for i in range(count):
            phones = patterns[i % len(patterns)]
            chunks = [np.zeros(640)]
            for phone in phones:
                length = int(rng.integers(2000, 3200))
                frequency = (340 if phone == "tone-a" else 1180) + float(rng.uniform(-15, 15))
                tone = 0.22 * np.sin(2 * np.pi * frequency * np.arange(length) / SAMPLE_RATE + rng.uniform(0, 1))
                tone *= np.minimum(1, np.minimum(np.arange(length) / 160, np.arange(length)[::-1] / 160))
                chunks.extend([tone, np.zeros(int(rng.integers(500, 900)))])
            signal = np.concatenate(chunks)
            signal += rng.normal(0, 0.0005, len(signal))
            name = f"{split}-{i:02d}"
            audio = directory / f"{name}.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
                wav.writeframes((signal * 32767).astype("<i2").tobytes())
            items.append({"id": name, "audioPath": audio.name, "audioSha256": digest(audio.read_bytes()),
                          "speakerHash": digest(f"synthetic-speaker-{name}".encode()),
                          "householdHash": digest(f"synthetic-household-{name}".encode()),
                          "split": split, "producedPhones": phones,
                          "provenance": f"generated-tones-v1; seed={seed}; no human recording"})
    path = directory / "manifest.json"
    write_json(path, {"schemaVersion": 1, "purpose": "synthetic-engineering", "labelSource": "produced-phones",
                      "vocabulary": [BLANK, "tone-a", "tone-b"], "items": items, **AUTHORITY})
    return path
