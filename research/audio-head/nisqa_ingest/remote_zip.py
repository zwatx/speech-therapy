"""Selective, validator-pinned access to the official NISQA ZIP.

Construction performs no network access. Explicit bootstrap uses HEAD; directory
inspection and exact allowlisted member retrieval use bounded HTTP ranges only.
The full archive's advertised MD5 cannot be verified by this transport.
"""
from __future__ import annotations

import fcntl
from email.utils import parsedate_to_datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import time
from urllib.parse import urlsplit
import zipfile
import zlib

import requests
from urllib3.exceptions import ProtocolError, ReadTimeoutError

OFFICIAL_URL = 'https://zenodo.org/records/4728081/files/NISQA_Corpus.zip'
CORPUS_SIZE = 15945499507
PILOT_BUDGET = 256 * 1024**2
METADATA_BUDGET = 16 * 1024**2


class RemoteZipError(ValueError):
    pass


class _Transient(RemoteZipError):
    pass


def _require(condition, message):
    if not condition:
        raise RemoteZipError(message)


class _Ranges(io.RawIOBase):
    """A seekable sparse view that never reads outside explicit allowed ranges."""
    def __init__(self, owner):
        self.owner, self.position, self.allowed, self.metadata = owner, 0, [], False

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        _require(type(offset) is int and whence in (0, 1, 2), 'Invalid ZIP seek')
        position = offset + (self.position if whence == 1 else self.owner.expected_size if whence == 2 else 0)
        _require(0 <= position <= self.owner.expected_size, 'ZIP seek outside archive')
        self.position = position
        return position

    def read(self, size=-1):
        _require(type(size) is int, 'Invalid ZIP read')
        if size < 0:
            size = self.owner.expected_size - self.position
        size = min(size, self.owner.expected_size - self.position)
        if not size:
            return b''
        start, end = self.position, self.position + size
        cached = self.owner._cached(start, end)
        if cached is None:
            _require(any(a <= start and end <= b for a, b in self.allowed),
                     'ZIP attempted an unapproved byte range')
            cached = self.owner._fetch(start, end - 1, metadata=self.metadata)
        self.position = end
        return cached


class RemoteZip:
    def __init__(self, url, expected_size, output_directory, max_bytes=PILOT_BUDGET, *,
                 metadata_bytes=METADATA_BUDGET, allowed_hosts=('zenodo.org',),
                 max_member_compressed=64 * 1024**2, max_member_uncompressed=128 * 1024**2,
                 max_expansion_ratio=1000, max_entries=200000, request_bytes=1024**2,
                 chunk_bytes=64 * 1024, timeout=(5., 15.), request_seconds=45., retries=1,
                 session=None, sleep=time.sleep):
        _require(url == OFFICIAL_URL, 'Exact official archive URL required')
        _require(tuple(allowed_hosts) == ('zenodo.org',), 'Unreviewed archive host allowlist')
        self._check_url(url)
        _require(type(expected_size) is int and expected_size > 0, 'Invalid pinned archive size')
        for value, limit, label in ((max_bytes, PILOT_BUDGET, 'total budget'),
                                    (metadata_bytes, METADATA_BUDGET, 'metadata budget'),
                                    (request_bytes, 1024**2, 'request size'),
                                    (chunk_bytes, 64 * 1024, 'chunk size')):
            _require(type(value) is int and 0 < value <= limit, 'Invalid ' + label)
        _require(metadata_bytes <= max_bytes, 'Metadata budget exceeds total budget')
        _require(type(retries) is int and 0 <= retries <= 2, 'Retries must be bounded by two')
        _require(isinstance(timeout, tuple) and len(timeout) == 2
                 and all(type(x) in (int, float) and 0 < x <= 30 for x in timeout)
                 and type(request_seconds) in (int, float) and 0 < request_seconds <= 60,
                 'Finite bounded request timeouts required')
        _require(all(type(x) is int and 0 < x <= PILOT_BUDGET for x in
                     (max_member_compressed, max_member_uncompressed, max_entries))
                 and type(max_expansion_ratio) in (int, float) and 1 <= max_expansion_ratio <= 1000,
                 'Invalid member bounds')
        self.url, self.expected_size = url, expected_size
        _require(not Path(output_directory).is_symlink(), 'Output directory must not be a symlink')
        self.output = Path(output_directory).resolve()
        self.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        _require(not any((self.output/name).is_symlink() for name in
                         ('transport.lock', 'transport-state.json', 'request-journal.jsonl')),
                 'Transport bookkeeping must not be a symlink')
        self._lock = (self.output/'transport.lock').open('a+b')
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock.close()
            raise RemoteZipError('Transport directory is already in use')
        self._state_path, self._journal_path = self.output/'transport-state.json', self.output/'request-journal.jsonl'
        self.settings = dict(url=url, expectedSize=expected_size, maxBytes=max_bytes,
                             metadataBytes=metadata_bytes, requestBytes=request_bytes, chunkBytes=chunk_bytes,
                             maxMemberCompressed=max_member_compressed, maxMemberUncompressed=max_member_uncompressed,
                             maxExpansionRatio=max_expansion_ratio, maxEntries=max_entries)
        try:
            if self._state_path.exists():
                self.state = json.loads(self._state_path.read_text())
                _require(self.state.get('version') == 1 and self.state.get('settings') == self.settings,
                         'Persisted source or budget settings differ')
                _require(self._journal_path.is_file(), 'Missing persisted request journal')
                for key in ('bytesRead', 'metadataRead', 'uncertainBytes', 'uncertainMetadata', 'reserved', 'reservedMetadata'):
                    _require(type(self.state.get(key)) is int and self.state[key] >= 0, 'Invalid persisted budget')
                _require(self.state['metadataRead'] <= self.state['bytesRead']
                         and self.state['uncertainMetadata'] <= self.state['uncertainBytes']
                         and self.state['reservedMetadata'] <= self.state['reserved']
                         and self.state['bytesRead'] + self.state['uncertainBytes'] + self.state['reserved'] <= max_bytes
                         and self.state['metadataRead'] + self.state['uncertainMetadata']
                         + self.state['reservedMetadata'] <= metadata_bytes,
                         'Persisted accounting exceeds its budget')
                journal = [json.loads(line) for line in self._journal_path.read_text().splitlines()]
                _require(all(entry.get('url') == url for entry in journal)
                         and sum(entry.get('bytes', 0) for entry in journal if entry.get('event') == 'GET')
                         <= self.state['bytesRead']
                         and sum(entry.get('uncertainBytes', 0) for entry in journal)
                         <= self.state['uncertainBytes']
                         and (self.state['validator'] is not None or not any(
                             entry.get('event') == 'GET' or entry.get('outcome') == 'verified' for entry in journal)),
                         'Persisted journal or accounting differs')
                if self.state['reserved']:
                    # An interrupted read may have occurred before its byte count was
                    # synced. Conservatively spend its remaining reservation.
                    abandoned, abandoned_metadata = self.state['reserved'], self.state['reservedMetadata']
                    self.state['uncertainBytes'] += abandoned
                    self.state['uncertainMetadata'] += abandoned_metadata
                    self.state['reserved'] = self.state['reservedMetadata'] = 0
                    self._persist()
                    self._journal(dict(event='interrupted-reservation', status='budget-preserved',
                                       uncertainBytes=abandoned, uncertainMetadata=abandoned_metadata))
            else:
                _require(set(p.name for p in self.output.iterdir()) == {'transport.lock'},
                         'New transport requires an empty dedicated directory')
                self.state = dict(version=1, settings=self.settings, validator=None, bytesRead=0,
                                  metadataRead=0, uncertainBytes=0, uncertainMetadata=0,
                                  reserved=0, reservedMetadata=0)
                self._journal_path.touch(exist_ok=False, mode=0o600)
                self._persist()
            self.session = requests.Session() if session is None else session
            if session is None:
                self.session.trust_env = False
            self._owns_session = session is None
            self.timeout, self.request_seconds, self.retries, self.sleep = timeout, request_seconds, retries, sleep
            self._ready, self._cache, self._zip, self._infos = False, [], None, None
            self._reader = _Ranges(self)
        except BaseException:
            self._lock.close()
            raise

    @staticmethod
    def _check_url(url):
        parsed = urlsplit(url)
        _require(parsed.scheme == 'https' and parsed.hostname == 'zenodo.org'
                 and parsed.port in (None, 443) and not parsed.username and not parsed.password
                 and url == OFFICIAL_URL, 'Unapproved resolved archive URL or host')

    def _persist(self):
        with tempfile.NamedTemporaryFile(mode='w', dir=self.output, prefix='.budget-', delete=False) as stream:
            json.dump(self.state, stream, sort_keys=True, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
            temporary = stream.name
        os.replace(temporary, self._state_path)
        descriptor = os.open(self.output, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _journal(self, entry):
        entry = dict(url=self.url, **entry)
        with self._journal_path.open('a') as stream:
            stream.write(json.dumps(entry, sort_keys=True, allow_nan=False) + '\n')
            stream.flush(); os.fsync(stream.fileno())

    def _response(self, response):
        self._check_url(response.url)
        _require(response.headers.get('Content-Encoding', 'identity').lower() == 'identity'
                 and not response.headers.get('Transfer-Encoding'), 'Nonidentity or ambiguous response encoding')
        return dict(etag=response.headers.get('ETag'), lastModified=response.headers.get('Last-Modified'))

    def bootstrap(self):
        """Explicit HEAD verification; no response body is read."""
        response = None
        entry = dict(event='HEAD', range=None, bytes=0, sha256=hashlib.sha256(b'').hexdigest())
        try:
            response = self.session.head(self.url, headers={'Accept-Encoding': 'identity'},
                                         timeout=self.timeout, allow_redirects=False, stream=True)
            entry['status'] = response.status_code
            _require(response.status_code == 200, 'HEAD must return 200 without a redirect')
            validator = self._response(response)
            entry['validators'] = validator
            _require(response.headers.get('Content-Length') == str(self.expected_size),
                     'HEAD archive length differs')
            etag = validator['etag']
            strong = isinstance(etag, str) and re.fullmatch(r'"[^"\r\n]+"', etag)
            modified = validator['lastModified']
            try:
                valid_modified = (isinstance(modified, str) and '\r' not in modified and '\n' not in modified
                                  and parsedate_to_datetime(modified).tzinfo is not None)
            except (ValueError, TypeError, OverflowError):
                valid_modified = False
            _require(strong or valid_modified,
                     'A strong ETag or Last-Modified plus length is required')
            validator['ifRange'] = etag if strong else modified
            if self.state['validator'] is not None:
                _require(validator == self.state['validator'], 'Archive validator changed on restart')
            else:
                self.state['validator'] = validator
                self._persist()
            self._ready = True
            entry['outcome'] = 'verified'
            return dict(url=self.url, size=self.expected_size, **validator)
        except BaseException as error:
            entry['outcome'], entry['error'] = 'failed', type(error).__name__
            raise
        finally:
            self._journal(entry)
            if response is not None:
                response.close()

    def _reserve(self, count, metadata):
        _require(self.state['bytesRead'] + self.state['uncertainBytes'] + count <= self.settings['maxBytes'],
                 'Cumulative transport byte budget exceeded')
        _require(not metadata or self.state['metadataRead'] + self.state['uncertainMetadata'] + count
                 <= self.settings['metadataBytes'], 'Cumulative metadata byte budget exceeded')
        self.state['reserved'] = count
        self.state['reservedMetadata'] = count if metadata else 0
        self._persist()

    def _range(self, start, end, metadata):
        count = end - start + 1
        for attempt in range(self.retries + 1):
            entry = dict(event='GET', range=[start, end], attempt=attempt + 1,
                         metadata=metadata, status=None)
            try:
                self._reserve(count + 1, metadata)
            except RemoteZipError:
                self._journal(dict(**entry, outcome='not-issued', error='BudgetRejected', bytes=0,
                                   sha256=hashlib.sha256(b'').hexdigest()))
                raise
            response, read, digest, in_read = None, 0, hashlib.sha256(), False
            transient = False
            try:
                deadline = time.monotonic() + self.request_seconds
                response = self.session.get(self.url, headers={
                    'Range': f'bytes={start}-{end}', 'If-Range': self.state['validator']['ifRange'],
                    'Accept-Encoding': 'identity'}, timeout=self.timeout, allow_redirects=False, stream=True)
                entry['status'] = response.status_code
                entry['validators'] = dict(etag=response.headers.get('ETag'),
                                            lastModified=response.headers.get('Last-Modified'))
                if response.status_code in (429, 502, 503, 504):
                    raise _Transient('Transient range status')
                # In particular, a full-archive 200 is rejected before raw.read.
                _require(response.status_code == 206, 'Exact HTTP 206 range response required')
                validator = self._response(response)
                entry['validators'] = validator
                _require(validator == {k: self.state['validator'][k] for k in ('etag', 'lastModified')},
                         'Archive validators changed during range retrieval')
                _require(response.headers.get('Content-Range') == f'bytes {start}-{end}/{self.expected_size}'
                         and response.headers.get('Content-Length') == str(count),
                         'Range endpoints, total, or length differ')
                chunks = []
                response.raw.decode_content = False
                while read <= count:
                    _require(time.monotonic() < deadline, 'Range request deadline exceeded')
                    in_read = True
                    chunk = response.raw.read(min(self.settings['chunkBytes'], count + 1 - read))
                    in_read = False
                    if not chunk:
                        break
                    _require(isinstance(chunk, bytes), 'Nonbyte range response')
                    read += len(chunk); digest.update(chunk)
                    self.state['bytesRead'] += len(chunk)
                    self.state['reserved'] = max(0, self.state['reserved'] - len(chunk))
                    if metadata:
                        self.state['metadataRead'] += len(chunk)
                        self.state['reservedMetadata'] = max(0, self.state['reservedMetadata'] - len(chunk))
                    self._persist()
                    _require(read <= count, 'Range body exceeds its declared length')
                    chunks.append(chunk)
                if read != count:
                    raise _Transient('Truncated range body')
                entry['outcome'] = 'complete'
                return b''.join(chunks)
            except (requests.Timeout, requests.ConnectionError, ProtocolError, ReadTimeoutError, _Transient) as error:
                entry['outcome'], entry['error'] = 'failed', type(error).__name__
                transient = True
                if attempt == self.retries:
                    raise RemoteZipError('Transient range attempts exhausted') from error
            except BaseException as error:
                entry['outcome'], entry['error'] = 'failed', type(error).__name__
                raise
            finally:
                entry['bytes'], entry['sha256'] = read, digest.hexdigest()
                if in_read:
                    # A raw I/O failure can consume bytes without returning them.
                    # Spend the outstanding reservation rather than undercount.
                    entry['uncertainBytes'] = self.state['reserved']
                    self.state['uncertainBytes'] += self.state['reserved']
                    self.state['uncertainMetadata'] += self.state['reservedMetadata']
                self.state['reserved'] = self.state['reservedMetadata'] = 0
                self._persist(); self._journal(entry)
                if response is not None:
                    response.close()
            if transient:
                self.sleep(.25 * (attempt + 1))
        raise RemoteZipError('Range retrieval failed')

    def _fetch(self, start, end, *, metadata):
        _require(self._ready, 'Explicit bootstrap is required before range access')
        _require(type(start) is int and type(end) is int and 0 <= start <= end < self.expected_size,
                 'Invalid archive range')
        chunks = []
        for offset in range(start, end + 1, self.settings['requestBytes']):
            chunks.append(self._range(offset, min(end, offset + self.settings['requestBytes'] - 1), metadata))
        return b''.join(chunks)

    def _cached(self, start, end):
        for offset, value in self._cache:
            if offset <= start and end <= offset + len(value):
                return value[start - offset:end - offset]
        return None

    def _metadata(self, start, count):
        _require(count > 0, 'Invalid empty ZIP metadata range')
        cached = self._cached(start, start + count)
        if cached is None:
            cached = self._fetch(start, start + count - 1, metadata=True)
            self._cache.append((start, cached))
        return cached

    def members(self):
        """Inspect only bounded tail, ZIP64 records, and central directory metadata."""
        if self._infos is not None:
            return [self._member(info) for info in self._infos.values()]
        tail_start = max(0, self.expected_size - 65557)
        tail = self._metadata(tail_start, self.expected_size - tail_start)
        offset = tail.rfind(b'PK\x05\x06')
        _require(offset >= 0 and offset + 22 <= len(tail), 'Missing ZIP end record')
        end = struct.unpack_from('<4s4H2LH', tail, offset)
        _, disk, central_disk, disk_count, count, central_size, central_start, comment_size = end
        end_start = tail_start + offset
        _require(offset + 22 + comment_size == len(tail) and disk == central_disk == 0
                 and disk_count == count, 'Unsupported multidisk or malformed ZIP end record')
        central_end = end_start
        if count == 0xffff or central_size == 0xffffffff or central_start == 0xffffffff:
            locator_start = end_start - 20
            locator = self._metadata(locator_start, 20)
            signature, zip_disk, zip_offset, disks = struct.unpack('<4sLQL', locator)
            _require(signature == b'PK\x06\x07' and zip_disk == 0 and disks == 1,
                     'Invalid ZIP64 locator')
            record = self._metadata(zip_offset, 56)
            fields = struct.unpack('<4sQ2H2L4Q', record)
            signature, record_size, _, _, disk, central_disk, disk_count, count, central_size, central_start = fields
            _require(signature == b'PK\x06\x06' and 44 <= record_size <= 1024**2
                     and zip_offset + record_size + 12 == locator_start
                     and disk == central_disk == 0 and disk_count == count,
                     'Invalid ZIP64 end record')
            if record_size > 44:
                self._metadata(zip_offset, record_size + 12)
            central_end = zip_offset
        _require(0 < central_size <= self.settings['metadataBytes'] and 0 < count <= self.settings['maxEntries']
                 and 0 <= central_start < central_end and central_start + central_size == central_end,
                 'Invalid or oversized central directory')
        self._metadata(central_start, central_size)
        self.central_start = central_start
        try:
            archive = zipfile.ZipFile(self._reader, 'r', allowZip64=True)
            infos = archive.infolist()
            _require(len(infos) == count and archive.start_dir == central_start, 'Central directory count or offset differs')
            names = set()
            for info in infos:
                self._check_member(info)
                folded = info.filename.casefold()
                _require(folded not in names, 'Duplicate or casefold-colliding ZIP filename')
                names.add(folded)
            self._zip, self._infos = archive, {info.filename: info for info in infos}
        except (zipfile.BadZipFile, NotImplementedError, UnicodeError) as error:
            raise RemoteZipError('Invalid or unsupported ZIP directory') from error
        return [self._member(info) for info in self._infos.values()]

    @staticmethod
    def _safe_name(name, *, single=False):
        _require(isinstance(name, str) and name and '\x00' not in name and '\\' not in name
                 and ':' not in name and not name.startswith('/'), 'Unsafe ZIP or output filename')
        parts = name.rstrip('/').split('/')
        _require(all(part and part not in ('.', '..') for part in parts)
                 and (not single or (len(parts) == 1 and not name.endswith('/'))),
                 'Unsafe ZIP or output path')

    def _check_member(self, info):
        self._safe_name(info.orig_filename)
        _require(info.orig_filename == info.filename, 'Truncated ZIP filename')
        mode = stat.S_IFMT(info.external_attr >> 16)
        _require(mode in (0, stat.S_IFREG, stat.S_IFDIR) and (mode != stat.S_IFDIR or info.is_dir()),
                 'ZIP member is a symlink or nonregular file')
        _require(not info.flag_bits & 1 and not info.flag_bits & ~0x80e
                 and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                 'Encrypted or unsupported ZIP member')
        _require(info.compress_type != zipfile.ZIP_STORED or
                 (info.compress_size == info.file_size and not info.flag_bits & 6),
                 'Stored member size or flags differ')
        _require(not info.external_attr & 0x10 or info.is_dir(), 'Unsupported directory attribute')
        _require(0 <= info.header_offset < self.central_start
                 and 0 <= info.compress_size <= self.settings['maxMemberCompressed']
                 and 0 <= info.file_size <= self.settings['maxMemberUncompressed']
                 and info.header_offset + 30 + info.compress_size <= self.central_start,
                 'ZIP member offset or size outside bounds')
        _require(info.file_size <= max(1, info.compress_size) * self.settings['maxExpansionRatio'],
                 'Unreasonable ZIP member expansion')
        _require(not info.is_dir() or info.file_size == info.compress_size == 0, 'Nonempty directory member')

    @staticmethod
    def _member(info):
        return dict(name=info.filename, compressedSize=info.compress_size, size=info.file_size,
                    crc32=f'{info.CRC:08x}', compression=info.compress_type,
                    headerOffset=info.header_offset, directory=info.is_dir(),
                    filename=info.filename, header_offset=info.header_offset,
                    compress_size=info.compress_size, file_size=info.file_size,
                    CRC=info.CRC, compress_type=info.compress_type, flags=info.flag_bits)

    def acquire(self, name, *, allowlist, output_name, metadata=False,
                max_compressed=None, max_uncompressed=None):
        """Retrieve one explicit member, preserving any failed partial output."""
        _require(isinstance(allowlist, (set, frozenset, tuple, list)) and allowlist
                 and all(isinstance(item, str) for item in allowlist) and name in allowlist,
                 'Exact member name is not explicitly allowlisted')
        self._safe_name(output_name, single=True)
        _require(len(output_name.encode('utf-8')) <= 240, 'Output filename is too long')
        self.members()
        _require(name in self._infos and not self._infos[name].is_dir(), 'Unknown or nonfile ZIP member')
        info = self._infos[name]
        _require(type(metadata) is bool, 'Member metadata flag must be boolean')
        max_compressed = self.settings['maxMemberCompressed'] if max_compressed is None else max_compressed
        max_uncompressed = self.settings['maxMemberUncompressed'] if max_uncompressed is None else max_uncompressed
        _require(type(max_compressed) is int and 0 < max_compressed <= self.settings['maxMemberCompressed']
                 and type(max_uncompressed) is int and 0 < max_uncompressed <= self.settings['maxMemberUncompressed']
                 and info.compress_size <= max_compressed and info.file_size <= max_uncompressed,
                 'Member exceeds explicit per-call size bounds')
        final, partial = self.output/output_name, self.output/(output_name + '.partial')
        _require(not final.exists() and not partial.exists(), 'Output or preserved partial already exists')
        entry = dict(event='member', name=name, output=output_name, status='started', metadata=metadata,
                     maxCompressed=max_compressed, maxUncompressed=max_uncompressed)
        self._journal(entry)
        try:
            header = self._metadata(info.header_offset, 30)
            fields = struct.unpack('<4s5H3L2H', header)
            signature, _, flags, compression, _, _, _, _, _, name_length, extra_length = fields
            _require(signature == b'PK\x03\x04' and flags == info.flag_bits and compression == info.compress_type,
                     'Local header differs from central member')
            header_end = info.header_offset + 30 + name_length + extra_length
            _require(header_end + info.compress_size <= self.central_start, 'Member data overlaps central directory')
            self._metadata(info.header_offset + 30, name_length + extra_length)
            self._reader.allowed = [(info.header_offset, header_end + info.compress_size)]
            self._reader.metadata = metadata
            digest, crc, size = hashlib.sha256(), 0, 0
            with partial.open('xb') as output, self._zip.open(info, 'r') as source:
                while True:
                    block = source.read(self.settings['chunkBytes'])
                    if not block:
                        break
                    size += len(block)
                    _require(size <= info.file_size and size <= self.settings['maxMemberUncompressed'],
                             'Uncompressed member exceeds its bound')
                    output.write(block); digest.update(block); crc = zlib.crc32(block, crc)
                _require(size == info.file_size and crc == info.CRC, 'Member size or CRC differs')
                output.flush(); os.fsync(output.fileno())
            os.link(partial, final)
            partial.unlink()
            result = dict(path=str(final), sha256=digest.hexdigest(), size=size,
                          member=self._member(info), archive=dict(url=self.url, size=self.expected_size,
                          validator=dict(self.state['validator']), fullArchiveMd5Verified=False))
            self._journal(dict(event='member', name=name, output=output_name, status='complete',
                               bytes=size, sha256=digest.hexdigest()))
            return result
        except BaseException as error:
            self._journal(dict(event='member', name=name, output=output_name, status='failed', error=type(error).__name__))
            raise
        finally:
            self._reader.allowed = []
            self._reader.metadata = False

    def close(self):
        if self._zip is not None:
            self._zip.close()
        if self._owns_session:
            self.session.close()
        self._lock.close()

    def manifest(self):
        """JSON-safe frozen bindings and cumulative accounting; no member payload."""
        def pin(path):
            return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        return dict(url=self.url, expectedSize=self.expected_size,
                    validator=None if self.state['validator'] is None else dict(self.state['validator']),
                    settings=dict(self.settings),
                    bytesRead=self.state['bytesRead'], metadataRead=self.state['metadataRead'],
                    uncertainBytes=self.state['uncertainBytes'], uncertainMetadata=self.state['uncertainMetadata'],
                    budgetSpent=self.state['bytesRead'] + self.state['uncertainBytes'],
                    metadataBudgetSpent=self.state['metadataRead'] + self.state['uncertainMetadata'],
                    state=pin(self._state_path), journal=pin(self._journal_path),
                    fullArchiveMd5Verified=False)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
