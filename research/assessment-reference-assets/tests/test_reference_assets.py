import copy
import hashlib
import unittest

import reference_assets as refs


def example_page(word='rabbit'):
    title = refs.PLAN[word]['title']
    return {'title': title, 'ns': 6, 'pageid': 7,
            'revisions': [{'revid': 21, 'timestamp': '2026-10-04T00:00:00Z',
                           'slots': {'main': {'content': '{{Information|source={{own}}|author=Dvortygirl}}{{self|cc-by-sa-3.0-migrated}}'}}}],
            'imageinfo': [{'url': 'https://upload.wikimedia.org/wikipedia/commons/a/a0/' + title[5:],
                           'descriptionurl': 'https://commons.wikimedia.org/wiki/' + title,
                           'size': 4, 'sha1': hashlib.sha1(b'OggS').hexdigest(), 'mime': 'application/ogg',
                           'extmetadata': {'Artist': {'value': 'Dvortygirl'}, 'Credit': {'value': 'Own work'},
                                           'LicenseShortName': {'value': 'CC BY-SA 3.0'},
                                           'LicenseUrl': {'value': 'http://creativecommons.org/licenses/by-sa/3.0/'}}}]}


class MetadataTests(unittest.TestCase):
    def test_explicit_per_file_license_and_source_are_required(self):
        record = refs.validate_metadata('rabbit', example_page())
        self.assertEqual(record['author'], 'Dvortygirl')
        self.assertEqual(record['licenseId'], 'CC-BY-SA-3.0')
        self.assertEqual(record['licenseUrl'], 'https://creativecommons.org/licenses/by-sa/3.0/')
        self.assertIn('oldid=21', record['permanentSourcePageUrl'])
        self.assertEqual(refs.verify_original(record, b'OggS'), hashlib.sha256(b'OggS').hexdigest())
        for location in ('license', 'ownership', 'author', 'title', 'url', 'size', 'revision', 'namespace', 'timestamp'):
            page = example_page()
            if location == 'license': page['imageinfo'][0]['extmetadata']['LicenseShortName']['value'] = 'Unknown'
            if location == 'ownership': page['revisions'][0]['slots']['main']['content'] = 'No copyright release here'
            if location == 'author': page['imageinfo'][0]['extmetadata']['Artist']['value'] = ''
            if location == 'title': page['title'] = 'File:Foreign.ogg'
            if location == 'url': page['imageinfo'][0]['url'] = 'https://attacker.example/audio.ogg'
            if location == 'size': page['imageinfo'][0]['size'] = True
            if location == 'revision': page['revisions'][0]['revid'] = True
            if location == 'namespace': page['ns'] = 6.0
            if location == 'timestamp': page['revisions'][0]['timestamp'] = True
            with self.subTest(case=location), self.assertRaises(refs.AssetError):
                refs.validate_metadata('rabbit', page)

    def test_changed_or_truncated_original_is_rejected(self):
        record = refs.validate_metadata('rabbit', example_page())
        for value in (b'Ogg', b'Else', b'OggS-more', 'OggS'):
            with self.subTest(value=value), self.assertRaises(refs.AssetError):
                refs.verify_original(record, value)

    def test_known_wikimedia_host_does_not_permit_a_foreign_file_source(self):
        for key in ('url', 'descriptionurl'):
            page = example_page()
            page['imageinfo'][0][key] = page['imageinfo'][0][key].replace('rabbit', 'foreign')
            with self.subTest(key=key), self.assertRaises(refs.AssetError):
                refs.validate_metadata('rabbit', page)

    def test_explicit_pd_self_is_not_inferred_from_generic_public_domain_metadata(self):
        page = example_page('thumb')
        page['imageinfo'][0]['extmetadata']['LicenseShortName']['value'] = 'Public domain'
        page['imageinfo'][0]['extmetadata'].pop('LicenseUrl')
        page['revisions'][0]['slots']['main']['content'] = '{{Information|source={{own}}|author=Dvortygirl}}{{PD-self}}'
        record = refs.validate_metadata('thumb', page)
        self.assertEqual(record['licenseId'], 'PD-self')
        page['revisions'][0]['slots']['main']['content'] = '{{PD-old}} author=Dvortygirl'
        with self.assertRaises(refs.AssetError): refs.validate_metadata('thumb', page)

    def test_malformed_metadata_container_has_a_fixed_error(self):
        for value in (None, [], True, 'PRIVATE_SOURCE_TEXT'):
            with self.subTest(case=type(value).__name__), self.assertRaises(refs.AssetError):
                refs.validate_metadata('rabbit', value)

    def test_fixed_pack_roster_has_thirteen_source_words_with_no_variant_coverage_claim(self):
        words = refs.pack_words()
        self.assertEqual(len(words), 13)
        self.assertEqual(set(words), set(refs.PLAN))
        self.assertEqual(words['yoyo'], 'yo-yo')
        self.assertEqual(refs.gap_record('rabbit', 'metadata_unavailable')['reason'], 'metadata_unavailable')
        with self.assertRaises(refs.AssetError): refs.gap_record('rabbit', 'PRIVATE_PATH')


if __name__ == '__main__':
    unittest.main()


class WaveAndPrivacyTests(unittest.TestCase):
    def test_malformed_wav_has_fixed_failure_and_pcm_shape_is_measured(self):
        import io
        import wave
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as writer:
            writer.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            writer.writeframes(b'\x00\x00' * 320)
        self.assertEqual(refs.wav_details(stream.getvalue())['durationSeconds'], 0.02)
        for malformed in (b'not a wave', b'', 'RIFF'):
            with self.subTest(case=type(malformed).__name__), self.assertRaises(refs.AssetError):
                refs.wav_details(malformed)

    def test_private_exclusive_writes_do_not_follow_or_replace_existing_files(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            refs._directory(root)
            path = root / 'receipt.json'
            refs._write(path, b'first receipt')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
            with self.assertRaises(FileExistsError): refs._write(path, b'replacement')
            link = root / 'link.json'
            link.symlink_to(path)
            with self.assertRaises(OSError): refs._write(link, b'replacement')
            self.assertEqual(path.read_bytes(), b'first receipt')
            fifo = root / 'fifo'
            os.mkfifo(fifo, 0o600)
            with self.assertRaises(OSError): refs._write(fifo, b'never written')
            with self.assertRaises(refs.AssetError): refs._read(fifo)
            os.link(path, root / 'hardlink.json')
            with self.assertRaises(refs.AssetError): refs._read(path)


class RegistryTests(unittest.TestCase):
    def fixture(self, root):
        import io
        import wave
        for folder in ('source-evidence', 'originals', 'wav', 'receipts'):
            refs._directory(root / folder)
        page = example_page()
        record = refs.validate_metadata('rabbit', page)
        evidence = refs._bytes({'apiRequestUrl': refs.API, 'page': page})
        refs._write(root / 'source-evidence/metadata-response.json', refs._bytes({'query': {'pages': [page]}}))
        refs._write(root / 'source-evidence/rabbit.json', evidence)
        refs._write(root / 'source-evidence/rabbit.html', b'Invented source evidence for isolated tests.')
        refs._write(root / 'originals/rabbit.ogg', b'OggS')
        refs._write(root / 'receipts/ffmpeg-version.txt', b'ffmpeg invented-test-version\n')
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as writer:
            writer.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            writer.writeframes(b'\x00\x00' * 320)
        converted = stream.getvalue()
        refs._write(root / 'wav/rabbit.wav', converted)
        original_sha = hashlib.sha256(b'OggS').hexdigest()
        wav_sha = hashlib.sha256(converted).hexdigest()
        changes = 'Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.'
        receipt = {'schemaVersion': 1, 'sourceWord': 'rabbit',
                   'command': ['/usr/bin/ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', '/dev/fd/3',
                               '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '-f', 'wav', '/dev/fd/4'],
                   'ffmpegVersion': 'ffmpeg invented-test-version', 'originalSha256': original_sha, 'wavSha256': wav_sha,
                   'changes': changes, 'derivativeLicenseId': record['licenseId'],
                   'commandNote': 'Descriptors identify these receipt-bound files; reproduce using originalPath and wavPath.'}
        receipt_raw = refs._bytes(receipt)
        refs._write(root / 'receipts/rabbit.json', receipt_raw)
        record.update(refs.wav_details(converted))
        record.update({'sourceEvidencePath': str(root / 'source-evidence/rabbit.json'), 'sourceEvidenceSha256': hashlib.sha256(evidence).hexdigest(),
                       'sourcePageEvidencePath': str(root / 'source-evidence/rabbit.html'), 'sourcePageEvidenceSha256': hashlib.sha256(b'Invented source evidence for isolated tests.').hexdigest(),
                       'originalPath': str(root / 'originals/rabbit.ogg'), 'originalSha256': original_sha,
                       'wavPath': str(root / 'wav/rabbit.wav'), 'wavSha256': wav_sha, 'changes': changes,
                       'derivativeLicenseId': record['licenseId'],
                       'attribution': f"{refs.PLAN['rabbit']['title']} — {record['author']}; {record['sourcePageUrl']}; {record['licenseUrl']}. {changes}",
                       'conversionReceiptPath': str(root / 'receipts/rabbit.json'), 'conversionReceiptSha256': hashlib.sha256(receipt_raw).hexdigest()})
        return {'schemaVersion': 1, 'sourcePackSha256': refs.PACK_SHA256, 'use': 'local_engineering_reference_assessment',
                'permissionMeaning': 'Recorded per-file public license grants only; no speaker identity, age or participant consent established',
                'clinicalReferenceApproved': False,
                'variantCoverageMeaning': 'One recording per source word; both rabbit/vase dictionary variants retained upstream; no all-variant coverage claim',
                'assets': [record], 'gaps': [refs.gap_record(word, 'original_unavailable') for word in refs.pack_words() if word != 'rabbit']}

    def test_registry_binds_real_fixture_files_and_complete_requirement_keeps_gaps_terminal(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            registry = self.fixture(root)
            with patch.object(refs, 'DEFAULT_OUTPUT', root):
                validated = refs.validate_registry(registry, require_complete=False)
                validated['assets'][0]['permissions']['localInference']['allowed'] = False
                self.assertTrue(registry['assets'][0]['permissions']['localInference']['allowed'])
                with self.assertRaises(refs.AssetError): refs.validate_registry(registry)
                for changes in ({'wavSha256': '0' * 64}, {'wavPath': str(root / 'PRIVATE_FOREIGN')},
                                {'clinicalReferenceApproved': True}, {'speakerAgeKnown': True},
                                {'licenseId': 'CC0-1.0'}, {'permissions': {}}, {'extra': True}):
                    changed = copy.deepcopy(registry)
                    changed['assets'][0].update(changes)
                    with self.subTest(case=next(iter(changes))), self.assertRaises(refs.AssetError):
                        refs.validate_registry(changed, require_complete=False)
                for filename in ('source-evidence/rabbit.json', 'source-evidence/rabbit.html', 'originals/rabbit.ogg',
                                 'wav/rabbit.wav', 'receipts/rabbit.json'):
                    path = root / filename
                    original = path.read_bytes()
                    path.write_bytes(b'altered bytes')
                    with self.subTest(file=filename), self.assertRaises(refs.AssetError):
                        refs.validate_registry(registry, require_complete=False)
                    path.write_bytes(original)

    def test_resume_enforces_retained_cooldown_before_network_or_conversion(self):
        import tempfile
        import time
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            registry = self.fixture(root)
            registry['retryAfterSeconds'] = 600
            registry['retryNotBeforeUnixSeconds'] = int(time.time()) + 600
            refs._write(root / 'assets.json', refs._bytes(registry))
            with patch.object(refs, '_fetch', side_effect=AssertionError('network must remain unused')):
                with self.assertRaises(refs.AssetError) as error:
                    refs.acquire(root, resume=True)
            self.assertEqual(str(error.exception), 'download_cooldown_active')
