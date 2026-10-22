"""Synthetic HTTP and sparse ZIP64 transport tests; no network acquisition."""
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
import zipfile

from requests.structures import CaseInsensitiveDict
from urllib3.exceptions import ProtocolError

from nisqa_ingest.remote_zip import OFFICIAL_URL, RemoteZip, RemoteZipError


def archive(entries, *, compression=zipfile.ZIP_STORED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=compression) as output:
        for name, body in entries:
            output.writestr(name, body)
    return stream.getvalue()


class Sparse:
    def __init__(self, size, pieces):
        self.size, self.pieces = size, pieces

    def read(self, start, count):
        value = bytearray(count)
        for offset, content in self.pieces:
            left, right = max(start, offset), min(start + count, offset + len(content))
            if left < right:
                value[left - start:right - start] = content[left - offset:right - offset]
        return bytes(value)


class Raw(io.BytesIO):
    def __init__(self, value):
        super().__init__(value)
        self.calls, self.bytes = 0, 0

    def read(self, count=-1):
        self.calls += 1
        value = super().read(count)
        self.bytes += len(value)
        return value


class Response:
    def __init__(self, body=b'', *, status=206, headers=None, url=OFFICIAL_URL):
        self.raw, self.status_code, self.headers, self.url = Raw(body), status, CaseInsensitiveDict(headers or {}), url
        self.closed = False

    def close(self):
        self.closed = True


class HTTP:
    def __init__(self, source, *, alter=None, etag='"fixture-v1"', modified=None):
        self.source = source if isinstance(source, Sparse) else Sparse(len(source), [(0, source)])
        self.alter, self.etag, self.modified = alter, etag, modified
        self.requests, self.responses = [], []

    def validators(self):
        return {k: v for k, v in (('ETag', self.etag), ('Last-Modified', self.modified)) if v is not None}

    def head(self, url, **kwargs):
        self.requests.append(('HEAD', url, kwargs))
        response = Response(status=200, headers={**self.validators(), 'Content-Length': str(self.source.size)})
        self.responses.append(response)
        return response

    def get(self, url, **kwargs):
        self.requests.append(('GET', url, kwargs))
        start, end = map(int, kwargs['headers']['Range'][6:].split('-'))
        response = Response(self.source.read(start, end - start + 1), headers={
            **self.validators(), 'Content-Length': str(end - start + 1),
            'Content-Range': f'bytes {start}-{end}/{self.source.size}'})
        if self.alter:
            self.alter(response, start, end)
        self.responses.append(response)
        return response


def zip64_sparse():
    normal = archive([('notice.txt', b'official synthetic notice')])
    end = normal.rfind(b'PK\x05\x06')
    central_start = struct.unpack_from('<L', normal, end + 16)[0]
    central = bytearray(normal[central_start:end])
    # A central ZIP64 extra field holds a local-header offset beyond 4 GiB.
    local_offset = 2**32 + 4096
    struct.pack_into('<L', central, 42, 0xffffffff)
    struct.pack_into('<H', central, 30, 12)
    central.extend(struct.pack('<HHQ', 1, 8, local_offset))
    new_central_start = local_offset + central_start
    zip64_offset = new_central_start + len(central)
    record = struct.pack('<4sQ2H2L4Q', b'PK\x06\x06', 44, 45, 45, 0, 0, 1, 1, len(central), new_central_start)
    locator = struct.pack('<4sLQL', b'PK\x06\x07', 0, zip64_offset, 1)
    endrecord = struct.pack('<4s4H2LH', b'PK\x05\x06', 0, 0, 0xffff, 0xffff, 0xffffffff, 0xffffffff, 0)
    trailer = bytes(central) + record + locator + endrecord
    return Sparse(new_central_start + len(trailer), [(local_offset, normal[:central_start]),
                                                   (new_central_start, trailer)])


class RemoteZipTests(unittest.TestCase):
    def open(self, directory, source, **kwargs):
        http = kwargs.pop('session', HTTP(source))
        remote = RemoteZip(OFFICIAL_URL, source.size if isinstance(source, Sparse) else len(source),
                           directory, session=http, sleep=lambda _: None, **kwargs)
        self.addCleanup(remote.close)
        return remote, http

    def test_explicit_head_directory_then_exact_member_crc_sha_and_nooverwrite(self):
        body = b'audio fixture bytes ' * 10000
        source = archive([('TRAIN/one.wav', body), ('notice.txt', b'notice')])
        with tempfile.TemporaryDirectory() as directory:
            remote, http = self.open(directory, source)
            self.assertFalse(http.requests)
            with self.assertRaises(RemoteZipError):
                remote.members()
            pin = remote.bootstrap()
            self.assertEqual(pin['etag'], '"fixture-v1"')
            self.assertEqual(http.responses[0].raw.calls, 0)
            members = remote.members()
            self.assertEqual(members[0]['filename'], 'TRAIN/one.wav')
            self.assertEqual(members[0]['file_size'], len(body))
            metadata_requests = len(http.requests)
            result = remote.acquire('TRAIN/one.wav', allowlist={'TRAIN/one.wav'}, output_name='original.wav')
            self.assertEqual(Path(result['path']).read_bytes(), body)
            self.assertEqual(result['sha256'], hashlib.sha256(body).hexdigest())
            self.assertFalse(result['archive']['fullArchiveMd5Verified'])
            header_end = 30 + len('TRAIN/one.wav')
            for method, _, options in http.requests[metadata_requests:]:
                if method == 'GET':
                    start, end = map(int, options['headers']['Range'][6:].split('-'))
                    self.assertTrue(0 <= start <= end < header_end + len(body))
                    self.assertEqual(options['headers']['If-Range'], '"fixture-v1"')
                    self.assertEqual(options['headers']['Accept-Encoding'], 'identity')
                    self.assertFalse(options['allow_redirects'])
            with self.assertRaises(RemoteZipError):
                remote.acquire('TRAIN/one.wav', allowlist={'TRAIN/one.wav'}, output_name='original.wav')
            journal = Path(directory, 'request-journal.jsonl').read_text()
            self.assertNotIn(body[:100].decode(), journal)
            self.assertEqual(remote.manifest()['bytesRead'], sum(r.raw.bytes for r in http.responses))

    def test_zip64_sparse_offsets_and_member_retrieval_without_large_allocation(self):
        source = zip64_sparse()
        with tempfile.TemporaryDirectory() as directory:
            remote, http = self.open(directory, source)
            remote.bootstrap()
            members = remote.members()
            self.assertGreater(members[0]['header_offset'], 2**32)
            result = remote.acquire('notice.txt', allowlist=['notice.txt'], output_name='notice.txt')
            self.assertEqual(Path(result['path']).read_bytes(), b'official synthetic notice')
            self.assertLess(remote.manifest()['bytesRead'], 70000)
            self.assertTrue(all(r.raw.bytes <= 65557 for r in http.responses))

    def test_reject_wrong_range_status_validator_encoding_and_redirect_before_body(self):
        source = archive([('notice.txt', b'notice')])
        alterations = {
            '200': lambda r, a, b: setattr(r, 'status_code', 200),
            'range': lambda r, a, b: r.headers.__setitem__('Content-Range', f'bytes {a+1}-{b}/{len(source)}'),
            'length': lambda r, a, b: r.headers.__setitem__('Content-Length', str(b-a)),
            'etag': lambda r, a, b: r.headers.__setitem__('ETag', '"stale"'),
            'encoding': lambda r, a, b: r.headers.__setitem__('Content-Encoding', 'gzip'),
            'redirect': lambda r, a, b: setattr(r, 'url', 'https://elsewhere.example/archive.zip'),
        }
        for name, alter in alterations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                remote, http = self.open(directory, source, session=HTTP(source, alter=alter))
                remote.bootstrap()
                with self.assertRaises(RemoteZipError):
                    remote.members()
                self.assertEqual(http.responses[-1].raw.calls, 0)
                self.assertEqual(remote.manifest()['bytesRead'], 0)
                self.assertEqual(len([r for r in http.requests if r[0] == 'GET']), 1)

    def test_truncated_attempt_bytes_and_restart_budget_are_preserved(self):
        source = archive([('notice.txt', b'notice')])
        def truncate(response, start, end):
            response.raw = Raw(response.raw.getvalue()[:20])
        with tempfile.TemporaryDirectory() as directory:
            remote, http = self.open(directory, source, session=HTTP(source, alter=truncate),
                                     max_bytes=len(source) + 25, metadata_bytes=len(source) + 25, retries=1)
            remote.bootstrap()
            with self.assertRaises(RemoteZipError):
                remote.members()
            self.assertEqual(remote.manifest()['bytesRead'], 40)
            remote.close()
            reopened, second = self.open(directory, source, max_bytes=len(source) + 25,
                                         metadata_bytes=len(source) + 25, retries=1)
            reopened.bootstrap()
            with self.assertRaises(RemoteZipError):
                reopened.members()
            self.assertEqual(len(second.requests), 1)
            self.assertEqual(reopened.manifest()['bytesRead'], 40)

    def test_overbudget_rejected_before_body_and_stale_head_on_restart(self):
        source = archive([('notice.txt', b'notice')])
        with tempfile.TemporaryDirectory() as directory:
            remote, http = self.open(directory, source, max_bytes=100, metadata_bytes=100)
            remote.bootstrap()
            with self.assertRaises(RemoteZipError):
                remote.members()
            self.assertEqual(len(http.requests), 1)
            remote.close()
            reopened, http2 = self.open(directory, source, max_bytes=100, metadata_bytes=100,
                                        session=HTTP(source, etag='"different"'))
            with self.assertRaises(RemoteZipError):
                reopened.bootstrap()
            self.assertEqual(http2.responses[-1].raw.calls, 0)

    def test_unsafe_zip_names_types_duplicates_compression_and_bounds(self):
        for name in ('../escape', '/absolute', 'a\\b', 'a/../b', 'C:drive', './same'):
            source = archive([(name, b'x')])
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                remote, _ = self.open(directory, source)
                remote.bootstrap()
                with self.assertRaises(RemoteZipError):
                    remote.members()
        for source in (archive([('A', b'x'), ('a', b'y')]),
                       archive([('x', b'x')], compression=zipfile.ZIP_BZIP2)):
            with tempfile.TemporaryDirectory() as directory:
                remote, _ = self.open(directory, source)
                remote.bootstrap()
                with self.assertRaises(RemoteZipError):
                    remote.members()
        info = zipfile.ZipInfo('link')
        info.create_system, info.external_attr = 3, (stat.S_IFLNK | 0o777) << 16
        source = archive([(info, b'target')])
        with tempfile.TemporaryDirectory() as directory:
            remote, _ = self.open(directory, source)
            remote.bootstrap()
            with self.assertRaises(RemoteZipError):
                remote.members()
        source = archive([('too-large', b'x' * 100)])
        with tempfile.TemporaryDirectory() as directory:
            remote, _ = self.open(directory, source, max_member_uncompressed=50)
            remote.bootstrap()
            with self.assertRaises(RemoteZipError):
                remote.members()

    def test_crc_failure_partial_preserved_and_exact_allowlist_required(self):
        source = bytearray(archive([('schema.csv', b'private,target\nrow,5\n')]))
        source[30 + len('schema.csv')] ^= 1
        with tempfile.TemporaryDirectory() as directory:
            remote, http = self.open(directory, bytes(source))
            remote.bootstrap(); remote.members()
            count = len(http.requests)
            for allowlist in ({'*'}, [], None):
                with self.assertRaises(RemoteZipError):
                    remote.acquire('schema.csv', allowlist=allowlist, output_name='schema.csv')
            self.assertEqual(len(http.requests), count)
            with self.assertRaises((RemoteZipError, zipfile.BadZipFile)):
                remote.acquire('schema.csv', allowlist={'schema.csv'}, output_name='schema.csv')
            self.assertTrue(Path(directory, 'schema.csv.partial').is_file())
            self.assertFalse(Path(directory, 'schema.csv').exists())
            with self.assertRaises(RemoteZipError):
                remote.acquire('schema.csv', allowlist={'schema.csv'}, output_name='schema.csv')
            self.assertNotIn('private,target', Path(directory, 'request-journal.jsonl').read_text())

    def test_identity_and_last_modified_fallback(self):
        source = archive([('notice.txt', b'notice')])
        with tempfile.TemporaryDirectory() as directory:
            http = HTTP(source, etag=None, modified='Sun, 27 Sep 2026 18:00:00 GMT')
            remote, _ = self.open(directory, source, session=http)
            remote.bootstrap(); remote.members()
            self.assertEqual(http.requests[-1][2]['headers']['If-Range'], http.modified)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RemoteZipError):
                RemoteZip('http://zenodo.org/archive.zip', len(source), directory, session=HTTP(source))

    def test_metadata_member_budget_and_explicit_member_caps(self):
        source = archive([('notice.txt', b'x' * 130000), ('last.txt', b'last')])
        with tempfile.TemporaryDirectory() as directory:
            remote, http = self.open(directory, source, metadata_bytes=100000)
            remote.bootstrap(); remote.members()
            with self.assertRaises(RemoteZipError):
                remote.acquire('notice.txt', allowlist={'notice.txt'}, output_name='too-small.txt',
                               max_compressed=100, max_uncompressed=100)
            count = len(http.requests)
            with self.assertRaises(RemoteZipError):
                remote.acquire('notice.txt', allowlist={'notice.txt'}, output_name='notice.txt', metadata=True)
            # Only the two exact local-header requests can occur; payload is
            # rejected before reading because it exceeds the metadata budget.
            self.assertLessEqual(len(http.requests) - count, 2)
            self.assertLess(remote.manifest()['metadataRead'], 100000)
            self.assertTrue(Path(directory, 'notice.txt.partial').exists())

    def test_encrypted_nul_out_of_range_and_oversized_central_directory(self):
        original = archive([('abc', b'value')])
        start = original.index(b'PK\x01\x02')
        fixtures = []
        encrypted = bytearray(original); struct.pack_into('<H', encrypted, start + 8, 1)
        fixtures.append(bytes(encrypted))
        nul = bytearray(original); nul[start + 47] = 0
        fixtures.append(bytes(nul))
        bad_offset = bytearray(original); struct.pack_into('<L', bad_offset, start + 42, start + 1000)
        fixtures.append(bytes(bad_offset))
        size = 17 * 1024**2
        trailer = struct.pack('<4s4H2LH', b'PK\x05\x06', 0, 0, 1, 1, size, 0, 0)
        fixtures.append(Sparse(size + len(trailer), [(size, trailer)]))
        for fixture in fixtures:
            with self.subTest(fixture=type(fixture).__name__), tempfile.TemporaryDirectory() as directory:
                remote, http = self.open(directory, fixture)
                remote.bootstrap()
                with self.assertRaises(RemoteZipError):
                    remote.members()
                self.assertLess(remote.manifest()['bytesRead'], 70000)

    def test_unreturned_network_bytes_and_interrupted_reservation_are_conservatively_spent(self):
        source = archive([('notice.txt', b'notice')])
        class Broken(Raw):
            def read(self, count=-1):
                super().read(5)
                raise ProtocolError('synthetic interrupted read')
        def broken(response, start, end):
            response.raw = Broken(response.raw.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            remote, http = self.open(directory, source, session=HTTP(source, alter=broken), retries=0)
            remote.bootstrap()
            with self.assertRaises(RemoteZipError):
                remote.members()
            self.assertEqual(remote.manifest()['bytesRead'], 0)
            self.assertGreaterEqual(remote.manifest()['budgetSpent'], http.responses[-1].raw.bytes)
            self.assertEqual(remote.manifest()['uncertainBytes'], len(source) + 1)
        with tempfile.TemporaryDirectory() as directory:
            remote, _ = self.open(directory, source)
            remote.bootstrap()
            remote.state['reserved'], remote.state['reservedMetadata'] = 30, 30
            remote._persist(); remote.close()
            reopened, _ = self.open(directory, source)
            self.assertEqual(reopened.manifest()['uncertainBytes'], 30)
            self.assertEqual(reopened.manifest()['uncertainMetadata'], 30)


if __name__ == '__main__':
    unittest.main()
