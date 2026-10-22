"""Synthetic fixed-40 transport coverage; no network or corpus access."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from nisqa_ingest.frozen_directory_transport import FrozenDirectoryZip
from nisqa_quality.transport import QualityDirectoryZip
from nisqa_quality.replication_transport import ReplicationDirectoryZip, POLICY, TRAIN_PREFIX
from nisqa_ingest.remote_zip import RemoteZip, RemoteZipError, OFFICIAL_URL
from nisqa_ingest.test_remote_zip import HTTP, Raw, Sparse, archive


class Clock:
    def __init__(self):
        self.now, self.sleeps = 0., []

    def __call__(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration


def fixture(method=zipfile.ZIP_DEFLATED, body=b'synthetic samples ' * 100, count=40):
    names = [f'{TRAIN_PREFIX}{index:03d}.wav' for index in range(count)]
    raw = archive([(name, body) for name in names], compression=method)
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        members = [RemoteZip._member(info) for info in source.infolist()]
    return raw, members, names, body


class ReplicationTests(unittest.TestCase):
    def open(self, directory, raw, members, names, **kwargs):
        clock = kwargs.pop('clock', Clock())
        http = kwargs.pop('session', HTTP(raw))
        size = raw.size if isinstance(raw, Sparse) else len(raw)
        remote = ReplicationDirectoryZip(OFFICIAL_URL, size, directory, frozen_members=members,
                                    selected_names=names, study_sha256=kwargs.pop('study_sha256', 'a' * 64), session=http, clock=clock, sleep=clock.sleep, **kwargs)
        self.addCleanup(remote.close)
        return remote, http, clock

    def test_stored_and_deflate_exact_three_ranges_no_directory_reads(self):
        for method in (0, 8):
            raw, members, names, body = fixture(method)
            with self.subTest(method=method), tempfile.TemporaryDirectory() as directory:
                remote, http, clock = self.open(directory, raw, members, names)
                self.assertFalse(http.requests)
                with self.assertRaises(RemoteZipError):
                    remote.members()
                remote.bootstrap()
                self.assertEqual(remote.members(), members)
                self.assertEqual(len(http.requests), 1)
                result = remote.acquire(names[8], allowlist=names, output_name='resume-audio-08.wav')
                self.assertEqual(Path(result['path']).read_bytes(), body)
                self.assertEqual(result['member'], members[8])
                self.assertEqual(result['sha256'], hashlib.sha256(body).hexdigest())
                get_ranges = [r[2]['headers']['Range'] for r in http.requests if r[0] == 'GET']
                start = members[8]['header_offset']; header_end = start + 30 + len(names[8])
                self.assertEqual(get_ranges, [f'bytes={start}-{start+29}', f'bytes={start+30}-{header_end-1}',
                                             f"bytes={header_end}-{header_end+members[8]['compress_size']-1}"])
                self.assertEqual(clock.sleeps, [2., 2.])
                manifest = remote.manifest()
                self.assertEqual(manifest['metadataRead'], 30 + len(names[8]))
                self.assertEqual(manifest['bytesRead'], 30 + len(names[8]) + members[8]['compress_size'])
                self.assertFalse(manifest['fullArchiveMd5Verified'])
                with self.assertRaises(RemoteZipError):
                    remote.acquire(names[8], allowlist=names, output_name='resume-audio-08.wav')

    def test_pacing_across_members_and_payload_chunk_bound(self):
        body = bytes(range(256)) * 1000
        raw, members, names, _ = fixture(0, body)
        with tempfile.TemporaryDirectory() as directory:
            remote, http, clock = self.open(directory, raw, members, names)
            remote.bootstrap()
            for index in (0, 1):
                remote.acquire(names[index], allowlist=names, output_name=f'{index}.wav')
            gets = [r for r in http.requests if r[0] == 'GET']
            self.assertEqual(len(gets), 6)
            self.assertEqual(len(clock.sleeps), 5)
            for request in gets:
                a, b = map(int, request[2]['headers']['Range'][6:].split('-'))
                self.assertLessEqual(b - a + 1, 1024**2)

    def test_allowlist_and_bounds_fail_before_get(self):
        raw, members, names, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            remote, http, _ = self.open(directory, raw, members, names)
            remote.bootstrap()
            cases = [dict(allowlist=names[:1], output_name='x'), dict(allowlist=names, output_name='../x'),
                     dict(allowlist=names, output_name='x', max_uncompressed=1),
                     dict(allowlist=names, output_name='x', max_compressed=1)]
            for options in cases:
                with self.assertRaises(RemoteZipError):
                    remote.acquire(names[0], **options)
            self.assertEqual(len(http.requests), 1)

    def test_header_filename_crc_size_method_and_flags_mismatch(self):
        raw, members, names, _ = fixture()
        mutations = [(0, b'FAIL'), (8, struct.pack('<H', 0)), (6, struct.pack('<H', 1)),
                     (14, struct.pack('<I', 0)), (18, struct.pack('<I', 1)), (22, struct.pack('<I', 1)),
                     (30, b'WRONG')]
        for offset, replacement in mutations:
            changed = bytearray(raw); changed[offset:offset + len(replacement)] = replacement
            with self.subTest(offset=offset), tempfile.TemporaryDirectory() as directory:
                remote, http, _ = self.open(directory, bytes(changed), members, names)
                remote.bootstrap()
                with self.assertRaises(RemoteZipError):
                    remote.acquire(names[0], allowlist=names, output_name='x')
                self.assertLessEqual(len(http.requests), 3)

    def test_crc_failure_preserves_partial_and_nooverwrite(self):
        raw, members, names, body = fixture(0)
        changed = bytearray(raw); changed[30 + len(names[0])] ^= 1
        with tempfile.TemporaryDirectory() as directory:
            remote, _, _ = self.open(directory, bytes(changed), members, names)
            remote.bootstrap()
            with self.assertRaisesRegex(RemoteZipError, 'CRC'):
                remote.acquire(names[0], allowlist=names, output_name='x')
            partial = Path(directory, 'x.partial')
            self.assertTrue(partial.exists())
            self.assertFalse(Path(directory, 'x').exists())
            self.assertEqual(partial.stat().st_size, len(body))
            with self.assertRaises(RemoteZipError):
                remote.acquire(names[0], allowlist=names, output_name='x')

    def test_deflate_trailing_truncated_and_expansion_fail(self):
        # Build exact synthetic compressed bodies with valid header/directory
        # identity, so the decompression checks are independently exercised.
        raw, members, names, _ = fixture()
        first = members[0]; start = 30 + len(names[0]); count = first['compress_size']
        variants = [raw[start:start + count] + b'x', raw[start:start + count - 1]]
        for payload in variants:
            modified_members = copy.deepcopy(members)
            delta = len(payload) - count
            changed = bytearray(raw[:start] + payload + raw[start + count:])
            struct.pack_into('<I', changed, 18, len(payload))
            for item in modified_members:
                if item['header_offset'] > 0:
                    item['header_offset'] += delta; item['headerOffset'] += delta
            modified_members[0]['compress_size'] = modified_members[0]['compressedSize'] = len(payload)
            with tempfile.TemporaryDirectory() as directory:
                remote, _, _ = self.open(directory, bytes(changed), modified_members, names)
                remote.bootstrap()
                with self.assertRaises(RemoteZipError):
                    remote.acquire(names[0], allowlist=names, output_name='x')
                self.assertTrue(Path(directory, 'x.partial').exists())
        modified_members = copy.deepcopy(members)
        modified_members[0]['file_size'] = modified_members[0]['size'] = 1
        changed = bytearray(raw); struct.pack_into('<I', changed, 22, 1)
        with tempfile.TemporaryDirectory() as directory:
            remote, _, _ = self.open(directory, bytes(changed), modified_members, names)
            remote.bootstrap()
            with self.assertRaisesRegex(RemoteZipError, 'bound'):
                remote.acquire(names[0], allowlist=names, output_name='x')

    def test_snapshot_alias_collision_path_overlap_and_selection_validation(self):
        raw, members, names, _ = fixture()
        variants = []
        for field, value in [('name', 'different'), ('filename', '../escape'), ('compress_size', -1), ('CRC', 2**32), ('flags', 1)]:
            changed = copy.deepcopy(members); changed[0][field] = value; variants.append(changed)
        changed = copy.deepcopy(members); changed[1] = copy.deepcopy(changed[0]); variants.append(changed)
        changed = copy.deepcopy(members); changed[1]['filename'] = changed[0]['filename'].swapcase(); changed[1]['name'] = changed[1]['filename']; variants.append(changed)
        changed = copy.deepcopy(members); changed[1]['header_offset'] = changed[1]['headerOffset'] = 31; variants.append(changed)
        for snapshot in variants:
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(RemoteZipError):
                    self.open(directory, raw, snapshot, names)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RemoteZipError):
                self.open(directory, raw, members, names[:39])

    def test_descriptor_and_zip64_local_sentinel_are_explicitly_unsupported(self):
        raw, members, names, _ = fixture()
        descriptor = copy.deepcopy(members); descriptor[0]['flags'] = 8
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RemoteZipError, 'descriptor'):
                self.open(directory, raw, descriptor, names)
        changed = bytearray(raw); struct.pack_into('<I', changed, 18, 0xffffffff)
        with tempfile.TemporaryDirectory() as directory:
            remote, _, _ = self.open(directory, bytes(changed), members, names)
            remote.bootstrap()
            with self.assertRaisesRegex(RemoteZipError, 'ZIP64'):
                remote.acquire(names[0], allowlist=names, output_name='x')

    def test_sparse_header_offsets_over_4gib_do_not_reread_directory(self):
        raw, members, names, body = fixture()
        base = 2**32 + 100
        shifted = copy.deepcopy(members)
        for item in shifted:
            item['header_offset'] += base; item['headerOffset'] += base
        source = Sparse(base + len(raw), [(base, raw)])
        with tempfile.TemporaryDirectory() as directory:
            remote, http, _ = self.open(directory, source, shifted, names)
            remote.bootstrap()
            result = remote.acquire(names[0], allowlist=names, output_name='x')
            self.assertEqual(Path(result['path']).read_bytes(), body)
            self.assertEqual(len(http.requests), 4)
            self.assertLess(remote.manifest()['bytesRead'], 1000)

    def test_429_is_terminal_no_body_no_retry_and_200_rejected(self):
        raw, members, names, _ = fixture()
        for status in (429, 200):
            with tempfile.TemporaryDirectory() as directory:
                http = HTTP(raw, alter=lambda r, a, b: setattr(r, 'status_code', status))
                remote, _, _ = self.open(directory, raw, members, names, session=http)
                remote.bootstrap()
                with self.assertRaises(RemoteZipError):
                    remote.acquire(names[0], allowlist=names, output_name='x')
                self.assertEqual(len(http.requests), 2)
                self.assertEqual(http.responses[-1].raw.calls, 0)
                self.assertEqual(remote.manifest()['bytesRead'], 0)
                journal = [json.loads(line) for line in Path(directory, 'request-journal.jsonl').read_text().splitlines()]
                self.assertEqual([row for row in journal if row['event'] == 'GET'][0]['status'], status)

    def test_truncation_budget_and_restart_binding_preserved(self):
        raw, members, names, _ = fixture()
        budget = 10 + 30 + len(names[0]) + 5
        def truncate(response, a, b):
            response.raw = Raw(response.raw.getvalue()[:10])
        with tempfile.TemporaryDirectory() as directory:
            remote, _, _ = self.open(directory, raw, members, names, session=HTTP(raw, alter=truncate),
                                     max_bytes=budget, metadata_bytes=budget)
            remote.bootstrap()
            with self.assertRaises(RemoteZipError):
                remote.acquire(names[0], allowlist=names, output_name='x')
            self.assertEqual(remote.manifest()['bytesRead'], 10)
            remote.close(); self._cleanups.pop()
            restarted, http, _ = self.open(directory, raw, members, names, max_bytes=budget, metadata_bytes=budget)
            self.assertEqual(restarted.manifest()['bytesRead'], 10)
            restarted.bootstrap()
            with self.assertRaisesRegex(RemoteZipError, 'budget'):
                restarted.acquire(names[0], allowlist=names, output_name='x')
            self.assertEqual(restarted.manifest()['bytesRead'], 10 + 30 + len(names[0]))
            restarted.close(); self._cleanups.pop()
            changed = copy.deepcopy(members); changed[0]['CRC'] ^= 1; changed[0]['crc32'] = f"{changed[0]['CRC']:08x}"
            with self.assertRaisesRegex(RemoteZipError, 'changed on restart'):
                self.open(directory, raw, changed, names, max_bytes=budget, metadata_bytes=budget)

    def test_policy_json_and_symlink_output_nooverwrite(self):
        json.dumps(POLICY, allow_nan=False)
        self.assertEqual(POLICY['transientRetries'], 0)
        raw, members, names, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            remote, http, _ = self.open(directory, raw, members, names)
            remote.bootstrap()
            Path(directory, 'x').symlink_to(Path(directory, 'missing'))
            with self.assertRaises(RemoteZipError):
                remote.acquire(names[0], allowlist=names, output_name='x')
            self.assertEqual(len(http.requests), 1)

    def test_full_40_sparse_members_both_methods_and_global_pacing(self):
        for method in (0, 8):
            raw, members, names, body = fixture(method, body=b'bounded synthetic fixture')
            base = 2**32 + 100
            shifted = copy.deepcopy(members)
            for item in shifted:
                item['header_offset'] += base; item['headerOffset'] += base
            source = Sparse(base + len(raw), [(base, raw)])
            with self.subTest(method=method), tempfile.TemporaryDirectory() as directory:
                remote, http, clock = self.open(directory, source, shifted, names)
                remote.bootstrap()
                self.assertEqual(remote.members(), shifted)
                for index, name in enumerate(names):
                    result = remote.acquire(name, allowlist=names, output_name=f'synthetic-{index}.wav')
                    self.assertEqual(result['sha256'], hashlib.sha256(body).hexdigest())
                    self.assertEqual(result['member'], shifted[index])
                    self.assertEqual(Path(result['path']).read_bytes(), body)
                self.assertEqual(len(http.requests), 121)
                self.assertEqual(clock.sleeps, [2.] * 119)
                self.assertEqual(remote.manifest()['metadataRead'], sum(30 + len(n) for n in names))
                self.assertEqual(remote.manifest()['bytesRead'], sum(30 + len(n) + m['compress_size'] for n, m in zip(names, shifted)))

    def test_name_length_and_extra_caps_reject_before_second_get(self):
        raw, members, names, _ = fixture()
        for offset, value in ((26, len(names[0]) + 1), (28, 4097), (28, 65535)):
            changed = bytearray(raw); struct.pack_into('<H', changed, offset, value)
            with self.subTest(offset=offset, value=value), tempfile.TemporaryDirectory() as directory:
                remote, http, _ = self.open(directory, bytes(changed), members, names)
                remote.bootstrap()
                with self.assertRaisesRegex(RemoteZipError, 'length'):
                    remote.acquire(names[0], allowlist=names, output_name='x')
                self.assertEqual(len(http.requests), 2)
                self.assertEqual(remote.manifest()['metadataRead'], 30)

    def test_payload_cap_and_canonical_study_sha_reject(self):
        raw, members, names, _ = fixture()
        for sha in ('a' * 63, 'A' * 64, 'g' * 64, None):
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(RemoteZipError, 'SHA256'):
                    self.open(directory, raw, members, names, study_sha256=sha)
        with tempfile.TemporaryDirectory() as directory:
            remote, http, _ = self.open(directory, raw, members, names)
            remote.bootstrap()
            with self.assertRaisesRegex(RemoteZipError, 'bounds'):
                remote.acquire(names[0], allowlist=names, output_name='x', max_compressed=1024**2 + 1)
            self.assertEqual(len(http.requests), 1)
        base, big_members, big_names, _ = fixture(0)
        delta = 1024**2 + 1 - big_members[0]['compress_size']
        big_members[0]['file_size'] = big_members[0]['size'] = 1024**2 + 1
        big_members[0]['compress_size'] = big_members[0]['compressedSize'] = 1024**2 + 1
        for item in big_members[1:]:
            item['header_offset'] += delta; item['headerOffset'] += delta
        oversized = Sparse(len(base) + delta, [(0, base[:30])])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RemoteZipError, 'one MiB'):
                self.open(directory, oversized, big_members, big_names)

    def test_prior_twenty_binding_counters_and_journal_prefix_preserved(self):
        raw, members, names, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            old_clock = Clock()
            with FrozenDirectoryZip(OFFICIAL_URL, len(raw), directory, frozen_members=members,
                                    selected_names=names[:20], session=HTTP(raw), clock=old_clock, sleep=old_clock.sleep) as old:
                old.bootstrap()
                old.acquire(names[0], allowlist=names[:20], output_name='prior20.wav')
                before = copy.deepcopy(old.state)
                prefix = Path(directory, 'request-journal.jsonl').read_bytes()
            remote, _, _ = self.open(directory, raw, members, names)
            for key in ('settings', 'validator', 'frozenDirectoryBinding', 'bytesRead', 'metadataRead',
                        'uncertainBytes', 'uncertainMetadata', 'reserved', 'reservedMetadata'):
                self.assertEqual(remote.state[key], before[key])
            self.assertTrue(Path(directory, 'request-journal.jsonl').read_bytes().startswith(prefix))
            remote.bootstrap()
            remote.acquire(names[1], allowlist=names, output_name='replication.wav')
            self.assertEqual(remote.state['frozenDirectoryBinding'], before['frozenDirectoryBinding'])
            self.assertGreater(remote.state['bytesRead'], before['bytesRead'])
            self.assertEqual(remote.manifest()['replicationDirectoryBinding']['studySha256'], 'a' * 64)
            self.assertTrue(Path(directory, 'request-journal.jsonl').read_bytes().startswith(prefix))

    def test_study_restart_drift_closes_lock_and_leaves_state_unchanged(self):
        raw, members, names, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            remote, _, _ = self.open(directory, raw, members, names)
            remote.bootstrap()
            before = Path(directory, 'transport-state.json').read_bytes()
            remote.close(); self._cleanups.pop()
            with self.assertRaisesRegex(RemoteZipError, 'restart'):
                self.open(directory, raw, members, names, study_sha256='b' * 64)
            self.assertEqual(Path(directory, 'transport-state.json').read_bytes(), before)
            # A subsequent valid constructor proves the rejected constructor
            # released its advisory lock rather than leaving the ledger busy.
            reopened, _, _ = self.open(directory, raw, members, names)
            self.assertEqual(reopened.state['replicationDirectoryBinding']['studySha256'], 'a' * 64)

    def test_429_on_payload_preserves_empty_partial_and_stops(self):
        raw, members, names, _ = fixture()
        start = 30 + len(names[0])
        def throttle(response, a, b):
            if a == start:
                response.status_code = 429
        with tempfile.TemporaryDirectory() as directory:
            remote, http, _ = self.open(directory, raw, members, names, session=HTTP(raw, alter=throttle))
            remote.bootstrap()
            with self.assertRaises(RemoteZipError):
                remote.acquire(names[0], allowlist=names, output_name='x')
            self.assertEqual(len(http.requests), 4)
            self.assertEqual(http.responses[-1].raw.calls, 0)
            self.assertTrue(Path(directory, 'x.partial').exists())
            self.assertFalse(Path(directory, 'x').exists())
            self.assertEqual(remote.manifest()['bytesRead'], 30 + len(names[0]))

    def test_evaluation_and_nested_selected_names_rejected_without_requests(self):
        raw, members, names, _ = fixture()
        for replacement in ('NISQA_Corpus/NISQA_TEST_LIVE/deg/test.wav', TRAIN_PREFIX + 'nested/recording.wav'):
            modified = copy.deepcopy(members)
            modified[0]['name'] = modified[0]['filename'] = replacement
            selected = [replacement] + names[1:]
            with tempfile.TemporaryDirectory() as directory:
                http = HTTP(raw)
                with self.assertRaisesRegex(RemoteZipError, 'TRAIN_LIVE'):
                    self.open(directory, raw, modified, selected, session=http)
                self.assertFalse(http.requests)
                # Validation failure must release the shared ledger lock.
                valid, _, _ = self.open(directory, raw, members, names)
                self.assertEqual(valid.state['replicationDirectoryBinding']['studySha256'], 'a' * 64)

    def test_prior_twenty_and_two_hundred_bindings_failures_and_journal_preserved(self):
        raw, members, names, _ = fixture(count=260)
        with tempfile.TemporaryDirectory() as directory:
            clock = Clock()
            with FrozenDirectoryZip(OFFICIAL_URL, len(raw), directory, frozen_members=members,
                    selected_names=names[:20], session=HTTP(raw), clock=clock, sleep=clock.sleep) as old:
                old.bootstrap()
                old.acquire(names[0], allowlist=names[:20], output_name='prior-twenty.wav')
            failed_index = 21
            failed_payload = members[failed_index]['header_offset'] + 30 + len(names[failed_index])
            def throttle(response, a, b):
                if a == failed_payload: response.status_code = 429
            clock = Clock()
            with QualityDirectoryZip(OFFICIAL_URL, len(raw), directory, frozen_members=members,
                    selected_names=names[20:220], study_sha256='b'*64,
                    session=HTTP(raw, alter=throttle), clock=clock, sleep=clock.sleep) as quality:
                quality.bootstrap()
                quality.acquire(names[20], allowlist=names[20:220], output_name='prior-quality.wav')
                with self.assertRaises(RemoteZipError):
                    quality.acquire(names[21], allowlist=names[20:220], output_name='prior-failed.wav')
                before = copy.deepcopy(quality.state)
            journal_path = Path(directory, 'request-journal.jsonl')
            prefix = journal_path.read_bytes()
            self.assertEqual(Path(directory, 'prior-failed.wav.partial').stat().st_size, 0)
            remote, http, _ = self.open(directory, raw, members, names[220:])
            self.assertFalse(http.requests)
            for key in ('settings','validator','frozenDirectoryBinding','qualityDirectoryBinding','bytesRead','metadataRead',
                        'uncertainBytes','uncertainMetadata','reserved','reservedMetadata'):
                self.assertEqual(remote.state[key], before[key])
            manifest = remote.manifest()
            self.assertEqual(manifest['frozenDirectoryBinding'], before['frozenDirectoryBinding'])
            self.assertEqual(manifest['qualityDirectoryBinding'], before['qualityDirectoryBinding'])
            self.assertEqual(manifest['replicationDirectoryBinding']['studySha256'], 'a'*64)
            self.assertEqual(manifest['replicationDirectoryPolicy']['selectedNames'], 40)
            self.assertTrue(journal_path.read_bytes().startswith(prefix))
            remote.bootstrap()
            remote.acquire(names[220], allowlist=names[220:], output_name='replication.wav')
            self.assertEqual(remote.state['frozenDirectoryBinding'], before['frozenDirectoryBinding'])
            self.assertEqual(remote.state['qualityDirectoryBinding'], before['qualityDirectoryBinding'])
            self.assertGreater(remote.state['bytesRead'], before['bytesRead'])
            self.assertTrue(journal_path.read_bytes().startswith(prefix))
            self.assertTrue(Path(directory, 'prior-twenty.wav').exists())
            self.assertTrue(Path(directory, 'prior-quality.wav').exists())
            self.assertTrue(Path(directory, 'prior-failed.wav.partial').exists())
            remote.close(); self._cleanups.pop()
            frozen_state = Path(directory, 'transport-state.json').read_bytes()
            with self.assertRaisesRegex(RemoteZipError, 'restart'):
                self.open(directory, raw, members, names[220:], study_sha256='c'*64)
            self.assertEqual(Path(directory, 'transport-state.json').read_bytes(), frozen_state)
            reopened, _, _ = self.open(directory, raw, members, names[220:])
            self.assertEqual(reopened.state['qualityDirectoryBinding'], before['qualityDirectoryBinding'])

    def test_interrupted_reservation_conservatively_spent_with_both_old_bindings(self):
        raw, members, names, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            remote, _, _ = self.open(directory, raw, members, names)
            remote.bootstrap()
            old_twenty = {'policy':'synthetic-old20','directorySha256':'b'*64,'selectedNamesSha256':'c'*64}
            old_quality = {'policy':'synthetic-old200','directorySha256':'d'*64,'selectedNamesSha256':'e'*64,'studySha256':'f'*64}
            remote.state.update(frozenDirectoryBinding=old_twenty,qualityDirectoryBinding=old_quality,
                                uncertainBytes=7,uncertainMetadata=3,reserved=11,reservedMetadata=5)
            remote._persist()
            prefix = Path(directory, 'request-journal.jsonl').read_bytes()
            remote.close(); self._cleanups.pop()
            restarted, http, _ = self.open(directory, raw, members, names)
            self.assertFalse(http.requests)
            self.assertEqual(restarted.state['frozenDirectoryBinding'], old_twenty)
            self.assertEqual(restarted.state['qualityDirectoryBinding'], old_quality)
            self.assertEqual(restarted.state['uncertainBytes'],18)
            self.assertEqual(restarted.state['uncertainMetadata'],8)
            self.assertEqual(restarted.state['reserved'],0); self.assertEqual(restarted.state['reservedMetadata'],0)
            self.assertEqual(restarted.manifest()['budgetSpent'],18)
            self.assertEqual(restarted.manifest()['metadataBudgetSpent'],8)
            self.assertTrue(Path(directory, 'request-journal.jsonl').read_bytes().startswith(prefix))
            journal = [json.loads(line) for line in Path(directory, 'request-journal.jsonl').read_text().splitlines()]
            self.assertEqual(journal[-1]['event'],'interrupted-reservation')
            self.assertEqual(journal[-1]['uncertainBytes'],11)

    def test_selected_set_restart_drift_rejected(self):
        raw, members, names, _ = fixture(count=41)
        with tempfile.TemporaryDirectory() as directory:
            remote, _, _ = self.open(directory, raw, members, names[:40])
            remote.close(); self._cleanups.pop()
            before = Path(directory, 'transport-state.json').read_bytes()
            with self.assertRaisesRegex(RemoteZipError, 'restart'):
                self.open(directory, raw, members, names[1:])
            self.assertEqual(Path(directory, 'transport-state.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
