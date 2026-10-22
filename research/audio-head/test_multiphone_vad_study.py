"""Fake-model tests only; never load the pretrained network or corpus audio."""
import copy
import unittest
from pathlib import Path
import torch
import multiphone_vad_study as study


class FakeModel:
    def __init__(self, probability=0.9):
        self.probability, self.resets, self.chunks = probability, 0, []

    def reset_states(self):
        self.resets += 1
        self.chunks = []

    def __call__(self, chunk, rate):
        assert rate == 16000
        self.chunks.append(chunk.clone())
        return torch.tensor(self.probability)


class StudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = study.ROOT/'vad-source-v1/utils_vad.py'
        if not path.exists():
            raise unittest.SkipTest('Pinned official helper unavailable')
        cls.helper = study.load_helper(study.raw.binding(path,
            '15d0f6b3ef9590e22ca2f146e1436f6901da356cb552d3183df4100862b333cb'))

    def test_nonfinite_and_out_of_range_model_outputs(self):
        for value in (float('nan'), float('inf'), -0.1, 1.1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                study.infer(self.helper, FakeModel(value), torch.zeros(512))

    def test_tail_padding_and_original_length(self):
        samples = torch.ones(8200)
        model = FakeModel()
        result = study.infer(self.helper, model, samples)
        self.assertEqual(len(result['probabilities']), 17)
        self.assertTrue(torch.equal(model.chunks[-1][:8], torch.ones(8)))
        self.assertTrue(torch.equal(model.chunks[-1][8:], torch.zeros(504)))
        self.assertLessEqual(result['timestamps'][-1]['end'], len(samples))
        self.assertTrue(torch.equal(samples, torch.ones(8200)))

    def test_state_reset_between_clips(self):
        model = FakeModel()
        first = study.infer(self.helper, model, torch.ones(8192))
        study.infer(self.helper, model, torch.zeros(2048))
        again = study.infer(self.helper, model, torch.ones(8192))
        self.assertEqual(model.resets, 3)
        self.assertEqual(first, again)

    def test_short_and_allzero(self):
        self.assertFalse(study.infer(self.helper, FakeModel(), torch.ones(1600))['vad'])
        self.assertFalse(study.infer(self.helper, FakeModel(0), torch.zeros(8192))['vad'])

    def test_invalid_timestamp_intervals(self):
        for timestamps in ([{'start': 0, 'end': 1001}], [{'start': -1, 'end': 100}],
                           [{'start': 0, 'end': 300}, {'start': 299, 'end': 500}],
                           [{'start': 0, 'end': float('inf')}], [{'start': True, 'end': 30}],
                           [{'start': 10, 'end': 10}]):
            with self.subTest(timestamps=timestamps), self.assertRaises(ValueError):
                study.validate_timestamps(timestamps, 1000)

    def fixture(self):
        clip = dict(id='fake', sampleCount=8192)
        record = dict(clip=clip, **study.infer(self.helper, FakeModel(), torch.ones(8192)))
        return [clip], {'fake': record}

    def test_record_coverage(self):
        clips, records = self.fixture()
        self.assertEqual(study.derive_records(self.helper, clips, records), records)
        for altered in ({}, {**records, 'extra': records['fake']}):
            with self.assertRaises(ValueError): study.derive_records(self.helper, clips, altered)

    def test_record_corruption_and_decision_tampering(self):
        clips, records = self.fixture()
        for field, value in [('vad', False), ('timestamps', []), ('probabilities', [float('nan')]*16),
                             ('probabilities', [0.9]*15), ('clip', dict(id='fake', sampleCount=8000))]:
            altered = copy.deepcopy(records)
            altered['fake'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                study.derive_records(self.helper, clips, altered)


if __name__ == '__main__': unittest.main()
