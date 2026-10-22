"""Position identity, rating alignment and immutable speaker-membership checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import multiphone_position_data as data
from multiphone_data import derive_examples


def annotation(phones, strings, text='WORD'):
    raters = [[0 if t.startswith('(') else 1 if t.startswith('{') else 2
               for t in s.split() if not t.startswith('[')] for s in strings]
    return ({'text': text, 'words': [{'text': text, 'phones': phones,
        'phones-accuracy': [sum(r[i] for r in raters)/5 for i in range(len(phones))]}]},
        {'text': text, 'words': [{'text': text, 'ref-phones': ' '.join(phones), 'phones': strings}]})


def small_cohort():
    clips, rows = [], []
    for i in range(6):
        clip, speaker = str(i), 'speaker'+str(i)
        a, d = annotation(['B', 'B', 'AO1', 'ZH'], ['B (B) AO1 ZH']*5)
        clips.append(dict(id=clip, speakerId=speaker, audioSha256='hash'+str(i), age=7, ageBand='child',
                          text=a['text'], words=a['words'], canonicalPhones=a['words'][0]['phones']))
        for row in data.derive_positions(clip, speaker, 7, a, d):
            rows.append(dict(row, clipIndex=i))
    assignment = {c['speakerId']: i % 3 for i, c in enumerate(clips)}
    partitions = []
    for fold in range(3):
        hold = sorted(s for s in assignment if assignment[s] == fold)
        fit = sorted(set(assignment)-set(hold))
        partitions.append(dict(fold=fold, outerFitSpeakers=fit, outerHoldoutSpeakers=hold,
                               innerFitSpeakers=fit[1:], innerValidationSpeakers=fit[:1]))
    return (dict(authorPartition='train', rows=rows, clips=clips),
            dict(authorPartition='train', splitSeed=123, speakerAssignments=assignment, folds=partitions))


class PositionDataTests(unittest.TestCase):
    def test_repeated_phone_keeps_different_labels_and_all_five_raters(self):
        a, d = annotation(['B', 'AH0', 'B'], ['B AH0 (B)', '{B} AH0 (B)', '(B) AH0 {B}',
                                                    'B [R] AH0 (B)', 'B AH0 (B)'])
        rows = data.derive_positions('clip', 'speaker', 7, a, d)
        self.assertEqual([r['id'] for r in rows], ['clip:0:0', 'clip:0:2'])
        self.assertEqual([r['canonicalIndex'] for r in rows], [0, 2])
        self.assertEqual([r['raterCounts'] for r in rows], [[1, 1, 3], [4, 1, 0]])
        self.assertEqual(rows[1]['raterScores'], [0, 0, 1, 0, 0])
        self.assertTrue(all(r['humanNoteRaw'] is None for r in rows))

    def test_repeated_words_have_distinct_position_ids_and_stress_preserved(self):
        a, d = annotation(['B', 'AH1'], ['B AH1']*5)
        a['words'] *= 2
        d['words'] *= 2
        rows = data.derive_positions('clip', 'speaker', 7, a, d)
        self.assertEqual([r['id'] for r in rows], ['clip:0:0', 'clip:1:0'])
        self.assertEqual([r['canonicalIndex'] for r in rows], [0, 2])
        bad = deepcopy(d)
        bad['words'][0]['phones'][0] = 'B AH0'
        with self.assertRaisesRegex(ValueError, 'Rater sequence'):
            data.derive_positions('clip', 'speaker', 7, a, bad)

    def test_sparse_notes_remain_literal_and_absence_unknown(self):
        for raw in ('R*', '<unk>', '<DEL>', 'D Z'):
            a, d = annotation(['B', 'B'], ['(B) B']*5)
            note = {'index': 0, 'canonical-phone': 'B', 'pronounced-phone': raw}
            a['words'][0]['mispronunciations'] = [note]
            rows = data.derive_positions('clip', 'speaker', 7, a, d)
            self.assertEqual(rows[0]['humanNoteRaw'], note)
            self.assertIsNone(rows[1]['humanNoteRaw'])
            a['words'][0]['mispronunciations'].append(note)
            with self.assertRaisesRegex(ValueError, 'duplicate sparse note'):
                data.derive_positions('clip', 'speaker', 7, a, d)

    def test_invalid_five_rater_alignment_and_means_fail(self):
        a, d = annotation(['B'], ['B']*5)
        for change in ('count', 'sequence', 'syntax', 'mean'):
            aa, dd = deepcopy(a), deepcopy(d)
            if change == 'count':
                dd['words'][0]['phones'].pop()
            elif change == 'sequence':
                dd['words'][0]['phones'][0] = 'R'
            elif change == 'syntax':
                dd['words'][0]['phones'][0] = 'B?'
            else:
                aa['words'][0]['phones-accuracy'] = [1]
            with self.subTest(change=change), self.assertRaises(ValueError):
                data.derive_positions('clip', 'speaker', 7, aa, dd)

    def test_legacy_join_uses_position_and_retains_original_index(self):
        a, d = annotation(['B', 'R', 'R', 'ZH'], ['B R (R) ZH']*5)
        old = derive_examples('clip', 'speaker', 7, a, d)
        for row in old:
            row['trainingEligible'] = row['targetPhone'] != 'ZH'
        old = list(reversed(old))  # unsupported row occupies index 0
        rows = data.derive_positions('clip', 'speaker', 7, a, d)
        self.assertEqual(data.reconcile_legacy(rows, {'rows': old}), 1)
        self.assertEqual(rows[0]['legacyRowIndex'], 1)
        self.assertEqual(rows[0]['legacyRowId'], 'clip:B')
        self.assertIsNone(rows[1]['legacyRowIndex'])
        self.assertEqual([r['targetPhone'] for r in rows], ['B', 'R', 'R'])
        bad = deepcopy(old)
        bad[1]['raterCounts'] = [5, 0, 0]
        with self.assertRaisesRegex(ValueError, 'Legacy label'):
            data.reconcile_legacy(rows, {'rows': bad})
        with self.assertRaisesRegex(ValueError, 'Missing or duplicate legacy'):
            data.reconcile_legacy(rows[1:], {'rows': old})
        with self.assertRaisesRegex(ValueError, 'Duplicate position'):
            data.reconcile_legacy(rows+[rows[0]], {'rows': old})

    def test_split_memberships_preserved_and_every_position_held_once(self):
        cohort, old = small_cohort()
        result = data.build_splits(cohort, old)
        self.assertEqual(result['speakerAssignments'], old['speakerAssignments'])
        held = []
        for fold, original in zip(result['folds'], old['folds']):
            for group in data.GROUPS:
                self.assertEqual(fold[group+'Speakers'], original[group+'Speakers'])
                self.assertEqual(len(fold[group+'Rows']), 2*len(fold[group+'Clips']))
            held += fold['outerHoldoutRows']
        self.assertEqual(sorted(held), list(range(12)))
        self.assertEqual(data.build_splits(cohort, old), result)

    def test_split_rejects_duplicate_audio_missing_positions_and_speaker_changes(self):
        for change in ('audio', 'missing', 'duplicate', 'speaker', 'overlap', 'position'):
            cohort, old = small_cohort()
            if change == 'audio':
                cohort['clips'][1]['audioSha256'] = cohort['clips'][0]['audioSha256']
            elif change == 'missing':
                cohort['rows'].pop()
            elif change == 'duplicate':
                cohort['rows'].append(cohort['rows'][0])
            elif change == 'speaker':
                old['speakerAssignments']['extra'] = 0
            elif change == 'overlap':
                old['folds'][0]['innerFitSpeakers'] += old['folds'][0]['innerValidationSpeakers']
            else:
                cohort['rows'][0]['canonicalIndex'] = 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                data.build_splits(cohort, old)

    def test_declaration_retains_failure_and_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            output = root/'outputs/fresh'
            with patch.object(data, 'HERE', root), patch.object(data, 'inputs', side_effect=ValueError('missing input')):
                with self.assertRaisesRegex(ValueError, 'missing input'):
                    data.declare(output)
                self.assertEqual(json.loads((output/'setup-failure.json').read_text())['message'], 'missing input')
                with self.assertRaisesRegex(ValueError, 'Fresh ignored'):
                    data.declare(output)

    def test_artifact_lifecycle_exact_rebuild_no_overwrite_and_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory).resolve()/'plan.json'
            pin = data.write_new(plan, {'declared': True})
            cohort = dict(provenance={'inputBindings': {}}, labelSummary={'rows': 2}, summary={})
            splits = {'speakerAssignments': {'speaker': 0}}
            with patch.object(data, 'calculate', return_value=(cohort, splits)):
                result = data.run(plan, pin['sha256'])
                self.assertEqual(result['path'], str(plan.parent/'report.json'))
                self.assertTrue(data.run(plan, pin['sha256'], verify=True)['verified'])
                with self.assertRaisesRegex(ValueError, 'No overwrite'):
                    data.run(plan, pin['sha256'])
                # Even semantically equal JSON with different bytes is rejected.
                path = plan.parent/'cohort.json'
                path.write_text(json.dumps(cohort))
                report_path = plan.parent/'report.json'
                report = json.loads(report_path.read_text())
                report['outputs']['cohort'] = data.binding(path)
                report_path.write_bytes(data.json_bytes(report))
                with self.assertRaisesRegex(ValueError, 'Saved artifacts differ'):
                    data.run(plan, pin['sha256'], verify=True)

    def test_failed_build_leaves_failure_record_and_cannot_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory).resolve()/'plan.json'
            pin = data.write_new(plan, {'declared': True})
            with patch.object(data, 'calculate', side_effect=ValueError('broken rating')):
                with self.assertRaisesRegex(ValueError, 'broken rating'):
                    data.run(plan, pin['sha256'])
                self.assertEqual(json.loads((plan.parent/'failure.json').read_text())['message'], 'broken rating')
                with self.assertRaisesRegex(ValueError, 'No overwrite'):
                    data.run(plan, pin['sha256'])

    def test_writer_and_runtime_are_real_and_no_overwrite(self):
        self.assertIn('sha256', data.runtime()['executable'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'data.json'
            pin = data.write_new(path, {'truth': True})
            self.assertEqual(data.read_bound(pin), {'truth': True})
            with self.assertRaises(FileExistsError):
                data.write_new(path, {'truth': False})
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Pinned input'):
                data.read_bound(pin)


if __name__ == '__main__':
    unittest.main()
