"""Synthetic source-code grouping/selection tests; no actual file selection."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nisqa_ingest import routing, source_code_selection as core


def row(reader, condition, *, book='00000', chapter='0009', segment='17', capture_index='1'):
    reader = f'{reader:05d}' if type(reader) is int else reader
    reference = f'book_{book}_chp_{chapter}_reader_{reader}_{segment}_seg.wav'
    filename = reference[:-4] + f'_live_{condition.lower()}_{capture_index}.wav'
    return dict(path=routing.PREFIX + filename, metadata=dict(
        con='opaque-condition-code', file='opaque-file-code',
        con_description='Skype' if condition == 'Skype' else 'VoIP-landline to mobile',
        filename_deg=filename, filename_ref=reference, source='DNS', lang='en',
        filepath_ref=routing.TRAIN + '/ref/' + reference))


def inventory(rows):
    return dict(training=rows, columns=list(core.FIELDS), **core.INVENTORY_FLAGS)


def fixture(groups=25):
    return inventory([row(i, condition) for i in range(groups) for condition in ('phone', 'Skype')])


class SourceCodeSelectionTests(unittest.TestCase):
    def test_actual_frozen_selector_quota_order_disjointness_and_complete_evidence(self):
        source = fixture()
        prepared = core.prepare_inventory(source)
        result = core.select20(prepared)
        projection = [{k: r[k] for k in ('path', 'captureCondition', 'readerGroup')} for r in prepared['eligible']]
        expected = routing.select(projection)
        self.assertEqual([r['path'] for r in result['selected']], [r['path'] for r in expected])
        self.assertEqual([r['captureCondition'] for r in result['selected']], ['phone'] * 10 + ['Skype'] * 10)
        self.assertEqual(len({r['readerGroup'] for r in result['selected']}), 20)
        self.assertEqual(len(result['selectionExclusions']), 30)
        self.assertEqual(prepared['support']['sharedGroups'], 25)
        self.assertEqual(prepared['support']['conditionRows'], {'phone': 25, 'Skype': 25})
        self.assertEqual(prepared['eligibilityExclusions'], [])
        self.assertEqual(core.select20(core.prepare_inventory(inventory(list(reversed(source['training']))))), result)
        self.assertTrue(all(len(r['identitySha256']) == 64 for r in result['selected']))
        self.assertEqual(routing.SALT, 'cadence-nisqa-train-live-ingest-v1')

    def test_exclusive_groups_precede_shared_and_insufficient_support_has_no_replacement(self):
        rows = ([row(i, 'phone') for i in range(5)] + [row(i, 'Skype') for i in range(5, 10)]
                + [row(i, c) for i in range(10, 25) for c in ('phone', 'Skype')])
        prepared = core.prepare_inventory(inventory(rows))
        chosen = core.select20(prepared)['selected']
        self.assertEqual({r['readerNumberCode'] for r in chosen[:5]}, {f'{i:05d}' for i in range(5)})
        self.assertEqual({r['readerNumberCode'] for r in chosen[10:15]}, {f'{i:05d}' for i in range(5, 10)})
        self.assertEqual(prepared['support']['exclusiveGroups'], {'phone': 5, 'Skype': 5})
        with self.assertRaises(ValueError):
            core.select20(core.prepare_inventory(fixture(19)))

    def test_codes_across_books_preserve_lineage_and_never_claim_people(self):
        source = fixture()
        source['training'].append(row(1, 'phone', book='12345', chapter='0123', segment='0002', capture_index='003'))
        prepared = core.prepare_inventory(source)
        members = [r for r in prepared['eligible'] if r['readerNumberCode'] == '00001']
        self.assertEqual(len({r['readerGroup'] for r in members}), 1)
        self.assertEqual({r['bookCode'] for r in members}, {'00000', '12345'})
        changed = next(r for r in members if r['bookCode'] == '12345')
        self.assertEqual((changed['chapterCode'], changed['segmentCode'], changed['captureIndex']), ('0123', '0002', '003'))
        self.assertEqual(changed['archiveMember'], 'NISQA_Corpus/' + changed['path'])
        result = core.select20(prepared)
        for value in (prepared, result):
            for flag in ('personIdentityVerified', 'speakerIndependentEvaluationEligible',
                         'numericTargetsAccessed', 'waveformAcquired'):
                self.assertIs(value[flag], False)
        self.assertTrue(result['scoreDefinitionAuditPending'])

    def test_reference_links_merge_components_conservatively_and_transitively(self):
        # A synthetic component-algorithm fixture, not an assertion that the
        # current anchored publisher grammar maps one reference to two codes.
        rows = [dict(readerNumberCode=code, sourceReferenceID=reference)
                for code, reference in (('00001', 'ref-a'), ('00002', 'ref-a'),
                                        ('00002', 'ref-b'), ('00003', 'ref-b'), ('00004', 'ref-c'))]
        expected = {'00001': 'DNS-reader_00001+00002+00003', '00002': 'DNS-reader_00001+00002+00003',
                    '00003': 'DNS-reader_00001+00002+00003', '00004': 'DNS-reader_00004'}
        self.assertEqual(core._components(rows), expected)
        self.assertEqual(core._components(list(reversed(rows))), expected)

    def test_quality_and_audio_metadata_inputs_are_rejected_without_interpretation(self):
        class Forbidden:
            def __str__(self):
                raise AssertionError('Target was interpreted')
            def __float__(self):
                raise AssertionError('Target was decoded')
        for field in ('mos', 'votes', 'standard_deviation', 'audioDuration', 'prediction'):
            source = fixture()
            source['training'][0]['metadata'][field] = Forbidden()
            with self.subTest(field=field), self.assertRaises(ValueError):
                core.prepare_inventory(source)
        prepared = core.prepare_inventory(fixture())
        prepared['eligible'][0]['quality'] = {'mos': Forbidden()}
        with self.assertRaises(ValueError):
            core.select20(prepared)
        source = fixture()
        for r in source['training']:
            r['metadata']['con'] = 'opaque-never-numeric-1e999'
            r['metadata']['file'] = 'opaque-never-numeric-NaN'
        baseline = core.select20(core.prepare_inventory(fixture()))
        altered = core.select20(core.prepare_inventory(source))
        self.assertEqual([r['path'] for r in baseline['selected']], [r['path'] for r in altered['selected']])

    def test_safe_paths_exact_ref_join_description_source_and_grammar_fail_closed(self):
        changes = [
            ('path', '../escape.wav'), ('path', '/absolute.wav'), ('path', 'NISQA_TRAIN_LIVE/deg/a\\b.wav'),
            ('path', 'NISQA_TRAIN_LIVE/deg/a\x00b.wav'), ('path', 'NISQA_TRAIN_LIVE/deg/./file.wav'),
            ('filepath_ref', 'NISQA_TRAIN_LIVE/ref/../file.wav'),
            ('filepath_ref', 'NISQA_TRAIN_LIVE/ref/other.wav'), ('filename_deg', 'other.wav'),
            ('filename_ref', 'book_0000_chp_0009_reader_00001_17_seg.wav'),
            ('filename_deg', 'book_00000_chp_0009_reader_00000_18_seg_live_phone_1.wav'),
            ('con_description', 'Skype'), ('con_description', 'phone'), ('source', 'OTHER'), ('lang', 'de'),
        ]
        for field, value in changes:
            source = fixture()
            target = source['training'][0] if field == 'path' else source['training'][0]['metadata']
            target[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                core.prepare_inventory(source)
        source = fixture()
        source['training'].append(copy.deepcopy(source['training'][0]))
        with self.assertRaises(ValueError):
            core.prepare_inventory(source)

    def test_unexpected_inventory_schema_or_nonopaque_values_fail_before_selection(self):
        cases = []
        value = fixture(); value['numericTargetsAccessed'] = True; cases.append(value)
        value = fixture(); value['columns'].append('mos'); cases.append(value)
        value = fixture(); value['training'][0]['metadata']['file'] = 5; cases.append(value)
        value = fixture(); value['training'][0]['extra'] = 'unexpected'; cases.append(value)
        value = fixture(); value['extra'] = 'unexpected'; cases.append(value)
        for value in cases:
            with self.assertRaises(ValueError):
                core.prepare_inventory(value)
        with self.assertRaises(ValueError):
            core.prepare_inventory(fixture(), expected_count=1020)

    def test_synthetic_review_gate_bindings_runtime_and_no_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            here = base/'research'; (here/'outputs').mkdir(parents=True)
            protocol = base/'protocol.md'; protocol.write_text('synthetic identity-only protocol')
            source = base/'source.py'; source.write_text('synthetic source')
            data = base/'inventory.json'; core.write(data, fixture())
            plan_value = dict(study=core.STUDY, protocol=core.binding(protocol),
                inputs={'lineageInventory': core.binding(data)}, sources={'source': core.binding(source)},
                lineageSources={}, archiveSources={}, expectedInventoryCount=50,
                runtime={'synthetic': 'fixture-only'}, rules=core.RULES, **core.FLAGS)
            with patch.multiple(core, HERE=here, PROTOCOL=protocol), patch.object(core, 'declaration', return_value=plan_value):
                pin = core.declare(here/'outputs'/'pilot')
                review = base/'review.json'
                core.write(review, dict(planSha256=pin['sha256'], verdict='clear', blockingFindings=[],
                                        independent=False, reviewer='synthetic reviewer'))
                with self.assertRaises(ValueError):
                    core.run(pin['path'], pin['sha256'], review)
                self.assertFalse(Path(pin['path']).with_name('selection-started.json').exists())
                review.unlink()
                core.write(review, dict(planSha256=pin['sha256'], verdict='clear', blockingFindings=[],
                                        independent=True, reviewer='synthetic reviewer'))
                source.write_text('changed source')
                with self.assertRaises(ValueError):
                    core.run(pin['path'], pin['sha256'], review)
                source.write_text('synthetic source')
                freeze = core.read(core.run(pin['path'], pin['sha256'], review))
                self.assertEqual(freeze['selectedCount'], 20)
                self.assertEqual(freeze['selectedSourceCodeGroupCount'], 20)
                self.assertEqual(core.read(freeze['selected'])['conditionCounts'], {'phone': 10, 'Skype': 10})
                self.assertEqual(core.read(freeze['eligible'])['support']['eligibleCount'], 50)
                with self.assertRaises(ValueError):
                    core.run(pin['path'], pin['sha256'], review)
                changed_runtime = {**plan_value, 'runtime': {'synthetic': 'changed'}}
                with patch.object(core, 'declaration', return_value=changed_runtime), self.assertRaises(ValueError):
                    core.load(pin['path'], pin['sha256'])


if __name__ == '__main__':
    unittest.main()
