"""Versioned HTTP-validator tests plus inherited synthetic transport checks."""
import json
from pathlib import Path
import tempfile

from nisqa_ingest.http_transport_v2 import DATE_GAP_SECONDS, POLICY, RemoteZipV2
from nisqa_ingest.remote_zip import OFFICIAL_URL, RemoteZip, RemoteZipError
from nisqa_ingest.test_remote_zip import HTTP, RemoteZipTests, Sparse, archive

MODIFIED = 'Sat, 14 Feb 2026 09:45:34 GMT'
DATE = 'Sun, 27 Sep 2026 18:00:00 GMT'


class HTTPV2(HTTP):
    def __init__(self, *args, date=DATE, omit_modified=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.date, self.omit_modified = date, omit_modified

    def head(self, url, **kwargs):
        response = super().head(url, **kwargs)
        if self.date is not None:
            response.headers['Date'] = self.date
        return response

    def get(self, url, **kwargs):
        response = super().get(url, **kwargs)
        if self.omit_modified:
            response.headers.pop('Last-Modified', None)
        return response


class HTTPTransportV2Tests(RemoteZipTests):
    # Inherited tests exercise the actual v2 range loop, sparse ZIP64 reader,
    # acquisition/CRC, unsafe archives, and persisted cumulative accounting.
    def open(self, directory, source, **kwargs):
        http = kwargs.pop('session', HTTPV2(source))
        remote = RemoteZipV2(OFFICIAL_URL, source.size if isinstance(source, Sparse) else len(source),
                             directory, session=http, sleep=lambda _: None, **kwargs)
        self.addCleanup(remote.close)
        return remote, http

    def test_identity_and_last_modified_fallback(self):
        source = archive([('notice.txt', b'notice')])
        with tempfile.TemporaryDirectory() as directory:
            http = HTTPV2(source, etag=None, modified=MODIFIED, omit_modified=True)
            remote, _ = self.open(directory, source, session=http)
            remote.bootstrap(); remote.members()
            self.assertEqual(http.requests[-1][2]['headers']['If-Range'], MODIFIED)
            self.assertEqual(remote.manifest()['validator']['mode'], 'date')
            self.assertEqual(remote.manifest()['validatorPolicy'], POLICY)
            journal = [json.loads(line) for line in Path(directory, 'request-journal.jsonl').read_text().splitlines()]
            self.assertEqual(journal[0]['date'], DATE)
            self.assertGreater(journal[0]['strengthEvidence']['gapSeconds'], DATE_GAP_SECONDS)
            actual = next(entry['validators'] for entry in journal if entry['event'] == 'GET')
            self.assertEqual(actual, {'etag': None, 'lastModified': None})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RemoteZipError):
                RemoteZipV2('http://zenodo.org/archive.zip', len(source), directory, session=HTTP(source))

    def test_omitted_last_modified_accepted_for_strong_etag_without_synthesized_journal(self):
        source = archive([('notice.txt', b'notice')])
        with tempfile.TemporaryDirectory() as directory:
            remote, _ = self.open(directory, source, session=HTTPV2(source, modified=MODIFIED, omit_modified=True))
            remote.bootstrap(); remote.members()
            journal = [json.loads(line) for line in Path(directory, 'request-journal.jsonl').read_text().splitlines()]
            actual = next(entry['validators'] for entry in journal if entry['event'] == 'GET')
            self.assertEqual(actual, {'etag': '"fixture-v1"', 'lastModified': None})
            self.assertEqual(remote.manifest()['validator']['lastModified'], MODIFIED)

    def test_conflicting_provided_validators_and_missing_required_etag_fail_before_body(self):
        source = archive([('notice.txt', b'notice')])
        cases = (
            ('missing-etag', '"fixture-v1"', lambda r, a, b: r.headers.pop('ETag')),
            ('changed-etag', '"fixture-v1"', lambda r, a, b: r.headers.__setitem__('ETag', '"other"')),
            ('changed-modified-etag-mode', '"fixture-v1"', lambda r, a, b: r.headers.__setitem__('Last-Modified', DATE)),
            ('changed-modified-date-mode', None, lambda r, a, b: r.headers.__setitem__('Last-Modified', DATE)),
            ('unexpected-etag-date-mode', None, lambda r, a, b: r.headers.__setitem__('ETag', '"new"')),
        )
        for label, etag, alter in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                remote, http = self.open(directory, source, session=HTTPV2(
                    source, etag=etag, modified=MODIFIED, alter=alter))
                remote.bootstrap()
                with self.assertRaises(RemoteZipError):
                    remote.members()
                self.assertEqual(http.responses[-1].raw.calls, 0)
                self.assertEqual(remote.manifest()['bytesRead'], 0)

    def test_weak_or_malformed_etag_never_falls_back_to_old_date(self):
        source = archive([('notice.txt', b'notice')])
        for etag in ('W/"weak"', 'malformed', '', '"has space"'):
            with self.subTest(etag=etag), tempfile.TemporaryDirectory() as directory:
                remote, http = self.open(directory, source, session=HTTPV2(source, etag=etag, modified=MODIFIED))
                with self.assertRaises(RemoteZipError):
                    remote.bootstrap()
                self.assertFalse(remote._ready)
                self.assertEqual(http.responses[-1].raw.calls, 0)
                self.assertEqual(len(http.requests), 1)

    def test_date_mode_requires_valid_aware_date_modified_and_conservative_gap(self):
        source = archive([('notice.txt', b'notice')])
        cases = ((None, MODIFIED), ('invalid', MODIFIED),
                 ('Sun, 27 Sep 2026 18:00:00', MODIFIED),
                 ('Sat, 14 Feb 2026 09:46:33 GMT', MODIFIED),
                 (MODIFIED, MODIFIED), (DATE, 'invalid'), (DATE, 'Sat, 14 Feb 2026 09:45:34'))
        for date, modified in cases:
            with self.subTest(date=date, modified=modified), tempfile.TemporaryDirectory() as directory:
                remote, http = self.open(directory, source, session=HTTPV2(source, etag=None, modified=modified, date=date))
                with self.assertRaises(RemoteZipError):
                    remote.bootstrap()
                self.assertEqual(http.responses[-1].raw.calls, 0)
        with tempfile.TemporaryDirectory() as directory:
            remote, _ = self.open(directory, source, session=HTTPV2(
                source, etag=None, modified=MODIFIED, date='Sat, 14 Feb 2026 09:46:34 GMT', omit_modified=True))
            remote.bootstrap(); remote.members()
            self.assertEqual(remote.manifest()['validatorEvidence']['gapSeconds'], 60.)

    def test_restart_date_can_change_but_representation_identity_and_strength_evidence_stay_pinned(self):
        source = archive([('notice.txt', b'notice')])
        with tempfile.TemporaryDirectory() as directory:
            remote, _ = self.open(directory, source, session=HTTPV2(source, etag=None, modified=MODIFIED))
            identity = remote.bootstrap(); remote.members()
            first = remote.manifest()
            remote.close()
            reopened, _ = self.open(directory, source, session=HTTPV2(
                source, etag=None, modified=MODIFIED, date='Mon, 28 Sep 2026 18:00:00 GMT'))
            self.assertEqual(reopened.bootstrap(), identity)
            self.assertEqual(reopened.manifest()['validatorEvidence'], first['validatorEvidence'])
            self.assertEqual(reopened.manifest()['bytesRead'], first['bytesRead'])
            reopened.close()
            changed, http = self.open(directory, source, session=HTTPV2(
                source, etag=None, modified='Sun, 15 Feb 2026 09:45:34 GMT'))
            with self.assertRaises(RemoteZipError):
                changed.bootstrap()
            self.assertFalse(changed._ready)
            self.assertEqual(http.responses[-1].raw.calls, 0)

    def test_cached_directory_cannot_bypass_failed_repeat_bootstrap(self):
        source = archive([('notice.txt', b'notice')])
        with tempfile.TemporaryDirectory() as directory:
            remote, http = self.open(directory, source)
            remote.bootstrap(); remote.members()
            http.etag = '"changed"'
            with self.assertRaises(RemoteZipError):
                remote.bootstrap()
            with self.assertRaises(RemoteZipError):
                remote.members()
            with self.assertRaises(RemoteZipError):
                remote.acquire('notice.txt', allowlist={'notice.txt'}, output_name='notice.txt')

    def test_legacy_pin_is_not_silently_upgraded(self):
        source = archive([('notice.txt', b'notice')])
        with tempfile.TemporaryDirectory() as directory:
            with RemoteZip(OFFICIAL_URL, len(source), directory, session=HTTP(source)) as legacy:
                legacy.bootstrap()
            state = Path(directory, 'transport-state.json').read_bytes()
            journal = Path(directory, 'request-journal.jsonl').read_bytes()
            with self.assertRaises(RemoteZipError):
                RemoteZipV2(OFFICIAL_URL, len(source), directory, session=HTTPV2(source))
            self.assertEqual(Path(directory, 'transport-state.json').read_bytes(), state)
            self.assertEqual(Path(directory, 'request-journal.jsonl').read_bytes(), journal)

    def test_http_errors_redirects_and_wrong_total_never_read_body(self):
        source = archive([('notice.txt', b'notice')])
        for status in (200, 301, 302, 400, 404, 416, 429, 500, 502, 503, 504):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                remote, http = self.open(directory, source, retries=0, session=HTTPV2(
                    source, alter=lambda response, a, b: setattr(response, 'status_code', status)))
                remote.bootstrap()
                with self.assertRaises(RemoteZipError):
                    remote.members()
                self.assertEqual(http.responses[-1].raw.calls, 0)
        with tempfile.TemporaryDirectory() as directory:
            remote, http = self.open(directory, source, session=HTTPV2(source, alter=lambda r, a, b:
                r.headers.__setitem__('Content-Range', f'bytes {a}-{b}/{len(source) + 1}')))
            remote.bootstrap()
            with self.assertRaises(RemoteZipError):
                remote.members()
            self.assertEqual(http.responses[-1].raw.calls, 0)


if __name__ == '__main__':
    import unittest
    unittest.main()
