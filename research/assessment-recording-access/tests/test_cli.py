import contextlib
import io
from pathlib import Path
import tempfile
import unittest


class CliTests(unittest.TestCase):
    def test_fresh_private_initialization_prints_no_credentials_and_preserves_existing_root(self):
        from recording_access.__main__ import main
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / 'vault'
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['init', str(root), 'project-a']), 0)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            credentials = root / 'fixture-credentials.json'
            self.assertEqual(credentials.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('password', output.getvalue())
            self.assertNotIn(credentials.read_text(), output.getvalue())
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['init', str(root), 'project-a']), 1)
            self.assertTrue(credentials.exists())

    def test_private_import_hidden_login_and_exclusive_metadata_export(self):
        import json
        from unittest.mock import patch
        from recording_access.__main__ import main
        from test_vault import pcm, declaration
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / 'vault'
            sink = io.StringIO()
            with contextlib.redirect_stdout(sink):
                self.assertEqual(main(['init', str(root), 'project-a']), 0)
            credentials = json.loads((root / 'fixture-credentials.json').read_bytes())['accounts'][0]
            raw = pcm()
            wave_file, declarations = Path(parent) / 'fixture.wav', Path(parent) / 'declaration.json'
            wave_file.write_bytes(raw)
            declarations.write_text(json.dumps(declaration(raw)))
            wave_file.chmod(0o600)
            declarations.chmod(0o600)
            sink = io.StringIO()
            with contextlib.redirect_stdout(sink):
                self.assertEqual(main(['import', str(root), str(wave_file), str(declarations)]), 0)
            receipt = json.loads(sink.getvalue())
            exported = Path(parent) / 'metadata.json'
            with patch('recording_access.__main__.getpass.getpass', return_value=credentials['password']), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['read-check', str(root), credentials['accountId'], receipt['recordingId'], 'review']), 0)
                self.assertEqual(main(['export-metadata', str(root), credentials['accountId'], str(exported)]), 0)
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(['export-metadata', str(root), credentials['accountId'], str(exported)]), 1)
            self.assertEqual(exported.stat().st_mode & 0o777, 0o600)
            projection = exported.read_text()
            self.assertNotIn(credentials['password'], projection)
            self.assertNotIn('invented-subject-a', projection)
            self.assertEqual(json.loads(projection)['counts']['recordingIntentDenominator'], 1)

    def test_unsafe_input_link_fifo_and_nonprivate_output_parent_fail_closed(self):
        import os
        from recording_access.__main__ import operator_read, operator_write
        from recording_access import VaultError
        with tempfile.TemporaryDirectory() as parent:
            base = Path(parent)
            actual = base / 'private.json'
            actual.write_bytes(b'{}')
            actual.chmod(0o600)
            linked = base / 'link.json'
            linked.symlink_to(actual)
            fifo = base / 'pipe'
            os.mkfifo(fifo, 0o600)
            for path in (linked, fifo):
                with self.subTest(path=path.name), self.assertRaises(VaultError):
                    operator_read(path, 100)
            base.chmod(0o755)
            with self.assertRaises(VaultError):
                operator_write(base / 'export.json', {})
            base.chmod(0o700)
