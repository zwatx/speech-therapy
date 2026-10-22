"""Fixed generated nonspeech and public pending-content workflow fixtures."""

import copy
import hashlib
import io
import math
import struct
import wave
from functools import lru_cache

from workbench.content import prepare_content_manifest
from workbench.demo import make_manifest
from workbench.domain import ValidationError, bind_manifest, semantic_digest


PUBLIC_PACK_SHA256 = "a957a9e3291f0d90b275d40cd914890836ee7e6fc4fd361f7589cd1444587ef3"


@lru_cache(maxsize=1)
def fixture_wave():
    """Return a quiet 220 Hz tone: transport material, never speech evidence."""
    samples = b"".join(struct.pack("<h", round(800 * math.sin(2 * math.pi * 220 * index / 16000)))
                       for index in range(19200))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(samples)
    return buffer.getvalue()


def fixture_manifest():
    """Keep invented workflow metadata separate from the nonspeech media bytes."""
    manifest = copy.deepcopy(make_manifest())
    manifest.update(projectId="demo-review", title="Generated nonspeech access fixture")
    sha = hashlib.sha256(fixture_wave()).hexdigest()
    for attempt in manifest["attempts"]:
        if attempt["recording"] is not None:
            attempt["recording"].update(sha256=sha, durationMs=1200)
    return bind_manifest(manifest)


def validate_manifest_origin(manifest, public_pack_bytes):
    """Accept only closed generated metadata or the exact fixed public pack."""
    try:
        digest = semantic_digest(manifest)
        if digest == semantic_digest(fixture_manifest()):
            return "fixture"
        if (type(public_pack_bytes) is bytes
                and hashlib.sha256(public_pack_bytes).hexdigest() == PUBLIC_PACK_SHA256
                and digest == semantic_digest(prepare_content_manifest(public_pack_bytes))):
            return "content-preparation"
    except (ValidationError, TypeError, ValueError, RecursionError):
        pass
    raise ValidationError("manifest_origin_invalid") from None
