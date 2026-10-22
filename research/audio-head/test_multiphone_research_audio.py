"""Synthetic/raw-container tests only; no encoder or real-audio inference."""
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import wave

import numpy as np

import multiphone_research_audio as raw


class RawAudioTests(unittest.TestCase):
    def setUp(self):
        self.mapping = json.loads(raw.local.RECIPE.read_text())
        self.vocab = {token: i+4 for i, token in enumerate(sorted(set(self.mapping['vowels'].values()) |
            set(self.mapping['consonants'].values()) | set(self.mapping['stressOverrides'].values())))}
        self.prompt = {'schemaVersion': 1, 'language': 'en', 'transcript': 'BALL',
            'words': [{'text': 'BALL', 'phones': ['B', 'AO1', 'L']}],
            'targets': [{'id': 'ball-b', 'wordIndex': 0, 'phoneIndex': 0, 'targetPhone': 'B'}]}

    def validate(self, prompt=None, frames=20, support=None):
        return raw.validate_prompt(self.prompt if prompt is None else prompt, self.mapping, self.vocab,
                                   raw.inference.TARGETS[:23] if support is None else support, frames)

    def test_caller_target_order_and_zero_based_word_positions(self):
        value = self.validate()
        self.assertEqual(value['targets'][0]['canonicalIndex'], 0)
        self.assertEqual(value['targets'][0]['targetWord'], 'BALL')
        self.assertEqual(value['targets'][0]['modelTargetId'], 0)
        prompt = copy.deepcopy(self.prompt)
        prompt['words'].append({'text': 'FISH', 'phones': ['F', 'IH1', 'SH']}); prompt['transcript'] = 'BALL FISH'
        prompt['targets'].insert(0, {'id': 'fish-sh', 'wordIndex': 1, 'phoneIndex': 2, 'targetPhone': 'SH'})
        result = self.validate(prompt)
        self.assertEqual([r['id'] for r in result['targets']], ['fish-sh', 'ball-b'])
        self.assertEqual([r['canonicalIndex'] for r in result['targets']], [5, 0])

    def test_no_invented_transcript_phones_or_target_identity(self):
        changes = [lambda p: p.update(transcript='BALL!'),
                   lambda p: p['words'][0]['phones'].__setitem__(1, 'AX'),
                   lambda p: p['words'][0]['phones'].__setitem__(0, 'B1'),
                   lambda p: p['targets'][0].update(targetPhone='P'),
                   lambda p: p['targets'][0].update(wordIndex=1),
                   lambda p: p['targets'][0].update(phoneIndex=True),
                   lambda p: p.update(language='fr'),
                   lambda p: p.update(referenceAudio='invented')]
        for change in changes:
            with self.subTest(change=change):
                value = copy.deepcopy(self.prompt); change(value)
                with self.assertRaises(ValueError): self.validate(value)

    def test_repeated_requested_phone_rejected_even_if_only_one_target(self):
        value = copy.deepcopy(self.prompt)
        value['words'][0]['phones'].append('B')
        with self.assertRaisesRegex(ValueError, 'exactly one'): self.validate(value)
        value = copy.deepcopy(self.prompt); value['targets'].append(copy.deepcopy(value['targets'][0]))
        with self.assertRaisesRegex(ValueError, 'target ID'): self.validate(value)
        value['targets'][1]['id'] = 'different-id'
        with self.assertRaisesRegex(ValueError, 'exactly one'): self.validate(value)

    def test_unsupported_zh_and_no_fit_support_rejected(self):
        with self.assertRaisesRegex(ValueError, 'supported'): self.validate(support=['P'])
        value = copy.deepcopy(self.prompt); value['words'][0]['phones'][0] = 'ZH'; value['targets'][0]['targetPhone'] = 'ZH'
        with self.assertRaisesRegex(ValueError, 'supported'): self.validate(value)

    def test_ctc_minimum_counts_required_blank_between_adjacent_same_tokens(self):
        with self.assertRaisesRegex(ValueError, 'cannot fit'): self.validate(frames=2)
        value = copy.deepcopy(self.prompt); value['words'][0]['phones'] = ['B', 'AO1', 'AO1']
        with self.assertRaisesRegex(ValueError, 'cannot fit'): self.validate(value, frames=3)
        self.validate(value, frames=4)

    def test_feature_order_scalar_definitions_and_context_window(self):
        # A deliberately simple canonical path: B at frame2, L at frame7.
        mapping = {'minimumTargetFramesDiagnostic': 2}
        probabilities = np.full((10, 392), .001/390)
        probabilities[:, 0] = .998; probabilities[:, 4] = .0005; probabilities[:, 5] = .0005
        probabilities[2, 0], probabilities[2, 4] = .001, .9975
        probabilities[7, 0], probabilities[7, 5] = .001, .9975
        probabilities /= probabilities.sum(1, keepdims=True)
        logp = np.log(probabilities).astype(np.float32)
        prompt = {'mappedTokenIds': [4, 5], 'targets': [
            {'id': 'last', 'canonicalIndex': 1, 'modelTargetId': 15},
            {'id': 'first', 'canonicalIndex': 0, 'modelTargetId': 0}]}
        hidden = np.arange(10*1024, dtype=np.float32).reshape(10, 1024)
        features, rows, _ = raw.make_features(prompt, logp, hidden, mapping)
        self.assertEqual(features.dtype, np.float32); self.assertEqual(features.shape, (2, 1037))
        self.assertEqual([row['id'] for row in rows], ['last', 'first'])
        self.assertEqual([row['intervalFrames'] for row in rows], [[7, 8], [2, 3]])
        self.assertEqual([row['estimatedPoolingWindowFrames'] for row in rows], [[5, 10], [0, 5]])
        np.testing.assert_array_equal(features[0, :1024], hidden[5:10].mean(0, dtype=np.float64).astype(np.float32))
        np.testing.assert_array_equal(features[1, :1024], hidden[:5].mean(0, dtype=np.float64).astype(np.float32))
        self.assertAlmostEqual(float(features[0, 1024+9]), .02)
        self.assertEqual(float(features[0, 1024+10]), 1)
        with self.assertRaisesRegex(ValueError, 'grid'): raw.make_features(prompt, logp, hidden[:-1], mapping)

    def wav(self, channels=1, rate=16000, width=2):
        target = io.BytesIO()
        with wave.open(target, 'wb') as stream:
            stream.setnchannels(channels); stream.setsampwidth(width); stream.setframerate(rate)
            stream.writeframes(bytes(1600*channels*width))
        return target.getvalue()

    def test_pcm_input_rejected_without_silent_conversion_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'recording.wav'; path.write_bytes(self.wav()); before = path.read_bytes()
            value = raw.read_rating_pcm(path, raw.digest(path)); self.assertEqual(len(value), 1600)
            self.assertEqual(path.read_bytes(), before)
            for kwargs in ({'channels': 2}, {'rate': 48000}, {'width': 1}):
                path.write_bytes(self.wav(**kwargs))
                with self.assertRaisesRegex(ValueError, 'mono PCM16'): raw.read_rating_pcm(path, raw.digest(path))
            with self.assertRaisesRegex(ValueError, 'changed'): raw.read_rating_pcm(path, 'wrong')

    def test_captured_json_and_symlink_binding_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); first = root/'first'; second = root/'second'; alias = root/'alias'
            first.write_text('{"value":1}'); second.write_text('{"value":2}'); alias.symlink_to(first)
            bound = raw.binding(alias)
            value, captured = raw.read_bound_json(alias, bound['sha256'])
            self.assertEqual(value, {'value': 1}); self.assertEqual(captured['sha256'], bound['sha256'])
            alias.unlink(); alias.symlink_to(second)
            with self.assertRaisesRegex(ValueError, 'changed'): raw.guard({'input': bound})
            with self.assertRaisesRegex(ValueError, 'JSON differs'): raw.read_bound_json(alias, bound['sha256'])

    def test_mocked_full_pipeline_publishes_or_rejects_changed_original(self):
        for mutate_source in (False, True):
            with self.subTest(mutate_source=mutate_source), tempfile.TemporaryDirectory(dir=raw.HERE/'outputs') as tmp:
                root = Path(tmp); wav = root/'audio.wav'; wav.write_bytes(self.wav())
                prompt = root/'prompt.json'; prompt.write_text(json.dumps(self.prompt))
                bundle = root/'bundle'; bundle.mkdir(); (bundle/'manifest.json').write_text('{"filesSha256":{}}')
                contract_path = root/'contract.json'; contract_path.write_text('{}')
                columns = [f'targetPhonetic:{i}' for i in range(1024)]+list(raw.inference.SCALARS)
                contract = {'featureSourceBindingSha256': 'fixed', 'featureColumns': columns,
                            'ctcCheckpoint': {'id': 'synthetic'}, 'ctcSessionOptions': {'threads': 2}, 'limitations': ['synthetic']}
                class FakeHead:
                    feature_source_binding_sha256 = 'fixed'
                    feature_columns = columns
                    supported_phones = raw.inference.TARGETS[:23]
                    variant = 'synthetic'
                    def predict(self, values, ids):
                        self_outer.assertEqual(values.shape, (1, 1037))
                        self_outer.assertEqual(values.dtype, np.float32)
                        self_outer.assertEqual(ids.tolist(), [0])
                        if mutate_source: wav.write_bytes(wav.read_bytes()+b'changed')
                        return np.array([[.1, .2, .7]])
                self_outer = self
                def fake_worker(argv, **kwargs):
                    job_path = Path(argv[2]); job = json.loads(job_path.read_text())
                    logits = np.full((4, 392), -np.log(392), dtype='<f4')
                    output = job_path.parent; (output/'ctc.f32').write_bytes(logits.tobytes())
                    raw.write_json(output/'ctc.json', {'complete': True, 'jobSha256': raw.digest(job_path),
                        'audioSha256': job['audioSha256'], 'frames': 4, 'checkpoint': contract['ctcCheckpoint'],
                        'sessionOptions': contract['ctcSessionOptions'], 'fetchAttempts': 0,
                        'posteriorsPath': 'ctc.f32', 'posteriorsSha256': raw.digest(output/'ctc.f32')})
                args = SimpleNamespace(contract=contract_path, contract_sha256=raw.digest(contract_path), wav=wav,
                    wav_sha256=raw.digest(wav), prompt=prompt, prompt_sha256=raw.digest(prompt), bundle=bundle,
                    manifest_sha256=raw.digest(bundle/'manifest.json'), phonetic_snapshot=root/'unused',
                    output=root/'result', node='unused')
                pins = {'contract': raw.binding(contract_path)}
                with mock.patch.object(raw, 'load_contract', return_value=(contract, self.mapping, {}, self.vocab, pins)), \
                     mock.patch.object(raw.inference, 'load_head', return_value=FakeHead()), \
                     mock.patch.object(raw.subprocess, 'run', side_effect=fake_worker), \
                     mock.patch.object(raw.phonetic, 'PhoneticEncoder', return_value=lambda _: np.ones((4, 1024), dtype=np.float32)):
                    if mutate_source:
                        with self.assertRaisesRegex(ValueError, 'changed during'): raw.run(args)
                        self.assertFalse(args.output.exists())
                        self.assertFalse((root/'result.partial/report.json').exists())
                        self.assertTrue((root/'result.partial/failure.json').exists())
                    else:
                        result = raw.run(args)
                        self.assertEqual(result['targets'], 1)
                        report = json.loads((args.output/'report.json').read_text())
                        self.assertTrue(report['complete'])
                        self.assertEqual(report['targets'][0]['subjectiveCorpusRatingProbabilities'], [.1, .2, .7])
                        self.assertEqual(report['inputProvenance'], 'caller-supplied; author partition unspecified')
                        self.assertEqual(raw.digest(wav), args.wav_sha256)
                        self.assertFalse((root/'result.partial').exists())


if __name__ == '__main__': unittest.main()
