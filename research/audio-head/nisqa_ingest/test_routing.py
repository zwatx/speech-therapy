"""Synthetic combined-CSV boundary and deterministic metadata-only selection."""
import csv
import io
import unittest

from nisqa_ingest import routing as r

HEADER = ['db', 'filepath_deg', 'mos', 'noi', 'dis', 'col', 'loud', 'reader']
SCALES = {name: [1, 5] for name in r.TARGETS}


def csv_source(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(HEADER)
    writer.writerows(rows)
    stream.seek(0)
    return stream


def train(index, values=None):
    return [r.TRAIN, f'{r.PREFIX}{index}.wav', *(values or ['3']*5), f'reader{index}']


class RoutingTests(unittest.TestCase):
    def test_inventory_reads_only_identity_and_explicit_metadata(self):
        rows = [['NISQA_VAL_LIVE', 'NISQA_VAL_LIVE/deg/v.wav', 'SECRET,\nTOKEN', 'nan', 'bad', '6', 'inf', 'heldout'],
                train(1, ['TRAIN_SECRET']*5)]
        rows[1][-1] = 'opaque,\nreader'
        result = r.inventory(csv_source(rows), metadata_fields=['reader'], verified_metadata_fields=['reader'])
        self.assertEqual(len(result['training']), 1)
        self.assertEqual(result['training'][0]['metadata'], {'reader': 'opaque,\nreader'})
        self.assertNotIn('SECRET', repr(result))
        self.assertNotIn('nan', repr(result))
        self.assertFalse(result['targetFieldsAccessed'])

    def test_metadata_targets_and_unverified_fields_rejected(self):
        for fields, verified in [(['mos'], ['mos']), (['reader'], []), (['unknown'], ['reader'])]:
            with self.assertRaises(ValueError):
                r.inventory(csv_source([]), metadata_fields=fields, verified_metadata_fields=verified)

    def test_unsafe_training_paths_and_prefix_tricks(self):
        paths = ['/NISQA_TRAIN_LIVE/deg/a.wav', 'NISQA_TRAIN_LIVE/deg/../a.wav',
                 'NISQA_TRAIN_LIVE\\deg\\a.wav', 'NISQA_TRAIN_LIVEx/deg/a.wav',
                 'NISQA_TRAIN_LIVE/deg/a\x00.wav', 'NISQA_TRAIN_LIVE/deg//a.wav']
        for path in paths:
            with self.subTest(path=path), self.assertRaises(ValueError):
                r.inventory(csv_source([[r.TRAIN, path, *['3']*5, 'reader']]))
        with self.assertRaises(ValueError):
            r.inventory(csv_source([['NISQA_VAL_LIVE', r.PREFIX+'a.wav', *['3']*5, 'reader']]))

    def test_duplicate_inventory_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate CSV identity'):
            r.inventory(csv_source([train(1), train(1)]))

    def test_selected_only_numeric_access_mixed_row_order(self):
        rows = [train(i) for i in range(20)]
        unselected = train(99, ['OUTSIDE_SECRET', 'nan', 'inf', '-1000', 'bad'])
        heldout = ['NISQA_VAL_LIVE', 'NISQA_VAL_LIVE/deg/v.wav', 'HELDOUT_SECRET', 'NaN', 'inf', 'bad', '-999', 'x']
        chosen = [row[1] for row in rows]
        result = r.selected_values(csv_source([heldout, *rows[10:], unselected, *rows[:10]]), chosen, scales=SCALES)
        self.assertEqual([row['path'] for row in result['rows']], chosen)
        self.assertTrue(result['trainingOnly'] and result['completeTargets'])
        self.assertNotIn('SECRET', repr(result))
        self.assertEqual(result['rows'][0]['quality'], {name: 3. for name in r.TARGETS})

    def test_selected_numeric_failure_does_not_expose_target(self):
        for token in ('SELECTED_SECRET', 'NaN', 'inf', '6'):
            rows = [train(i) for i in range(20)]
            rows[0][2] = token
            with self.assertRaises(ValueError) as error:
                r.selected_values(csv_source(rows), [row[1] for row in rows], scales=SCALES)
            self.assertNotIn(token, str(error.exception))

    def test_missing_and_duplicate_selected_identity_cannot_replace(self):
        rows = [train(i) for i in range(20)]
        chosen = [row[1] for row in rows]
        for contents in (rows[:-1]+[train(99)], rows+[train(0)]):
            with self.assertRaises(ValueError):
                r.selected_values(csv_source(contents), chosen, scales=SCALES)
        with self.assertRaises(ValueError):
            r.selected_values(csv_source(rows), chosen[:-1]+[chosen[0]], scales=SCALES)

    def test_declared_missingness_is_preserved_and_readiness_separate(self):
        rows = [train(i) for i in range(20)]
        rows[0][2] = 'NA'
        result = r.selected_values(csv_source(rows), [row[1] for row in rows], scales=SCALES,
                                   missing_values={'mos': ['NA']})
        self.assertIsNone(result['rows'][0]['quality']['mos'])
        self.assertEqual(result['rows'][0]['declaredMissing'], {'mos': 'NA'})
        self.assertFalse(result['completeTargets'])

    def test_selection_is_order_invariant_and_has_fixed_quotas(self):
        metadata = [dict(path=f'{r.PREFIX}{i}-{j}.wav', captureCondition='phone' if i%2==0 else 'Skype',
                         readerGroup=f'group{i}') for i in range(30) for j in range(2)]
        selected = r.select(metadata)
        self.assertEqual(selected, r.select(list(reversed(metadata))))
        self.assertEqual(len({row['readerGroup'] for row in selected}), 20)
        self.assertEqual([row['captureCondition'] for row in selected].count('phone'), 10)
        self.assertEqual([row['captureCondition'] for row in selected].count('Skype'), 10)

    def test_shared_group_feasibility_and_insufficiency(self):
        metadata = [dict(path=f'{r.PREFIX}{i}-{condition}.wav', captureCondition=condition, readerGroup=f'g{i}')
                    for i in range(20) for condition in ('phone', 'Skype')]
        self.assertEqual(len(r.select(metadata)), 20)
        for subset in (metadata[:18], [row for row in metadata if row['captureCondition']=='phone']):
            with self.assertRaises(ValueError):
                r.select(subset)
        with self.assertRaises(ValueError):
            r.select([dict(metadata[0], mos=3.)])


if __name__ == '__main__': unittest.main()
