"""Descriptor-bound access to the fixed nonspeech transport fixture."""

from contextlib import contextmanager
import hashlib
import io
import os
import stat
import wave

from workbench.domain import ValidationError

from .fixtures import fixture_wave, validate_manifest_origin


_FILENAME = "fixture-v1.wav"
_ASSETS = frozenset(f"invented-attempt-{number:02}" for number in (1, 2, 4, 5, 6, 8, 9, 10, 11))
_MAX_BYTES = 128 * 1024
_EXPECTED_BYTES = 38444


@contextmanager
def _directory(path, *, dir_fd=None):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValidationError("fixture_unavailable")
        yield descriptor
    finally:
        os.close(descriptor)


def _fixture(manifest):
    if validate_manifest_origin(manifest, None) != "fixture":
        raise ValidationError("fixture_unavailable")


def _private_file(descriptor):
    info = os.fstat(descriptor)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise ValidationError("fixture_unavailable")
    return info


def _read_bounded(descriptor):
    content = bytearray()
    while len(content) <= _MAX_BYTES:
        chunk = os.read(descriptor, min(8192, _MAX_BYTES + 1 - len(content)))
        if not chunk:
            break
        content.extend(chunk)
    if len(content) > _MAX_BYTES:
        raise ValidationError("fixture_unavailable")
    return bytes(content)


def _validate_buffer(content, expected_sha):
    if len(content) != _EXPECTED_BYTES or hashlib.sha256(content).hexdigest() != expected_sha:
        raise ValidationError("fixture_unavailable")
    with wave.open(io.BytesIO(content), "rb") as recording:
        if ((recording.getnchannels(), recording.getsampwidth(), recording.getframerate(),
             recording.getnframes(), recording.getcomptype()) != (1, 2, 16000, 19200, "NONE")
                or len(recording.readframes(19201)) != 38400):
            raise ValidationError("fixture_unavailable")


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def create_media(project_dir, manifest):
    """Write one shared fixture exclusively; an existing file is never replaced."""
    try:
        _fixture(manifest)
        if not os.path.isabs(project_dir):
            raise ValidationError("fixture_unavailable")
        with _directory(project_dir) as project:
            try:
                os.mkdir("media", 0o700, dir_fd=project)
            except FileExistsError:
                pass
            with _directory("media", dir_fd=project) as media:
                descriptor = os.open(_FILENAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=media)
                try:
                    _private_file(descriptor)
                    remaining = memoryview(fixture_wave())
                    while remaining:
                        written = os.write(descriptor, remaining)
                        if written <= 0:
                            raise ValidationError("fixture_unavailable")
                        remaining = remaining[written:]
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.fsync(media)
            os.fsync(project)
    except (OSError, ValidationError, TypeError, ValueError, RecursionError):
        raise ValidationError("fixture_unavailable") from None


def read_fixture(project_dir, manifest, attempt_id):
    """Return a complete bounded buffer; the parent owns current authorization."""
    try:
        _fixture(manifest)
        if type(attempt_id) is not str or not os.path.isabs(project_dir):
            raise ValidationError("fixture_unavailable")
        attempt = next((attempt for attempt in manifest["attempts"] if attempt["id"] == attempt_id), None)
        if (attempt is None or attempt["recording"] is None
                or attempt["recording"]["origin"] != "synthetic" or attempt["recording"]["assetId"] not in _ASSETS):
            raise ValidationError("fixture_unavailable")
        with _directory(project_dir) as project, _directory("media", dir_fd=project) as media:
            descriptor = os.open(_FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=media)
            try:
                before = _private_file(descriptor)
                if before.st_size != _EXPECTED_BYTES or before.st_size > _MAX_BYTES:
                    raise ValidationError("fixture_unavailable")
                content = _read_bounded(descriptor)
                _validate_buffer(content, attempt["recording"]["sha256"])
                if _identity(before) != _identity(_private_file(descriptor)):
                    raise ValidationError("fixture_unavailable")
            finally:
                os.close(descriptor)
        return content
    except (OSError, ValidationError, TypeError, ValueError, RecursionError, EOFError, wave.Error):
        raise ValidationError("fixture_unavailable") from None
