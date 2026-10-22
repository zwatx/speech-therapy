"""Synthetic row/window, waveform, checkpoint and atomic-resume tests only."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

import numpy as np

import multiphone_phonetic_features as extraction


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True))


class PhoneticFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='cadence-phonetic-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.audio, self.metadata = self.root / 'audio', self.root / 'metadata'
        (self.metadata / 'train').mkdir(parents=True)
        self.train_bytes = b'000000001 0001\n000000002 0002\n'
        (self.metadata / 'train/utt2spk').write_bytes(self.train_bytes)
        self.clips, rows = [], []
        for index in range(2):
            clip_id, speaker = f'{index+1:09d}', f'{index+1:04d}'
            path = self.audio / 'WAVE' / ('SPEAKER' + speaker) / (clip_id + '.WAV')
            path.parent.mkdir(parents=True)
            with wave.open(str(path), 'wb') as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(np.full(3200, 100 + index, dtype='<i2').tobytes())
            self.clips.append({'id': clip_id, 'speakerId': speaker, 'audioPath': str(path),
                               'audioSha256': extraction.digest(path), 'sampleCount': 3200, 'canonicalPhoneCount': 2})
            for phone_id, phone in enumerate(('B', 'P')):
                rows.append({'id': clip_id + ':' + phone, 'clipId': clip_id, 'clipIndex': index,
                             'targetId': phone_id, 'targetPhone': phone, 'wordIndex': 0,
                             'phoneIndex': phone_id, 'trainingEligible': True, 'raterCounts': [0, 0, 5]})
        self.cohort = {'authorPartition': 'train', 'clips': self.clips, 'rows': rows}
        self.cohort_path, self.split_path = self.root / 'cohort.json', self.root / 'splits.json'
        save(self.cohort_path, self.cohort)
        save(self.split_path, {'authorPartition': 'train'})
        self.recipe = extraction.read_json(extraction.RECIPE)
        self.recipe.update(expectedEligibleRows=4, expectedClips=2,
                           cohortSha256=extraction.digest(self.cohort_path), splitsSha256=extraction.digest(self.split_path))
        self.feature_rows = []
        for raw_index in (3, 0, 2, 1):  # Deliberately not cohort/clip order.
            row = rows[raw_index]
            interval = [1, 2] if row['targetId'] == 0 else [6, 7]
            self.feature_rows.append({'rowIndex': raw_index, 'rowId': row['id'], 'canonicalIndex': row['targetId'],
                **{key: row[key] for key in ('clipId', 'targetId', 'targetPhone', 'wordIndex', 'phoneIndex')},
                'intervalFrames': interval, 'estimatedPoolingWindowFrames': [max(0, interval[0]-2), min(9, interval[1]+2)]})
        manifest = {'authorPartition': 'train', 'fullCohortCoverage': True, 'partition': 'allEligibleAuthorTrain',
                    'cohortSha256': self.recipe['cohortSha256'], 'splitsSha256': self.recipe['splitsSha256'],
                    'clips': [{**clip, 'clipIndex': i, 'canonicalPhones': ['B', 'P'], 'targetRows': [
                        {key: value for key, value in row.items() if key not in ('clipId', 'intervalFrames', 'estimatedPoolingWindowFrames')}
                        for row in self.feature_rows if row['clipId'] == clip['id']]}
                        for i, clip in enumerate(self.clips)]}
        save(self.root / 'manifest.json', manifest)
        save(self.root / 'original-recipe.json', {key: self.recipe[key] for key in ('convKernel', 'convStride', 'poolingContextFrames')})
        (self.root / 'ctc').mkdir()
        save(self.root / 'ctc/config.json', {'manifestSha256': extraction.digest(self.root / 'manifest.json')})
        config_sha = extraction.digest(self.root / 'ctc/config.json')
        save(self.root / 'ctc/index.json', {'complete': True, 'configSha256': config_sha,
             'entries': {clip['id']: {'frames': 9, 'audioSha256': clip['audioSha256'], 'configSha256': config_sha}
                         for clip in self.clips}})
        self.features = {'complete': True, 'fullCohortCoverage': True, 'eligibleCohortRows': 4,
            'failedRows': [], 'unmappableRows': [], 'rowIndices': [3, 0, 2, 1], 'rows': self.feature_rows,
            'cohortSha256': self.recipe['cohortSha256'], 'splitsSha256': self.recipe['splitsSha256'],
            'sourceSha256': {name: extraction.digest(extraction.HERE / name)
                            for name in ('multiphone_local_features.py', 'alignment_pilot.py')}, **extraction.FALSE_FLAGS}
        for name, filename in (('manifest', 'manifest.json'), ('ctcIndex', 'ctc/index.json'), ('recipe', 'original-recipe.json')):
            self.features[name + 'Path'] = str(self.root / filename)
            self.features[name + 'Sha256'] = extraction.digest(self.root / filename)
        self.feature_path = self.root / 'features.json'
        self.persist()

    def persist(self):
        save(self.feature_path, self.features)
        self.recipe['featuresSha256'] = extraction.digest(self.feature_path)

    def load(self):
        with patch.object(extraction, 'AUDIO', self.audio), patch.object(extraction, 'METADATA', self.metadata), \
             patch.object(extraction, 'pinned_bytes', return_value=self.train_bytes):
            return extraction.load_inputs(self.cohort_path, self.split_path, self.feature_path, self.recipe)

    def config(self, bindings):
        return {'recipe': {**self.recipe, 'hiddenWidth': 4}, 'bindings': bindings}

    @staticmethod
    def frames(samples):
        return np.arange(36, dtype=np.float32).reshape(9, 4) + float(samples[0])

    def runner(self, output, config, rows, clips, by_clip, fail_second=False):
        calls = []
        class FakeEncoder:
            def __init__(self, *unused):
                pass
            def __call__(encoder, samples):
                calls.append(float(samples[0]))
                if fail_second and len(calls) == 2:
                    raise RuntimeError('interrupted synthetic extraction')
                return PhoneticFeatureTests.frames(samples)
        output.mkdir(exist_ok=True)
        with patch.object(extraction, 'PhoneticEncoder', FakeEncoder), contextlib.redirect_stdout(io.StringIO()):
            report = extraction.extract_locked(output, self.root, config, rows, clips, by_clip, time.perf_counter())
        return report, calls

    def test_original_order_and_window_identity_preserved(self):
        rows, clips, by_clip, bindings = self.load()
        self.assertEqual([row['rowIndex'] for row in rows], [3, 0, 2, 1])
        self.assertEqual([row['outputIndex'] for row in by_clip[clips[0]['id']]], [1, 3])
        self.assertEqual(bindings['features']['sha256'], self.recipe['featuresSha256'])
        self.features['rows'][0]['targetPhone'] = 'B'
        self.persist()
        with self.assertRaisesRegex(ValueError, 'identity/order'):
            self.load()

    def test_partial_duplicate_row_and_changed_window_or_grid_refused(self):
        original = deepcopy(self.features)
        for mutate in (lambda x: x.update(fullCohortCoverage=False),
                       lambda x: x.update(rowIndices=[3, 0, 2, 2]),
                       lambda x: x['rows'][0].update(estimatedPoolingWindowFrames=[3, 9])):
            self.features = deepcopy(original)
            mutate(self.features)
            self.persist()
            with self.assertRaises(ValueError):
                self.load()
        self.features = original
        path = self.root / 'ctc/index.json'
        index = extraction.read_json(path)
        index['entries'][self.clips[0]['id']]['frames'] = 8
        save(path, index)
        self.features['ctcIndexSha256'] = extraction.digest(path)
        self.persist()
        with self.assertRaisesRegex(ValueError, 'frame grid'):
            self.load()

    def test_features_do_not_use_subjective_rating_values(self):
        before, *_ = self.load()
        changed = deepcopy(self.cohort)
        for row in changed['rows']:
            row['raterCounts'] = ['not', 'used', 'by extractor']
        save(self.cohort_path, changed)
        self.recipe['cohortSha256'] = extraction.digest(self.cohort_path)
        self.features['cohortSha256'] = self.recipe['cohortSha256']
        path = self.root / 'manifest.json'
        manifest = extraction.read_json(path)
        manifest['cohortSha256'] = self.recipe['cohortSha256']
        save(path, manifest)
        self.features['manifestSha256'] = extraction.digest(path)
        ctc_config_path = self.root / 'ctc/config.json'
        save(ctc_config_path, {'manifestSha256': self.features['manifestSha256']})
        index_path = self.root / 'ctc/index.json'
        index = extraction.read_json(index_path)
        index['configSha256'] = extraction.digest(ctc_config_path)
        for entry in index['entries'].values():
            entry['configSha256'] = index['configSha256']
        save(index_path, index)
        self.features['ctcIndexSha256'] = extraction.digest(index_path)
        self.persist()
        after, *_ = self.load()
        self.assertEqual(before, after)

    def test_local_and_global_means_have_exact_dtype_values_and_bounds(self):
        frames = np.arange(36, dtype=np.float32).reshape(9, 4)
        local, global_vector = extraction.pooled_vectors(frames, self.feature_rows[:2], 9, 4)
        self.assertEqual(local.dtype, np.float32)
        np.testing.assert_array_equal(local[0], frames[4:9].mean(0, dtype=np.float64).astype(np.float32))
        np.testing.assert_array_equal(global_vector, frames.mean(0, dtype=np.float64).astype(np.float32))
        for broken in (frames.astype(np.float64), frames[:-1], np.full_like(frames, np.nan)):
            with self.assertRaisesRegex(ValueError, 'frame grid'):
                extraction.pooled_vectors(broken, self.feature_rows, 9, 4)
        with self.assertRaisesRegex(ValueError, 'target window'):
            extraction.pooled_vectors(frames, [{'estimatedPoolingWindowFrames': [0, 10]}], 9, 4)

    def test_interruption_resumes_only_complete_units_and_assembles_original_order(self):
        rows, clips, by_clip, binding = self.load()
        output, config = self.root / 'output', self.config(binding)
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            self.runner(output, config, rows, clips, by_clip, fail_second=True)
        self.assertTrue((output / 'clips' / clips[0]['id'] / 'entry.json').is_file())
        self.assertFalse((output / 'features.json').exists())
        report, calls = self.runner(output, config, rows, clips, by_clip)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report['resumedClips'], 1)
        self.assertEqual(report['rowIndices'], [3, 0, 2, 1])
        target, global_matrix = np.load(output / 'target.npy'), np.load(output / 'global.npy')
        for position, row in enumerate(rows):
            clip = next(clip for clip in clips if clip['id'] == row['clipId'])
            samples = extraction.read_rating_pcm(Path(clip['audioPath']), clip['audioSha256'])
            expected, mean = extraction.pooled_vectors(self.frames(samples), [row], 9, 4)
            np.testing.assert_array_equal(target[position], expected[0])
            np.testing.assert_array_equal(global_matrix[position], mean)
        pins = {name: extraction.digest(output / name) for name in ('features.json', 'index.json', 'target.npy', 'global.npy')}
        again, calls = self.runner(output, config, rows, clips, by_clip)
        self.assertEqual(again, report)
        self.assertEqual(calls, [])
        self.assertEqual(pins, {name: extraction.digest(output / name) for name in pins})

    def test_resume_refuses_corrupted_units_and_wrong_row_bindings(self):
        rows, clips, by_clip, binding = self.load()
        for problem in ('bytes', 'binding', 'missing-checksum'):
            with self.subTest(problem=problem):
                output, config = self.root / problem, self.config(binding)
                with self.assertRaises(RuntimeError):
                    self.runner(output, config, rows, clips, by_clip, fail_second=True)
                directory = output / 'clips' / clips[0]['id']
                if problem == 'bytes':
                    with (directory / 'vectors.npz').open('ab') as stream:
                        stream.write(b'changed')
                elif problem == 'binding':
                    entry = extraction.read_json(directory / 'entry.json')
                    entry['binding']['rows'][0]['outputIndex'] = 0
                    save(directory / 'entry.json', entry)
                else:
                    (directory / 'entry.json').unlink()
                with self.assertRaises((ValueError, FileNotFoundError)):
                    self.runner(output, config, rows, clips, by_clip)
                self.assertFalse((output / 'features.json').exists())

    def test_resume_rejects_rehashed_wrong_dtype_or_nonfinite_vectors(self):
        rows, clips, by_clip, binding = self.load()
        for bad_type in ('float64', 'nonfinite'):
            output, config = self.root / bad_type, self.config(binding)
            with self.assertRaises(RuntimeError):
                self.runner(output, config, rows, clips, by_clip, fail_second=True)
            directory = output / 'clips' / clips[0]['id']
            with np.load(directory / 'vectors.npz', allow_pickle=False) as archive:
                target, global_vector = archive['target'].copy(), archive['global'].copy()
            if bad_type == 'float64':
                target = target.astype(np.float64)
            else:
                target[0, 0] = np.nan
            np.savez_compressed(directory / 'vectors.npz', target=target, **{'global': global_vector})
            entry = extraction.read_json(directory / 'entry.json')
            entry['sha256'] = extraction.digest(directory / 'vectors.npz')
            save(directory / 'entry.json', entry)
            with self.assertRaisesRegex(ValueError, 'cached vector shape/dtype/values'):
                self.runner(output, config, rows, clips, by_clip)

    def test_checkpoint_identity_and_artifact_pins_checked_before_loading(self):
        snapshot = self.root / 'checkpoint'
        snapshot.mkdir()
        save(snapshot / 'config.json', {'hidden_size': 1024, 'vocab_size': 392,
                                       'conv_kernel': self.recipe['convKernel'], 'conv_stride': self.recipe['convStride']})
        (snapshot / 'pytorch_model.bin').write_bytes(b'synthetic-not-loadable-model')
        recipe = deepcopy(self.recipe)
        recipe['artifactSha256'] = {name: extraction.digest(snapshot / name) for name in ('config.json', 'pytorch_model.bin')}
        download = {'repo': recipe['modelId'], 'revision': recipe['revision'],
                    'files': {name: {'sha256': sha} for name, sha in recipe['artifactSha256'].items()}}
        path = self.root / 'download.json'
        save(path, download)
        recipe['downloadRecordSha256'] = extraction.digest(path)
        self.assertEqual(len(extraction.checkpoint_files(snapshot, path, recipe)), 3)
        (snapshot / 'pytorch_model.bin').write_bytes(b'different-weights')
        with self.assertRaisesRegex(ValueError, 'checkpoint artifact differs'):
            extraction.checkpoint_files(snapshot, path, recipe)

    def test_waveform_changes_are_checked_even_for_resumed_clips(self):
        rows, clips, by_clip, binding = self.load()
        output, config = self.root / 'audio-change', self.config(binding)
        with self.assertRaises(RuntimeError):
            self.runner(output, config, rows, clips, by_clip, fail_second=True)
        with Path(clips[0]['audioPath']).open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'WAV changed'):
            self.runner(output, config, rows, clips, by_clip)

    def test_binding_mutation_prevents_publication(self):
        rows, clips, by_clip, binding = self.load()
        self.feature_path.write_text(self.feature_path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.runner(self.root / 'input-change', self.config(binding), rows, clips, by_clip)
        self.assertFalse((self.root / 'input-change/features.json').exists())

    def test_unit_changed_after_validation_cannot_receive_new_authoritative_hash(self):
        rows, clips, by_clip, binding = self.load()
        original = extraction.checked_unit
        changed = False

        def mutate_after_read(directory, *args, **kwargs):
            nonlocal changed
            result = original(directory, *args, **kwargs)
            if not changed:
                with (directory / 'vectors.npz').open('ab') as stream:
                    stream.write(b'changed-after-validation-before-index-hash')
                changed = True
            return result

        output = self.root / 'publication-race'
        with patch.object(extraction, 'checked_unit', side_effect=mutate_after_read):
            with self.assertRaisesRegex(ValueError, 'binding/checksum'):
                self.runner(output, self.config(binding), rows, clips, by_clip)
        self.assertFalse((output / 'features.json').exists())

    def test_finished_matrix_or_index_corruption_is_not_silently_overwritten(self):
        rows, clips, by_clip, binding = self.load()
        for name in ('target.npy', 'index.json'):
            output, config = self.root / name.replace('.', '-'), self.config(binding)
            self.runner(output, config, rows, clips, by_clip)
            with (output / name).open('ab') as stream:
                stream.write(b' ')
            before = (output / name).read_bytes()
            with self.assertRaises(ValueError):
                self.runner(output, config, rows, clips, by_clip)
            self.assertEqual(before, (output / name).read_bytes())


if __name__ == '__main__':
    unittest.main()
