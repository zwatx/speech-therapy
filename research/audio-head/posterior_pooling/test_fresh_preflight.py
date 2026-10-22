"""Synthetic-only fresh-control runner tests: temporary files, stub encoder and references."""
import contextlib
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from posterior_pooling import extract as e, fresh_preflight as f

IDS = ['p0', 'p1', 'p2', 'p3']
ENV = {'platform': 'synthetic-cpu', 'threads': 2}
SMALL = np.float32(2.**-19)


def synthetic_logp(seed):
    rng = np.random.default_rng(seed)
    logits = np.full((5, 392), -30., dtype=np.float64)
    logits[:, 0] = 0; logits[0, 4] = 3; logits[2, 5] = 2; logits[4, 5] = 1
    logits[:, :6] += rng.normal(scale=.3, size=(5, 6))
    return (logits-np.logaddexp.reduce(logits, axis=1)[:, None]).astype('<f4')


class Samples:
    def __init__(self, key): self.key = key
    def numel(self): return 5


class Encoder:
    """Stub for the shared original encoder; perturb(call, hidden) may alter one forward."""
    def __init__(self, hidden, perturb=None):
        self.hidden, self.perturb, self.calls = hidden, perturb, []

    def __call__(self, samples):
        self.calls.append(samples.key)
        value = self.hidden[samples.key].copy()
        if self.perturb: self.perturb(len(self.calls), value)
        return value


class Synthetic:
    """Four synthetic probes with two full-prompt rows each; no actual metadata or payloads."""
    def __init__(self, directory):
        self.root = Path(directory).resolve(); folder = self.root/'outputs/fresh'; folder.mkdir(parents=True)
        self.hidden = {}; clips = []
        for i, cid in enumerate(IDS):
            audio = folder/(cid+'.wav'); audio.write_bytes(('synthetic '+cid).encode())
            ctc = folder/(cid+'.f32'); synthetic_logp(i).tofile(ctc)
            rows = [self.row(cid, 2*i, 0, [0, 1], [0, 3], 4), self.row(cid, 2*i+1, 1, [2, 4], [0, 5], 5)]
            clips.append(dict(id=cid, audioPath=str(audio), audioSha256=e.digest(audio), sampleCount=5, frames=5,
                              fullTokens=[4, 5], rows=rows, posterior=e.file_binding(ctc)))
            self.hidden[str(audio)] = np.random.default_rng(100+i).normal(scale=.5, size=(5, 1024)).astype(np.float32)
        hard = np.concatenate([e.pooled_vectors(self.hidden[c['audioPath']], c['rows'], 5)[0] for c in clips])
        # Historical references: exact, exact, one-element tiny drift, one-row large drift.
        self.reference = hard.copy(); self.reference[4, 0] += SMALL; self.reference[7] += 3
        roles = {cid: ['fit-duration-probe'] for cid in IDS[:3]} | {IDS[3]: ['global-longest-hardware-only']}
        plan = dict(study=f.RECIPE['version'], recipe=f.RECIPE, clips=clips,
                    probes=dict(selectedClipIds=IDS, repeatClipIds=IDS, roles=roles),
                    inputs={k: dict(path=k, sha256='0'*64) for k in f.REFERENCE_KEYS}, model={}, runtime=ENV,
                    sources={str(p): e.file_binding(p) for p in f.new_sources()}, **f.FLAGS)
        self.plan_path = folder/'plan.json'; self.sha = e.write_new(self.plan_path, plan)['sha256']
        self.plan = e.read_json(self.plan_path)
        self.review = folder/'review.json'
        e.write_new(self.review, dict(planSha256=self.sha, verdict='clear', blockingFindings=[], independent=True, reviewer='synthetic'))
        self.out = folder/'run'

    @staticmethod
    def row(cid, index, canonical, interval, window, token):
        return dict(id=f'{cid}:0:{canonical}', clipId=cid, targetId='T', rowIndex=index, outputIndex=index,
                    canonicalIndex=canonical, wordIndex=0, phoneIndex=canonical, targetPhone='T',
                    intervalFrames=interval, estimatedPoolingWindowFrames=window, tokenId=token)

    @contextlib.contextmanager
    def patched(self, encoder):
        with patch.object(e, 'HERE', self.root), patch.object(f, 'checked_plan', return_value=self.plan), \
             patch.object(e, 'environment', return_value=ENV), patch.object(e, 'checked_references', return_value=self.reference), \
             patch.object(e, 'load_encoder', side_effect=lambda plan: contextlib.nullcontext(encoder)), \
             patch.object(e, 'read_rating_pcm', side_effect=lambda path, sha: Samples(str(path))):
            yield

    def run(self, encoder=None):
        encoder = encoder or Encoder(self.hidden)
        with self.patched(encoder):
            return f.run(self.plan_path, self.sha, self.review, self.out), encoder


class FreshPreflightTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.fx = Synthetic(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_eight_forwards_all_four_repeats_same_forward_and_descriptive_history(self):
        fx = self.fx; encoder = Encoder(fx.hidden)
        with fx.patched(encoder), patch.object(e, 'extract_clip', wraps=e.extract_clip) as forward:
            pin = f.run(fx.plan_path, fx.sha, fx.review, fx.out)
        # One extract_clip call per encoder forward: candidate and hard share it.
        self.assertEqual(forward.call_count, 8)
        self.assertEqual(encoder.calls, [c['audioPath'] for c in fx.plan['clips']]*2)
        report = e.read_json(Path(pin['path']))
        self.assertEqual(report['runOrder'], IDS*2); self.assertEqual(report['encoderForwards'], 8)
        self.assertEqual(sorted(report['repeats']), IDS)
        self.assertEqual(sorted(r['forward'] for r in report['repeats'].values()), [5, 6, 7, 8])
        self.assertTrue(all(r['candidateBitExact'] and r['hardBitExact'] for r in report['repeats'].values()))
        self.assertNotIn('cachedHardExact', report); self.assertIs(report['historicalHardGate'], False)
        history = [r['historicalHardDescriptive'] for r in report['records']]
        self.assertEqual([h['differingRows'] for h in history], [0, 0, 1, 1])
        self.assertGreater(history[2]['rowMaxAbs'][0], 0); self.assertLess(history[2]['rowMaxAbs'][0], 1e-5)
        self.assertEqual(history[2]['rowMaxAbs'][1], 0); self.assertGreater(history[3]['rowMaxAbs'][1], 2.9)
        self.assertEqual(report['historicalHardDescriptive']['differingRows'], 2)
        for clip, record in zip(fx.plan['clips'], report['records']):
            self.assertEqual(record['artifact']['sha256'], e.digest(Path(record['artifact']['path'])))
            self.assertEqual(e.read_json(fx.out/(clip['id']+'.json')), record)
            with np.load(record['artifact']['path'], allow_pickle=False) as saved:
                self.assertEqual(set(saved.files), {'candidate', 'hard'})
                np.testing.assert_array_equal(saved['hard'], e.pooled_vectors(fx.hidden[clip['audioPath']], clip['rows'], 5)[0])
                self.assertEqual((saved['candidate'].shape, saved['candidate'].dtype), ((2, 1024), np.float32))
            with np.load(report['repeats'][clip['id']]['artifact']['path'], allow_pickle=False) as repeat, \
                 np.load(record['artifact']['path'], allow_pickle=False) as saved:
                for key in ('candidate', 'hard'): np.testing.assert_array_equal(repeat[key], saved[key])
        for flag in f.FLAGS: self.assertIs(report[flag], False)
        self.assertEqual(Path(pin['path']).stat().st_mode & 0o777, 0o600)
        self.assertFalse((fx.out/'failure.json').exists())
        with fx.patched(encoder), self.assertRaisesRegex(ValueError, 'no implicit restart'):
            f.run(fx.plan_path, fx.sha, fx.review, fx.out)
        self.assertEqual(len(encoder.calls), 8)

    def test_one_ulp_within_run_candidate_or_hard_drift_fails_and_preserves_artifacts(self):
        real = e.extract_clip
        for key in ('candidate', 'hard'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                fx = Synthetic(directory); calls = [0]
                def forward(encoder, clip):
                    values, audit = real(encoder, clip); calls[0] += 1
                    if calls[0] == 6:
                        values[key][0, 0] = np.nextafter(values[key][0, 0], np.float32(np.inf))
                    return values, audit
                with fx.patched(Encoder(fx.hidden)), patch.object(e, 'extract_clip', side_effect=forward):
                    with self.assertRaisesRegex(ValueError, 'repeat of p1 differs'): f.run(fx.plan_path, fx.sha, fx.review, fx.out)
                    with self.assertRaisesRegex(ValueError, 'no implicit restart'): f.run(fx.plan_path, fx.sha, fx.review, fx.out)
                self.assertEqual(calls[0], 6)
                failure = e.read_json(fx.out/'failure.json')
                self.assertEqual((failure['completedClips'], failure['completedRepeats'], failure['encoderForwards']), (4, 1, 6))
                self.assertIn(f"'{key}BitExact': False", failure['errorMessage']); self.assertIn('Traceback', failure['errorTraceback'])
                self.assertIs(failure['successFrozen'], False); self.assertIs(failure['restartAllowed'], False)
                self.assertFalse((fx.out/'report.json').exists())
                expected = {'started.json', 'p0-repeat.npz', 'p1-repeat.npz'} | {c+s for c in IDS for s in ('.json', '.npz')}
                self.assertEqual(set(failure['artifacts']), expected)
                self.assertEqual({p.name for p in fx.out.iterdir()}, expected | {'failure.json'})

    def test_review_plan_and_runtime_barriers_precede_data_and_output(self):
        fx = self.fx; encoder = Encoder(fx.hidden)
        other = fx.root/'outputs/fresh/hold.json'
        e.write_new(other, dict(planSha256=fx.sha, verdict='hold', blockingFindings=['x'], independent=True, reviewer='synthetic'))
        cases = dict(sha=dict(sha='0'*64), review=dict(review=other),
                     source=dict(plan=ValueError('Fresh plan source changed')), runtime=dict(env=ValueError('runtime differs')))
        for name, case in cases.items():
            with self.subTest(case=name), fx.patched(encoder), \
                 patch.object(f, 'checked_plan', side_effect=case.get('plan'), return_value=fx.plan) as checked, \
                 patch.object(e, 'environment', side_effect=case.get('env'), return_value=ENV), \
                 patch.object(e, 'checked_references') as references:
                with self.assertRaises(ValueError): f.run(fx.plan_path, case.get('sha', fx.sha), case.get('review', fx.review), fx.out)
                if name in ('sha', 'review'): checked.assert_not_called()
                references.assert_not_called()
            self.assertFalse(fx.out.exists()); self.assertEqual(encoder.calls, [])

    def test_review_payload_source_and_geometry_drift_during_run_preserve_failure(self):
        def change_review(call, hidden):
            if call == 3: self.fx.review.write_text('{}')
        def change_audio(call, hidden):
            if call == 2: Path(self.fx.plan['clips'][1]['audioPath']).write_bytes(b'changed during forward')
        # (completed clips, completed extract_clip forwards, encoder calls); the audio
        # guard fails inside the second extract_clip, after its encoder call.
        cases = [('review', change_review, None, 'Clear review changed', (3, 3, 3)),
                 ('audio', change_audio, None, 'hash differs', (1, 1, 2)),
                 ('endSource', None, 'source', 'source changed', (4, 8, 8)),
                 ('geometry', None, 'geometry', 'geometry, dtype', (0, 1, 1))]
        real = e.extract_clip
        for name, perturb, kind, message, counts in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                fx = self.fx = Synthetic(directory); encoder = Encoder(fx.hidden, perturb)
                def forward(encoder, clip):
                    values, audit = real(encoder, clip)
                    if kind == 'geometry': values['hard'] = values['hard'].astype(np.float64)
                    return values, audit
                plans = [fx.plan, ValueError('Fresh plan source changed')] if kind == 'source' else None
                with fx.patched(encoder), patch.object(e, 'extract_clip', side_effect=forward), \
                     patch.object(f, 'checked_plan', side_effect=plans, return_value=fx.plan):
                    with self.assertRaisesRegex(ValueError, message): f.run(fx.plan_path, fx.sha, fx.review, fx.out)
                failure = e.read_json(fx.out/'failure.json')
                self.assertEqual((failure['completedClips'], failure['encoderForwards'], len(encoder.calls)), counts)
                self.assertIn(message, failure['errorMessage']); self.assertFalse((fx.out/'report.json').exists())
                if kind == 'geometry': self.assertFalse((fx.out/'p0.npz').exists())

    def lineage_files(self, root, old_plan, failure_changes=None):
        root.mkdir(parents=True, exist_ok=True)
        paths = {k: root/(k+'.json') for k in ('oldPlan', 'oldFailure', 'failureObservation', 'failureReview', 'historicalVerifierSynthetic')}
        paths.update(protocol=root/'protocol.md', historicalVerifier=root/'verify.py')
        paths['protocol'].write_text('synthetic protocol'); paths['historicalVerifier'].write_text('# synthetic verifier')
        e.write_new(paths['historicalVerifierSynthetic'], dict(complete=True))
        plan = e.write_new(paths['oldPlan'], old_plan)
        failure = e.write_new(paths['oldFailure'], dict(dict(planSha256=plan['sha256'], errorType='ValueError', completedClips=3,
                                                              partialOutputsPreserved=True), **(failure_changes or {})))
        e.write_new(paths['failureObservation'], dict(outcome='FAILED_HISTORICAL_EXACT_PARITY', failedClipId='001450051',
            failedClipMaximumHardMeanAbs=2.**-19, plan=plan, failure=failure, noRestart=True))
        e.write_new(paths['failureReview'], dict(verdict='clear', reviewer='claude-opus-5-5', observedOutcome='FAILED_HISTORICAL_EXACT_PARITY',
            preflightPassed=False, recommendedNextRoute='fresh-matched-cpu-preflight'))
        return {k: (path, e.digest(path)) for k, path in paths.items()}

    def old_declaration(self):
        ids = f.SELECTED
        return dict(study='posterior-pooling-cpu-preflight-v1', recipe=copy.deepcopy(e.RECIPE), inputs={'manifest': dict(path='m', sha256='0'*64)},
            clips=[dict(id=cid) for cid in ids], model={}, encoderRecipe={}, runtime=ENV, sources={'old': dict(path='old', sha256='0'*64)},
            probes=dict(fitClipIds=ids[:3], globalLongestClipId=ids[3], selectedClipIds=ids, repeatClipIds=[ids[0], ids[3]],
                        roles={cid: ['role'] for cid in ids}), **e.FLAGS)

    def test_declaration_requires_closed_v1_lineage_and_overrides_explicitly(self):
        root = self.fx.root/'lineage'; old = self.old_declaration()
        sources = {'fresh': dict(path='fresh', sha256='1'*64)}
        with patch.object(f, 'LINEAGE', self.lineage_files(root/'ok', old)), patch.object(e, 'declaration', return_value=copy.deepcopy(old)), \
             patch.object(f, 'sources', return_value=sources):
            plan = f.declaration()
        self.assertEqual(plan['study'], 'posterior-pooling-fresh-controls-cpu-preflight-v1'); self.assertEqual(plan['recipe'], f.RECIPE)
        self.assertNotIn('historicalParity', plan['recipe'])
        self.assertEqual(plan['probes']['repeatClipIds'], f.SELECTED); self.assertEqual(plan['probes']['selectedClipIds'], f.SELECTED)
        self.assertEqual(plan['probes']['historicalRepeatClipIds'], [f.SELECTED[0], f.SELECTED[3]])
        self.assertIs(plan['lineage']['historicalControlsDescriptiveOnly'], True); self.assertIs(plan['lineage']['freshMatchedControls'], True)
        self.assertEqual(plan['lineage']['outcome'], 'FAILED_HISTORICAL_EXACT_PARITY'); self.assertEqual(plan['sources'], sources)
        self.assertEqual({k: plan[k] for k in f.FIXED if k != 'probes'}, {k: old[k] for k in f.FIXED if k != 'probes'})
        for flag in f.FLAGS: self.assertIs(plan[flag], False)
        drifted = copy.deepcopy(old); drifted['probes']['fitRows'] = [1]
        reordered = copy.deepcopy(old); reordered['probes']['selectedClipIds'] = f.SELECTED[::-1]
        cases = [('pin', self.lineage_files(root/'pin', old), old, 'lineage differs'),
                 ('reopened', self.lineage_files(root/'reopened', old, dict(completedClips=4)), old, 'remain closed'),
                 ('metadata', self.lineage_files(root/'metadata', old), drifted, 'Fixed v1'),
                 ('probes', self.lineage_files(root/'probes', reordered), reordered, 'four declared probes')]
        (root/'pin/oldFailure.json').chmod(0o600); (root/'pin/oldFailure.json').write_text('{}')
        for name, lineage, current, message in cases:
            with self.subTest(case=name), patch.object(f, 'LINEAGE', lineage), patch.object(e, 'declaration', return_value=copy.deepcopy(current)) as old_route, \
                 patch.object(f, 'sources', return_value=sources):
                with self.assertRaisesRegex(ValueError, message): f.declaration()
                if name in ('pin', 'reopened'): old_route.assert_not_called()

    def test_declare_exclusive_fresh_directory_outside_frozen_v1(self):
        root = self.fx.root
        with patch.object(e, 'HERE', root), patch.object(f, 'declaration', return_value={'synthetic': True}), patch.object(f, 'OLD', root/'outputs/old'):
            pin = f.declare(root/'outputs/new')
            self.assertEqual(e.read_json(Path(pin['path'])), {'synthetic': True})
            self.assertEqual(Path(pin['path']).stat().st_mode & 0o777, 0o600)
            for out in (root/'outputs/new', root/'elsewhere', root/'outputs/old/fresh'):
                with self.subTest(out=out), self.assertRaisesRegex(ValueError, 'exclusive'): f.declare(out)

    def test_source_closure_rejects_unbound_local_import(self):
        root = self.fx.root/'closure'; package = root/'pkg'; package.mkdir(parents=True)
        for name in ('__init__.py', 'bound.py', 'unbound.py'): (package/name).write_text('')
        source = package/'fresh.py'; source.write_text('import json\nfrom pkg import bound, unbound\n')
        protocol = root/'protocol.md'; protocol.write_text('synthetic')
        bound = {str(p.resolve()): e.file_binding(p) for p in (package/'__init__.py', package/'bound.py')}
        with patch.object(e, 'HERE', root.resolve()), patch.object(f, 'new_sources', return_value=[source.resolve()]), \
             patch.object(f, 'LINEAGE', {}), patch.object(f, 'PROTOCOL', protocol):
            self.assertEqual(f.local_imports([source]), {(package/n).resolve() for n in ('__init__.py', 'bound.py', 'unbound.py')})
            with patch.object(e, 'sources', return_value=dict(bound)), self.assertRaisesRegex(ValueError, 'unbound.py'): f.sources()
            complete = dict(bound, **{str((package/'unbound.py').resolve()): e.file_binding(package/'unbound.py')})
            with patch.object(e, 'sources', return_value=complete):
                self.assertEqual(f.sources()[str(source.resolve())], e.file_binding(source))


if __name__ == '__main__': unittest.main()
