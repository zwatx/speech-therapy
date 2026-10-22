"""Synthetic-only selected-target boundary and strict nominal token checks."""
import csv
import io
import json
import unittest
from unittest.mock import patch

from nisqa_ingest import routing
from nisqa_ingest import selected_targets as s

HEADER = ['db', 'filepath_deg', *routing.TARGETS, 'unused']
PATHS = [routing.PREFIX + str(i) + '.wav' for i in range(20)]


def rows():
    return [[routing.TRAIN, path, *['3'] * 5, 'unused'] for path in PATHS]


def source(data):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(HEADER)
    writer.writerows(data)
    stream.seek(0)
    return stream


class SelectedTargetsTests(unittest.TestCase):
    def test_order_and_numeric_forms_and_json_policy(self):
        data = rows()
        data[0][2:7] = ['+1', '5.', '.3e1', '30E-1', '4.999']
        result = s.parse_selected_targets(source(list(reversed(data))), PATHS)
        self.assertEqual(result['selectedPaths'], PATHS)
        self.assertEqual([r['path'] for r in result['rows']], PATHS)
        self.assertEqual(list(result['rows'][0]['quality'].values()), [1, 5, 3, 3, 4.999])
        self.assertTrue(result['completeTargets'] and result['trainingOnly'])
        self.assertEqual(json.loads(json.dumps(s.POLICY)), s.POLICY)

    def test_unselected_short_rows_and_quoted_tokens_not_exposed(self):
        data = rows()
        heldout = ['NISQA_VAL_LIVE', 'NISQA_VAL_LIVE/deg/v.wav', 'SECRET,\nNaN', 'inf']
        unselected = [routing.TRAIN, routing.PREFIX+'other.wav']
        data[0][-1] = 'UNUSED_SECRET,\nquoted'
        result = s.parse_selected_targets(source([heldout, *data[:10], unselected, *data[10:]]), PATHS)
        self.assertNotIn('SECRET', repr(result))

    def test_discarded_targets_are_never_indexed(self):
        class GuardRow(list):
            def __getitem__(self, key):
                if key not in (0, 1):
                    raise AssertionError('Discarded target accessed')
                return super().__getitem__(key)
        sentinel = GuardRow(['NISQA_TEST_FOR', 'NISQA_TEST_FOR/deg/x.wav', object()])
        index = {name: i for i, name in enumerate(HEADER)}
        with patch.object(routing, '_reader', return_value=(iter([sentinel, *rows()]), HEADER, index)):
            result = s.parse_selected_targets(None, PATHS)
        self.assertTrue(result['completeTargets'])

    def test_exact_missingness_preserved(self):
        data = rows()
        data[0][2:7] = ['', 'NaN', '', 'NaN', '']
        result = s.parse_selected_targets(source(data), PATHS)
        self.assertFalse(result['completeTargets'])
        self.assertEqual(result['missingCounts'], dict.fromkeys(routing.TARGETS, 1))
        self.assertEqual(result['rows'][0]['declaredMissing'], dict(zip(routing.TARGETS, data[0][2:7])))
        self.assertEqual(result['rows'][0]['quality'], dict.fromkeys(routing.TARGETS))

    def test_invalid_tokens_generic_error(self):
        for token in ['nan', 'NAN', 'NA', ' NaN', 'NaN ', ' 3', '3 ', '3\n', '٣',
                      '３', '1_0', '0x3', 'inf', '+Infinity', '1e9999', '0.999', '5.001',
                      '-3', '1e', '.', 'SECRET,\nvalue']:
            with self.subTest(token=token):
                data = rows(); data[0][2] = token
                with self.assertRaises(ValueError) as caught:
                    s.parse_selected_targets(source(data), PATHS)
                self.assertEqual(str(caught.exception), 'Selected quality value invalid')

    def test_selected_width_duplicate_and_missing(self):
        for data in [rows()[:-1], rows()+[rows()[0]], [rows()[0][:-1], *rows()[1:]],
                     [rows()[0]+['extra'], *rows()[1:]]]:
            with self.assertRaises(ValueError):
                s.parse_selected_targets(source(data), PATHS)

    def test_required_header_and_selected_nonstring(self):
        for header in [HEADER[:-2], HEADER + ['mos'], ['db', 'filepath_deg']]:
            stream = io.StringIO(newline='')
            csv.writer(stream).writerow(header)
            stream.seek(0)
            with self.assertRaises(ValueError):
                s.parse_selected_targets(stream, PATHS)
        data = rows(); data[0][2] = object()
        index = {name: i for i, name in enumerate(HEADER)}
        with patch.object(routing, '_reader', return_value=(iter(data), HEADER, index)):
            with self.assertRaisesRegex(ValueError, '^Selected quality value invalid$'):
                s.parse_selected_targets(None, PATHS)

    def test_selection_count_safe_paths_and_split_agreement(self):
        invalid = [PATHS[:-1], PATHS+[routing.PREFIX+'extra.wav'], PATHS[:-1]+[PATHS[0]]]
        for path in ['/x.wav', 'NISQA_TRAIN_LIVEx/deg/x.wav', routing.PREFIX+'../x.wav',
                     routing.PREFIX+'x\\y.wav', routing.PREFIX+'x\x00.wav', routing.PREFIX+'./x.wav']:
            invalid.append(PATHS[:-1]+[path])
        for selected in invalid:
            with self.assertRaises(ValueError):
                s.parse_selected_targets(source(rows()), selected)
        data = rows(); data[0][0] = 'NISQA_VAL_LIVE'
        with self.assertRaises(ValueError):
            s.parse_selected_targets(source(data), PATHS)


if __name__ == '__main__':
    unittest.main()
