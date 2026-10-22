"""Synthetic recovery with real bounded transport; no corpus access."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nisqa_ingest import selected_recovery as r
from nisqa_ingest import selected_pilot as p
from nisqa_ingest.discovery import binding, read, write, transport_snapshot
from nisqa_ingest.http_transport_v2 import RemoteZipV2
from nisqa_ingest.frozen_directory_transport import FrozenDirectoryZip
from nisqa_ingest.remote_zip import OFFICIAL_URL
from nisqa_ingest.test_remote_zip import HTTP, archive
from nisqa_ingest.test_selected_pilot import wav


class RecoveryTests(unittest.TestCase):
    def fixture(self, parent, *, bad_audio=False, incomplete=False):
        prior = parent/'discovery'; prior.mkdir()
        output = parent/'recovery'; output.mkdir()
        selected = [dict(path=f'NISQA_TRAIN_LIVE/deg/{i}.wav',
            archiveMember=f'NISQA_Corpus/NISQA_TRAIN_LIVE/deg/{i}.wav', identitySha256=f'{i:064x}')
            for i in range(20)]
        body = archive([(row['archiveMember'], b'invalid' if bad_audio and i == 13 else wav())
                        for i,row in enumerate(selected)])
        http = HTTP(body)
        old = RemoteZipV2(OFFICIAL_URL,len(body),prior/'transport',session=http)
        old.bootstrap(); members = old.members()
        requests = p.audio_requests(selected,members)
        prefix = []
        allowed = [row['archiveMember'] for row in selected]
        for i, request in enumerate(requests[:8]):
            acquired = old.acquire(request['member'],allowlist=allowed,
                output_name=f'selected-audio-{i:02d}.wav',metadata=False)
            prefix.append(dict(path=request['path'],identitySha256=request['identitySha256'],acquired=acquired))
        (prior/'snapshot').mkdir()
        previous = transport_snapshot(old,prior/'snapshot'); old.close()
        partial = prior/'transport/selected-audio-08.wav.partial'; partial.write_bytes(b'preserved partial')
        write(prior/'members.json',members)
        targets = dict(trainingOnly=True,selectedPaths=[row['path'] for row in selected],completeTargets=not incomplete,
            rows=[dict(db='NISQA_TRAIN_LIVE',path=row['path'],quality=dict.fromkeys(('mos','noi','dis','col','loud'),3),
                       declaredMissing={}) for row in selected])
        write(prior/'targets.json',targets)
        plan = dict(prefixRecords=prefix,requests=requests,selected=selected,
            archive=dict(url=OFFICIAL_URL,size=len(body)),members=binding(prior/'members.json'),
            targets=binding(prior/'targets.json'),targetsFreeze=binding(prior/'targets.json'),
            discoveryRoot=str(prior),previousTransport=previous,failedPartial=binding(partial),
            outputNames=[f'resume-audio-{i:02d}.wav' for i in range(8,20)])
        write(output/'plan.json',plan); pin=binding(output/'plan.json')
        review=output/'review.json'
        write(review,dict(planSha256=pin['sha256'],verdict='clear',blockingFindings=[],independent=True,reviewer='synthetic'))
        now=[0.]
        def sleep(seconds): now[0]+=seconds
        def factory(plan):
            return FrozenDirectoryZip(OFFICIAL_URL,len(body),prior/'transport',frozen_members=members,
                selected_names=allowed,session=http,clock=lambda: now[0],sleep=sleep)
        return output,plan,pin,review,factory,http

    def execute(self, fixture):
        output,plan,pin,review,factory,_=fixture
        with patch.object(r,'load',return_value=(plan,pin)),patch.object(r,'transport',side_effect=factory):
            return read(r.run(pin['path'],pin['sha256'],review))

    def test_eight_retained_twelve_new_and_budget_prefix_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture=self.fixture(Path(directory)); output,plan,_,_,_,http=fixture
            before=len(http.requests); prefix=Path(plan['previousTransport']['journal']['path']).read_bytes()
            result=self.execute(fixture)
            acquired=read(binding(output/'acquisition-freeze.json'))
            records=read(acquired['records'])
            self.assertEqual(records[:8],plan['prefixRecords'])
            self.assertEqual([Path(v['acquired']['path']).name for v in records[8:]],plan['outputNames'])
            self.assertEqual(len(records),20)
            self.assertTrue(result['ingestionReady']); self.assertEqual(result['decodedCount'],20)
            self.assertGreater(acquired['transport']['bytesRead'],plan['previousTransport']['bytesRead'])
            self.assertGreater(acquired['transport']['metadataRead'],plan['previousTransport']['metadataRead'])
            self.assertTrue(Path(acquired['transport']['journal']['path']).read_bytes().startswith(prefix))
            self.assertEqual(Path(plan['failedPartial']['path']).read_bytes(),b'preserved partial')
            self.assertTrue(http.requests[before:])
            calls=http.requests[before:]
            self.assertEqual([v[0] for v in calls], ['HEAD']+['GET']*36)
            self.assertEqual(len(list((output/'acquisition').glob('record-*.json'))),20)

    def test_failure_preserves_records_and_no_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture=self.fixture(Path(directory)); output,plan,pin,review,factory,_=fixture
            original=FrozenDirectoryZip.acquire
            def fail(remote,name,**kwargs):
                if name==plan['requests'][9]['member']: raise ValueError('synthetic private detail')
                return original(remote,name,**kwargs)
            with patch.object(r,'load',return_value=(plan,pin)),patch.object(r,'transport',side_effect=factory), \
                    patch.object(FrozenDirectoryZip,'acquire',fail):
                with self.assertRaises(ValueError): r.run(pin['path'],pin['sha256'],review)
                with self.assertRaisesRegex(ValueError,'no implicit restart'): r.run(pin['path'],pin['sha256'],review)
            failed=read(binding(output/'acquisition-failure.json'))
            self.assertEqual(failed['completedCount'],9)
            self.assertTrue((output/'acquisition/record-08.json').exists())
            self.assertNotIn('private detail',json.dumps(failed))
            self.assertFalse((output/'acquisition-freeze.json').exists())
            self.assertGreater(failed['transport']['bytesRead'],plan['previousTransport']['bytesRead'])
            self.assertGreater(failed['transport']['metadataRead'],plan['previousTransport']['metadataRead'])
            self.assertEqual(Path(plan['failedPartial']['path']).read_bytes(),b'preserved partial')

    def test_existing_new_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture=self.fixture(Path(directory)); _,plan,_,_,_,_=fixture
            existing=Path(plan['discoveryRoot'])/'transport/resume-audio-08.wav'; existing.write_bytes(b'keep')
            with self.assertRaises(Exception): self.execute(fixture)
            self.assertEqual(existing.read_bytes(),b'keep')

    def test_decode_and_target_incompleteness_do_not_claim_ready(self):
        for bad_audio,incomplete,count in [(True,False,19),(False,True,20)]:
            with self.subTest(bad_audio=bad_audio),tempfile.TemporaryDirectory() as directory:
                fixture=self.fixture(Path(directory),bad_audio=bad_audio,incomplete=incomplete)
                result=self.execute(fixture)
                self.assertEqual(result['decodedCount'],count); self.assertFalse(result['ingestionReady'])
                audits=read(result['audits']); self.assertEqual(len(audits),20)
                if bad_audio: self.assertEqual(audits[13]['reason'],'Selected waveform audit failed')

    def test_ledger_and_prefix_file_tamper_fail(self):
        for kind in ('ledger','prefix'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                fixture=self.fixture(Path(directory)); output,plan,pin,review,factory,_=fixture
                if kind=='ledger':
                    state=Path(plan['discoveryRoot'])/'transport/transport-state.json'
                    state.write_bytes(state.read_bytes()+b' ')
                else: Path(plan['prefixRecords'][0]['acquired']['path']).write_bytes(b'tampered')
                with self.assertRaises(ValueError): self.execute(fixture)
                self.assertFalse((output/'acquisition-freeze.json').exists())

    def test_target_join_tamper_keeps_acquisition_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture=self.fixture(Path(directory)); output,plan,_,_,_,_=fixture
            target=Path(plan['targets']['path']); value=json.loads(target.read_text())
            value['selectedPaths'][0]='NISQA_TRAIN_LIVE/deg/other.wav'
            target.write_text(json.dumps(value)); plan['targets']=binding(target)
            with self.assertRaisesRegex(ValueError,'target joins'): self.execute(fixture)
            self.assertTrue((output/'acquisition-freeze.json').exists())
            self.assertTrue((output/'audit-failure.json').exists())
            self.assertFalse((output/'audit-freeze.json').exists())


if __name__=='__main__': unittest.main()
