"""Synthetic staged ingestion with real paced transport and immutable freezes."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nisqa_ingest.discovery import binding,read,write,transport_snapshot
from nisqa_ingest.http_transport_v2 import RemoteZipV2
from nisqa_ingest.remote_zip import OFFICIAL_URL
from nisqa_ingest.test_remote_zip import HTTP,archive
from nisqa_ingest.test_selected_pilot import wav
from nisqa_quality import ingestion as d,selection as s
from nisqa_quality.transport import QualityDirectoryZip
from nisqa_quality.test_selection import raw,prepare,pilot


class IngestionTests(unittest.TestCase):
    def fixture(self,parent,*,bad_audio=False):
        prior=parent/'discovery'; prior.mkdir()
        root=parent/'study'; root.mkdir()
        values=[raw(i,i) for i in range(20)]
        values.extend(raw(i,i,c) for i in range(20,520) for c in ('phone','Skype'))
        eligible=prepare(values); inspected=pilot(eligible)
        chosen=s.select_study(s.build_components(eligible,inspected))['selected']
        bad_path=chosen[0]['path'] if bad_audio else None
        body=archive([(r['archiveMember'],b'bad' if r['path']==bad_path else wav()) for r in eligible]+
                     [('NISQA_Corpus/NISQA_VAL_LIVE/deg/never.wav',b'EVAL_AUDIO_SENTINEL')])
        http=HTTP(body)
        remote=RemoteZipV2(OFFICIAL_URL,len(body),prior/'transport',session=http)
        remote.bootstrap(); members=remote.members()
        # A preserved old-20 binding must survive the new transport.
        remote.state['frozenDirectoryBinding']={'policy':'fixture old twenty'}; remote._persist()
        (prior/'snapshot').mkdir(); previous=transport_snapshot(remote,prior/'snapshot'); remote.close()
        # RemoteZipV2 has no subclass manifest field; the completed recovery
        # transport publishes this inherited binding alongside its snapshot.
        previous['frozenDirectoryBinding']={'policy':'fixture old twenty'}
        write(prior/'members.json',members)
        write(prior/'lineage.json',dict(training=values,columns=list(d.source_code_selection.FIELDS),
              **d.source_code_selection.INVENTORY_FLAGS))
        write(prior/'pilot.json',dict(selected=inspected))
        chosen_by={r['path']:r for r in chosen}
        with (prior/'combined.csv').open('w',newline='') as stream:
            writer=csv.writer(stream); writer.writerow(['db','filepath_deg','mos','noi','dis','col','loud'])
            for r in eligible:
                choice=chosen_by.get(r['path'])
                token='3' if choice and choice['partition']!='confirmation' else 'FORBIDDEN_SENTINEL,\nNaN'
                writer.writerow(['NISQA_TRAIN_LIVE',r['path'],*[token]*5])
            writer.writerow(['NISQA_VAL_LIVE','NISQA_VAL_LIVE/deg/never.wav','EVAL_TARGET_SENTINEL'])
        plan=dict(inputs={name:binding(prior/file) for name,file in
            [('lineageInventory','lineage.json'),('pilotSelected','pilot.json'),('members','members.json'),('combinedCSV','combined.csv')]},
            archive=dict(url=OFFICIAL_URL,size=len(body)),previousTransport=previous,discoveryRoot=str(prior))
        write(root/'plan.json',plan); pin=binding(root/'plan.json')
        review=root/'review.json'
        write(review,dict(planSha256=pin['sha256'],verdict='clear',blockingFindings=[],independent=True,reviewer='synthetic'))
        now=[0.]
        def sleep(seconds): now[0]+=seconds
        def factory(plan,sha,selected):
            return QualityDirectoryZip(OFFICIAL_URL,len(body),prior/'transport',frozen_members=members,
                selected_names=[r['archiveMember'] for r in selected],study_sha256=sha,session=http,
                clock=lambda:now[0],sleep=sleep)
        return root,plan,pin,review,factory,http

    def test_full_200_workflow_confirmation_stays_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root,plan,pin,review,factory,http=self.fixture(Path(directory))
            with patch.object(d,'load',return_value=(plan,pin)),patch.object(d,'transport',side_effect=factory):
                selected=d.selection(pin['path'],pin['sha256'],review)
                targets=read(d.targets(pin['path'],pin['sha256'],review,selected['sha256']))
                before=len(http.requests)
                audio=d.audio(pin['path'],pin['sha256'],review,selected['sha256'])
                audited=read(d.waveforms(pin['path'],pin['sha256'],review,selected['sha256'],audio['sha256']))
            self.assertTrue(targets['completeTargets']); self.assertEqual(targets['selectedCount'],160)
            self.assertFalse(targets['confirmationTargetsAccessed'])
            self.assertTrue(targets['numericTargetsAccessed'] and targets['qualityTargetsInterpreted'])
            self.assertEqual(audited['decodedCount'],200); self.assertTrue(audited['allSelectedDecoded'])
            self.assertEqual([r[0] for r in http.requests[before:]],['HEAD']+['GET']*600)
            acquired=read(audio)
            self.assertTrue(acquired['waveformAcquired'] and audited['waveformAcquired'])
            self.assertGreater(acquired['transport']['bytesRead'],plan['previousTransport']['bytesRead'])
            self.assertGreater(acquired['transport']['metadataRead'],plan['previousTransport']['metadataRead'])
            state=json.loads((Path(plan['discoveryRoot'])/'transport/transport-state.json').read_text())
            self.assertEqual(state['frozenDirectoryBinding'],{'policy':'fixture old twenty'})
            for artifact in root.rglob('*.json'): self.assertNotIn('SENTINEL',artifact.read_text())

    def test_429_terminal_preserves_records_partial_ledger_no_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root,plan,pin,review,factory,http=self.fixture(Path(directory))
            with patch.object(d,'load',return_value=(plan,pin)),patch.object(d,'transport',side_effect=factory):
                selected=d.selection(pin['path'],pin['sha256'],review)
                count=[0]
                def alter(response,start,end):
                    count[0]+=1
                    if count[0]==6: response.status_code=429
                http.alter=alter
                with self.assertRaises(Exception): d.audio(pin['path'],pin['sha256'],review,selected['sha256'])
                with self.assertRaisesRegex(ValueError,'no implicit restart'):
                    d.audio(pin['path'],pin['sha256'],review,selected['sha256'])
            failed=read(binding(root/'audio-failure.json'))
            self.assertEqual(failed['completedCount'],1); self.assertEqual(count[0],6)
            self.assertTrue((root/'audio/record-000.json').exists())
            self.assertTrue((Path(plan['discoveryRoot'])/'transport/quality-audio-001.wav.partial').exists())
            self.assertGreater(failed['transport']['bytesRead'],plan['previousTransport']['bytesRead'])
            self.assertFalse((root/'audio-freeze.json').exists())

    def test_budget_failure_before_targets_and_selection_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root,plan,pin,review,factory,http=self.fixture(Path(directory))
            with patch.object(d,'load',return_value=(plan,pin)):
                selected=d.selection(pin['path'],pin['sha256'],review)
                frozen=read(selected); path=Path(frozen['budget']['path']); path.write_text('{}')
                with self.assertRaises(ValueError): d.targets(pin['path'],pin['sha256'],review,selected['sha256'])
                self.assertFalse((root/'fit-selection-targets-freeze.json').exists())
            _,value=d._choices(plan)
            previous=dict(plan['previousTransport'],metadataRead=plan['previousTransport']['settings']['metadataBytes'])
            with self.assertRaisesRegex(ValueError,'budgets'):
                d.requests_for(value['selected'],read(plan['inputs']['members']),previous)

    def test_live_ledger_drift_rejected_before_network_and_no_overwrite(self):
        for kind in ('ledger','output'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root,plan,pin,review,factory,http=self.fixture(Path(directory))
                with patch.object(d,'load',return_value=(plan,pin)):
                    selected=d.selection(pin['path'],pin['sha256'],review)
                    folder=Path(plan['discoveryRoot'])/'transport'
                    if kind=='ledger':
                        file=folder/'transport-state.json'; file.write_bytes(file.read_bytes()+b' ')
                    else: (folder/'quality-audio-000.wav').write_bytes(b'keep')
                    with patch.object(d,'transport') as remote:
                        with self.assertRaises(ValueError): d.audio(pin['path'],pin['sha256'],review,selected['sha256'])
                        remote.assert_not_called()
                    if kind=='output': self.assertEqual((folder/'quality-audio-000.wav').read_bytes(),b'keep')

    def test_decode_failure_is_per_item_not_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root,plan,pin,review,factory,http=self.fixture(Path(directory),bad_audio=True)
            with patch.object(d,'load',return_value=(plan,pin)),patch.object(d,'transport',side_effect=factory):
                selected=d.selection(pin['path'],pin['sha256'],review)
                audio=d.audio(pin['path'],pin['sha256'],review,selected['sha256'])
                result=read(d.waveforms(pin['path'],pin['sha256'],review,selected['sha256'],audio['sha256']))
            self.assertEqual(result['decodedCount'],199); self.assertFalse(result['allSelectedDecoded'])
            audits=read(result['audits']); self.assertEqual(len(audits),200)
            self.assertEqual(audits[0]['reason'],'Selected waveform audit failed')

    def test_load_static_guards_do_not_bind_mutable_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root,plan,pin,review,factory,http=self.fixture(Path(directory))
            with patch.object(d,'HERE',Path(directory).resolve()),patch.object(d,'declaration',return_value=plan):
                output=Path(directory)/'outputs'; output.mkdir()
                file=output/'plan.json'; write(file,plan); frozen=binding(file)
                ledger=Path(plan['discoveryRoot'])/'transport/transport-state.json'; ledger.write_text('mutated')
                self.assertEqual(d.load(file,frozen['sha256'])[0],plan)
                with patch.object(d,'declaration',return_value=dict(plan,changed=True)):
                    with self.assertRaises(ValueError): d.load(file,frozen['sha256'])


if __name__=='__main__': unittest.main()
