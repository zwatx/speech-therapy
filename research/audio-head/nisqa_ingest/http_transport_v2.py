"""RFC-aware If-Range validation atop the frozen bounded ZIP transport.

RFC 9110 8.8.2.2 uses a >=1-second Date/Last-Modified gap plus clock
reasoning. This experiment adopts a more conservative >=60-second policy.
RFC 9110 13.1.5 forbids weak ETags and date fallback if any ETag exists.
RFC 9110 15.3.7 permits omitted Last-Modified on an If-Range 206, while
requiring ETag when it would have been present on the corresponding 200.

Primary text: https://www.rfc-editor.org/rfc/rfc9110.html
"""
from email.utils import parsedate_to_datetime
import hashlib
import re
import time

import requests
from urllib3.exceptions import ProtocolError, ReadTimeoutError

from nisqa_ingest.remote_zip import RemoteZip, RemoteZipError, _Transient, _require

POLICY = 'nisqa-if-range-v2'
DATE_GAP_SECONDS = 60


def _date(value):
    _require(isinstance(value, str) and '\r' not in value and '\n' not in value,
             'Missing or invalid HTTP date')
    try:
        result = parsedate_to_datetime(value)
    except (ValueError, TypeError, OverflowError) as error:
        raise RemoteZipError('Missing or invalid HTTP date') from error
    _require(result.tzinfo is not None and result.utcoffset() is not None,
             'Timezone-aware HTTP date required')
    return result


class RemoteZipV2(RemoteZip):
    """Same ZIP/range/budget API; corrected, evidence-backed validator policy."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            policy = self.state.get('validatorPolicy')
            _require(policy == POLICY or (policy is None and self.state['validator'] is None),
                     'A pinned legacy transport cannot be silently upgraded')
            if policy is None:
                self.state['validatorPolicy'] = POLICY
                self._persist()
        except BaseException:
            self.close()
            raise

    def bootstrap(self):
        """Pin representation identity and journal actual HEAD strength evidence."""
        self._ready = False
        response = None
        entry = dict(event='HEAD', range=None, bytes=0, sha256=hashlib.sha256(b'').hexdigest(),
                     validatorPolicy=POLICY)
        try:
            response = self.session.head(self.url, headers={'Accept-Encoding': 'identity'},
                                         timeout=self.timeout, allow_redirects=False, stream=True)
            entry['status'] = response.status_code
            entry['date'] = response.headers.get('Date')
            entry['validators'] = dict(etag=response.headers.get('ETag'),
                                        lastModified=response.headers.get('Last-Modified'))
            _require(response.status_code == 200, 'HEAD must return 200 without a redirect')
            actual = self._response(response)
            _require(response.headers.get('Content-Length') == str(self.expected_size),
                     'HEAD archive length differs')
            etag, modified = actual['etag'], actual['lastModified']
            if etag is not None:
                _require(isinstance(etag, str) and re.fullmatch(r'"[\x21\x23-\x7e\x80-\xff]*"', etag),
                         'If-Range requires a strong valid ETag; date fallback is forbidden when ETag exists')
                mode, if_range = 'strong-etag', etag
                evidence = dict(mode=mode, strongEtag=True, source='HEAD', date=entry['date'])
            else:
                date, last_modified = _date(entry['date']), _date(modified)
                gap = (date - last_modified).total_seconds()
                evidence = dict(mode='date', source='HEAD', date=entry['date'], lastModified=modified,
                                gapSeconds=gap, minimumGapSeconds=DATE_GAP_SECONDS,
                                gapPolicy='conservative experiment policy; not RFC minimum')
                entry['strengthEvidence'] = evidence
                _require(gap >= DATE_GAP_SECONDS, 'Last-Modified lacks the required conservative Date gap')
                mode, if_range = 'date', modified
            entry['strengthEvidence'] = evidence
            identity = dict(**actual, ifRange=if_range, mode=mode)
            if self.state['validator'] is not None:
                _require(identity == self.state['validator'], 'Archive validator changed on restart')
                _require(self.state.get('validatorEvidence') is not None,
                         'Missing pinned validator strength evidence')
            else:
                self.state['validator'] = identity
                self.state['validatorEvidence'] = evidence
                self._persist()
            self._ready = True
            entry['outcome'] = 'verified'
            return dict(url=self.url, size=self.expected_size, **identity)
        except BaseException as error:
            entry['outcome'], entry['error'] = 'failed', type(error).__name__
            raise
        finally:
            self._journal(entry)
            if response is not None:
                response.close()

    def _check_range_validators(self, actual):
        pinned = self.state['validator']
        if pinned['mode'] == 'strong-etag':
            _require(actual['etag'] == pinned['etag'], 'Required strong response ETag is missing or changed')
        else:
            _require(pinned['mode'] == 'date' and pinned['etag'] is None and actual['etag'] is None,
                     'Response ETag conflicts with the pinned date validator')
        # If-Range 206 may omit Last-Modified. A provided conflicting value
        # always fails; raw actual fields remain unmodified in the journal.
        _require(actual['lastModified'] is None or actual['lastModified'] == pinned['lastModified'],
                 'Provided response Last-Modified conflicts with the pinned identity')

    def _range(self, start, end, metadata):
        """Frozen bounded read/accounting loop, with only validator policy changed."""
        count = end - start + 1
        for attempt in range(self.retries + 1):
            entry = dict(event='GET', range=[start, end], attempt=attempt + 1,
                         metadata=metadata, status=None, validatorPolicy=POLICY)
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
                entry['date'] = response.headers.get('Date')
                entry['validators'] = dict(etag=response.headers.get('ETag'),
                                            lastModified=response.headers.get('Last-Modified'))
                if response.status_code in (429, 502, 503, 504):
                    raise _Transient('Transient range status')
                _require(response.status_code == 206, 'Exact HTTP 206 range response required')
                actual = self._response(response)
                self._check_range_validators(actual)
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

    def members(self):
        _require(self._ready, 'Successful explicit v2 bootstrap is required')
        return super().members()

    def manifest(self):
        return {**super().manifest(), 'validatorPolicy': POLICY,
                'validatorEvidence': self.state.get('validatorEvidence')}
