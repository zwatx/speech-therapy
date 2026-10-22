"""Paced exact-member retrieval from a previously validated, SHA-bound directory.

Trust boundary: the caller verifies the complete directory snapshot binding and
its original validator (including external attributes). This module checks its
internal consistency and local headers; it never retrieves a central directory.
"""
import copy
import hashlib
import json
import os
import struct
import time
import zlib

from nisqa_ingest.http_transport_v2 import RemoteZipV2
from nisqa_ingest.remote_zip import _require

POLICY = {
    'version': 'nisqa-frozen-directory-v1', 'selectedNames': 20,
    'directoryTrust': 'caller SHA-bound complete snapshot previously validated including external attributes',
    'directoryRequests': False, 'minGetIntervalSeconds': 2,
    'maxPayloadRequestBytes': 1024**2, 'compressionMethods': [0, 8],
    'maxTotalBudgetBytes': 256 * 1024**2, 'maxMetadataBudgetBytes': 16 * 1024**2,
    'localHeaderRequests': '30 bytes then exact filename plus extra bytes; metadata budget',
    'memberBounds': 'before next strictly greater header offset or archive size',
    'unsupportedSelectedHeaders': ['data descriptor', 'local ZIP64 size sentinel'],
    'selectedFlags': 0,
    'transientRetries': 0, 'http429': 'terminal stop; inherited journal and budget preservation',
    'decoding': 'bounded declared-size plus one; exact size CRC32 and SHA256; no evaluation',
    'output': 'exclusive partial creation, hardlink publication without overwrite; preserve failed partial',
    'fullArchiveMd5Verified': False,
}


class _PacedSession:
    def __init__(self, session, clock, sleep):
        self.session, self.clock, self.sleep, self.last = session, clock, sleep, None

    def get(self, *args, **kwargs):
        now = self.clock()
        if self.last is not None:
            delay = 2 - (now - self.last)
            if delay > 0:
                self.sleep(delay)
            _require(self.clock() - self.last >= 2, 'Pacing clock or sleep did not advance')
        self.last = self.clock()
        return self.session.get(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.session, name)


class FrozenDirectoryZip(RemoteZipV2):
    def __init__(self, *args, frozen_members, selected_names, clock=time.monotonic,
                 sleep=time.sleep, **kwargs):
        _require(type(kwargs.get('retries', 0)) is int and kwargs.get('retries', 0) == 0,
                 'Recovery transport performs no transient retries')
        kwargs['retries'] = 0
        super().__init__(*args, sleep=sleep, **kwargs)
        try:
            _require(isinstance(frozen_members, list) and 0 < len(frozen_members) <= self.settings['maxEntries'],
                     'Complete frozen directory list required')
            self.frozen_members = copy.deepcopy(frozen_members)
            self.entries, folded, offsets = {}, set(), set()
            aliases = {'name': 'filename', 'headerOffset': 'header_offset', 'compressedSize': 'compress_size',
                       'size': 'file_size', 'compression': 'compress_type'}
            for entry in self.frozen_members:
                _require(isinstance(entry, dict), 'Invalid frozen directory entry')
                name = entry.get('filename')
                self._safe_name(name)
                _require(name.casefold() not in folded, 'Duplicate or casefold-colliding frozen filename')
                folded.add(name.casefold())
                for key in ('header_offset', 'compress_size', 'file_size', 'CRC', 'compress_type', 'flags'):
                    _require(type(entry.get(key)) is int and entry[key] >= 0, 'Invalid frozen member integer')
                for alias, key in aliases.items():
                    _require(alias not in entry or (type(entry[alias]) is type(entry[key]) and entry[alias] == entry[key]),
                             'Conflicting frozen member aliases')
                _require('crc32' not in entry or entry['crc32'] == f"{entry['CRC']:08x}", 'Conflicting CRC alias')
                directory = name.endswith('/')
                _require(type(entry.get('directory')) is bool and entry['directory'] == directory,
                         'Frozen directory flag differs from filename')
                offset, compressed, size = entry['header_offset'], entry['compress_size'], entry['file_size']
                _require(offset not in offsets and offset + 30 + compressed <= self.expected_size,
                         'Duplicate or out-of-bounds frozen header offset')
                offsets.add(offset)
                _require(entry['CRC'] <= 0xffffffff and entry['compress_type'] in (0, 8)
                         and not entry['flags'] & 1 and not entry['flags'] & ~0x80e,
                         'Unsupported frozen flags, CRC or compression')
                _require(entry['compress_type'] != 0 or (compressed == size and not entry['flags'] & 6),
                         'Stored size or flags differ')
                _require(compressed <= self.settings['maxMemberCompressed'] and size <= self.settings['maxMemberUncompressed']
                         and size <= max(1, compressed) * self.settings['maxExpansionRatio']
                         and (not directory or size == compressed == 0), 'Frozen member size exceeds bounds')
                self.entries[name] = entry
            ordered = sorted(offsets)
            self.boundaries = dict(zip(ordered, ordered[1:] + [self.expected_size]))
            for entry in self.entries.values():
                _require(entry['header_offset'] + 30 + entry['compress_size'] <= self.boundaries[entry['header_offset']],
                         'Overlapping frozen member ranges')
            _require(isinstance(selected_names, (list, tuple, set, frozenset)) and len(selected_names) == 20
                     and all(isinstance(name, str) for name in selected_names) and len(set(selected_names)) == 20
                     and all(name in self.entries and not self.entries[name]['directory'] for name in selected_names),
                     'Exactly twenty distinct frozen file names required')
            self.selected_names = frozenset(selected_names)
            _require(all(self.entries[name]['flags'] == 0 for name in self.selected_names),
                     'Selected flags must be zero; descriptors and other flags are unsupported')
            def digest(value):
                return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            self.frozen_binding = dict(policy=POLICY['version'], directorySha256=digest(self.frozen_members),
                                       selectedNamesSha256=digest(sorted(self.selected_names)))
            prior = self.state.get('frozenDirectoryBinding')
            _require(prior is None or prior == self.frozen_binding, 'Frozen directory or selected names changed on restart')
            if prior is None:
                self.state['frozenDirectoryBinding'] = self.frozen_binding
                self._persist()
                self._journal(dict(event='frozen-directory', binding=self.frozen_binding, policy=POLICY))
            self.session = _PacedSession(self.session, clock, sleep)
        except BaseException:
            self.close()
            raise

    def _range(self, start, end, metadata):
        # The session wrapper also paces every inherited retry, not just the
        # first attempt. Inherited HTTP validation and accounting stay intact.
        return super()._range(start, end, metadata)

    def members(self):
        _require(self._ready, 'Successful explicit v2 bootstrap is required')
        return copy.deepcopy(self.frozen_members)

    @staticmethod
    def _extras(value):
        extras, offset = {}, 0
        while offset < len(value):
            _require(offset + 4 <= len(value), 'Truncated local extra field')
            tag, count = struct.unpack_from('<HH', value, offset)
            offset += 4
            _require(offset + count <= len(value) and tag not in extras, 'Invalid or duplicate local extra field')
            extras[tag] = value[offset:offset + count]
            offset += count
        return extras

    def _local_header(self, entry):
        offset, bound = entry['header_offset'], self.boundaries[entry['header_offset']]
        header = self._fetch(offset, offset + 29, metadata=True)
        signature, version, flags, method, _, _, crc, compressed, size, name_length, extra_length = struct.unpack('<4s5H3L2H', header)
        _require(signature == b'PK\x03\x04' and flags == entry['flags'] and method == entry['compress_type']
                 and version <= 63 and name_length > 0, 'Local header differs from frozen member')
        end = offset + 30 + name_length + extra_length
        _require(end + entry['compress_size'] <= bound, 'Local member overlaps next header or archive boundary')
        extra_and_name = self._fetch(offset + 30, end - 1, metadata=True)
        try:
            name = extra_and_name[:name_length].decode('utf-8' if flags & 0x800 else 'cp437', errors='strict')
        except UnicodeError as error:
            raise ValueError('Invalid local filename encoding') from error
        _require(name == entry['filename'], 'Local filename differs from frozen member')
        self._extras(extra_and_name[name_length:])
        _require(not flags & 8 and size != 0xffffffff and compressed != 0xffffffff,
                 'Data descriptors or local ZIP64 size sentinels are unsupported')
        _require(crc == entry['CRC'] and size == entry['file_size'] and compressed == entry['compress_size'],
                 'Local CRC or sizes differ from frozen member')
        return end

    def acquire(self, name, *, allowlist, output_name, metadata=False, max_compressed=None, max_uncompressed=None):
        _require(self._ready, 'Successful explicit v2 bootstrap is required')
        _require(isinstance(allowlist, (set, frozenset, list, tuple)) and len(allowlist) == 20
                 and all(isinstance(item, str) for item in allowlist)
                 and frozenset(allowlist) == self.selected_names and name in self.selected_names,
                 'Allowlist must exactly equal the fixed twenty names')
        self._safe_name(output_name, single=True)
        _require(len(output_name.encode('utf-8')) <= 240 and type(metadata) is bool, 'Invalid output name or metadata flag')
        entry = self.entries[name]
        max_compressed = self.settings['maxMemberCompressed'] if max_compressed is None else max_compressed
        max_uncompressed = self.settings['maxMemberUncompressed'] if max_uncompressed is None else max_uncompressed
        _require(type(max_compressed) is int and 0 < max_compressed <= self.settings['maxMemberCompressed']
                 and type(max_uncompressed) is int and 0 < max_uncompressed <= self.settings['maxMemberUncompressed']
                 and entry['compress_size'] <= max_compressed and entry['file_size'] <= max_uncompressed,
                 'Member exceeds explicit per-call size bounds')
        final, partial = self.output/output_name, self.output/(output_name + '.partial')
        _require(not os.path.lexists(final) and not os.path.lexists(partial), 'Output or preserved partial already exists')
        self._journal(dict(event='member', name=name, output=output_name, status='started', metadata=metadata,
                           maxCompressed=max_compressed, maxUncompressed=max_uncompressed))
        try:
            start = self._local_header(entry)
            digest, crc, size = hashlib.sha256(), 0, 0
            decoder = zlib.decompressobj(-15) if entry['compress_type'] == 8 else None
            with partial.open('xb') as output:
                for offset in range(0, entry['compress_size'], self.settings['requestBytes']):
                    count = min(self.settings['requestBytes'], entry['compress_size'] - offset)
                    payload = self._fetch(start + offset, start + offset + count - 1, metadata=metadata)
                    block = payload if decoder is None else decoder.decompress(payload, entry['file_size'] - size + 1)
                    size += len(block)
                    _require(size <= entry['file_size'] and size <= max_uncompressed, 'Decoded member exceeds bound')
                    _require(decoder is None or (not decoder.unconsumed_tail and not decoder.unused_data),
                             'Trailing or unconsumed compressed bytes')
                    output.write(block); digest.update(block); crc = zlib.crc32(block, crc)
                _require(decoder is None or decoder.eof, 'Truncated DEFLATE stream')
                _require(size == entry['file_size'] and crc == entry['CRC'], 'Member size or CRC differs')
                output.flush(); os.fsync(output.fileno())
            os.link(partial, final)
            partial.unlink()
            result = dict(path=str(final), sha256=digest.hexdigest(), size=size, member=copy.deepcopy(entry),
                          archive=dict(url=self.url, size=self.expected_size, validator=dict(self.state['validator']),
                                       fullArchiveMd5Verified=False))
            self._journal(dict(event='member', name=name, output=output_name, status='complete', bytes=size, sha256=digest.hexdigest()))
            return result
        except BaseException as error:
            self._journal(dict(event='member', name=name, output=output_name, status='failed', error=type(error).__name__))
            raise

    def manifest(self):
        return {**super().manifest(), 'frozenDirectoryBinding': dict(self.frozen_binding), 'frozenDirectoryPolicy': copy.deepcopy(POLICY)}
