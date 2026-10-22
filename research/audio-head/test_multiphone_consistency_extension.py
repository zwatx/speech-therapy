"""Small mixed-origin fixtures; no actual encoder inference or corpus outcomes."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import multiphone_consistency_extension as extension
from test_multiphone_consistency_features import metadata


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cohort, self.splits, self.clean, self.canonical, old_recipe = metadata()
        old_rows, old_clips, _ = extension.original.select_subset(self.cohort, self.splits, self.clean, self.canonical, old_recipe)
        self.old_plan = {'rowIndices': old_rows, 'clips': old_clips}
        self.recipe = deepcopy(extension.read_json(extension.RECIPE))
        eligible = [i for i, row in enumerate(self.cohort['rows']) if row['trainingEligible']]
        full_count = len({self.cohort['rows'][i]['clipId'] for i in eligible})
        self.recipe.update(expectedClips=full_count, expectedRows=len(eligible), reusedClips=len(old_clips),
            reusedRows=len(old_rows), newClips=full_count-len(old_clips), newRows=len(eligible)-len(old_rows))
        indices, clips, reused, new = extension.full_metadata(self.cohort, self.splits, self.clean,
            self.canonical, self.recipe, self.old_plan)
        self.plan = {'clips': clips, 'rowIndices': indices, 'reusedClipIds': reused, 'newClipIds': new,
            'expectedClips': full_count, 'recipe': self.recipe, 'inputFiles': {}}
        self.old_path, self.new_path = self.root/'old-plan.json', self.root/'plan.json'
        extension.atomic_json(self.old_path, self.old_plan); extension.atomic_json(self.new_path, self.plan)
        self.old_pin, self.plan_pin = extension.pin(self.old_path), extension.pin(self.new_path)

    def fixture_units(self):
        entries, audio, measurements, origins = {}, {}, {}, {}
        ctcs = {'original': {'entries': {}}, 'extension': {'entries': {}}}
        for clip in self.plan['clips']:
            cid = clip['id']; old = cid in self.plan['reusedClipIds']; kind = 'original' if old else 'extension'
            root = self.root / kind; root.mkdir(exist_ok=True)
            wav = root / (cid+'.wav'); wav.write_bytes(b'PCM-'+cid.encode())
            posterior = root / (cid+'.f32'); posterior.write_bytes(b'posterior-'+cid.encode())
            a = {'id': cid, 'clipId': cid, 'audioPath': str(wav), 'audioSha256': extension.digest(wav), 'sampleCount': clip['sampleCount']}
            ctc = {**a, 'path': posterior.name, 'frames': 4, 'sha256': extension.digest(posterior)}
            ctcs[kind]['entries'][cid] = ctc
            rows = [{**row, 'intervalFrames': [1, 2], 'estimatedPoolingWindowFrames': [0, 4]} for row in clip['targets']]
            target = np.array([np.full(1024, r['rowIndex']) for r in rows], dtype=np.float32)
            scalar = np.array([np.full(13, r['rowIndex']+.5) for r in rows], dtype=np.float32)
            measurement = {'requestedSNRdB': 20}
            entries[cid] = extension.original.save_unit(root / cid, clip, a, measurement, rows, target, scalar,
                ctc, self.old_pin['sha256'] if old else self.plan_pin['sha256'])
            audio[cid], measurements[cid] = a, measurement
        for kind in ctcs: extension.atomic_json(self.root/kind/'index.json', ctcs[kind])
        old_report = {'planPath': str(self.old_path), 'planSha256': self.old_pin['sha256'],
            'derivedFiles': {'ctcIndex/noise20db': extension.pin(self.root/'original/index.json')}}
        new_ctc = extension.pin(self.root/'extension/index.json')
        origins = extension.origins_for(self.plan, self.plan_pin, old_report, new_ctc)
        index = {'complete': True, 'planSha256': self.plan_pin['sha256'], 'rowIndices': self.plan['rowIndices'],
            'entries': entries, 'noisyAudio': audio, 'recordingMeasurements': measurements,
            'originByClip': origins, 'clipCount': len(entries), **extension.FLAGS}
        old_index = {key: {cid: index[key][cid] for cid in self.plan['reusedClipIds']}
                     for key in ('entries', 'noisyAudio', 'recordingMeasurements')}
        return index, old_report, old_index, new_ctc

    def test_complete_metadata_keeps_holdout_waveforms_but_no_labels_or_model_scoring(self):
        self.assertTrue(set(self.splits['folds'][0]['outerHoldoutRows']) <= set(self.plan['rowIndices']))
        self.assertEqual(len(self.plan['rowIndices']), self.recipe['expectedRows'])
        self.assertEqual(set(self.plan['newClipIds']) & set(self.plan['reusedClipIds']), set())
        self.assertNotIn('outerInferencePerformed', extension.FLAGS)
        self.assertFalse(extension.FLAGS['outerModelEvaluationPerformed'])
        before = deepcopy(self.plan['clips'])
        for row in self.cohort['rows']: row['raterCounts'] = [5, 0, 0]
        actual = extension.full_metadata(self.cohort, self.splits, self.clean, self.canonical, self.recipe, self.old_plan)
        self.assertEqual(actual[1], before)
        self.assertTrue(all('raterCounts' not in r for c in before for r in c['targets']))

    def test_source_identity_and_duplicate_canonical_rows_rejected(self):
        changed = deepcopy(self.clean); changed['rows'][0]['rowId'] = 'other'
        with self.assertRaisesRegex(ValueError, 'identity'):
            extension.full_metadata(self.cohort, self.splits, changed, self.canonical, self.recipe, self.old_plan)
        changed = deepcopy(self.canonical); changed['clips'][0]['audioSha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'source'):
            extension.full_metadata(self.cohort, self.splits, self.clean, changed, self.recipe, self.old_plan)
        changed = deepcopy(self.clean); changed['rows'].append(changed['rows'][0])
        with self.assertRaisesRegex(ValueError, 'coverage'):
            extension.full_metadata(self.cohort, self.splits, changed, self.canonical, self.recipe, self.old_plan)

    def test_mixed_origin_assembly_matches_all_rows_and_leaves_original_bytes_unchanged(self):
        index, old_report, old_index, new_ctc = self.fixture_units()
        extension.check_index(self.plan, self.plan_pin, index, old_report, old_index, new_ctc)
        originals = {p: p.read_bytes() for p in (self.root/'original').rglob('*') if p.is_file()}
        out = self.root/'assembled'; out.mkdir()
        rows, descriptors, pins = extension.assemble(self.plan, index, out)
        t, s = np.load(out/'target.npy'), np.load(out/'scalars.npy')
        self.assertEqual([r['rowIndex'] for r in rows], self.plan['rowIndices'])
        np.testing.assert_array_equal(t[:, 0], self.plan['rowIndices'])
        np.testing.assert_array_equal(s[:, 0], np.asarray(self.plan['rowIndices'])+.5)
        self.assertEqual(descriptors['target']['shape'], [len(rows), 1024]); extension.guard(pins)
        self.assertTrue(all(p.read_bytes() == data for p, data in originals.items()))

    def test_relabeling_reused_plan_rejected_even_if_other_metadata_rehashed(self):
        index, report, old_index, ctc = self.fixture_units()
        cid = self.plan['reusedClipIds'][0]
        index['originByClip'][cid]['planSha256'] = self.plan_pin['sha256']
        with self.assertRaisesRegex(ValueError, 'origin identity'):
            extension.check_index(self.plan, self.plan_pin, index, report, old_index, ctc)
        with self.assertRaisesRegex(ValueError, 'partition binding'):
            extension.audit_units(self.plan, index)

    def test_missing_or_duplicate_rows_and_rehashed_target_swaps_rejected(self):
        index, *_ = self.fixture_units()
        cid = self.plan['newClipIds'][0]
        missing = deepcopy(index); del missing['entries'][cid]
        with self.assertRaisesRegex(ValueError, 'coverage'): extension.audit_units(self.plan, missing)
        entry = index['entries'][cid]; meta = extension.read_json(Path(entry['entryPath']))
        meta['rows'].reverse(); extension.atomic_json(Path(entry['entryPath']), meta)
        entry['entrySha256'] = extension.digest(Path(entry['entryPath']))
        with self.assertRaisesRegex(ValueError, 'partition binding'): extension.audit_units(self.plan, index)

    def test_rehashed_assembled_matrix_corruption_cannot_publish(self):
        index, *_ = self.fixture_units(); out = self.root/'assembled'; out.mkdir()
        save = np.save
        def wrong(stream, values, **kwargs):
            values = values.copy(); values[0, 0] += 1; save(stream, values, **kwargs)
        with patch.object(extension.np, 'save', side_effect=wrong), self.assertRaisesRegex(ValueError, 'assembled matrix'):
            extension.assemble(self.plan, index, out)

    def test_waveform_mutation_is_detected_by_authoritative_origin_pins(self):
        index, *_ = self.fixture_units()
        cid = self.plan['reusedClipIds'][0]
        Path(index['noisyAudio'][cid]['audioPath']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'artifact changed'): extension.audit_units(self.plan, index)

    def test_inference_failure_preserves_artifacts_and_never_reprocesses_originals(self):
        index, old_report, old_index, ctc_pin = self.fixture_units()
        calls = []
        def waveform(clip, output, seed):
            calls.append(clip['id']); return index['noisyAudio'][clip['id']], index['recordingMeasurements'][clip['id']]
        with patch.object(extension, 'validate_plan', return_value=({}, {}, old_report, {}, old_index, {})),\
             patch.object(extension.original, 'write_noisy', side_effect=waveform),\
             patch.object(extension, 'make_batch', return_value=({}, {'ctcIndex': ctc_pin})),\
             patch.object(extension.original.extraction, 'PhoneticEncoder', side_effect=ValueError('encoder failure')):
            with self.assertRaisesRegex(ValueError, 'encoder failure'):
                extension.run(self.new_path, self.plan_pin['sha256'])
        self.assertEqual(calls, self.plan['newClipIds'])
        self.assertFalse((self.root/'features/features.json').exists())
        self.assertFalse(extension.read_json(self.root/'features/failure.json')['complete'])
        with patch.object(extension, 'validate_plan', return_value=({}, {}, old_report, {}, old_index, {})),\
             self.assertRaisesRegex(ValueError, 'Fresh extraction'):
            extension.run(self.new_path, self.plan_pin['sha256'])


    def test_late_input_mutation_blocks_completion_publication(self):
        index, old_report, old_index, ctc_pin = self.fixture_units()
        old_report['originalParity'] = []
        old_report['derivedFiles']['parity'] = self.old_pin
        self.plan['recipe']['cleanFeatureBindingSha256'] = 'binding'
        self.plan.update(partition='all-eligible-author-training-rows', recipeSha256='recipe')
        extension.atomic_json(self.new_path, self.plan)
        current_pin = extension.pin(self.new_path)
        marker = self.root/'source'; marker.write_text('original')
        inputs = {'source': extension.pin(marker)}
        ctc = extension.read_json(Path(ctc_pin['path']))
        def waveform(clip, output, seed):
            cid = clip['id']; return index['noisyAudio'][cid], index['recordingMeasurements'][cid]
        def aligned(logp, hidden, clip, recipe):
            entry = index['entries'][clip['id']]
            with np.load(entry['path']) as value: t, s = value['target'].copy(), value['scalars'].copy()
            return extension.read_json(Path(entry['entryPath']))['rows'], s, t, None
        assemble = extension.assemble
        def changed_after_assembly(*args):
            result = assemble(*args); marker.write_text('changed'); return result
        with patch.object(extension, 'validate_plan', return_value=({}, {}, old_report, {}, old_index, inputs)),\
             patch.object(extension.original, 'write_noisy', side_effect=waveform),\
             patch.object(extension, 'make_batch', return_value=(ctc, {'ctcIndex': ctc_pin})),\
             patch.object(extension.original.extraction, 'PhoneticEncoder', return_value=lambda x: None),\
             patch.object(extension.original, 'read_rating_pcm', return_value=None),\
             patch.object(extension.original, 'load_logp', return_value=(None, None)),\
             patch.object(extension.original.capture, 'aligned_features', side_effect=aligned),\
             patch.object(extension, 'assemble', side_effect=changed_after_assembly):
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                extension.run(self.new_path, current_pin['sha256'])
        self.assertFalse((self.root/'features/features.json').exists())
        self.assertTrue((self.root/'features/failure.json').is_file())

if __name__ == '__main__': unittest.main()
