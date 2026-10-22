"""Synthetic-only full-extraction tests: tiny declared cohort, stub encoder and references; no actual data."""
import contextlib
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from posterior_pooling import extract as e, fresh_preflight as f, full_extract as x
from posterior_pooling.test_fresh_preflight import ENV, SMALL, Encoder, Samples, synthetic_logp

S = list(x.SELECTED)
# Cohort order interleaves the four probes with three non-probe clips.
IDS = ['c0', S[2], 'c1', S[0], S[3], 'c2', S[1]]
SUPPORT = dict(clips=7, positions=14, children=2, targets=1)
ROLES = {cid: ['fit-duration-probe'] for cid in S[:3]} | {S[3]: ['global-longest-hardware-only']}


def ulp(value):
    return np.nextafter(value, np.float32(np.inf))


def row(cid, output, canonical, interval, window, token):
    return dict(id=f'{cid}:0:{canonical}', clipId=cid, targetId='T', rowIndex=output, outputIndex=output,
                canonicalIndex=canonical, wordIndex=0, phoneIndex=canonical, targetPhone='T',
                intervalFrames=interval, estimatedPoolingWindowFrames=window, tokenId=token)


class Cohort:
    """Seven synthetic clips, two rows each, non-monotone output indices, frozen preflight arrays for the four probes."""
    def __init__(self, directory):
        self.root = Path(directory).resolve(); folder = self.root/'outputs/full'; folder.mkdir(parents=True)
        self.fresh = self.root/'outputs/fresh'; (self.fresh/'run').mkdir(parents=True)
        self.hidden = {}; clips = []
        for i, cid in enumerate(IDS):
            audio = folder/(cid+'.wav'); audio.write_bytes(('synthetic '+cid).encode())
            ctc = folder/(cid+'.f32'); synthetic_logp(i).tofile(ctc)
            rows = [row(cid, i, 0, [0, 1], [0, 3], 4), row(cid, 13-i, 1, [2, 4], [0, 5], 5)]
            clips.append(dict(id=cid, audioPath=str(audio), audioSha256=e.digest(audio), sampleCount=5, frames=5,
                              fullTokens=[4, 5], rows=rows, posterior=e.file_binding(ctc)))
            self.hidden[str(audio)] = np.random.default_rng(100+i).normal(scale=.5, size=(5, 1024)).astype(np.float32)
        self.by_id = {c['id']: c for c in clips}
        frozen = {cid: f.save_arrays(self.fresh/'run'/(cid+'.npz'), self.pooled(cid)) for cid in S}
        self.frozen = {cid: b['sha256'] for cid, b in frozen.items()}
        self.reference = np.zeros((14, 1024), dtype=np.float32)
        for clip in clips:
            self.reference[[r['outputIndex'] for r in clip['rows']]] = self.pooled(clip['id'])['hard']
        self.reference[9, 0] += SMALL  # one descriptive historical row difference, never a gate
        plan = dict(study=x.RECIPE['version'], recipe=x.RECIPE, clips=clips,
                    probes=dict(selectedClipIds=S, startClipIds=S, endClipIds=S, roles=ROLES, frozenArtifacts=frozen),
                    support=SUPPORT, inputs={k: dict(path=k, sha256='0'*64) for k in f.REFERENCE_KEYS}, model={}, runtime=ENV,
                    prerequisites=dict(bindings={}, frozenArtifacts=frozen),
                    sources={str(p): e.file_binding(p) for p in x.new_sources()}, **x.FLAGS)
        self.plan_path = folder/'plan.json'; self.sha = e.write_new(self.plan_path, plan)['sha256']
        self.plan = e.read_json(self.plan_path)
        self.review = folder/'review.json'
        e.write_new(self.review, dict(planSha256=self.sha, verdict='clear', blockingFindings=[], independent=True, reviewer='synthetic'))
        self.out = folder/'run'

    def pooled(self, cid):
        clip = self.by_id[cid]
        logp = np.fromfile(clip['posterior']['path'], dtype='<f4').reshape(5, 392)
        return e.pool_clip(self.hidden[clip['audioPath']], logp, clip)[0]

    def paths(self, ids):
        return [self.by_id[cid]['audioPath'] for cid in ids]

    @contextlib.contextmanager
    def patched(self, encoder):
        with patch.object(e, 'HERE', self.root), patch.object(x, 'checked_plan', return_value=self.plan), \
             patch.object(e, 'environment', return_value=ENV), patch.object(e, 'checked_references', return_value=self.reference), \
             patch.object(e, 'load_encoder', side_effect=lambda plan: contextlib.nullcontext(encoder)), \
             patch.object(e, 'read_rating_pcm', side_effect=lambda path, sha: Samples(str(path))), \
             patch.object(x, 'FRESH', self.fresh), patch.object(x, 'FROZEN', self.frozen), patch.dict(x.SUPPORT, SUPPORT):
            yield

    def run(self, encoder=None):
        encoder = encoder or Encoder(self.hidden)
        with self.patched(encoder):
            return x.run(self.plan_path, self.sha, self.review, self.out), encoder


def single_arm(call, key, real=e.extract_clip):
    """extract_clip wrapper changing one element of one arm by one float32 ULP at the given forward."""
    calls = [0]
    def forward(encoder, clip):
        values, audit = real(encoder, clip); calls[0] += 1
        if calls[0] == call:
            values[key][0, 0] = ulp(values[key][0, 0])
        return values, audit
    return forward, calls


class FullRunTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.fx = Cohort(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_start_cohort_end_forwards_share_one_forward_and_matrices_assign_every_row_once(self):
        fx = self.fx; encoder = Encoder(fx.hidden)
        with fx.patched(encoder), patch.object(e, 'extract_clip', wraps=e.extract_clip) as forward:
            pin = x.run(fx.plan_path, fx.sha, fx.review, fx.out)
        order = S+IDS+S
        self.assertEqual(forward.call_count, len(order)); self.assertEqual(encoder.calls, fx.paths(order))
        report = e.read_json(Path(pin['path']))
        self.assertEqual(report['runOrder'], order); self.assertEqual(report['encoderForwards'], 15)
        self.assertEqual(report['forwardCounts'], dict(start=4, cohort=7, end=4))
        self.assertEqual([r['forward'] for r in report['start']+report['records']+report['end']], list(range(1, 16)))
        self.assertTrue(all(r['candidateFrozenBitExact'] and r['hardFrozenBitExact'] for r in report['start']))
        self.assertTrue(all(r[k+l+'BitExact'] for r in report['end'] for k in x.KEYS for l in ('Start', 'Cohort')))
        matrices = {}
        for k in x.KEYS:
            self.assertEqual(report['matrices'][k], dict(e.file_binding(fx.out/(k+'.npy')), shape=[14, 1024], dtype='float32'))
            matrices[k] = np.load(fx.out/(k+'.npy'), allow_pickle=False)
            self.assertEqual((matrices[k].shape, matrices[k].dtype), ((14, 1024), np.float32))
        for entry in report['records']:
            cid = entry['clipId']; record = e.read_json(fx.out/(cid+'.json')); rows = x.indices(fx.by_id[cid])
            self.assertEqual(entry['record'], e.file_binding(fx.out/(cid+'.json')))
            self.assertEqual(record['startProbeMatch'], {'candidateStartBitExact': True, 'hardStartBitExact': True} if cid in S else None)
            self.assertEqual(record['roles'], ROLES.get(cid, []))
            expected = fx.pooled(cid)
            for k in x.KEYS: np.testing.assert_array_equal(matrices[k][rows], expected[k])
        self.assertEqual(report['historicalHardDescriptive']['differingRows'], 1); self.assertIs(report['historicalHardGate'], False)
        for flag in x.FLAGS: self.assertIs(report[flag], False)
        self.assertEqual(Path(pin['path']).stat().st_mode & 0o777, 0o600); self.assertFalse((fx.out/'failure.json').exists())
        with fx.patched(encoder), self.assertRaisesRegex(ValueError, 'no implicit restart'):
            x.run(fx.plan_path, fx.sha, fx.review, fx.out)
        self.assertEqual(len(encoder.calls), 15)

    def test_one_ulp_start_cohort_or_end_mismatch_either_arm_stops_with_saved_evidence(self):
        # (forward, stage, message, completed counts, unit saved before the gate raised)
        cases = [(2, 'start', f'Start probe {S[1]} differs from frozen', dict(start=1, cohort=0, end=0), 'start-'+S[1], 'Frozen'),
                 (6, 'cohort', f'Cohort probe {S[2]} differs', dict(start=4, cohort=1, end=0), S[2], 'Start'),
                 (13, 'end', f'End probe {S[1]} differs', dict(start=4, cohort=7, end=1), 'end-'+S[1], 'Cohort')]
        for call, stage, message, counts, unit, label in cases:
            for key in x.KEYS:
                with self.subTest(stage=stage, key=key), tempfile.TemporaryDirectory() as directory:
                    fx = Cohort(directory); forward, calls = single_arm(call, key); encoder = Encoder(fx.hidden)
                    with fx.patched(encoder), patch.object(e, 'extract_clip', side_effect=forward):
                        with self.assertRaisesRegex(ValueError, message): x.run(fx.plan_path, fx.sha, fx.review, fx.out)
                        with self.assertRaisesRegex(ValueError, 'no implicit restart'): x.run(fx.plan_path, fx.sha, fx.review, fx.out)
                    self.assertEqual((calls[0], len(encoder.calls)), (call, call))
                    failure = e.read_json(fx.out/'failure.json')
                    self.assertEqual((failure['stage'], failure['completedForwards'], failure['encoderForwards']), (stage, counts, call))
                    self.assertIn('Traceback', failure['errorTraceback']); self.assertIs(failure['successFrozen'], False)
                    self.assertIs(failure['restartAllowed'], False)
                    self.assertIn(unit+'.npz', failure['artifacts']); self.assertIn(unit+'.json', failure['artifacts'])
                    record = e.read_json(fx.out/(unit+'.json')); flags = record.get('startProbeMatch') or record
                    other = [k for k in x.KEYS if k != key][0]
                    self.assertIs(flags[key+label+'BitExact'], False); self.assertIs(flags[other+label+'BitExact'], True)
                    for name in ('report.json', 'candidate.npy', 'hard.npy'): self.assertFalse((fx.out/name).exists())

    def test_review_plan_and_runtime_barriers_precede_data_and_output(self):
        fx = self.fx; encoder = Encoder(fx.hidden)
        other = fx.root/'outputs/full/hold.json'
        e.write_new(other, dict(planSha256=fx.sha, verdict='hold', blockingFindings=['x'], independent=True, reviewer='synthetic'))
        cases = dict(sha=dict(sha='0'*64), review=dict(review=other),
                     plan=dict(plan=ValueError('Full plan source changed')), runtime=dict(env=ValueError('runtime differs')))
        for name, case in cases.items():
            with self.subTest(case=name), fx.patched(encoder), \
                 patch.object(x, 'checked_plan', side_effect=case.get('plan'), return_value=fx.plan) as checked, \
                 patch.object(e, 'environment', side_effect=case.get('env'), return_value=ENV), \
                 patch.object(e, 'checked_references') as references, patch.object(x, 'frozen_probes') as frozen:
                with self.assertRaises(ValueError): x.run(fx.plan_path, case.get('sha', fx.sha), case.get('review', fx.review), fx.out)
                if name in ('sha', 'review'): checked.assert_not_called()
                references.assert_not_called(); frozen.assert_not_called()
            self.assertFalse(fx.out.exists()); self.assertEqual(encoder.calls, [])

    def test_frozen_review_payload_and_unit_drift_preserve_failure(self):
        def change_review(call, hidden):
            if call == 8: self.fx.review.write_text('{}')
        def change_audio(call, hidden):
            if call == 7: Path(self.fx.by_id['c1']['audioPath']).write_bytes(b'changed during forward')
        def change_unit(call, hidden):
            if call == 12: (self.fx.out/'c0.npz').write_bytes(b'changed')
        # (stage, completed counts, completed extract_clip forwards, encoder calls)
        cases = [('frozen', None, 'Frozen preflight artifact differs', ('references', dict(start=0, cohort=0, end=0), 0, 0)),
                 ('review', change_review, 'Clear review changed', ('cohort', dict(start=4, cohort=4, end=0), 8, 8)),
                 ('audio', change_audio, 'hash differs', ('cohort', dict(start=4, cohort=2, end=0), 6, 7)),
                 ('unit', change_unit, 'Saved clip artifact changed', ('assembly', dict(start=4, cohort=7, end=4), 15, 15))]
        for name, perturb, message, expected in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                fx = self.fx = Cohort(directory)
                if name == 'frozen': (fx.fresh/'run'/(S[0]+'.npz')).write_bytes(b'changed')
                encoder = Encoder(fx.hidden, perturb)
                with fx.patched(encoder), self.assertRaisesRegex(ValueError, message):
                    x.run(fx.plan_path, fx.sha, fx.review, fx.out)
                failure = e.read_json(fx.out/'failure.json')
                self.assertEqual((failure['stage'], failure['completedForwards'], failure['encoderForwards'], len(encoder.calls)), expected)
                self.assertIn(message, failure['errorMessage']); self.assertFalse((fx.out/'candidate.npy').exists())

    def test_run_order_requires_exact_clip_probe_and_output_index_coverage(self):
        plan = self.fx.plan
        with patch.dict(x.SUPPORT, SUPPORT):
            self.assertEqual(x.run_order(plan), S+IDS+S)
            def swap(p): p['clips'][0]['rows'][0]['outputIndex'] = 1
            mutations = dict(duplicateClip=lambda p: p['clips'].__setitem__(1, copy.deepcopy(p['clips'][0])),
                             missingClip=lambda p: p['clips'].pop(2), duplicateRow=swap,
                             missingRow=lambda p: p['clips'][0]['rows'].pop(),
                             missingProbe=lambda p: p['clips'].pop(1),
                             probeOrder=lambda p: p['probes'].__setitem__('endClipIds', S[::-1]),
                             frozen=lambda p: p['probes']['frozenArtifacts'].pop(S[0]))
            for name, mutate in mutations.items():
                changed = copy.deepcopy(plan); mutate(changed)
                with self.subTest(mutation=name), self.assertRaises(ValueError): x.run_order(changed)
        matrices = {k: np.zeros((3, 2), dtype=np.float32) for k in x.KEYS}; assigned = np.zeros(3, dtype=bool)
        x.assign(matrices, assigned, [2, 0], {k: np.ones((2, 2), dtype=np.float32) for k in x.KEYS})
        with self.assertRaisesRegex(ValueError, 'more than once'):
            x.assign(matrices, assigned, [1, 2], {k: np.ones((2, 2), dtype=np.float32) for k in x.KEYS})
        self.assertEqual(assigned.tolist(), [True, False, True])

    def test_late_probe_or_record_drift_prevents_matrix_and_success_freeze(self):
        targets = ('c0.json', 'start-'+S[0]+'.npz', 'end-'+S[0]+'.json')
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                fx = Cohort(directory)
                def corrupt(call, hidden):
                    if call == 13: (fx.out/target).write_text('{}')
                encoder = Encoder(fx.hidden, corrupt)
                with fx.patched(encoder), self.assertRaises(ValueError):
                    x.run(fx.plan_path, fx.sha, fx.review, fx.out)
                failure = e.read_json(fx.out/'failure.json')
                self.assertEqual((failure['stage'], failure['encoderForwards']), ('final guards', 15))
                self.assertIs(failure['successFrozen'], False)
                self.assertIs(failure['restartAllowed'], False)
                for name in ('candidate.npy', 'hard.npy', 'report.json'): self.assertFalse((fx.out/name).exists())


class DeclarationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.root = Path(self.directory.name).resolve()

    def tearDown(self):
        self.directory.cleanup()

    def write(self, name, value):
        self.written = getattr(self, 'written', 0)+1
        return e.write_new(self.root/f'{self.written}-{name.replace("/", "-")}.json', value)

    def metadata(self, index_extra=None):
        manifest = dict(clips=[dict(id=c) for c in ('a', 'b', 'n')], rowIds=['r'], rowIndices=[0])
        entries = {c: dict(clipId=c, frames=5, vocabularySize=392, audioSha256=c*64, sampleCount=5, path='x') for c in ('a', 'b')}
        entries.update(index_extra or {})
        values = dict(manifest=manifest, positionPlan=dict(clips=['positions']), scalarPlan=dict(clips=['phones']),
                      scalarReport=dict(newCtcJobs={'n': {}}, posteriorBindings={c: {'path': c} for c in ('a', 'b', 'n')}),
                      mapping=dict(poolingContextFrames=2), vocabulary={'<pad>': 0}, oldIndex=dict(entries=entries))
        pins = {k: self.write(k, value) for k, value in values.items()}
        pins['newCTC/n/job'] = self.write('newCTC/n/job', dict(job=True))
        pins['newCTC/n/result'] = self.write('newCTC/n/result', dict(frames=7, audioSha256='n'*64, sampleCount=7, other=1))
        return pins, values

    @staticmethod
    def joined(ids=('a', 'b', 'n')):
        return [dict(id=c, speakerId=c in 'ab', rows=[dict(outputIndex=i, targetId='T')]) for i, c in enumerate(ids)]

    def test_full_join_passes_all_manifest_clips_and_old_plus_new_metadata_to_unchanged_join(self):
        pins, values = self.metadata(); clips = self.joined(); calls = []
        def join(*args):
            calls.append(copy.deepcopy(args)); return copy.deepcopy(clips)
        support = dict(clips=3, positions=3, children=2, targets=1)
        with patch.object(e, '_metadata', return_value=(pins, [clips[1]], {}, {'m': 1}, ENV, {'r': 1})), \
             patch.object(e, 'join_clips', side_effect=join), patch.object(x, 'SELECTED', ['b']), patch.dict(x.SUPPORT, support):
            result = x.full_join()
            self.assertEqual(result, (pins, clips, {'m': 1}, ENV, {'r': 1}))
            manifest, positions, phones, bindings, metadata, recipe, vocabulary = calls[0]
            self.assertEqual((manifest, positions, phones, recipe, vocabulary), (values['manifest'], ['positions'], ['phones'],
                             values['mapping'], values['vocabulary']))
            self.assertEqual(bindings, values['scalarReport']['posteriorBindings'])
            self.assertEqual(metadata, {'a': dict(frames=5, vocabularySize=392, audioSha256='a'*64, sampleCount=5),
                                        'b': dict(frames=5, vocabularySize=392, audioSha256='b'*64, sampleCount=5),
                                        'n': dict(frames=7, vocabularySize=392, audioSha256='n'*64, sampleCount=7)})
            cases = dict(selected=((pins, [clips[0]]), clips, 'four declared probes'),
                         reordered=((pins, [clips[1]]), clips[::-1], 'support differs'),
                         missingRow=((pins, [clips[1]]), [dict(c, rows=[]) if c['id'] == 'a' else c for c in clips], 'support differs'))
            for name, ((case_pins, selected), returned, message) in cases.items():
                with self.subTest(case=name), patch.object(e, '_metadata', return_value=(case_pins, selected, {}, {}, ENV, {})), \
                     patch.object(e, 'join_clips', return_value=returned), self.assertRaisesRegex(ValueError, message):
                    x.full_join()
            duplicate, _ = self.metadata(dict(n=dict(clipId='n', frames=7, vocabularySize=392, audioSha256='n', sampleCount=7)))
            with patch.object(e, '_metadata', return_value=(duplicate, [clips[1]], {}, {}, ENV, {})), \
                 self.assertRaisesRegex(ValueError, 'duplicates'):
                x.full_join()
            Path(pins['newCTC/n/result']['path']).write_text('{}')
            with patch.object(e, '_metadata', return_value=(pins, [clips[1]], {}, {}, ENV, {})), self.assertRaisesRegex(ValueError, 'changed'):
                x.full_join()

    def test_declaration_is_metadata_only_and_matches_frozen_preflight_exactly(self):
        clips = [dict(id=c, rows=[]) for c in ['c0']+S]; by_id = {c['id']: c for c in clips}
        pins, model, encoder = {'manifest': dict(path='m', sha256='0'*64)}, {'m': 1}, {'r': 1}
        prerequisites = dict(bindings={'freshPlan': dict(path='p', sha256='1'*64)}, frozenArtifacts={c: dict(path=c, sha256='2'*64) for c in S})
        preflight = dict(inputs=pins, model=model, encoderRecipe=encoder, runtime=ENV, clips=[by_id[c] for c in S],
                         probes=dict(selectedClipIds=S, roles=ROLES))
        blocked = AssertionError('payload opened during declaration')
        def declared(changes=None):
            with patch.object(x, 'checked_prerequisites', return_value=(prerequisites, dict(preflight, **(changes or {})))), \
                 patch.object(x, 'full_join', return_value=(pins, clips, model, ENV, encoder)), \
                 patch.object(x, 'sources', return_value={'s': dict(path='s', sha256='3'*64)}), \
                 patch.object(np, 'load', side_effect=blocked), patch.object(np, 'fromfile', side_effect=blocked):
                return x.declaration()
        plan = declared()
        self.assertEqual(plan['study'], 'posterior-pooling-full-extraction-v1'); self.assertEqual(plan['clips'], clips)
        self.assertEqual(plan['probes'], dict(selectedClipIds=S, startClipIds=S, endClipIds=S, roles=ROLES,
                                              frozenArtifacts=prerequisites['frozenArtifacts']))
        self.assertEqual(plan['prerequisites'], prerequisites); self.assertEqual(plan['support'], x.SUPPORT)
        self.assertIs(plan['recipe']['resume'], False); self.assertNotIn('historicalParity', plan['recipe'])
        for flag in x.FLAGS: self.assertIs(plan[flag], False)
        cases = dict(clip=dict(clips=[dict(by_id[S[0]], rows=[1])]+[by_id[c] for c in S[1:]]),
                     order=dict(clips=[by_id[c] for c in S[::-1]]), inputs=dict(inputs={}), runtime=dict(runtime={'threads': 1}))
        for name, changes in cases.items():
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, 'preflight'): declared(changes)

    def prerequisite_files(self, changes):
        fresh = self.root/'fresh'; work = self.root/'work'; work.mkdir(exist_ok=True)
        folder = self.root/('case-'+str(len(list(self.root.glob('case-*'))))); folder.mkdir()
        frozen = {c: '9'*64 for c in S}
        def binding(c): return {'path': str(fresh/'run'/(c+'.npz')), 'sha256': frozen[c]}
        plan = e.write_new(folder/'plan.json', dict(synthetic=True))
        review = dict(path='astra', sha256='2'*64)
        report = dict(complete=True, plan=plan, study=f.RECIPE['version'], runOrder=S*2, encoderForwards=8, repeatsExact=True,
                      records=[dict(clipId=c, artifact=binding(c)) for c in S], review=review, processId=1,
                      repeats={c: dict(artifact=binding(c), candidateBitExact=True, hardBitExact=True) for c in S})
        changes.get('report', lambda r: None)(report); report_pin = e.write_new(folder/'report.json', report)
        verification = dict(complete=True, verified=True, plan=plan, report=report_pin, review=review, runnerProcessId=1, processId=2,
                            additionalEncoderForwards=4, hardCrossProcessBitExact=True, orderedCoverage=S)
        changes.get('verification', lambda r: None)(verification); verification_pin = e.write_new(folder/'verification.json', verification)
        observation = dict(complete=True, runner=report_pin, verification=verification_pin, allWithinRunRepeatsBitExact=True,
                           hardCrossProcessBitExact=True, processesDistinct=True, totalRealEncoderForwards=12)
        results = dict(verdict='clear', reviewer='claude-opus-5-5', blockingFindings=[], preflightPassed=True,
                       readyToPrepareFullExtractionDeclaration=True,
                       observedOutcome='FRESH_CPU_PREFLIGHT_AND_SEPARATE_PROCESS_VERIFICATION_PASS')
        changes.get('results', lambda r: None)(results)
        pins = dict(freshPlan=plan, freshReport=report_pin, freshVerification=verification_pin,
                    freshObservation=e.write_new(folder/'observation.json', observation),
                    freshResultsReview=e.write_new(folder/'results.json', results))
        return {k: (Path(p['path']), p['sha256']) for k, p in pins.items()}, frozen, fresh

    def test_prerequisites_bind_passing_preflight_verification_audit_and_results_review(self):
        prerequisites, frozen, fresh = self.prerequisite_files({})
        with patch.object(x, 'PREREQUISITES', prerequisites), patch.object(x, 'FROZEN', frozen), patch.object(x, 'FRESH', fresh), \
             patch.object(f, 'checked_plan', return_value={'preflight': True}) as checked:
            result, preflight = x.checked_prerequisites()
            checked.assert_called_once_with(prerequisites['freshPlan'][0], prerequisites['freshPlan'][1])
        self.assertEqual(preflight, {'preflight': True}); self.assertEqual(set(result['bindings']), set(x.PREREQUISITES))
        self.assertEqual(result['frozenArtifacts'][S[0]], {'path': str(fresh/'run'/(S[0]+'.npz')), 'sha256': '9'*64})
        cases = dict(
            frozenSha=({'report': lambda r: r['records'][1]['artifact'].__setitem__('sha256', '8'*64)}, 'frozen artifact'),
            repeatNotExact=({'report': lambda r: r['repeats'][S[2]].__setitem__('hardBitExact', False)}, 'frozen artifact'),
            samePid=({'verification': lambda r: r.__setitem__('processId', 1)}, 'separate-process'),
            hold=({'results': lambda r: r.__setitem__('verdict', 'hold')}, 'does not clear'),
            notReady=({'results': lambda r: r.__setitem__('readyToPrepareFullExtractionDeclaration', False)}, 'does not clear'),
            pin=({}, 'prerequisites differ'))
        for name, (changes, message) in cases.items():
            prerequisites, frozen, fresh = self.prerequisite_files(changes)
            if name == 'pin': prerequisites['freshObservation'][0].write_text('{}')
            with self.subTest(case=name), patch.object(x, 'PREREQUISITES', prerequisites), patch.object(x, 'FROZEN', frozen), \
                 patch.object(x, 'FRESH', fresh), patch.object(f, 'checked_plan') as checked:
                with self.assertRaisesRegex(ValueError, message): x.checked_prerequisites()
                checked.assert_not_called()

    def test_declare_exclusive_outside_old_and_fresh_and_source_closure(self):
        with patch.object(e, 'HERE', self.root), patch.object(x, 'declaration', return_value={'synthetic': True}), \
             patch.object(f, 'OLD', self.root/'outputs/old'), patch.object(x, 'FRESH', self.root/'outputs/fresh'):
            pin = x.declare(self.root/'outputs/new')
            self.assertEqual(e.read_json(Path(pin['path'])), {'synthetic': True})
            for out in (self.root/'outputs/new', self.root/'elsewhere', self.root/'outputs/old/full', self.root/'outputs/fresh/full'):
                with self.subTest(out=out), self.assertRaisesRegex(ValueError, 'exclusive'): x.declare(out)
        package = self.root/'pkg'; package.mkdir()
        for name in ('__init__.py', 'bound.py', 'unbound.py'): (package/name).write_text('')
        source = package/'full.py'; source.write_text('from pkg import bound, unbound\n')
        protocol = self.root/'protocol.md'; protocol.write_text('synthetic')
        bound = {str((package/n).resolve()): e.file_binding(package/n) for n in ('__init__.py', 'bound.py')}
        with patch.object(e, 'HERE', self.root), patch.object(x, 'new_sources', return_value=[source.resolve()]), \
             patch.object(x, 'PREREQUISITES', {}), patch.object(x, 'PROTOCOL', protocol):
            with patch.object(f, 'sources', return_value=dict(bound)), self.assertRaisesRegex(ValueError, 'unbound.py'): x.sources()
            complete = dict(bound, **{str((package/'unbound.py').resolve()): e.file_binding(package/'unbound.py')})
            with patch.object(f, 'sources', return_value=complete):
                self.assertEqual(x.sources()[str(source.resolve())], e.file_binding(source))


if __name__ == '__main__': unittest.main()
