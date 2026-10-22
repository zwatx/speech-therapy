"""Synthetic complete selected import, partial failures and ledger preservation."""
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from nisqa_ingest import selected_pilot as p
from nisqa_ingest.discovery import binding, read, transport_snapshot, write
from nisqa_ingest.http_transport_v2 import RemoteZipV2
from nisqa_ingest.remote_zip import OFFICIAL_URL
from nisqa_ingest.test_remote_zip import HTTP, archive


def wav():
    payload = struct.pack('<hhh', -16384, 0, 16384)
    fmt = struct.pack('<HHIIHH', 1, 1, 16000, 32000, 2, 16)
    body = b'WAVEfmt '+struct.pack('<I', len(fmt))+fmt+b'data'+struct.pack('<I', len(payload))+payload
    return b'RIFF'+struct.pack('<I', len(body))+body


class PilotTests(unittest.TestCase):
    def fixture(self, root, *, token='3', bad_audio=False):
        prior = root/'discovery'; prior.mkdir()
        output = root/'pilot'; output.mkdir()
        selected = [dict(path=f'NISQA_TRAIN_LIVE/deg/train-{i:02d}.wav',
            archiveMember=f'NISQA_Corpus/NISQA_TRAIN_LIVE/deg/train-{i:02d}.wav',
            identitySha256=f'{i:064x}') for i in range(20)]
        names = [r['archiveMember'] for r in selected]
        source = archive([(name, b'invalid WAV' if bad_audio and i == 3 else wav())
                          for i, name in enumerate(names)] +
                         [('NISQA_Corpus/NISQA_VAL_LIVE/deg/eval.wav', b'EVALUATION_AUDIO_SENTINEL')])
        http = HTTP(source)
        remote = RemoteZipV2(OFFICIAL_URL, len(source), prior/'transport', session=http)
        remote.bootstrap(); members = remote.members()
        (prior/'snapshot').mkdir()
        previous = transport_snapshot(remote, prior/'snapshot'); remote.close()
        write(prior/'members.json', members)
        rows = ['db,filepath_deg,mos,noi,dis,col,loud']
        rows += [f'NISQA_TRAIN_LIVE,{r["path"]},{token},3,3,3,3' for r in selected]
        rows += ['NISQA_VAL_LIVE,NISQA_VAL_LIVE/deg/eval.wav,EVAL_TARGET_SENTINEL',
                 'NISQA_TRAIN_LIVE,NISQA_TRAIN_LIVE/deg/unselected.wav,TRAIN_TARGET_SENTINEL']
        (prior/'combined.csv').write_text('\n'.join(rows)+'\n')
        plan = dict(selected=selected, requests=p.audio_requests(selected, members),
            inputs=dict(members=binding(prior/'members.json'), combinedCSV=binding(prior/'combined.csv')),
            archive=dict(url=OFFICIAL_URL, size=len(source)), discoveryRoot=str(prior), previousTransport=previous)
        write(output/'plan.json', plan); pin = binding(output/'plan.json')
        review = output/'review.json'
        write(review, dict(planSha256=pin['sha256'], verdict='clear', blockingFindings=[],
                           independent=True, reviewer='synthetic fixture only'))
        def factory(_plan):
            return RemoteZipV2(OFFICIAL_URL, len(source), prior/'transport', session=http)
        return output, plan, pin, review, factory

    def test_actual_sparse_transport_exact_twenty_targets_audio_waveforms(self):
        with tempfile.TemporaryDirectory() as directory:
            root, plan, pin, review, factory = self.fixture(Path(directory))
            calls = []
            original = RemoteZipV2.acquire
            def acquire(remote, name, **kwargs):
                calls.append((name, kwargs['metadata']))
                return original(remote, name, **kwargs)
            with patch.object(p, 'load', return_value=(plan, pin)), patch.object(p, 'transport', side_effect=factory), \
                    patch.object(RemoteZipV2, 'acquire', acquire):
                target = read(p.targets(pin['path'], pin['sha256'], review))
                audio_pin = p.audio(pin['path'], pin['sha256'], review)
                audit = read(p.waveforms(pin['path'], pin['sha256'], review, audio_pin['sha256']))
            self.assertTrue(target['completeTargets'])
            self.assertEqual(calls, [(r['member'], False) for r in plan['requests']])
            self.assertEqual(audit['decodedCount'], 20)
            self.assertTrue(audit['allSelectedDecoded'])
            self.assertGreater(read(audio_pin)['transport']['bytesRead'], plan['previousTransport']['bytesRead'])
            for path in root.rglob('*.json'):
                self.assertNotIn('SENTINEL', path.read_text())
            self.assertEqual(len(list((root/'audio').glob('record-*.json'))), 20)

    def test_bad_target_preserved_audio_still_imports_no_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root, plan, pin, review, factory = self.fixture(Path(directory), token='5.0001')
            with patch.object(p, 'load', return_value=(plan, pin)), patch.object(p, 'transport', side_effect=factory):
                with self.assertRaises(ValueError):
                    p.targets(pin['path'], pin['sha256'], review)
                self.assertTrue(read(binding(root/'targets-failure.json'))['samplePreserved'])
                with self.assertRaisesRegex(ValueError, 'no implicit restart'):
                    p.targets(pin['path'], pin['sha256'], review)
                self.assertEqual(read(p.audio(pin['path'], pin['sha256'], review))['selectedCount'], 20)

    def test_missing_targets_and_decode_failure_are_honest_preserved_items(self):
        with tempfile.TemporaryDirectory() as directory:
            root, plan, pin, review, factory = self.fixture(Path(directory), token='NaN', bad_audio=True)
            with patch.object(p, 'load', return_value=(plan, pin)), patch.object(p, 'transport', side_effect=factory):
                target = read(p.targets(pin['path'], pin['sha256'], review))
                audio_pin = p.audio(pin['path'], pin['sha256'], review)
                audited = read(p.waveforms(pin['path'], pin['sha256'], review, audio_pin['sha256']))
            self.assertFalse(target['completeTargets'])
            self.assertEqual(read(target['targets'])['missingCounts']['mos'], 20)
            self.assertEqual(audited['decodedCount'], 19)
            self.assertFalse(audited['allSelectedDecoded'])
            self.assertEqual(len(read(audited['audits'])), 20)

    def test_mid_acquisition_failure_keeps_first_record_and_spending(self):
        with tempfile.TemporaryDirectory() as directory:
            root, plan, pin, review, factory = self.fixture(Path(directory))
            original = RemoteZipV2.acquire
            def acquire(remote, name, **kwargs):
                if name == plan['requests'][1]['member']:
                    raise ValueError('synthetic failure')
                return original(remote, name, **kwargs)
            with patch.object(p, 'load', return_value=(plan, pin)), patch.object(p, 'transport', side_effect=factory), \
                    patch.object(RemoteZipV2, 'acquire', acquire):
                with self.assertRaises(ValueError):
                    p.audio(pin['path'], pin['sha256'], review)
                with self.assertRaisesRegex(ValueError, 'no implicit restart'):
                    p.audio(pin['path'], pin['sha256'], review)
            failed = read(binding(root/'audio-failure.json'))
            self.assertEqual(failed['completedCount'], 1)
            self.assertTrue((root/'audio/record-00.json').exists())
            self.assertGreater(failed['transport']['bytesRead'], plan['previousTransport']['bytesRead'])
            self.assertFalse((root/'audio-freeze.json').exists())

    def test_ledger_drift_rejects_before_audio_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root, plan, pin, review, factory = self.fixture(Path(directory))
            state_path = Path(plan['discoveryRoot'])/'transport/transport-state.json'
            state = json.loads(state_path.read_text()); state['bytesRead'] += 1
            state_path.write_text(json.dumps(state))
            with patch.object(p, 'load', return_value=(plan, pin)), patch.object(p, 'transport') as remote:
                with self.assertRaises(ValueError):
                    p.audio(pin['path'], pin['sha256'], review)
                remote.assert_not_called()

    def test_member_selection_join_and_size_fail_without_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            _, plan, _, _, _ = self.fixture(Path(directory))
            selected = plan['selected']; members = read(plan['inputs']['members'])
            with self.assertRaises(ValueError):
                p.audio_requests(selected[:19], members)
            changed = [dict(r) for r in selected]
            changed[0]['archiveMember'] = changed[1]['archiveMember']
            with self.assertRaises(ValueError):
                p.audio_requests(changed, members)
            changed = [dict(r) for r in members]
            changed[0]['file_size'] = 129*1024*1024
            with self.assertRaises(ValueError):
                p.audio_requests(selected, changed)


if __name__ == '__main__':
    unittest.main()
