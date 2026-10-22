"""Acquire only the fixed public prompt-reference plan with per-file receipts."""

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import html
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import urllib.parse
import urllib.request
import urllib.error
import wave

PACK_SHA256 = 'a957a9e3291f0d90b275d40cd914890836ee7e6fc4fd361f7589cd1444587ef3'
ROOT = Path(__file__).resolve().parents[2]
PACK_PATH = ROOT / 'docs/consumer-assessment/proposed-engineering-pack.json'
DEFAULT_OUTPUT = ROOT / 'work/assessment-real-data-20261004/references'
API = 'https://commons.wikimedia.org/w/api.php'
USER_AGENT = 'SpeechTherapyReferencePreparation/1.0 (local public-source research; no credentials)'
LIMIT = 8 * 1024 * 1024
_last_fetch = 0.0
PLAN = {word: {'title': f'File:En-us-{word}.ogg', 'license': 'CC-BY-SA-3.0', 'variety': 'US English (source label)'}
        for word in ('rabbit', 'bread', 'door', 'baby', 'banana', 'sky', 'vase', 'ring', 'treasure')}
PLAN.update({
    'thumb': {'title': 'File:En-us-thumb.ogg', 'license': 'PD-self', 'variety': 'US English (source label)'},
    'feather': {'title': 'File:En-us-feather.ogg', 'license': 'PD-self', 'variety': 'US English (source label)'},
    'backpack': {'title': 'File:En-uk-backpack.ogg', 'license': 'CC-BY-3.0-US', 'variety': 'London, England (source label)'},
    'yoyo': {'title': 'File:LL-Q1860 (eng)-Flame, not lame-yoyo.wav', 'license': 'CC0-1.0', 'variety': 'English; variety unspecified'},
})
LICENSES = {
    'CC-BY-SA-3.0': ('CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0/', 'cc-by-sa-3.0'),
    'CC-BY-3.0-US': ('CC BY 3.0 us', 'https://creativecommons.org/licenses/by/3.0/us/', 'cc-by-3.0-us'),
    'CC0-1.0': ('CC0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'cc-zero'),
    'PD-self': ('Public domain', 'https://commons.wikimedia.org/wiki/Template:PD-self', 'pd-self'),
}
GAPS = {'metadata_unavailable', 'source_license_unavailable', 'original_unavailable', 'original_mismatch', 'conversion_failed'}


class AssetError(ValueError):
    """Only fixed error codes leave acquisition boundaries."""


class Throttled(AssetError):
    def __init__(self, retry_after):
        super().__init__('download_throttled')
        self.retry_after = retry_after


class _Plain(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _plain(value):
    if type(value) is not str or len(value) > 10000:
        raise AssetError('source_license_unavailable')
    parser = _Plain()
    parser.feed(value)
    return html.unescape(' '.join(parser.parts)).strip()


def _bytes(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'


def pack_words():
    raw = PACK_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PACK_SHA256:
        raise AssetError('source_pack_drift')
    pack = json.loads(raw.decode('utf-8'))
    words = {prompt['sourceWord'].strip().casefold(): prompt['word'] for prompt in pack['prompts']}
    if set(words) != set(PLAN):
        raise AssetError('source_pack_drift')
    return dict(sorted(words.items()))


def _url(url, host, prefix):
    if type(url) is not str:
        raise AssetError('source_license_unavailable')
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != host or not parsed.path.startswith(prefix)
            or parsed.username or parsed.password or parsed.fragment or parsed.port is not None):
        raise AssetError('source_license_unavailable')
    return url


def validate_metadata(word, page):
    """Require the selected license, revision, authorship and source evidence."""
    try:
        plan = PLAN[word]
        if (type(page) is not dict or page.get('missing') or page['title'] != plan['title']
                or type(page['ns']) is not int or page['ns'] != 6):
            raise AssetError('source_license_unavailable')
        info = page['imageinfo'][0]
        revision = page['revisions'][0]
        text = revision['slots']['main']['content']
        if type(revision['revid']) is not int or revision['revid'] < 1 or type(text) is not str:
            raise AssetError('source_license_unavailable')
        if type(revision['timestamp']) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', revision['timestamp']) is None:
            raise AssetError('source_license_unavailable')
        datetime.fromisoformat(revision['timestamp'])
        text.encode('utf-8')
        license_id = plan['license']
        short_name, license_url, template = LICENSES[license_id]
        ext = info['extmetadata']
        if ext['LicenseShortName']['value'] != short_name or template not in text.casefold():
            raise AssetError('source_license_unavailable')
        # Retain and check the actual file's own-work/source declaration; do not
        # infer its audio license from Commons' site-wide metadata license.
        credit = _plain(ext.get('Credit', {}).get('value', ''))
        author = _plain(ext.get('Artist', {}).get('value', ''))
        if license_id == 'PD-self' and not author and 'recorded by Dvortygirl' in text:
            author = 'Dvortygirl'
            credit = 'Recorded by Dvortygirl; explicit PD-self release'
        if not author or not credit or (license_id == 'PD-self' and '{{pd-self}}' not in text.casefold()):
            raise AssetError('source_license_unavailable')
        if license_id != 'PD-self':
            declared_url = ext['LicenseUrl']['value'].replace('http://', 'https://')
            if declared_url.rstrip('/').removesuffix('/deed.en').rstrip('/') != license_url.rstrip('/'):
                raise AssetError('source_license_unavailable')
        url = _url(info['url'], 'upload.wikimedia.org', '/wikipedia/commons/')
        source_url = _url(info['descriptionurl'], 'commons.wikimedia.org', '/wiki/File:')
        if (urllib.parse.unquote(urllib.parse.urlsplit(source_url).path).replace('_', ' ') != '/wiki/' + plan['title']
                or urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1]).replace('_', ' ') != plan['title'][5:]):
            raise AssetError('source_license_unavailable')
        if (type(info['size']) is not int or not 0 < info['size'] <= LIMIT
                or type(info['sha1']) is not str or re.fullmatch('[0-9a-f]{40}', info['sha1']) is None
                or info['mime'] not in ('application/ogg', 'audio/ogg', 'audio/x-wav', 'audio/wav')):
            raise AssetError('source_license_unavailable')
        return {'id': 'commons-' + word, 'word': pack_words()[word], 'sourceWord': word,
                'sourcePageUrl': source_url, 'originalUrl': url, 'author': author,
                'licenseId': license_id, 'licenseUrl': license_url, 'sourceCredit': credit,
                'sourceRevisionId': revision['revid'], 'sourceRevisionTimestamp': revision['timestamp'],
                'permanentSourcePageUrl': 'https://commons.wikimedia.org/w/index.php?' + urllib.parse.urlencode({'title': page['title'], 'oldid': revision['revid']}),
                'apiSha1': info['sha1'], 'apiSizeBytes': info['size'], 'originalMime': info['mime'],
                'declaredVariety': plan['variety'], 'varietyVerified': False,
                'speakerAgeKnown': False, 'clinicalReferenceApproved': False,
                'promptMatchVerified': False, 'speakerIdentityVerified': False, 'participantConsentEstablished': False,
                'dictionaryVariantCoverageEstablished': False,
                'permissionBasis': 'Per-file source license/release; no identity or participant consent established',
                'permissions': {purpose: {'allowed': True, 'basis': license_id, 'conditions': 'Retain attribution, source and license; preserve share-alike for CC-BY-SA-3.0 derivatives'}
                                for purpose in ('referencePlayback', 'localInference', 'storage', 'redistribution')},
                'allowedUserResearchUse': True}
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        raise AssetError('source_license_unavailable') from None


def verify_original(metadata, data):
    if (type(data) is not bytes or len(data) != metadata['apiSizeBytes']
            or hashlib.sha1(data).hexdigest() != metadata['apiSha1']):
        raise AssetError('original_mismatch')
    return hashlib.sha256(data).hexdigest()


def gap_record(word, reason):
    if word not in PLAN or reason not in GAPS:
        raise AssetError('invalid_gap')
    return {'sourceWord': word, 'word': pack_words()[word], 'candidateTitle': PLAN[word]['title'],
            'reason': reason, 'audioAcquired': False, 'clinicalReferenceApproved': False}


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != 'https' or parsed.netloc not in ('commons.wikimedia.org', 'upload.wikimedia.org'):
            raise AssetError('metadata_unavailable')
        return super().redirect_request(request, fp, code, message, headers, newurl)


def _fetch(url):
    global _last_fetch
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc not in ('commons.wikimedia.org', 'upload.wikimedia.org'):
        raise AssetError('metadata_unavailable')
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    time.sleep(max(0.0, 2.0 - (time.monotonic() - _last_fetch)))
    _last_fetch = time.monotonic()
    try:
        with urllib.request.build_opener(_Redirect()).open(request, timeout=30) as response:
            raw = response.read(LIMIT + 1)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            delay = error.headers.get('Retry-After', '600')
            raise Throttled(int(delay) if delay.isdigit() else 600) from None
        raise
    if len(raw) > LIMIT:
        raise AssetError('metadata_unavailable')
    return raw


def _directory(path):
    path.mkdir(mode=0o700, exist_ok=True)
    _check_directory(path)


def _check_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise AssetError('private_output_required')


def _read(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > LIMIT):
            raise AssetError('private_input_required')
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise AssetError('private_input_required')
    return raw


def _write(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def wav_details(raw):
    try:
        if type(raw) is not bytes or len(raw) > LIMIT:
            raise AssetError('conversion_failed')
        with wave.open(io.BytesIO(raw), 'rb') as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise AssetError('conversion_failed')
            count = stream.getnframes()
            if count <= 0 or len(stream.readframes(count)) != count * 2:
                raise AssetError('conversion_failed')
            return {'durationSeconds': count / 16000, 'sampleRateHz': 16000, 'sampleWidthBytes': 2, 'channels': 1, 'sampleCount': count}
    except (wave.Error, EOFError, TypeError, ValueError):
        raise AssetError('conversion_failed') from None


def _conversion(record, output, ffmpeg, version):
    word = record['sourceWord']
    original_path = output / f"originals/{word}{'.wav' if record['originalMime'] in ('audio/x-wav', 'audio/wav') else '.ogg'}"
    if original_path.exists():
        original = _read(original_path)
    else:
        original = _fetch(record['originalUrl'])
        verify_original(record, original)
        _write(original_path, original)
    record['originalSha256'] = verify_original(record, original)
    wav_path = output / f'wav/{word}.wav'
    command = None
    if not wav_path.exists():
        original_fd = os.open(original_path, os.O_RDONLY | os.O_NOFOLLOW)
        wav_fd = os.open(wav_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        command = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', f'/dev/fd/{original_fd}',
                   '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '-f', 'wav', f'/dev/fd/{wav_fd}']
        try:
            subprocess.run(command, check=True, capture_output=True, pass_fds=(original_fd, wav_fd), timeout=30)
            os.fsync(wav_fd)
        finally:
            os.close(original_fd)
            os.close(wav_fd)
    converted = _read(wav_path)
    record.update(wav_details(converted))
    changes = 'Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.'
    record.update({'originalPath': str(original_path), 'wavPath': str(wav_path), 'wavSha256': hashlib.sha256(converted).hexdigest(),
                   'changes': changes, 'derivativeLicenseId': record['licenseId'],
                   'attribution': f"{PLAN[word]['title']} — {record['author']}; {record['sourcePageUrl']}; {record['licenseUrl']}. {changes}"})
    receipt_path = output / f'receipts/{word}.json'
    if command is not None:
        receipt = {'schemaVersion': 1, 'sourceWord': word, 'command': command, 'ffmpegVersion': version.splitlines()[0],
                   'originalSha256': record['originalSha256'], 'wavSha256': record['wavSha256'],
                   'changes': changes, 'derivativeLicenseId': record['licenseId'],
                   'commandNote': 'Descriptors identify these receipt-bound files; reproduce using originalPath and wavPath.'}
        _write(receipt_path, _bytes(receipt))
    receipt_bytes = _read(receipt_path)
    receipt = json.loads(receipt_bytes.decode('utf-8'))
    if receipt['originalSha256'] != record['originalSha256'] or receipt['wavSha256'] != record['wavSha256']:
        raise AssetError('conversion_failed')
    record['conversionReceiptPath'] = str(receipt_path)
    record['conversionReceiptSha256'] = hashlib.sha256(receipt_bytes).hexdigest()
    return record


def _asset(word, page, request_url, output, ffmpeg, version):
    record = validate_metadata(word, page)
    evidence = _bytes({'apiRequestUrl': request_url, 'page': page})
    evidence_path = output / f'source-evidence/{word}.json'
    if evidence_path.exists():
        if _read(evidence_path) != evidence:
            raise AssetError('source_license_unavailable')
    else:
        _write(evidence_path, evidence)
    html_path = output / f'source-evidence/{word}.html'
    if html_path.exists():
        source_html = _read(html_path)
    else:
        source_html = _fetch(record['permanentSourcePageUrl'])
        _write(html_path, source_html)
    record.update({'sourceEvidencePath': str(evidence_path), 'sourceEvidenceSha256': hashlib.sha256(evidence).hexdigest(),
                   'sourcePageEvidencePath': str(html_path), 'sourcePageEvidenceSha256': hashlib.sha256(source_html).hexdigest()})
    return _conversion(record, output, ffmpeg, version)


def _save_registry(output, registry, previous):
    if previous is not None:
        number = len(list((output / 'receipts').glob('registry-*.json'))) + 1
        _write(output / f'receipts/registry-{number:04d}.json', previous)
        _write(output / 'assets.next.json', _bytes(registry))
        os.replace(output / 'assets.next.json', output / 'assets.json')
        descriptor = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    else:
        _write(output / 'assets.json', _bytes(registry))


def acquire(output=DEFAULT_OUTPUT, resume=False):
    """Fixed public plan only; resumes preserve original assets and receipts."""
    words = pack_words()
    output = Path(output).absolute()
    _directory(output)
    previous = _read(output / 'assets.json') if resume else None
    if previous is not None:
        previous_registry = json.loads(previous.decode('utf-8'))
        not_before = previous_registry.get('retryNotBeforeUnixSeconds')
        if not_before is not None and (type(not_before) is not int or time.time() < not_before):
            raise AssetError('download_cooldown_active')
    if not resume and any(output.iterdir()):
        raise AssetError('output_not_empty')
    for name in ('source-evidence', 'originals', 'wav', 'receipts'):
        _directory(output / name)
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        raise AssetError('conversion_failed')
    if resume:
        version = _read(output / 'receipts/ffmpeg-version.txt').decode('utf-8')
    else:
        version = subprocess.run([ffmpeg, '-version'], check=True, capture_output=True, text=True).stdout
        _write(output / 'receipts/ffmpeg-version.txt', version.encode('utf-8'))
    query = urllib.parse.urlencode({'action': 'query', 'format': 'json', 'formatversion': '2',
                                   'prop': 'imageinfo|revisions', 'iiprop': 'url|size|sha1|mime|extmetadata',
                                   'rvprop': 'ids|timestamp|content', 'rvslots': 'main',
                                   'titles': '|'.join(PLAN[word]['title'] for word in words)})
    request_url = API + '?' + query
    if resume:
        raw = _read(output / 'source-evidence/metadata-response.json')
    else:
        raw = _fetch(request_url)
        _write(output / 'source-evidence/metadata-response.json', raw)
    response = json.loads(raw.decode('utf-8'))
    pages = {page['title']: page for page in response['query']['pages']}
    assets, gaps = [], []
    retry_after = None
    for word in words:
        if retry_after is not None:
            gaps.append(gap_record(word, 'original_unavailable'))
            continue
        try:
            assets.append(_asset(word, pages[PLAN[word]['title']], request_url, output, ffmpeg, version))
        except Throttled as error:
            retry_after = error.retry_after
            gaps.append(gap_record(word, 'original_unavailable'))
        except (AssetError, OSError, ValueError, KeyError, subprocess.SubprocessError, wave.Error) as error:
            code = str(error) if isinstance(error, AssetError) and str(error) in GAPS else 'original_unavailable'
            gaps.append(gap_record(word, code))
    registry = {'schemaVersion': 1, 'sourcePackSha256': PACK_SHA256, 'use': 'local_engineering_reference_assessment',
                'permissionMeaning': 'Recorded per-file public license grants only; no speaker identity, age or participant consent established',
                'clinicalReferenceApproved': False, 'variantCoverageMeaning': 'One recording per source word; both rabbit/vase dictionary variants retained upstream; no all-variant coverage claim',
                'assets': assets, 'gaps': gaps}
    if retry_after is not None:
        registry['retryAfterSeconds'] = retry_after
        registry['retryNotBeforeUnixSeconds'] = int(time.time()) + retry_after + 1
    _save_registry(output, registry, previous)
    return registry


def validate_registry(registry, require_complete=True):
    """Bind the closed public plan and private bytes; establish no identity truth."""
    try:
        if type(require_complete) is not bool or type(registry) is not dict:
            raise AssetError('invalid_registry')
        required = {'schemaVersion', 'sourcePackSha256', 'use', 'permissionMeaning',
                    'clinicalReferenceApproved', 'variantCoverageMeaning', 'assets', 'gaps'}
        if set(registry) not in (required, required | {'retryAfterSeconds'}, required | {'retryAfterSeconds', 'retryNotBeforeUnixSeconds'}):
            raise AssetError('invalid_registry')
        if (type(registry['schemaVersion']) is not int or registry['schemaVersion'] != 1
                or registry['sourcePackSha256'] != PACK_SHA256
                or registry['use'] != 'local_engineering_reference_assessment'
                or registry['clinicalReferenceApproved'] is not False
                or registry['permissionMeaning'] != 'Recorded per-file public license grants only; no speaker identity, age or participant consent established'
                or registry['variantCoverageMeaning'] != 'One recording per source word; both rabbit/vase dictionary variants retained upstream; no all-variant coverage claim'
                or type(registry['assets']) is not list or type(registry['gaps']) is not list
                or ('retryAfterSeconds' in registry and (type(registry['retryAfterSeconds']) is not int or not 0 < registry['retryAfterSeconds'] <= 86400))):
            raise AssetError('invalid_registry')
        if 'retryNotBeforeUnixSeconds' in registry and type(registry['retryNotBeforeUnixSeconds']) is not int:
            raise AssetError('invalid_registry')
        if require_complete and (registry['gaps'] or len(registry['assets']) != 13):
            raise AssetError('invalid_registry')
        words = pack_words()
        identities = []
        for asset in registry['assets']:
            if type(asset) is not dict or type(asset.get('sourceWord')) is not str or asset['sourceWord'] not in words:
                raise AssetError('invalid_registry')
            identities.append(asset['sourceWord'])
        for gap in registry['gaps']:
            if type(gap) is not dict or gap != gap_record(gap['sourceWord'], gap['reason']):
                raise AssetError('invalid_registry')
            identities.append(gap['sourceWord'])
        if len(identities) != len(words) or set(identities) != set(words):
            raise AssetError('invalid_registry')
        output = DEFAULT_OUTPUT.absolute()
        for directory in (output, *(output / name for name in ('source-evidence', 'originals', 'wav', 'receipts'))):
            _check_directory(directory)
        response = json.loads(_read(output / 'source-evidence/metadata-response.json').decode('utf-8'))
        pages = {page['title']: page for page in response['query']['pages']}
        version = _read(output / 'receipts/ffmpeg-version.txt').decode('utf-8').splitlines()[0]
        for asset in registry['assets']:
            word = asset['sourceWord']
            evidence_path = output / f'source-evidence/{word}.json'
            evidence = _read(evidence_path)
            saved = json.loads(evidence.decode('utf-8'))
            page = pages[PLAN[word]['title']]
            if _bytes(saved['page']) != _bytes(page):
                raise AssetError('invalid_registry')
            expected = validate_metadata(word, page)
            html_path = output / f'source-evidence/{word}.html'
            expected.update({'sourceEvidencePath': str(evidence_path), 'sourceEvidenceSha256': hashlib.sha256(evidence).hexdigest(),
                             'sourcePageEvidencePath': str(html_path), 'sourcePageEvidenceSha256': hashlib.sha256(_read(html_path)).hexdigest()})
            original_path = output / f"originals/{word}{'.wav' if expected['originalMime'] in ('audio/x-wav', 'audio/wav') else '.ogg'}"
            original = _read(original_path)
            original_sha = verify_original(expected, original)
            wav_path = output / f'wav/{word}.wav'
            converted = _read(wav_path)
            wav_sha = hashlib.sha256(converted).hexdigest()
            expected.update(wav_details(converted))
            changes = 'Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.'
            receipt_path = output / f'receipts/{word}.json'
            receipt_bytes = _read(receipt_path)
            receipt = json.loads(receipt_bytes.decode('utf-8'))
            if (set(receipt) != {'schemaVersion', 'sourceWord', 'command', 'ffmpegVersion', 'originalSha256', 'wavSha256', 'changes', 'derivativeLicenseId', 'commandNote'}
                    or type(receipt['schemaVersion']) is not int or receipt['schemaVersion'] != 1
                    or receipt['sourceWord'] != word or receipt['originalSha256'] != original_sha
                    or receipt['wavSha256'] != wav_sha or receipt['ffmpegVersion'] != version
                    or receipt['changes'] != changes or receipt['derivativeLicenseId'] != expected['licenseId']
                    or receipt['commandNote'] != 'Descriptors identify these receipt-bound files; reproduce using originalPath and wavPath.'):
                raise AssetError('invalid_registry')
            command = receipt['command']
            if (type(command) is not list or len(command) != 17 or type(command[0]) is not str or Path(command[0]).name != 'ffmpeg'
                    or command[1:7] != ['-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i']
                    or command[8:16] != ['-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '-f', 'wav']
                    or type(command[7]) is not str or re.fullmatch('/dev/fd/[0-9]+', command[7]) is None
                    or type(command[16]) is not str or re.fullmatch('/dev/fd/[0-9]+', command[16]) is None):
                raise AssetError('invalid_registry')
            expected.update({'originalPath': str(original_path), 'originalSha256': original_sha,
                             'wavPath': str(wav_path), 'wavSha256': wav_sha, 'changes': changes,
                             'derivativeLicenseId': expected['licenseId'],
                             'attribution': f"{PLAN[word]['title']} — {expected['author']}; {expected['sourcePageUrl']}; {expected['licenseUrl']}. {changes}",
                             'conversionReceiptPath': str(receipt_path), 'conversionReceiptSha256': hashlib.sha256(receipt_bytes).hexdigest()})
            if _bytes(asset) != _bytes(expected):
                raise AssetError('invalid_registry')
        return deepcopy(registry)
    except (AssetError, OSError, ValueError, KeyError, IndexError, TypeError, OverflowError, RecursionError):
        raise AssetError('invalid_registry') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT, help='New or empty owned private output directory')
    parser.add_argument('--resume', action='store_true', help='Resume from retained private source evidence after a download cooldown')
    args = parser.parse_args()
    try:
        registry = acquire(args.output, resume=args.resume)
        print(json.dumps({'assets': len(registry['assets']), 'gaps': len(registry['gaps']), 'clinicalReferenceApproved': False}))
        return 0 if not registry['gaps'] else 1
    except (AssetError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error) if isinstance(error, AssetError) else 'acquisition_failed')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
