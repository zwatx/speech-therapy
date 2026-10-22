"""Research combined-filter tests; mocked VAD inference never loads a model."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import torch
import multiphone_vad_filter as filtering

raw = filtering.raw


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=raw.HERE/'outputs')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.audio = self.root/'audio.wav'
        self.audio.write_bytes(b'fake audio; decoder mocked')
        self.original = dict(inputBindings={'audio': raw.binding(self.audio)},
            ctcRuntime={'sampleCount': 8192}, targets=[dict(id='t', targetPhone='B', wordIndex=0,
            phoneIndex=0, subjectiveCorpusRatingProbabilities=[0.1, 0.2, 0.7])])
        self.source = self.root/'raw.json'
        raw.write_json(self.source, self.original)
        self.sha = raw.digest(self.source)

    def run_mocked(self, phone=True, vad=True, error=None):
        output = self.root/'result'
        fake_model = self.root/'model.jit'; fake_model.write_bytes(b'fake model')
        fake_helper = self.root/'helper.py'; fake_helper.write_bytes(b'fake helper')
        pins = {'vendor/silero_vad.jit': raw.binding(fake_model), 'vendor/utils_vad.py': raw.binding(fake_helper)}
        def evidence(report, sha, destination):
            raw.read_bound_json(report, sha)
            result = dict(sourceReport=raw.binding(report, sha), inputBindings=self.original['inputBindings'],
                          decision={'ratingAvailable': phone, 'reasons': [] if phone else ['no-recognized-phone-evidence']})
            raw.write_json(destination, result)
            return dict(report=str(destination), sha256=raw.digest(destination))
        inferred = dict(vad=vad, probabilities=[.9 if vad else .1]*16,
                        timestamps=[dict(start=0, end=8192)] if vad else [])
        with patch.object(filtering, 'approved_inputs', return_value=pins), \
             patch.object(filtering.gate, 'filter_report', side_effect=evidence), \
             patch.object(raw, 'read_rating_pcm', return_value=torch.zeros(8192)), \
             patch.object(filtering.study, 'load_helper', return_value=object()), \
             patch.object(filtering.torch.jit, 'load', return_value=MagicMock()), \
             patch.object(filtering.study, 'infer', side_effect=error, return_value=inferred):
            if error:
                with self.assertRaises(ValueError): filtering.filter_report(self.source, self.sha, output)
                self.assertFalse((output/'finalreport.json').exists())
                self.assertTrue((output/'phone-evidence.json').exists())
                return
            result = filtering.filter_report(self.source, self.sha, output)
        self.assertEqual(raw.digest(self.source), self.sha)
        return json.loads(Path(result['report']).read_text())

    def test_vad_only_rejection_masks_all_vectors(self):
        result = self.run_mocked(phone=True, vad=False)
        self.assertFalse(result['decision']['ratingAvailable'])
        self.assertTrue(all(t['subjectiveCorpusRatingProbabilities'] is None for t in result['targets']))

    def test_phone_only_rejection_masks_all_vectors(self):
        result = self.run_mocked(phone=False, vad=True)
        self.assertIsNone(result['targets'][0]['subjectiveCorpusRatingProbabilities'])

    def test_accepted_vectors_preserved(self):
        result = self.run_mocked()
        self.assertEqual(result['targets'], self.original['targets'])
        self.assertTrue(result['decision']['ratingAvailable'])
        self.assertFalse(result['learnerFeedbackEligible'])

    def test_inference_failure_has_no_final_report(self):
        self.run_mocked(error=ValueError('Invalid model probability: nonfinite'))

    def test_nonfinite_model_output_has_no_final_report(self):
        pins = filtering.approved_inputs()
        helper = filtering.study.load_helper(pins['vendor/utils_vad.py'])
        class NonfiniteModel:
            def reset_states(self): pass
            def __call__(self, chunk, rate): return torch.tensor(float('nan'))
        actual_infer = filtering.study.infer
        self.run_mocked(error=lambda *args: actual_infer(helper, NonfiniteModel(), torch.zeros(8192)))

    def test_raw_hash_mismatch_precedes_output(self):
        with self.assertRaises(ValueError): filtering.filter_report(self.source, '0'*64, self.root/'result')
        self.assertFalse((self.root/'result').exists())

    def test_approved_model_helper_and_source_mismatch(self):
        approved, _ = raw.read_bound_json(filtering.APPROVED_REPORT, filtering.APPROVED_SHA)
        original_reader = raw.read_bound_json
        for key in ('vendor/silero_vad.jit', 'vendor/utils_vad.py', 'studySource', 'sourceManifest'):
            damaged = copy.deepcopy(approved)
            damaged['inputBindings'][key]['sha256'] = '0'*64
            def reader(path, expected=None):
                if Path(path) == filtering.APPROVED_REPORT:
                    return damaged, raw.binding(filtering.APPROVED_REPORT, filtering.APPROVED_SHA)
                return original_reader(path, expected)
            with self.subTest(key=key), patch.object(raw, 'read_bound_json', side_effect=reader):
                with self.assertRaises(ValueError): filtering.approved_inputs()


if __name__ == '__main__': unittest.main()
