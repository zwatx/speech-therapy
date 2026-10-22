"""Synthetic-only full verifier tests: tiny declared cohort, stub encoder and temporary run artifacts."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from posterior_pooling import extract as e, fresh_preflight as f, fresh_verify as v, full_extract as x, full_verify as y
from posterior_pooling.test_fresh_preflight import ENV, Encoder
from posterior_pooling.test_fresh_verify import core_blocked
from posterior_pooling.test_full_extract import IDS, S, Cohort, ulp


def rewrite(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    return e.file_binding(Path(path))


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.reset(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def run_digests(self):
        return {p.name: e.digest(p) for p in self.run_dir.iterdir()}

    def verify(self, encoder, separate=True, sha=None, review=None):
        pid = os.getpid()+1 if separate else os.getpid()
        with self.fx.patched(encoder), patch.object(y.os, 'getpid', return_value=pid):
            return y.verify(self.fx.plan_path, sha or self.fx.sha, self.report, review or self.fx.review, self.out)

    def checked(self, report):
        with self.fx.patched(Encoder(self.fx.hidden)), patch.object(y.os, 'getpid', return_value=os.getpid()+1):
            return y.checked_report(self.fx.plan, e.file_binding(self.fx.plan_path), report, self.run_dir, e.file_binding(self.fx.review), ENV)

    def failed(self, encoder, message, counts):
        """Verification fails, preserves its receipt and the run directory; (diagnosed clips, replayed clips, forwards)."""
        before = self.run_digests()
        with self.assertRaisesRegex(ValueError, message): self.verify(encoder)
        failure = e.read_json(self.out)
        self.assertIs(failure['complete'], False); self.assertIs(failure['fullRouteStopped'], True); self.assertIs(failure['restartAllowed'], False)
        self.assertEqual((failure['diagnosticsVerifiedClips'], failure['acousticReplayClips'], failure['additionalEncoderForwards']), counts)
        self.assertEqual(len(encoder.calls), counts[2]); self.assertIn(message, failure['errorMessage'])
        self.assertEqual(set(failure['sourceBindings']), {p.name for p in x.new_sources()})
        for flag in f.FLAGS: self.assertIs(failure[flag], False)
        self.assertEqual({k: d for k, d in self.run_digests().items() if k != 'report.json'},
                         {k: d for k, d in before.items() if k != 'report.json'})
        with self.assertRaisesRegex(ValueError, 'no restart'): self.verify(Encoder(self.fx.hidden))
        return failure

    def rebind_record(self, cid, mutate):
        """Consistently tamper one cohort record and its report binding, isolating the independent replay."""
        report = e.read_json(self.report); record = e.read_json(self.run_dir/(cid+'.json')); mutate(record)
        entry = next(r for r in report['records'] if r['clipId'] == cid); entry['record'] = rewrite(self.run_dir/(cid+'.json'), record)
        rewrite(self.report, report)

    def test_separate_process_full_diagnostics_and_four_probe_replay_succeed(self):
        before = self.run_digests(); encoder = Encoder(self.fx.hidden)
        with core_blocked():
            pin = self.verify(encoder)
        result = e.read_json(Path(pin['path']))
        self.assertEqual(encoder.calls, self.fx.paths(S))
        for key in ('complete', 'verified', 'separateProcess', 'sharedEncoder', 'independentTablesKernel', 'independentDPDenseKernel',
                    'matricesEqualUnits', 'rowCoverageExact', 'frozenPreflightExact', 'cohortProbesExact', 'repeatsBitExact',
                    'hardCrossProcessBitExact', 'historicalHardDescriptiveOnly'):
            self.assertIs(result[key], True, key)
        self.assertIs(result['coreHelpersUsedForCandidate'], False); self.assertIs(result['fullAcousticReconstruction'], False)
        self.assertEqual((result['diagnosticsVerifiedClips'], result['diagnosticsVerifiedPositions'], result['acousticReplayPositions']), (7, 14, 8))
        self.assertEqual((result['runnerForwards'], result['additionalEncoderForwards'], result['totalActualForwards']), (15, 4, 19))
        self.assertEqual(result['orderedClipIds'], IDS); self.assertEqual([c['clipId'] for c in result['probes']], S)
        self.assertEqual((result['candidateAbsoluteTolerance'], result['auditAbsoluteTolerance']), (1e-6, 1e-10))
        self.assertEqual(result['historicalHardDescriptive']['differingRows'], 1); self.assertIs(result['historicalHardDescriptive']['gate'], False)
        self.assertEqual(result['report'], e.file_binding(self.report)); self.assertNotEqual(result['processId'], result['runnerProcessId'])
        self.assertEqual(set(result['sourcePins']), {p.name for p in x.new_sources()})
        for flag in f.FLAGS: self.assertIs(result[flag], False)
        self.assertEqual(self.run_digests(), before)
        with self.assertRaisesRegex(ValueError, 'no restart'): self.verify(Encoder(self.fx.hidden))

    def test_review_and_plan_hash_precede_report_arrays_and_encoder(self):
        other = self.fx.root/'outputs/full/hold.json'
        e.write_new(other, dict(planSha256=self.fx.sha, verdict='hold', blockingFindings=['x'], independent=True, reviewer='synthetic'))
        for name, change in dict(review=dict(review=other), sha=dict(sha='0'*64)).items():
            encoder = Encoder(self.fx.hidden)
            with self.subTest(case=name), self.fx.patched(encoder), patch.object(y.os, 'getpid', return_value=os.getpid()+1), \
                 patch.object(x, 'checked_plan') as checked, patch.object(e, 'checked_references') as references:
                with self.assertRaises(ValueError):
                    y.verify(self.fx.plan_path, change.get('sha', self.fx.sha), self.report, change.get('review', self.fx.review), self.out)
                checked.assert_not_called(); references.assert_not_called()
            self.assertEqual(encoder.calls, []); self.assertFalse(self.out.exists())

    def test_artifact_drift_during_probe_forwards_invalidates_completion(self):
        targets = ('c0.npz', 'c0.json', 'hard.npy', 'start-'+S[0]+'.npz', 'started.json')
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                self.reset(directory)
                def corrupt(call, hidden):
                    if call == 1:
                        path = self.run_dir/target
                        if target == 'started.json':
                            started = e.read_json(path); started['labelsRead'] = True; rewrite(path, started)
                        else:
                            path.write_bytes(b'late corruption after all diagnostics')
                encoder = Encoder(self.fx.hidden, corrupt)
                with self.assertRaises(ValueError): self.verify(encoder)
                failure = e.read_json(self.out)
                self.assertIs(failure['complete'], False)
                self.assertEqual((failure['stage'], failure['diagnosticsVerifiedClips'], failure['additionalEncoderForwards']),
                                 ('final guards', 7, 4))
                self.assertEqual(encoder.calls, self.fx.paths(S))
                self.assertIs(failure['restartAllowed'], False)
                self.assertTrue((self.run_dir/target).exists())

    def test_same_process_or_probe_acoustic_drift_stops_route(self):
        encoder = Encoder(self.fx.hidden)
        with patch.object(y, 'replay_diagnostics') as diagnostics:
            with self.fx.patched(encoder), patch.object(y.os, 'getpid', return_value=os.getpid()), self.assertRaisesRegex(ValueError, 'process'):
                y.verify(self.fx.plan_path, self.fx.sha, self.report, self.fx.review, self.out)
            diagnostics.assert_not_called()
        self.assertEqual(encoder.calls, []); self.assertIs(e.read_json(self.out)['complete'], False)
        def drift(call, hidden):
            if call == 2: hidden[:, 0] += 1e-3
        self.out = self.fx.root/'outputs/full/verification-drift.json'
        self.failed(Encoder(self.fx.hidden, drift), 'differs', (7, 1, 2))

    def test_every_clip_diagnostic_tamper_fails_before_audio_or_model(self):
        def rows(r): return r['audit']['rows']
        tampers = dict(
            qMass=lambda r: rows(r)[0].__setitem__('qMass', rows(r)[0]['qMass']+1e-9),
            centroid=lambda r: rows(r)[1].__setitem__('uCentroidFrame', rows(r)[1]['uCentroidFrame']+1e-9),
            outside=lambda r: rows(r)[1].__setitem__('qMassOutsideViterbiInterval', rows(r)[1]['qMassOutsideViterbiInterval']+1e-9),
            cosine=lambda r: rows(r)[0]['vectorDistance'].__setitem__('cosineDistance', rows(r)[0]['vectorDistance']['cosineDistance']+1e-9),
            state=lambda r: rows(r)[0].__setitem__('state', 3),
            occupancy=lambda r: r['audit']['ctc']['tokenOccupancies'].__setitem__(1, r['audit']['ctc']['tokenOccupancies'][1]+1e-9),
            frameMass=lambda r: r['audit']['ctc'].__setitem__('frameMassMaxAbs', r['audit']['ctc']['frameMassMaxAbs']+1e-8),
            history=lambda r: r['historicalHardDescriptive'].__setitem__('differingRows', 1))
        # Last non-probe cohort clip: every earlier clip already replayed; no audio or model is touched.
        for name, tamper in tampers.items():
            with self.subTest(tamper=name), tempfile.TemporaryDirectory() as directory:
                self.reset(directory); self.rebind_record('c2', tamper)
                # Blocking patches enter after fx.patched so they override its model/audio stubs.
                with self.fx.patched(Encoder(self.fx.hidden)), patch.object(y.os, 'getpid', return_value=os.getpid()+1), \
                     patch.object(e, 'load_encoder', side_effect=AssertionError('model loaded')), \
                     patch.object(e, 'read_rating_pcm', side_effect=AssertionError('audio read')), self.assertRaises(ValueError):
                    y.verify(self.fx.plan_path, self.fx.sha, self.report, self.fx.review, self.out)
                failure = e.read_json(self.out)
                self.assertEqual((failure['stage'], failure['diagnosticsVerifiedClips'], failure['additionalEncoderForwards']), ('diagnostics', 5, 0))

    def test_replay_diagnostics_is_independent_of_core_and_uses_fixed_audit_tolerance(self):
        clip = self.fx.by_id['c1']; record = e.read_json(self.run_dir/'c1.json')
        values = v.load_arrays(record['artifact'], clip)
        logp = np.fromfile(clip['posterior']['path'], dtype='<f4').reshape(5, 392)
        with core_blocked():
            posterior = v.posterior_checks(logp, clip['fullTokens'])
            self.assertEqual(y.replay_diagnostics(clip, record, values, posterior)['positions'], 2)
            for shift, ok in ((.5e-10, True), (2e-10, False)):
                changed = copy.deepcopy(record); changed['audit']['rows'][0]['qEffectiveFrames'] += shift
                with self.subTest(shift=shift):
                    if ok: y.replay_diagnostics(clip, changed, values, posterior)
                    else: self.assertRaises(ValueError, y.replay_diagnostics, clip, changed, values, posterior)
            # A persisted vector drift is caught by the replayed candidate/hard distances.
            moved = {k: a.copy() for k, a in values.items()}; moved['hard'][0] += np.float32(1e-3)
            with self.assertRaisesRegex(ValueError, 'Row audit differs'): y.replay_diagnostics(clip, record, moved, posterior)

    def test_bad_full_vocabulary_probabilities_of_any_clip_fail_before_audio_or_forward(self):
        clip = self.fx.by_id['c2']; path = Path(clip['posterior']['path'])
        np.zeros((5, 392), dtype='<f4').tofile(path)
        # checked_plan is a synthetic stub; the declared binding follows the tampered test payload.
        next(c for c in self.fx.plan['clips'] if c['id'] == 'c2')['posterior'] = e.file_binding(path)
        failure = self.failed(Encoder(self.fx.hidden), 'full-vocabulary normalization', (5, 0, 0))
        self.assertEqual(failure['stage'], 'diagnostics')

    def test_matrix_or_end_probe_unit_one_ulp_mismatch_rejected_before_model(self):
        # Bindings are rewritten consistently so only the array-equality gates can fail.
        # Row 3 belongs to the fourth cohort clip; the end probe is checked after all diagnostics.
        for target, message, counts in (('matrix', 'Matrix slice differs', (3, 0, 0)), ('end', 'probe arrays differ', (7, 0, 0))):
            for key in x.KEYS:
                with self.subTest(target=target, key=key), tempfile.TemporaryDirectory() as directory:
                    self.reset(directory); report = e.read_json(self.report)
                    if target == 'matrix':
                        path = self.run_dir/(key+'.npy'); matrix = np.load(path); matrix[3, 7] = ulp(matrix[3, 7]); path.unlink()
                        report['matrices'][key] = x.save_matrix(path, matrix)
                    else:
                        name = 'end-'+S[1]; record = e.read_json(self.run_dir/(name+'.json'))
                        values = v.load_arrays(record['artifact'], self.fx.by_id[S[1]]); values[key][1, 5] = ulp(values[key][1, 5])
                        (self.run_dir/(name+'.npz')).unlink(); record['artifact'] = f.save_arrays(self.run_dir/(name+'.npz'), values)
                        rewrite(self.run_dir/(name+'.json'), record); report['end'][1] = record
                    rewrite(self.report, report)
                    self.failed(Encoder(self.fx.hidden), message, counts)

    def reset(self, directory):
        self.fx = Cohort(directory); pin, _ = self.fx.run(); self.report = Path(pin['path']); self.run_dir = self.report.parent
        self.out = self.fx.root/'outputs/full/verification.json'

    def test_report_binding_order_coverage_flag_and_directory_tampering_rejected(self):
        report = e.read_json(self.report)
        self.assertEqual(self.checked(copy.deepcopy(report)), S+IDS+S)
        mutations = dict(
            order=lambda r: r['records'].reverse(),
            duplicate=lambda r: r['records'].__setitem__(1, copy.deepcopy(r['records'][0])),
            missing=lambda r: r['records'].pop(),
            startNotFrozen=lambda r: r['start'][0].__setitem__('hardFrozenBitExact', False),
            endNotCohort=lambda r: r['end'][2].__setitem__('candidateCohortBitExact', False),
            forwards=lambda r: r.__setitem__('encoderForwards', 14),
            counts=lambda r: r['forwardCounts'].__setitem__('end', 3),
            runner=lambda r: r['runner'].__setitem__('sha256', '0'*64),
            prerequisites=lambda r: r['prerequisites'].__setitem__('bindings', {'x': 1}),
            sourcePins=lambda r: r['sourcePins'].pop('full_verify.py'),
            matrixShape=lambda r: r['matrices']['hard'].__setitem__('shape', [13, 1024]),
            cohortArtifact=lambda r: r['records'][3]['artifact'].__setitem__('sha256', '0'*64),
            frozenFlag=lambda r: r.__setitem__('frozenPreflightExact', False),
            fits=lambda r: r.__setitem__('fitsPerformed', True),
            labels=lambda r: r.__setitem__('labelsRead', True),
            historicalGate=lambda r: r.__setitem__('historicalHardGate', True))
        for name, mutate in mutations.items():
            changed = copy.deepcopy(report); mutate(changed)
            with self.subTest(mutation=name), self.assertRaises(ValueError): self.checked(changed)
        with self.fx.patched(Encoder(self.fx.hidden)), patch.object(y.os, 'getpid', return_value=report['processId']), self.assertRaisesRegex(ValueError, 'process'):
            y.checked_report(self.fx.plan, e.file_binding(self.fx.plan_path), report, self.run_dir, e.file_binding(self.fx.review), ENV)
        tampers = dict(extra=lambda run: (run/'extra.json').write_text('{}'),
                       failure=lambda run: (run/'failure.json').write_text('{}'),
                       matrix=lambda run: (run/'hard.npy').write_bytes(b'changed'),
                       start=lambda run: (run/('start-'+S[0]+'.npz')).write_bytes(b'changed'),
                       record=lambda run: (run/'c1.json').write_text('{}'))
        for name, tamper in tampers.items():
            with self.subTest(tamper=name), tempfile.TemporaryDirectory() as directory:
                self.reset(directory); tamper(self.run_dir)
                with self.assertRaises(ValueError): self.checked(e.read_json(self.run_dir/'report.json'))


if __name__ == '__main__': unittest.main()
