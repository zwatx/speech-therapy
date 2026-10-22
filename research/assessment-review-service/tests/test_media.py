import os
import copy
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest

from review_service.fixtures import fixture_manifest, fixture_wave
from review_service.media import create_media, read_fixture
from workbench.domain import ValidationError


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project_dir = Path(self.temporary.name).resolve() / "demo-review"
        self.project_dir.mkdir(mode=0o700)
        self.manifest = fixture_manifest()

    def test_created_fixture_is_private_real_wave_shared_by_nine_closed_assets(self):
        create_media(self.project_dir, self.manifest)
        directory = self.project_dir / "media"
        files = list(directory.iterdir())
        self.assertEqual([path.name for path in files], ["fixture-v1.wav"])
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(files[0].stat().st_nlink, 1)
        for attempt in self.manifest["attempts"]:
            if attempt["recording"]:
                self.assertEqual(read_fixture(self.project_dir, self.manifest, attempt["id"]), fixture_wave())
        with self.assertRaises(ValidationError):
            create_media(self.project_dir, self.manifest)

    def test_changed_truncated_or_oversized_buffers_are_never_delivered(self):
        create_media(self.project_dir, self.manifest)
        fixture = self.project_dir / "media/fixture-v1.wav"
        original = fixture_wave()
        for invalid in (original[:-1], original + b"x", b"x" * (128 * 1024 + 1),
                        original[:50] + bytes([original[50] ^ 1]) + original[51:]):
            fixture.write_bytes(invalid)
            with self.subTest(size=len(invalid)), self.assertRaises(ValidationError) as error:
                read_fixture(self.project_dir, self.manifest, "attempt-01")

    def test_origin_spoof_paths_missing_recordings_and_unknown_attempts_are_generic(self):
        create_media(self.project_dir, self.manifest)
        cases = [(self.manifest, "attempt-03"), (self.manifest, "attempt-07"), (self.manifest, "unknown"),
                 (self.manifest, "../../PRIVATE_PATH"), (self.manifest, None), ({}, "attempt-01")]
        for field, value in (("assetId", "../../PRIVATE_PATH"), ("origin", "permissioned"), ("sha256", "0" * 64)):
            manifest = copy.deepcopy(self.manifest)
            manifest["attempts"][0]["recording"][field] = value
            cases.append((manifest, "attempt-01"))
        for manifest, attempt_id in cases:
            with self.subTest(attempt_id=attempt_id):
                with self.assertRaises(ValidationError) as error:
                    read_fixture(self.project_dir, manifest, attempt_id)
                self.assertEqual(str(error.exception), "fixture_unavailable")
        source_spoof = copy.deepcopy(self.manifest)
        malformed = b"X" * 38444
        source_spoof["attempts"][0]["recording"]["sha256"] = hashlib.sha256(malformed).hexdigest()
        (self.project_dir / "media/fixture-v1.wav").write_bytes(malformed)
        with self.assertRaises(ValidationError):
            read_fixture(self.project_dir, source_spoof, "attempt-01")

    def test_symlink_hardlink_missing_file_and_file_modes_are_denied(self):
        create_media(self.project_dir, self.manifest)
        fixture = self.project_dir / "media/fixture-v1.wav"
        original = self.project_dir / "private-original.wav"
        fixture.rename(original)
        fixture.symlink_to(original)
        self.assert_unavailable()
        with self.assertRaises(ValidationError):
            create_media(self.project_dir, self.manifest)
        fixture.unlink()
        os.link(original, fixture)
        self.assert_unavailable()
        fixture.unlink()
        self.assert_unavailable()
        original.rename(fixture)
        for mode in (0o644, 0o400, 0o660, 0o1600):
            fixture.chmod(mode)
            with self.subTest(mode=oct(mode)):
                self.assert_unavailable()
        fixture.chmod(0o600)
        self.assertEqual(read_fixture(self.project_dir, self.manifest, "attempt-01"), fixture_wave())

    def test_private_project_and_media_directory_modes_symlinks_and_types_are_checked(self):
        create_media(self.project_dir, self.manifest)
        media = self.project_dir / "media"
        for directory in (self.project_dir, media):
            directory.chmod(0o755)
            self.assert_unavailable()
            with self.assertRaises(ValidationError):
                create_media(self.project_dir, self.manifest)
            directory.chmod(0o700)
        real_media = self.project_dir / "original-media"
        media.rename(real_media)
        media.symlink_to(real_media, target_is_directory=True)
        self.assert_unavailable()
        media.unlink()
        media.write_bytes(b"not a directory")
        self.assert_unavailable()
        media.unlink()
        real_media.rename(media)
        alias = self.project_dir.parent / "symlink-project"
        alias.symlink_to(self.project_dir, target_is_directory=True)
        with self.assertRaises(ValidationError):
            read_fixture(alias, self.manifest, "attempt-01")

    def test_nonregular_fixture_is_rejected_without_waiting_for_pipe_input(self):
        create_media(self.project_dir, self.manifest)
        fixture = self.project_dir / "media/fixture-v1.wav"
        fixture.unlink()
        os.mkfifo(fixture, 0o600)
        self.assert_unavailable()
        fixture.unlink()
        fixture.mkdir(mode=0o700)
        self.assert_unavailable()

    def test_atomic_path_replacement_never_returns_unvalidated_bytes(self):
        create_media(self.project_dir, self.manifest)
        fixture = self.project_dir / "media/fixture-v1.wav"
        stop = threading.Event()
        started = threading.Event()
        replacement_errors = []

        def replace_path():
            count = 0
            try:
                while not stop.is_set():
                    replacement = fixture.parent / "replacement.wav"
                    descriptor = os.open(replacement, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    try:
                        os.write(descriptor, fixture_wave() if count % 2 else b"X" * 38444)
                    finally:
                        os.close(descriptor)
                    os.replace(replacement, fixture)
                    count += 1
                    started.set()
            except BaseException as error:
                replacement_errors.append(error)
                started.set()

        thread = threading.Thread(target=replace_path)
        thread.start()
        try:
            self.assertTrue(started.wait(5))
            for _ in range(30):
                try:
                    content = read_fixture(self.project_dir, self.manifest, "attempt-01")
                except ValidationError as error:
                    self.assertEqual(str(error), "fixture_unavailable")
                else:
                    self.assertEqual(content, fixture_wave())
        finally:
            stop.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(replacement_errors, [])

    def test_create_rejects_unregistered_origin_before_writing_media(self):
        invalid = copy.deepcopy(self.manifest)
        invalid["title"] = "Unregistered synthetic project"
        with self.assertRaises(ValidationError) as error:
            create_media(self.project_dir, invalid)
        self.assertEqual(str(error.exception), "fixture_unavailable")
        self.assertFalse((self.project_dir / "media").exists())

    def assert_unavailable(self):
        with self.assertRaises(ValidationError) as error:
            read_fixture(self.project_dir, self.manifest, "attempt-01")
        self.assertEqual(str(error.exception), "fixture_unavailable")


if __name__ == "__main__":
    unittest.main()
