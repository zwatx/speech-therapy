import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from content_review.__main__ import fixed_packet, main
from content_review.private_io import FileError, read_private
from content_review.validation import validation_draft
from content_review.packet import source_manifest
from workbench.store import Store


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)

    def call(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(x) for x in args])
        return code, out.getvalue(), err.getvalue()

    def private(self, name, raw=b'{}'):
        path = self.root / name
        path.write_bytes(raw)
        path.chmod(0o600)
        return path

    def test_build_check_and_exclusive_creation(self):
        output = self.root / 'packet'
        code, out, err = self.call(['build', output])
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out)['counts']['allTargetOccurrences'], 23)
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        self.assertEqual(len(list(output.iterdir())), 5)
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        for p in output.iterdir():
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        code, out, err = self.call(['check', output / 'packet.json', output / 'declarations.json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['status'], 'pending_declarations')
        code, out, err = self.call(['build', output])
        self.assertEqual((code, out), (2, ''))
        self.assertEqual(json.loads(err), {'error': 'output_unavailable'})
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_invalid_input_never_prints_source(self):
        marker = 'private-reviewer-comment-do-not-print'
        path = self.private('bad.json', ('{"note":"' + marker + '","note":1}').encode())
        code, out, err = self.call(['check', path, path])
        self.assertEqual(code, 2)
        self.assertNotIn(marker, out + err)
        self.assertNotIn(str(path), out + err)

    def test_invalid_arguments_never_echo_private_values(self):
        marker = 'private-reviewer-comment-do-not-print'
        for args in ([marker], ['build', str(self.root / 'out'), marker], ['check']):
            with self.subTest(args=args):
                code, out, err = self.call(args)
                self.assertEqual((code, out), (2, ''))
                self.assertEqual(json.loads(err), {'error': 'invalid_arguments'})
                self.assertNotIn(marker, out + err)

    def test_nonprivate_file_and_parent_rejected(self):
        path = self.private('input.json')
        path.chmod(0o644)
        with self.assertRaises(FileError):
            read_private(str(path))
        path.chmod(0o600)
        self.root.chmod(0o755)
        with self.assertRaises(FileError):
            read_private(str(path))
        self.root.chmod(0o700)

    def test_symlink_hardlink_directory_and_fifo_rejected(self):
        path = self.private('original.json')
        link = self.root / 'link.json'
        link.symlink_to(path)
        with self.assertRaises(FileError):
            read_private(str(link))
        hard = self.root / 'hard.json'
        os.link(path, hard)
        with self.assertRaises(FileError):
            read_private(str(path))
        folder = self.root / 'folder'
        folder.mkdir(mode=0o700)
        with self.assertRaises(FileError):
            read_private(str(folder))
        fifo = self.root / 'pipe'
        os.mkfifo(fifo, 0o600)
        with self.assertRaises(FileError):
            read_private(str(fifo))

    def test_ancestor_symlink_and_oversize_rejected(self):
        folder = self.root / 'private'
        folder.mkdir(mode=0o700)
        item = folder / 'input.json'
        item.write_bytes(b'{}')
        item.chmod(0o600)
        alias = self.root / 'alias'
        alias.symlink_to(folder, target_is_directory=True)
        with self.assertRaises(FileError):
            read_private(str(alias / item.name))
        with item.open('wb') as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
        with self.assertRaises(FileError):
            read_private(str(item))

    def test_validation_leaves_numeric_and_professional_inputs_pending(self):
        packet = fixed_packet()
        draft = validation_draft(packet)
        self.assertTrue(all(v is None for v in draft['pendingDecisions'].values()))
        self.assertFalse(any(draft['claimLimits'].values()))
        evidence = {r['id']: r['required'] for r in draft['evidenceRequirements']}
        self.assertIn('all_attempt_denominator', evidence)
        self.assertIn('repeat_and_conditions', evidence)
        self.assertIn('precision_and_correction', evidence)
        self.assertTrue(any('infeasible' in s for s in evidence['split_isolation']))
        changed = copy.deepcopy(packet)
        changed['claimLimits']['clinicalUseEligible'] = True
        with self.assertRaises(ValueError):
            validation_draft(changed)

    def test_export_command_retains_history_and_refuses_overwrite(self):
        store = Store.create(self.root / 'project.jsonl', source_manifest())
        store.record_content_review('r-beginning-rabbit', {
            'reviewerId': 'invented-account', 'decision': 'accepted',
            'notes': 'Invented engineering record', 'reference': None,
        })
        source = self.private('export.json', json.dumps(store.export_bundle()).encode())
        output = self.root / 'history.json'
        code, out, err = self.call(['inspect-export', source, output])
        self.assertEqual((code, err), (0, ''))
        result = json.loads(read_private(str(output)))
        self.assertEqual(result['records'][0]['engineeringDecision'], 'accepted')
        self.assertFalse(result['authenticationEstablished'])
        self.assertFalse(result['qualifiedApprovalEstablished'])
        self.assertNotIn('Invented engineering record', out)
        before = output.read_bytes()
        code, out, err = self.call(['inspect-export', source, output])
        self.assertEqual(code, 2)
        self.assertEqual(output.read_bytes(), before)

    def test_export_failure_leaves_no_output(self):
        source = self.private('bad-export.json', b'{"reviewer":"private-marker"}')
        output = self.root / 'history.json'
        code, out, err = self.call(['inspect-export', source, output])
        self.assertEqual((code, out), (2, ''))
        self.assertEqual(json.loads(err), {'error': 'invalid_preparation_export'})
        self.assertNotIn('private-marker', err)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
