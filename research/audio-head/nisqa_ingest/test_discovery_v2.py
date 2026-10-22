import tempfile
import json
import unittest
from unittest.mock import patch
from pathlib import Path

from nisqa_ingest import discovery_v2 as d


def member(name, size=100):
    return dict(filename=name, file_size=size, compress_size=size, is_dir=False)


class DiscoveryTests(unittest.TestCase):
    def test_new_version_cannot_discard_previous_body_spending(self):
        import shutil
        names = ('plan.json', 'directory-started.json', 'directory-failure.json',
                 'transport/transport-state.json', 'transport/request-journal.jsonl')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in names:
                target = root/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(d.PREVIOUS/name, target)
            path = root/'transport/transport-state.json'
            state = json.loads(path.read_text())
            state['bytesRead'] = 1
            path.write_text(json.dumps(state))
            with patch.object(d, 'PREVIOUS', root):
                with self.assertRaisesRegex(ValueError, 'spending cannot be reset'):
                    d.declaration()

    def test_metadata_allowlist_excludes_every_audio_and_evaluation_table(self):
        names = ['NISQA_Corpus/NISQA_corpus_file.csv',
                 'NISQA_Corpus/readme.txt', 'NISQA_Corpus/NISQA_TRAIN_LIVE/readme.txt',
                 'NISQA_Corpus/NISQA_TRAIN_LIVE/per_file.csv',
                 'NISQA_Corpus/NISQA_VAL_LIVE/per_file.csv',
                 'NISQA_Corpus/NISQA_TRAIN_LIVE/deg/audio.wav',
                 'NISQA_Corpus/NISQA_TEST_FOR/readme.txt']
        result = d.metadata_requests([member(n) for n in names])
        self.assertEqual({r['filename'] for r in result}, set(names[:4]))

    def test_missing_or_oversized_metadata_fails_without_replacement(self):
        with self.assertRaises(ValueError):
            d.metadata_requests([member('NISQA_Corpus/fake_file.csv')])
        with self.assertRaises(ValueError):
            d.metadata_requests([member('NISQA_Corpus/NISQA_corpus_file.csv', 9*1024*1024),
                                 member('NISQA_Corpus/NISQA_TRAIN_LIVE/readme.txt')])

    def test_artifact_tamper_and_partial_restart_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            d.write(root/'file.json', {'test': True})
            pin = d.binding(root/'file.json')
            (root/'file.json').write_text('{}')
            with self.assertRaises(ValueError):
                d.read(pin)
            d.fresh(root, 'metadata')
            with self.assertRaises(ValueError):
                d.fresh(root, 'metadata')

    def test_review_must_bind_exact_plan_and_be_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'review.json'
            d.write(path, dict(planSha256='correct', verdict='clear', blockingFindings=[],
                               independent=True, reviewer='independent reviewer'))
            d.checked_review(path, 'correct')
            with self.assertRaises(ValueError):
                d.checked_review(path, 'other')

    def test_metadata_identity_never_emits_combined_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'combined.csv'
            path.write_text('db,filepath_deg,mos,noi,dis,col,loud\n'
                            'NISQA_TRAIN_LIVE,NISQA_TRAIN_LIVE/deg/train.wav,TRAIN_SENTINEL,x,x,x,x\n'
                            'NISQA_VAL_LIVE,NISQA_VAL_LIVE/deg/val.wav,HELDOUT_SENTINEL,x,x,x,x\n')
            records = [dict(role='metadata', filename='NISQA_Corpus/NISQA_corpus_file.csv',
                            acquired=d.binding(path))]
            value = d.metadata_identity(records)
            self.assertNotIn('SENTINEL', json.dumps(value))
            self.assertEqual(len(value['identities']['training']), 1)
            self.assertFalse(value['readinessForAudioAcquisition'])

    def test_ledger_drift_rejected_against_immutable_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'transport').mkdir()
            frozen = {}
            for name, live_name in (('state', 'transport-state.json'), ('journal', 'request-journal.jsonl')):
                snapshot = root/(name+'.snapshot')
                snapshot.write_text('{}')
                (root/'transport'/live_name).write_text('{}')
                frozen[name] = d.binding(snapshot)
            d.check_ledger(root, frozen)
            (root/'transport/transport-state.json').write_text('{"bytesRead":0}')
            with self.assertRaises(ValueError):
                d.check_ledger(root, frozen)

    def test_synthetic_http_pipeline_freezes_stages_and_keeps_targets_opaque(self):
        from nisqa_ingest.remote_zip import OFFICIAL_URL, RemoteZip
        from nisqa_ingest.test_remote_zip import HTTP, archive
        csv_bytes = (b'db,filepath_deg,mos,noi,dis,col,loud\n'
                     b'NISQA_TRAIN_LIVE,NISQA_TRAIN_LIVE/deg/train.wav,TRAIN_SENTINEL,x,x,x,x\n'
                     b'NISQA_VAL_LIVE,NISQA_VAL_LIVE/deg/val.wav,HELDOUT_SENTINEL,x,x,x,x\n')
        source = archive([('NISQA_Corpus/readme.txt', b'fixture notice'),
                          ('NISQA_Corpus/NISQA_TRAIN_LIVE/readme.txt', b'fixture subset notice'),
                          ('NISQA_Corpus/NISQA_corpus_file.csv', csv_bytes),
                          ('NISQA_Corpus/NISQA_VAL_LIVE/deg/val.wav', b'not an acquired member')])
        http = HTTP(source)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol = root/'protocol.md'; protocol.write_text('synthetic protocol')
            plan = dict(archive=d.ARCHIVE, sources={}, documents={}, protocol=d.binding(protocol),
                        metadataTransferLimit=d.LIMIT, pilotTransferLimit=256*1024*1024,
                        metadataMemberMaxBytes=d.MEMBER_LIMIT, allowedHosts=['zenodo.org'])
            d.write(root/'plan.json', plan); pin = d.binding(root/'plan.json')
            review = root/'review.json'
            d.write(review, dict(planSha256=pin['sha256'], verdict='clear', blockingFindings=[],
                                  independent=True, reviewer='synthetic review fixture'))
            def factory(output, _plan):
                return RemoteZip(OFFICIAL_URL, len(source), output/'transport',
                                 session=http, sleep=lambda _: None)
            with patch.object(d, 'load', return_value=(plan, pin)), patch.object(d, 'PROTOCOL', protocol), \
                    patch.object(d, 'transport', side_effect=factory):
                directory_pin = d.directory(pin['path'], pin['sha256'], review)
                requested = d.declare_metadata(pin['path'], pin['sha256'], directory_pin['sha256'])
                metadata_pin = d.metadata(pin['path'], pin['sha256'], requested['sha256'])
                result_pin = d.identity_inventory(pin['path'], pin['sha256'], metadata_pin['sha256'])
            value = d.read(d.read(result_pin)['inventory'])
            self.assertEqual(len(value['identities']['training']), 1)
            for path in root.rglob('*.json'):
                self.assertNotIn('SENTINEL', path.read_text())
            # Directory accounting remains verifiable after the live ledger advances.
            for snapshot in d.read(directory_pin)['transport'].values():
                if isinstance(snapshot, dict) and 'path' in snapshot and 'sha256' in snapshot:
                    d.binding(snapshot['path'], snapshot['sha256'])
            records = d.read(d.read(metadata_pin)['records'])
            self.assertTrue(all(not r['filename'].endswith('.wav') for r in records))


if __name__ == '__main__':
    unittest.main()
