"""Synthetic-only verifier tests: brute-force oracle, stub encoder and temporary run artifacts."""
import contextlib
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from posterior_pooling import core, extract as e, fresh_preflight as f, fresh_verify as v
from posterior_pooling.test_core import direct_u, logsoftmax, oracle
from posterior_pooling.test_fresh_preflight import ENV, IDS, Encoder, Synthetic


def ulp(value):
    return np.nextafter(value, np.float32(np.inf))


@contextlib.contextmanager
def core_blocked():
    """The verifier's candidate weighting must not route through core or pool_clip."""
    blocked = AssertionError('core helper or pool_clip used by verifier')
    with patch.object(core, 'CTCPosterior', side_effect=blocked), patch.object(core, 'box_weights', side_effect=blocked), \
         patch.object(core, 'pool_hidden', side_effect=blocked), patch.object(core, 'vector_distance', side_effect=blocked), \
         patch.object(e, 'pool_clip', side_effect=blocked), patch.object(e, '_pool_clip', side_effect=blocked):
        yield


def replay_fixture(fx, index=2):
    """Runner-side saved arrays/audit for one synthetic probe; the verifier replays them independently."""
    clip = fx.plan['clips'][index]; hidden = fx.hidden[clip['audioPath']]
    logp = np.fromfile(clip['posterior']['path'], dtype='<f4').reshape(5, 392)
    values, audit = e.pool_clip(hidden, logp, clip)
    historical = fx.reference[[r['outputIndex'] for r in clip['rows']]]
    record = json.loads(json.dumps(dict(clipId=clip['id'], audit=audit,
        historicalHardDescriptive=f.historical_differences(values['hard'], historical))))
    return clip, record, hidden, logp, values, historical


def copied(values):
    return {k: a.copy() for k, a in values.items()}


class OracleTests(unittest.TestCase):
    def test_independent_tables_and_dense_kernel_match_bruteforce_oracle(self):
        rng = np.random.default_rng(1427)
        sharp = np.full((7, 3), -1000.); sharp[:, 0] = 0; sharp[3, 0], sharp[3, 1] = -1000., 0.
        cases = [(rng.normal(size=(n, 3)), target) for n, target in
                 ((1, [1]), (2, [1, 2]), (3, [1, 1]), (4, [1, 2, 1]), (5, [1, 1]), (5, [1, 2, 1, 2]), (4, []), (6, [2, 2, 1]))]
        cases += [([[2, 0, 1]]*3, [1, 1]), (sharp, [1]), ([[0, -1000, -1000]]*3, [1, 1])]
        for logits, target in cases:
            with self.subTest(frames=len(logits), target=target):
                logp = logsoftmax(logits); expected = oracle(logp, target)
                a, b, z = v.tables(logp, target)
                self.assertAlmostEqual(z, expected['logZ'], places=11); self.assertLessEqual(abs(z-b[0, 0]), 1e-10)
                np.testing.assert_allclose(np.exp(a[1:]+b[1:]-z), expected['gamma'], rtol=0, atol=2e-12)
                hidden = rng.normal(size=(len(logp), 4)).astype(np.float32)
                for j in range(len(target)):
                    gamma = expected['gamma'][:, 2*j+1]; q = gamma/gamma.sum()
                    wq, wu, duration = v.weights(a, b, z, j)
                    np.testing.assert_allclose(wq, q, rtol=0, atol=2e-12)
                    np.testing.assert_allclose(wu, direct_u(q), rtol=0, atol=2e-12)
                    self.assertAlmostEqual(np.exp(duration), gamma.sum(), places=10)
                    expected64 = sum(q[k]*hidden[max(0, k-2):k+3].mean(0, dtype=np.float64) for k in range(len(q)))
                    np.testing.assert_allclose(v.weighted_vector(hidden, wu), expected64.astype(np.float32), rtol=0, atol=1e-6)

    def test_dense_kernel_edges_and_impossible_paths(self):
        for frames in range(1, 10):
            kernel = v.dense_kernel(frames)
            for k in range(frames):
                lo, hi = max(0, k-2), min(frames, k+3)
                column = np.zeros(frames); column[lo:hi] = 1./(hi-lo)
                np.testing.assert_array_equal(kernel[:, k], column)
        # Source-normalized edges, not a globally renormalized convolution.
        np.testing.assert_allclose(v.dense_kernel(7) @ np.array([.75, 0, 0, .25, 0, 0, 0]),
                                   [.25, .3, .3, .05, .05, .05, 0], rtol=0, atol=1e-15)
        for frames, target in ((1, [1, 1]), (2, [1, 1]), (3, [1, 1, 1]), (1, [1, 2])):
            with self.subTest(frames=frames, target=target), self.assertRaisesRegex(ValueError, 'Impossible'):
                v.tables(logsoftmax([[0, 0, 0]]*frames), target)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.fx = Synthetic(self.directory.name)
        self.clip, self.record, self.hidden, self.logp, self.saved, self.historical = replay_fixture(self.fx)

    def tearDown(self):
        self.directory.cleanup()

    def replay(self, saved=None, repeat=None, record=None, historical=None, hidden=None, logp=None):
        saved = copied(self.saved) if saved is None else saved
        return v.replay_clip(self.clip, record or self.record, self.hidden if hidden is None else hidden,
                             self.logp if logp is None else logp, saved, copied(saved) if repeat is None else repeat,
                             self.historical if historical is None else historical)

    def test_replay_without_core_and_historical_drift_is_descriptive_only(self):
        with core_blocked():
            baseline = self.replay()
        self.assertTrue(baseline['hardCrossProcessBitExact'] and baseline['repeatBitExact'])
        self.assertLessEqual(baseline['maximumCandidateReplayAbs'], v.CANDIDATE_ATOL)
        outcome = {k: x for k, x in baseline.items() if k != 'historicalHardDescriptive'}
        for drift, differing in ((0., 0), (2.**-19, 1), (3., 1)):
            with self.subTest(drift=drift):
                historical = self.saved['hard'].copy(); historical[0, 0] += np.float32(drift)
                record = dict(self.record, historicalHardDescriptive=f.historical_differences(self.saved['hard'], historical))
                result = self.replay(record=record, historical=historical)
                self.assertEqual({k: x for k, x in result.items() if k != 'historicalHardDescriptive'}, outcome)
                self.assertEqual(result['historicalHardDescriptive']['differingRows'], differing)
                self.assertEqual(result['historicalHardDescriptive']['rowMaxAbs'][1], 0.)
                self.assertIs(result['historicalHardDescriptive']['gate'], False)
                if drift: self.assertGreater(result['historicalHardDescriptive']['rowMaxAbs'][0], 0.)

    def test_hard_one_ulp_rejected_across_processes_candidate_uses_fixed_atol_only(self):
        j = int(np.argmin(np.abs(self.saved['candidate'][0])))
        hard = copied(self.saved); hard['hard'][0, j] = ulp(hard['hard'][0, j])
        with self.assertRaisesRegex(ValueError, 'across processes'): self.replay(saved=hard)
        near = copied(self.saved); near['candidate'][0, j] = ulp(near['candidate'][0, j])
        self.assertLessEqual(self.replay(saved=near)['maximumCandidateReplayAbs'], v.CANDIDATE_ATOL)
        far = copied(self.saved); far['candidate'][0, j] += np.float32(2e-6)
        with self.assertRaisesRegex(ValueError, 'candidate replay'): self.replay(saved=far)
        for key in ('candidate', 'hard'):
            repeat = copied(self.saved); repeat[key][1, j] = ulp(repeat[key][1, j])
            with self.subTest(repeat=key), self.assertRaisesRegex(ValueError, 'within-run repeat'): self.replay(repeat=repeat)

    def test_audit_identity_history_and_geometry_tampering_rejected(self):
        def rows(r): return r['audit']['rows']
        tampers = dict(
            qMass=lambda r: rows(r)[0].__setitem__('qMass', rows(r)[0]['qMass']+1e-9),
            centroid=lambda r: rows(r)[1].__setitem__('qCentroidFrame', rows(r)[1]['qCentroidFrame']+1e-9),
            outside=lambda r: rows(r)[1].__setitem__('qMassOutsideViterbiInterval', rows(r)[1]['qMassOutsideViterbiInterval']+1e-9),
            l2=lambda r: rows(r)[0]['vectorDistance'].__setitem__('l2', rows(r)[0]['vectorDistance']['l2']+1e-9),
            token=lambda r: rows(r)[1].__setitem__('tokenId', 4),
            logZ=lambda r: r['audit']['ctc'].__setitem__('logProbability', r['audit']['ctc']['logProbability']+1e-9),
            occupancy=lambda r: r['audit']['ctc']['tokenOccupancies'].__setitem__(0, r['audit']['ctc']['tokenOccupancies'][0]+1e-9),
            historyRow=lambda r: r['historicalHardDescriptive']['rowMaxAbs'].__setitem__(0, 0.),
            historyCount=lambda r: r['historicalHardDescriptive'].__setitem__('differingRows', 0))
        for name, tamper in tampers.items():
            record = copy.deepcopy(self.record); tamper(record)
            with self.subTest(tamper=name), self.assertRaises(ValueError): self.replay(record=record)
        for name, change in dict(logp=dict(logp=self.logp.astype(np.float64)), hidden=dict(hidden=self.hidden[:, :1023].copy()),
                                 saved=dict(saved={k: a.astype(np.float64) for k, a in self.saved.items()})).items():
            with self.subTest(geometry=name), self.assertRaises(ValueError): self.replay(**change)

    def test_all_ctc_numerical_diagnostics_are_replayed(self):
        for field in ('frameMassMaxAbs', 'forwardBackwardAbs', 'logNormalizationMaxAbs', 'invariantAtol'):
            record = copy.deepcopy(self.record)
            record['audit']['ctc'][field] += 1e-8
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'CTC audit'):
                self.replay(record=record)

    def test_independent_posterior_input_checks_do_not_use_core(self):
        with core_blocked():
            v.posterior_checks(self.logp, self.clip['fullTokens'])
            for name, data in dict(normalization=np.zeros_like(self.logp), dtype=self.logp.astype(np.float64),
                                   vocabulary=self.logp[:, :391], nonfinite=np.full_like(self.logp, np.nan),
                                   positive=np.full_like(self.logp, np.float32(1e-4))).items():
                with self.subTest(input=name), self.assertRaises(ValueError):
                    v.posterior_checks(data, self.clip['fullTokens'])


class VerifyRunTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.fx = Synthetic(self.directory.name)
        pin, _ = self.fx.run(); self.report = Path(pin['path']); self.run_dir = self.report.parent
        self.out = self.fx.root/'outputs/fresh/verification.json'

    def tearDown(self):
        self.directory.cleanup()

    def run_digests(self):
        return {p.name: e.digest(p) for p in self.run_dir.iterdir()}

    def verify(self, encoder, review=None, sha=None, separate=True):
        pid = os.getpid()+1 if separate else os.getpid()
        with self.fx.patched(encoder), patch.object(v.os, 'getpid', return_value=pid):
            return v.verify(self.fx.plan_path, sha or self.fx.sha, self.report, review or self.fx.review, self.out)

    def checked(self, report, run=None):
        with patch.object(v.os, 'getpid', return_value=os.getpid()+1):
            return v.checked_report(self.fx.plan, e.file_binding(self.fx.plan_path), report, run or self.run_dir,
                                    e.file_binding(self.fx.review), ENV)

    def test_separate_process_replay_success_is_complete_and_exclusive(self):
        before = self.run_digests(); encoder = Encoder(self.fx.hidden)
        with core_blocked():
            pin = self.verify(encoder)
        result = e.read_json(Path(pin['path']))
        self.assertEqual(encoder.calls, [c['audioPath'] for c in self.fx.plan['clips']])
        for key in ('complete', 'verified', 'separateProcess', 'sharedEncoder', 'independentTablesKernel',
                    'hardCrossProcessBitExact', 'repeatsBitExact', 'historicalHardDescriptiveOnly'):
            self.assertIs(result[key], True, key)
        self.assertEqual(result['additionalEncoderForwards'], 4); self.assertIs(result['coreHelpersUsedForCandidate'], False)
        self.assertEqual(result['orderedCoverage'], IDS); self.assertEqual([c['clipId'] for c in result['clips']], IDS)
        self.assertEqual([c['historicalHardDescriptive']['differingRows'] for c in result['clips']], [0, 0, 1, 1])
        self.assertEqual((result['candidateAbsoluteTolerance'], result['auditAbsoluteTolerance']), (1e-6, 1e-10))
        self.assertEqual(result['report'], e.file_binding(self.report)); self.assertEqual(result['plan'], e.file_binding(self.fx.plan_path))
        self.assertEqual(result['review'], e.file_binding(self.fx.review)); self.assertNotEqual(result['processId'], result['runnerProcessId'])
        self.assertEqual(set(result['sourcePins']), {p.name for p in f.new_sources()})
        self.assertNotIn('cachedHardExact', result)
        for flag in f.FLAGS: self.assertIs(result[flag], False)
        self.assertEqual(self.run_digests(), before)
        with self.assertRaisesRegex(ValueError, 'no restart'): self.verify(Encoder(self.fx.hidden))

    def test_review_and_plan_hash_precede_report_arrays_and_encoder(self):
        other = self.fx.root/'outputs/fresh/hold.json'
        e.write_new(other, dict(planSha256=self.fx.sha, verdict='hold', blockingFindings=['x'], independent=True, reviewer='synthetic'))
        for name, change in dict(review=dict(review=other), sha=dict(sha='0'*64)).items():
            encoder = Encoder(self.fx.hidden)
            with self.subTest(case=name), self.fx.patched(encoder), patch.object(v.os, 'getpid', return_value=os.getpid()+1), \
                 patch.object(f, 'checked_plan') as checked, patch.object(e, 'checked_references') as references:
                with self.assertRaises(ValueError):
                    v.verify(self.fx.plan_path, change.get('sha', self.fx.sha), self.report, change.get('review', self.fx.review), self.out)
                checked.assert_not_called(); references.assert_not_called()
            self.assertEqual(encoder.calls, []); self.assertFalse(self.out.exists())

    def test_bad_full_vocabulary_probabilities_fail_before_audio_or_forward(self):
        # Keep hash guards satisfied to isolate the independent numerical barrier.
        # checked_plan is a synthetic stub; no real declaration or data is changed.
        clip = self.fx.plan['clips'][0]
        path = Path(clip['posterior']['path'])
        np.zeros((5, 392), dtype='<f4').tofile(path)
        clip['posterior'] = e.file_binding(path)
        encoder = Encoder(self.fx.hidden)
        with self.fx.patched(encoder), patch.object(v.os, 'getpid', return_value=os.getpid()+1), \
             patch.object(e, 'read_rating_pcm') as audio:
            with self.assertRaisesRegex(ValueError, 'full-vocabulary normalization'):
                v.verify(self.fx.plan_path, self.fx.sha, self.report, self.fx.review, self.out)
            audio.assert_not_called()
        self.assertEqual(encoder.calls, [])
        failure = e.read_json(self.out)
        self.assertIs(failure['complete'], False)
        self.assertEqual(failure['additionalEncoderForwards'], 0)

    def test_mismatch_source_runtime_or_same_process_stops_route_with_preserved_failure(self):
        def drift(call, hidden):
            if call == 3: hidden[:, 0] += 1e-3
        cases = dict(numerical=(drift, {}, True, 'differs', 2, 3),
                     source=(None, dict(plan=ValueError('Fresh plan source changed')), True, 'source changed', 0, 0),
                     runtime=(None, dict(env={'platform': 'other'}), True, 'runtime', 0, 0),
                     sameProcess=(None, {}, False, 'process', 0, 0))
        for name, (perturb, patches, separate, message, clips, forwards) in cases.items():
            with self.subTest(case=name):
                self.out = self.fx.root/f'outputs/fresh/verification-{name}.json'
                before = self.run_digests(); encoder = Encoder(self.fx.hidden, perturb)
                pid = os.getpid()+1 if separate else os.getpid()
                # Case patches enter after fx.patched so they override its defaults.
                with self.fx.patched(encoder), patch.object(v.os, 'getpid', return_value=pid), contextlib.ExitStack() as stack:
                    if 'plan' in patches: stack.enter_context(patch.object(f, 'checked_plan', side_effect=patches['plan']))
                    if 'env' in patches: stack.enter_context(patch.object(e, 'environment', return_value=patches['env']))
                    with self.assertRaisesRegex(ValueError, message):
                        v.verify(self.fx.plan_path, self.fx.sha, self.report, self.fx.review, self.out)
                failure = e.read_json(self.out)
                self.assertIs(failure['complete'], False); self.assertIs(failure['cpuRouteStopped'], True)
                self.assertEqual((failure['verifiedClips'], failure['additionalEncoderForwards'], len(encoder.calls)), (clips, forwards, forwards))
                self.assertIn(message, failure['errorMessage']); self.assertIs(failure['restartAllowed'], False)
                self.assertEqual(self.run_digests(), before)
                with self.assertRaisesRegex(ValueError, 'no restart'): self.verify(Encoder(self.fx.hidden))

    def test_report_binding_order_coverage_and_flag_mismatches_rejected(self):
        report = e.read_json(self.report)
        self.assertEqual(self.checked(copy.deepcopy(report)), IDS)
        def swap(r): r['repeats']['p0']['forward'], r['repeats']['p1']['forward'] = 6, 5
        mutations = dict(
            order=lambda r: r['records'].reverse(),
            duplicate=lambda r: r['records'].__setitem__(1, copy.deepcopy(r['records'][0])),
            missingRepeat=lambda r: r['repeats'].pop('p3'),
            repeatOrder=swap,
            repeatNotExact=lambda r: r['repeats']['p1'].__setitem__('hardBitExact', False),
            roles=lambda r: r['records'][0].__setitem__('roles', []),
            artifact=lambda r: r['records'][2]['artifact'].__setitem__('sha256', '0'*64),
            incomplete=lambda r: r.__setitem__('complete', False),
            forwards=lambda r: r.__setitem__('encoderForwards', 7),
            runtime=lambda r: r.__setitem__('environment', {'platform': 'other'}),
            review=lambda r: r['review'].__setitem__('sha256', '0'*64),
            plan=lambda r: r['plan'].__setitem__('sha256', '0'*64),
            runner=lambda r: r['runner'].__setitem__('sha256', '0'*64),
            reference=lambda r: r['references']['reference'].__setitem__('sha256', '1'*64),
            model=lambda r: r.__setitem__('model', {'x': dict(path='x', sha256='0'*64)}),
            training=lambda r: r.__setitem__('trainingPerformed', True),
            labels=lambda r: r.__setitem__('labelsRead', True),
            clinical=lambda r: r.__setitem__('clinicalUseEligible', True),
            cachedHistorical=lambda r: r.__setitem__('cachedHardExact', True),
            historicalGate=lambda r: r.__setitem__('historicalHardGate', True))
        for name, mutate in mutations.items():
            changed = copy.deepcopy(report); mutate(changed)
            with self.subTest(mutation=name), self.assertRaises(ValueError): self.checked(changed)
        with self.assertRaisesRegex(ValueError, 'process'):
            v.checked_report(self.fx.plan, e.file_binding(self.fx.plan_path), report, self.run_dir, e.file_binding(self.fx.review), ENV)

    def test_run_directory_file_tampering_rejected(self):
        def record(run):
            path = run/'p1.json'; value = e.read_json(path); value['seconds'] += 1; path.write_text(json.dumps(value))
        tampers = dict(extra=lambda run: (run/'extra.json').write_text('{}'),
                       failure=lambda run: (run/'failure.json').write_text('{}'),
                       repeat=lambda run: (run/'p2-repeat.npz').write_bytes(b'changed'),
                       record=record)
        for name, tamper in tampers.items():
            with self.subTest(tamper=name), tempfile.TemporaryDirectory() as directory:
                fx = Synthetic(directory); pin, _ = fx.run(); run = Path(pin['path']).parent
                tamper(run)
                with patch.object(v.os, 'getpid', return_value=os.getpid()+1), self.assertRaises(ValueError):
                    v.checked_report(fx.plan, e.file_binding(fx.plan_path), e.read_json(run/'report.json'), run,
                                     e.file_binding(fx.review), ENV)


if __name__ == '__main__': unittest.main()
