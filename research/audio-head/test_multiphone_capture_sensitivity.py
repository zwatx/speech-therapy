"""Synthetic-only capture diagnostic tests; no encoder inference or real labels."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

import multiphone_capture_sensitivity as capture


class CaptureTests(unittest.TestCase):
    def waveform(self):
        x = .2*np.sin(np.arange(16000)*.031)+.1*np.sin(np.arange(16000)*.057)
        return capture.pcm16_bytes(x)[1]

    def metadata(self, n=10):
        clips = []; rows = []
        for i in range(n*2):
            speaker = f'{i//2:04}'
            clips.append({'id': f'{i:09}', 'speakerId': speaker, 'age': 6+i//2%7, 'sampleCount': 16000,
                          'audioPath': '/original/'+str(i), 'audioSha256': str(i)})
            rows.append({'clipIndex': i, 'trainingEligible': True, 'speakerId': speaker, 'raterCounts': [0, 0, 5]})
        return {'authorPartition': 'train', 'clips': clips, 'rows': rows}, {
            'authorPartition': 'train', 'folds': [{'innerValidationRows': list(range(n*2)),
                'innerValidationClips': list(range(n*2)), 'innerFitRows': []}]}

    def test_selection_hashes_metadata_only_and_retains_all_if_fewer(self):
        cohort, splits = self.metadata()
        chosen, available = capture.select_clips(cohort, splits)
        self.assertEqual((len(chosen), available), (8, 10))
        self.assertEqual(len({cohort['clips'][i]['speakerId'] for i in chosen}), 8)
        for row in cohort['rows']: row['raterCounts'] = [5, 0, 0]
        for clip in cohort['clips']: clip.update(rms=1e-9, durationSeconds=0.1)
        splits['folds'][0]['innerValidationClips'].reverse()
        self.assertEqual(capture.select_clips(cohort, splits)[0], chosen)
        self.assertEqual(len(capture.select_clips(*self.metadata(5))[0]), 5)
        splits['folds'][0]['innerFitRows'] = [chosen[0]]
        with self.assertRaisesRegex(ValueError, 'fitting'): capture.select_clips(cohort, splits)

    def test_noise_determinism_snr_and_source_not_mutated(self):
        samples = self.waveform(); before = samples.copy(); sha = 'a'*64
        for condition, level in [('noise20db', 20), ('noise10db', 10)]:
            payload, a, info = capture.transform(samples, condition, sha)
            payload2, b, info2 = capture.transform(samples, condition, sha)
            self.assertEqual(payload, payload2); self.assertEqual(info, info2)
            np.testing.assert_array_equal(a, b); np.testing.assert_array_equal(samples, before)
            self.assertAlmostEqual(info['measuredSNRdBAfterPCM16'], level, places=2)
            self.assertEqual(info['commonSignalAndNoiseGainBeforeQuantization'], 1)
        changed = capture.transform(samples, 'noise10db', 'b'*64)[1]
        self.assertFalse(np.array_equal(a, changed))
        gain = capture.transform(samples, 'gain025', sha)[1]
        self.assertLessEqual(float(np.max(np.abs(gain-samples*.25))), .5/32768)

    def test_noise_common_gain_preserves_snr_without_clipping(self):
        x = capture.pcm16_bytes(.96*np.sin(np.arange(16000)*.031))[1]
        _, values, info = capture.transform(x, 'noise10db', 'b'*64)
        self.assertLess(info['commonSignalAndNoiseGainBeforeQuantization'], 1)
        self.assertLessEqual(np.max(np.abs(values)), .98002)
        self.assertEqual(info['quality']['railSamples'], 0)
        self.assertAlmostEqual(info['measuredSNRdBAfterPCM16'], 10, places=2)
        with self.assertRaisesRegex(ValueError, 'silent'): capture.transform(np.zeros(1600), 'noise20db', 'a')

    def test_original_file_preserved_and_wavs_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); source = directory/'original.wav'
            source.write_bytes(capture.pcm16_bytes(self.waveform())[0]); sha = capture.digest(source)
            before = source.read_bytes()
            variants = capture.write_variants(source, sha, directory/'derived', 20260926)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(Path(variants[0]['audioPath']).read_bytes(), before)
            self.assertEqual([v['condition'] for v in variants], list(capture.CONDITIONS))
            self.assertEqual({v['sampleCount'] for v in variants}, {16000})
            with self.assertRaisesRegex(ValueError, 'exists'):
                capture.write_variants(source, sha, directory/'derived', 20260926)

    def test_original_parity_is_exact_where_declared_and_fails_closed(self):
        values = np.array([[1, 2]], dtype=np.float32)
        self.assertEqual(capture.assert_parity(values, values, 0, 'scalars'), 0)
        changed = values.copy(); changed[0, 0] = np.nextafter(changed[0, 0], np.float32(2))
        with self.assertRaisesRegex(ValueError, 'do not relax'): capture.assert_parity(changed, values, 0, 'CTC')
        self.assertGreater(capture.assert_parity(changed, values, 2e-6, 'pooled'), 0)
        with self.assertRaisesRegex(ValueError, 'shapes'): capture.assert_parity(values, values[:, :1], 1, 'shape')

    def test_target_identity_order_rejected(self):
        cohort, splits = self.metadata(1); indices, _ = capture.select_clips(cohort, splits)
        index = indices[0]; source = cohort['clips'][index]
        row = {'rowIndex': index, 'rowId': source['id']+':B', 'clipId': source['id'], 'targetId': 0,
               'targetPhone': 'B', 'canonicalIndex': 0, 'wordIndex': 0, 'phoneIndex': 0}
        canonical = {**source, 'canonicalPhones': ['B'], 'mappedTokenIds': [4], 'mappingAmbiguities': [],
                     'targetRows': [row]}
        variants = [{'condition': k, 'audioPath': '/derived/'+k, 'audioSha256': source['audioSha256'] if k == 'original' else k,
                     'sampleCount': 16000} for k in capture.CONDITIONS]
        clip = {**canonical, 'clipIndex': index, 'targets': [row], 'variants': variants}
        plan = {'recipe': {'maximumSpeakers': 8, 'seed': 20260926}, 'clips': [clip], 'selectedSpeakers': 1,
                'availableChildSpeakers': 1, 'variantCount': 4, 'bindings': {
                    'derived/'+source['id']+'/'+v['condition']: {'path': v['audioPath'], 'sha256': v['audioSha256']} for v in variants}}
        manifest, original = {'clips': [canonical]}, {'rows': [row]}
        capture.validate_selected_plan(plan, cohort, splits, manifest, original)
        changed = copy.deepcopy(plan); changed['clips'][0]['targets'][0]['targetPhone'] = 'P'
        with self.assertRaisesRegex(ValueError, 'target identity'):
            capture.validate_selected_plan(changed, cohort, splits, manifest, original)
        changed = copy.deepcopy(plan); changed['clips'][0]['targets'] = []
        with self.assertRaisesRegex(ValueError, 'coverage'):
            capture.validate_selected_plan(changed, cohort, splits, manifest, original)

    def test_recomputed_windows_keep_target_order_and_scalar_order(self):
        probabilities = np.full((7, 392), .01/390)
        probabilities[:, 0] = .89; probabilities[:, 4] = .1
        probabilities[2, 0], probabilities[2, 4] = .1, .89
        probabilities /= probabilities.sum(1, keepdims=True)
        logp = np.log(probabilities).astype(np.float32)
        clip = {'mappedTokenIds': [4], 'targets': [{'rowIndex': 7, 'rowId': 'example:B', 'clipId': 'example',
            'targetId': 0, 'targetPhone': 'B', 'canonicalIndex': 0, 'wordIndex': 0, 'phoneIndex': 0}]}
        frames = np.arange(7*1024, dtype=np.float32).reshape(7, 1024)
        rows, scalars, pooled, _ = capture.aligned_features(logp, frames, clip, {'minimumTargetFramesDiagnostic': 2})
        self.assertEqual(rows[0]['rowId'], 'example:B'); self.assertEqual(rows[0]['intervalFrames'], [2, 3])
        self.assertEqual(rows[0]['estimatedPoolingWindowFrames'], [0, 5])
        self.assertEqual(scalars.shape, (1, 13)); self.assertEqual(scalars[0, 10], 1)
        self.assertAlmostEqual(float(scalars[0, 9]), .02)
        np.testing.assert_array_equal(pooled[0], frames[:5].mean(0, dtype=np.float64).astype(np.float32))

    def test_probability_shift_formula_has_no_labels(self):
        value = capture.probability_shift([[.1, .2, .7], [.5, .2, .3]], [[.2, .3, .5], [.3, .2, .5]])
        self.assertAlmostEqual(value['meanTotalVariation'], .2)
        self.assertAlmostEqual(value['meanExpectedRatingShift'], .05)
        self.assertAlmostEqual(value['meanAbsoluteExpectedRatingShift'], .35)
        self.assertEqual(value['argmaxClassChanges'], 1)
        with self.assertRaisesRegex(ValueError, 'probabilities'):
            capture.probability_shift([[0, 0, 0]], [[1, 0, 0]])

    def test_binding_guard_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source'; path.write_text('original')
            binding = {'a': capture.pin(path)}; capture.guard(binding)
            path.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'changed'): capture.guard(binding)

    def test_posterior_loaded_bytes_keep_authoritative_pin_after_later_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'values.f32'
            original = np.full((4, 392), -np.log(392), dtype='<f4')
            path.write_bytes(original.tobytes()); sha = capture.digest(path)
            values, binding = capture.load_posteriors(path, sha)
            path.write_bytes(np.zeros_like(original).tobytes())
            np.testing.assert_array_equal(values, original)
            self.assertEqual(binding['sha256'], sha)
            with self.assertRaisesRegex(ValueError, 'changed'): capture.guard({'posteriors': binding})
            with self.assertRaisesRegex(ValueError, 'artifact differs'): capture.load_posteriors(path, sha)


if __name__ == '__main__': unittest.main()
