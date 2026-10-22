"""Synthetic selection, integrity, once-only failure, and offline lineage checks."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import selection as s
from . import study as worker

raw = worker.raw


def rows():
    return [dict(filename=f'2-{1000+ci*10+i}-A-{ci}.wav', src_file=str(1000+ci*10+i),
                 take='A', fold='2', category=c, target=str(ci), esc10='False')
            for ci, c in enumerate(s.CATEGORIES) for i in range(6)]


class SelectionTests(unittest.TestCase):
    def test_fixed_order_sha_rank_and_lexicographic_take(self):
        candidates = rows()
        duplicate = {**candidates[0], 'take': 'B', 'filename': candidates[0]['filename'].replace('-A-', '-B-')}
        selected = s.select_rows(list(reversed(candidates))+[duplicate], set())
        expected = []
        for c in s.CATEGORIES:
            group = [r for r in candidates if r['category'] == c]
            expected.extend(sorted(group, key=lambda r: (hashlib.sha256(
                ('nonspeech-v1|'+r['src_file']).encode()).hexdigest(), r['src_file']))[:4])
        self.assertEqual(selected, expected)
        self.assertEqual(len({r['src_file'] for r in selected}), 60)

    def test_source_spanning_categories_skipped(self):
        candidates = rows()
        shared = s.select_rows(candidates, set())[0]['src_file']
        candidates[6]['src_file'] = shared
        result = s.select_rows(candidates, set())
        self.assertEqual(sum(r['src_file'] == shared for r in result), 1)

    def test_all_takes_of_excluded_source_removed_and_fold1_4_ignored(self):
        candidates = rows()
        excluded = candidates[0]['src_file']
        candidates.extend([{**candidates[0], 'take': 'B', 'filename': '2-1000-B-0.wav'},
                           {**candidates[0], 'src_file': 'extra', 'fold': '4', 'filename': '4-9999-A-0.wav'}])
        selected = s.select_rows(candidates, {excluded})
        self.assertNotIn(excluded, {r['src_file'] for r in selected})
        self.assertNotIn('extra', {r['src_file'] for r in selected})

    def test_shortfall_stops_no_substitution(self):
        candidates = [r for r in rows() if r['category'] != 'dog']
        with self.assertRaisesRegex(ValueError, 'Insufficient'):
            s.select_rows(candidates, set())

    def test_duplicate_metadata_and_ambiguous_take_stop(self):
        candidates = rows()
        with self.assertRaises(ValueError):
            s.select_rows(candidates+[candidates[0]], set())
        duplicate = {**candidates[0], 'filename': '2-9000-A-0.wav'}
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            s.select_rows(candidates+[duplicate], set())

    def test_recursive_history_exact_union_and_master_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            historical = rows()[:60]
            prior = {}
            for i in range(3):
                path = root/f'{i}/selection.json'
                path.parent.mkdir()
                raw.write_json(path, dict(commit=s.COMMIT, rows=historical[i*20:(i+1)*20]))
                prior[str(path.relative_to(root))] = raw.digest(path)
            extra = rows()[61]['filename']
            (root/'esc50.csv').write_text(extra)
            nested = root/'nested/deep'
            nested.mkdir(parents=True)
            # Filename crosses the read-chunk boundary.
            (nested/'record.txt').write_text('x'*(1024*1024-5)+' '+historical[0]['filename']+' ')
            audit, _ = s.scan_historical(root, rows(), prior)
            self.assertEqual(len(audit['filenames']), 60)
            (nested/'surprise.json').write_text(json.dumps(dict(name=extra)))
            with self.assertRaisesRegex(ValueError, 'Recursive historical scan'):
                s.scan_historical(root, rows(), prior)

    def test_history_union_must_be_sixty(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'exactly 60'):
                s.scan_historical(tmp, rows(), {})

    def test_attribution_metadata_and_no_missing_license(self):
        row = rows()[0]
        text = '- [2-1000-A.ogg]: clip derived from sample.wav (http://www.freesound.org/people/person/sounds/1000/) by person [CC0]'
        item = s.attribution(row, text)
        self.assertEqual(item['creator'], 'person')
        self.assertEqual(item['datasetLicense'], 'CC BY-NC 3.0')
        self.assertEqual(s.attribution({**row, 'esc10': 'True'}, text)['datasetLicense'], 'CC BY 3.0')
        with self.assertRaises(ValueError):
            s.attribution(row, '')


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_git_commit_tree_identity_and_size(self):
        row = rows()[0]
        commit = json.dumps(dict(sha=s.COMMIT, tree=dict(sha='a'*40))).encode()
        tree = dict(sha='a'*40, truncated=False, tree=[dict(path='audio/'+row['filename'],
                    type='blob', size=441044, sha='b'*40)])
        self.assertEqual(worker.audio_tree([row], json.dumps(tree), commit)[row['filename']]['gitBlobSha1'], 'b'*40)
        for key, value in (('sha', s.COMMIT), ('truncated', True)):
            with self.assertRaises(ValueError):
                worker.audio_tree([row], json.dumps({**tree, key: value}), commit)

    def test_download_git_blob_mismatch_stops_before_file_write(self):
        payload = b'synthetic download'
        clip = dict(url='https://example.invalid/declared', bytes=len(payload), gitBlobSha1=hashlib.sha1(
            b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest())
        with patch.object(worker, 'fetch_bytes', return_value=payload):
            pin = worker.download_clip(clip, self.root/'original')
        self.assertEqual(pin['sha256'], hashlib.sha256(payload).hexdigest())
        with patch.object(worker, 'fetch_bytes', return_value=payload+b'x'):
            with self.assertRaisesRegex(ValueError, 'blob mismatch'):
                worker.download_clip(clip, self.root/'wrong')
        self.assertFalse((self.root/'wrong').exists())

    def test_preflight_failure_happens_before_network_and_output(self):
        with patch.object(worker, 'output_path', return_value=self.root/'declaration'), \
             patch.object(worker.filtering, 'approved_context', side_effect=ValueError('environment mismatch')), \
             patch.object(worker, 'get_json') as fetch:
            with self.assertRaisesRegex(ValueError, 'environment mismatch'):
                worker.declare(self.root/'declaration')
        fetch.assert_not_called()
        self.assertFalse((self.root/'declaration').exists())

    def test_acquisition_network_error_stops_no_retry(self):
        plan = dict(inputBindings={})
        selection = dict(clips=[dict(metadata=rows()[0])])
        with patch.object(worker, 'checked_declaration', return_value=(self.root, plan, {}, selection)), \
             patch.object(worker, 'download_clip', side_effect=OSError('download failed')) as download:
            with self.assertRaises(OSError):
                worker.acquire(self.root, 'declared')
            self.assertEqual(download.call_count, 1)
            with self.assertRaisesRegex(ValueError, 'retry'):
                worker.acquire(self.root, 'declared')
            self.assertEqual(download.call_count, 1)

    def test_acquisition_conversion_failure_recorded_once(self):
        clip = dict(metadata=rows()[0])
        plan = dict(inputBindings={'ffmpeg': {'path': '/synthetic', 'sha256': 'ignored'}})
        with patch.object(worker, 'checked_declaration', return_value=(self.root, plan, {}, dict(clips=[clip]))), \
             patch.object(raw, 'guard'), patch.object(worker, 'download_clip', return_value={'path': 'synthetic', 'sha256': 's'}), \
             patch.object(worker.environment, 'convert', side_effect=RuntimeError('conversion failed')) as convert:
            worker.acquire(self.root, 'declared')
        record = json.loads((self.root/'acquisition/00.json').read_text())
        self.assertEqual(record['state'], 'failed')
        self.assertEqual(record['stage'], 'conversion')
        self.assertEqual(convert.call_count, 1)

    def test_integrity_failure_is_not_a_denominator_failure(self):
        with self.assertRaises(ValueError):
            worker.stop_on_hash_failure(ValueError('CTC posterior bytes differ'))
        worker.stop_on_hash_failure(RuntimeError('model process failed'))

    def acquisition_fixture(self):
        directory = self.root/'acquisition'
        (directory/'original').mkdir(parents=True)
        (directory/'pcm16').mkdir()
        payload = b'synthetic original'
        blob = hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
        clips, pins = [], []
        plan = dict(inputBindings=dict(ffmpeg=dict(path='/pinned/ffmpeg')))
        for i, row in enumerate(rows()[:60]):
            clip = dict(metadata=row, bytes=len(payload), gitBlobSha1=blob)
            source, destination = directory/'original'/row['filename'], directory/'pcm16'/row['filename']
            source.write_bytes(payload); destination.write_bytes(b'synthetic converted')
            command = ['/pinned/ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(source), '-map',
                       '0:a:0', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(destination)]
            record = dict(clip=clip,state='ready',original=raw.binding(source),converted=raw.binding(destination),
                          conversionCommand=command)
            pins.append(worker.freeze(directory/f'{i:02d}.json', record))
            clips.append(clip)
        manifest = dict(declaration={},records=pins)
        pin = worker.freeze(directory/'manifest.json', manifest)
        return dict(clips=clips), plan, manifest, pin

    def test_acquisition_manifest_requires_captured_sha(self):
        selection, plan, manifest, pin = self.acquisition_fixture()
        with patch.object(worker.environment, 'check_wave'):
            self.assertEqual(len(worker.read_acquisition(self.root, {}, selection, pin['sha256'], plan)[0]),60)
        Path(pin['path']).chmod(0o600)
        Path(pin['path']).write_text(json.dumps({**manifest, 'new': True}))
        with self.assertRaisesRegex(ValueError, 'Caller-pinned'):
            worker.read_acquisition(self.root, {}, selection, pin['sha256'], plan)

    def test_acquisition_rejects_rebound_arbitrary_conversion_path(self):
        selection, plan, manifest, pin = self.acquisition_fixture()
        path = self.root/'arbitrary.wav'; path.write_bytes(b'synthetic converted')
        record_path = Path(manifest['records'][0]['path'])
        record = json.loads(record_path.read_text()); record['converted'] = raw.binding(path)
        record_path.chmod(0o600); record_path.write_text(json.dumps(record))
        manifest['records'][0] = raw.binding(record_path)
        manifest_path = Path(pin['path']); manifest_path.chmod(0o600); manifest_path.write_text(json.dumps(manifest))
        with patch.object(worker.environment, 'check_wave'):
            with self.assertRaisesRegex(ValueError, 'conversion command'):
                worker.read_acquisition(self.root, {}, selection, raw.digest(manifest_path), plan)

    def test_acquisition_rejects_changed_conversion_recipe(self):
        selection, plan, manifest, pin = self.acquisition_fixture()
        record_path = Path(manifest['records'][0]['path'])
        record = json.loads(record_path.read_text()); record['conversionCommand'].insert(-1,'-af')
        record_path.chmod(0o600); record_path.write_text(json.dumps(record))
        manifest['records'][0] = raw.binding(record_path)
        manifest_path = Path(pin['path']); manifest_path.chmod(0o600); manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'conversion command'):
            worker.read_acquisition(self.root, {}, selection, raw.digest(manifest_path), plan)

    def test_run_attempts_once_and_preserves_all_failure_kinds(self):
        marker = self.root/'input'; marker.write_bytes(b'synthetic input')
        input_pin = raw.binding(marker)
        plan = dict(inputBindings=dict(node=input_pin),prompt=input_pin,contractSha256='contract',
                    snapshot=str(marker),head=dict(bundle=str(self.root),manifestSha256='manifest'))
        clips = [dict(metadata=row) for row in rows()[:4]]
        records = [dict(clip=clips[0],state='failed',stage='conversion',error='conversion failed')]+[
            dict(clip=clip,state='ready',converted=input_pin) for clip in clips[1:]]
        def adapter(args):
            if args.output.parent.name == '01':
                args.output.with_name('raw.partial').mkdir(parents=True)
                raise RuntimeError('adapter failed')
            args.output.mkdir(parents=True)
            raw.write_json(args.output/'report.json',dict(complete=True))
        def filter_report(path,sha,destination):
            if destination.parent.name == '02':
                raise RuntimeError('filter failed')
            (destination/'default250').mkdir(parents=True)
            raw.write_json(destination/'default250/finalreport.json',dict(complete=True))
            raw.write_json(destination/'finalreport.json',dict(complete=True))
        with patch.object(worker,'checked_declaration',return_value=(self.root,plan,{},dict(clips=clips))), \
             patch.object(worker,'read_acquisition',return_value=(records,{})), \
             patch.object(raw,'run',side_effect=adapter) as adapter_call, \
             patch.object(worker.filtering,'filter_report',side_effect=filter_report) as filter_call, \
             patch.object(worker,'reconstruct',return_value=dict(complete=True)):
            worker.run(self.root,'declaration','acquisition')
            self.assertEqual(adapter_call.call_count,3)
            self.assertEqual(filter_call.call_count,2)
            outcomes = [json.loads((self.root/'results'/f'{i:02d}-outcome.json').read_text()) for i in range(4)]
            self.assertEqual([o['state'] for o in outcomes],['failed','failed','failed','complete'])
            self.assertTrue(all(o['attempt'] == 1 for o in outcomes))
            self.assertEqual(outcomes[1]['partialOutputs'],['01/raw.partial'])
            with self.assertRaisesRegex(ValueError,'retry'):
                worker.run(self.root,'declaration','acquisition')
            self.assertEqual(adapter_call.call_count,3)


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        artifact = self.root/'synthetic'; artifact.write_bytes(b'synthetic frozen input')
        self.pin = raw.binding(artifact)
        self.pins = {name: self.pin for name in ('vendor/utils_vad.py', 'vendor/silero_vad.jit',
                                                'studySource', 'gateSource', 'rawSource')}
        # Preserve the real adapter's contract and binding-key shape with synthetic assets.
        contract = json.loads(raw.CONTRACT.read_text())
        contract_path = self.root/'contract.json'; raw.write_json(contract_path, contract)
        contract_pin = raw.binding(contract_path)
        manifest_path = self.root/'manifest.json'
        raw.write_json(manifest_path, dict(filesSha256={name: self.pin['sha256'] for name in raw.inference.FILES}))
        manifest_pin = raw.binding(manifest_path)
        raw_bindings = {'contract': contract_pin, **{
            'source/'+name: self.pin for name in set(contract['dependencySha256']) | set(raw.RUNTIME_SOURCES)}, **{
            'phonetic/'+name: self.pin for name in contract['phoneticCheckpoint']['artifactSha256']}}
        self.pins.update({'raw/'+name: pin for name,pin in raw_bindings.items()})
        self.pins.update({'head/'+name: self.pin for name in raw.inference.FILES})
        self.pins['headManifest'] = manifest_pin
        self.plan = dict(inputBindings=self.pins, prompt=self.pin, runtime=worker.vad.runtime(),
                         head=dict(manifestSha256=manifest_pin['sha256']), contractSha256=contract_pin['sha256'],
                         parameters=worker.vad.PARAMS, nodeVersion='v24.0.0')
        self.record = dict(converted=self.pin)
        self.raw_path = self.root/'raw.json'
        self.original = dict(complete=True, researchOnly=True, inputBindings={**raw_bindings,
                             'audio':self.pin,'prompt':self.pin,'headManifest':manifest_pin, **{
                                 'head/'+name:self.pin for name in raw.inference.FILES}},
                             headManifestSha256=manifest_pin['sha256'], contractSha256=contract_pin['sha256'], filesSha256={},
                             ctcRuntime=dict(sampleCount=80000,complete=True,checkpoint=contract['ctcCheckpoint'],
                                             fetchAttempts=0,sessionOptions=contract['ctcSessionOptions'],node='v24.0.0'))
        raw.write_json(self.raw_path, self.original)
        self.raw_pin = raw.binding(self.raw_path)

    def reports(self, phone=True, vad250=False, vad100=True, mutate=None):
        phone_decision = dict(ratingAvailable=phone, recognizedPhoneTokens=3)
        evidence = self.root/'phone.json'
        raw.write_json(evidence, dict(sourceReport=self.raw_pin, inputBindings=dict(audio=self.pin), decision=phone_decision))
        outcome = dict(rawReport=self.raw_pin)
        for policy, duration, present in (('combined250',250,vad250), ('combined100',100,vad100)):
            pins = {**self.pins, 'audio': self.pin}
            if policy == 'combined250':
                pins['phoneEvidenceReport'] = raw.binding(evidence)
            else:
                pins['default250Report'] = outcome['combined250']
            report = dict(complete=True, researchOnly=True, sourceReport=self.raw_pin, inputBindings=pins,
                          runtime=self.plan['runtime'], phoneEvidenceDecision=phone_decision,
                          decision=dict(ratingAvailable=phone and present),
                          vad=dict(parameters={**worker.vad.PARAMS,'min_speech_duration_ms':duration},
                                   sampleCount=80000, probabilities=[.9]*157,
                                   timestamps=[dict(start=0,end=8000)] if present else [], vad=present))
            if mutate:
                mutate(policy, report)
            path = self.root/(policy+'.json'); raw.write_json(path, report)
            outcome[policy] = raw.binding(path)
        return outcome

    def test_coprimary_counts_reconstructed_without_model_or_filter(self):
        outcome = self.reports()
        with patch.object(worker.raw, 'run', side_effect=AssertionError('inference forbidden')), \
             patch.object(worker.filtering, 'filter_report', side_effect=AssertionError('filter rerun forbidden')):
            decisions = worker.complete_decisions(outcome, self.record, self.plan)
        self.assertEqual(decisions, dict(combined250=False,combined100=True,vad250=False,vad100=True,
                                        phoneEvidence=True,recognizedPhoneTokens=3))

    def test_mutated_bound_report_hash_stops(self):
        outcome = self.reports()
        Path(outcome['combined100']['path']).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Caller-pinned'):
            worker.complete_decisions(outcome, self.record, self.plan)

    def test_decision_arithmetic_and_shared_probabilities_enforced(self):
        def corrupt(policy, report):
            if policy == 'combined100':
                report['decision']['ratingAvailable'] = False
        outcome = self.reports(mutate=corrupt)
        with self.assertRaisesRegex(ValueError, 'arithmetic'):
            worker.complete_decisions(outcome, self.record, self.plan)

    def replace_raw(self, mutate):
        mutate(self.original)
        self.raw_path.write_text(json.dumps(self.original))
        self.raw_pin = raw.binding(self.raw_path)

    def test_wrong_raw_source_pin_fails_even_when_rehashed(self):
        alternate = self.root/'alternate-source'; alternate.write_bytes(b'wrong source')
        self.replace_raw(lambda report: report['inputBindings'].update({
            'source/multiphone_research_audio.py':raw.binding(alternate)}))
        outcome = self.reports()
        with self.assertRaisesRegex(ValueError,'binding coverage'):
            worker.complete_decisions(outcome,self.record,self.plan)

    def test_missing_raw_source_pin_fails_required_coverage(self):
        self.replace_raw(lambda report: report['inputBindings'].pop('source/multiphone_research_audio.py'))
        outcome = self.reports()
        with self.assertRaisesRegex(ValueError,'binding coverage'):
            worker.complete_decisions(outcome,self.record,self.plan)

    def test_wrong_ctc_checkpoint_fails_even_when_rehashed(self):
        self.replace_raw(lambda report: report['ctcRuntime'].update(checkpoint={'id':'wrong-checkpoint'}))
        outcome = self.reports()
        with self.assertRaisesRegex(ValueError,'CTC checkpoint'):
            worker.complete_decisions(outcome,self.record,self.plan)

    def test_ctc_network_attempt_is_rejected(self):
        self.replace_raw(lambda report: report['ctcRuntime'].update(fetchAttempts=1))
        outcome = self.reports()
        with self.assertRaisesRegex(ValueError,'CTC checkpoint'):
            worker.complete_decisions(outcome,self.record,self.plan)

    def test_ctc_node_matches_declaration(self):
        self.replace_raw(lambda report: report['ctcRuntime'].update(node='v99.0.0'))
        outcome = self.reports()
        with self.assertRaisesRegex(ValueError,'CTC checkpoint'):
            worker.complete_decisions(outcome,self.record,self.plan)

    def test_ctc_thread_options_match_bound_contract(self):
        self.replace_raw(lambda report: report['ctcRuntime'].update(sessionOptions={
            'intraOpNumThreads':4,'interOpNumThreads':1,'executionMode':'sequential'}))
        outcome = self.reports()
        with self.assertRaisesRegex(ValueError,'CTC checkpoint'):
            worker.complete_decisions(outcome,self.record,self.plan)

    def test_failed_outcomes_stay_denominator_never_rejection(self):
        clip = dict(metadata=rows()[0])
        group = [dict(clip=clip,state='complete',decisions=dict(combined250=False,combined100=True)),
                 dict(clip=clip,state='failed',error='failed')]
        counts = worker.summarize(group)['overall']
        self.assertEqual(counts['policies']['combined250'], dict(admitted=0,rejected=1,failed=1,denominator=2))
        self.assertEqual(counts['policies']['combined100'], dict(admitted=1,rejected=0,failed=1,denominator=2))

    def test_partial_outputs_inventory(self):
        (self.root/'clip.partial').mkdir()
        (self.root/'clip.partial/failure.json').write_text('{}')
        self.assertEqual(worker.partials(self.root), ['clip.partial'])

    def test_frozen_declaration_cannot_be_overwritten(self):
        path = self.root/'declaration.json'
        worker.freeze(path, dict(inferencePerformed=False))
        with self.assertRaises(FileExistsError):
            worker.freeze(path, dict(inferencePerformed=True))


if __name__ == '__main__':
    unittest.main()
