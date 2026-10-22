"""Explicit-vote numerical and complete-partition synthetic tests only."""
import math
import unittest

import numpy as np

from lexical_phone_response import analysis as a


def fixture():
    rows, folds, groups, candidate, reference = [], [], [], [], []
    for speaker in range(10):
        for number, phone in enumerate(a.PHONES):
            rows.append(dict(id=f'{speaker}-{number}', clipId=f'clip-{speaker}-{number // 4}',
                             speakerId=f'child-{speaker}', targetPhone=phone,
                             raterCounts=([1, 1, 3], [0, 0, 5], [2, 2, 1])[(speaker + number) % 3]))
            folds.append(speaker // 2)
            groups.append((speaker + number) % 5)
            candidate.append(([.4, .2, .4], [.1, .3, .6])[number % 2])
            reference.append(([.2, .2, .6], [.3, .1, .6])[(number + speaker) % 2])
    return rows, folds, groups, np.log(candidate), np.log(reference)


def vote_oracle(row, candidate, reference):
    by_class = [sum(reference[rating] - candidate[rating] for _ in range(count)) / 5
                for rating, count in enumerate(row['raterCounts'])]
    return sum(by_class), by_class


class PhoneResponseTests(unittest.TestCase):
    def test_explicit_votes_sign_class_conditions_and_denominators(self):
        rows = [dict(id='a', clipId='one', speakerId='child', targetPhone='B', raterCounts=[2, 0, 3]),
                dict(id='b', clipId='one', speakerId='child', targetPhone='P', raterCounts=[0, 0, 5])]
        candidate = np.log([[.5, .25, .25], [.25, .25, .5]])
        reference = np.log([[.25, .25, .5], [.25, .25, .5]])
        result = a.analyze(rows, [0, 0], [0, 1], candidate, reference)
        self.assertAlmostEqual(result['rowLossDelta'][0], math.log(2) / 5)
        self.assertEqual(result['rowLossDelta'][1], 0.)
        self.assertAlmostEqual(result['pooled']['meanNLLDelta'], math.log(2) / 10)
        phone = result['perPhone']['B']
        self.assertAlmostEqual(phone['meanNLLDelta'], math.log(2) / 5)
        self.assertAlmostEqual(phone['pooledNLLContribution'], math.log(2) / 10)
        classes = phone['ratingClasses']
        self.assertAlmostEqual(classes['0']['conditionalNLLDelta'], -math.log(2))
        self.assertAlmostEqual(classes['2']['conditionalNLLDelta'], math.log(2))
        self.assertAlmostEqual(classes['0']['phoneNLLContribution'], -.4 * math.log(2))
        self.assertAlmostEqual(classes['2']['pooledNLLContribution'], .3 * math.log(2))
        self.assertIsNone(classes['1']['conditionalNLLDelta'])
        self.assertEqual(result['pooled']['support'], dict(positions=2, children=1, recordings=1, raterVotes=[2, 0, 8]))

    def test_full_phone_fold_word_child_partitions_against_simple_loop_oracle(self):
        rows, folds, groups, candidate, reference = fixture()
        result = a.analyze(rows, folds, groups, candidate, reference)
        oracle = [vote_oracle(row, candidate[i], reference[i]) for i, row in enumerate(rows)]
        np.testing.assert_allclose(result['rowLossDelta'], [value[0] for value in oracle], atol=1e-15, rtol=1e-14)
        np.testing.assert_allclose(result['rowClassLossDelta'], [value[1] for value in oracle], atol=1e-15, rtol=1e-14)
        children = sorted({row['speakerId'] for row in rows})
        self.assertEqual(tuple(result['perPhone']), a.PHONES)
        def check_cell(cell, positions, denominator):
            counts = [sum(rows[i]['raterCounts'][k] for i in positions) for k in range(3)]
            self.assertEqual(cell['support'], dict(positions=len(positions), children=len({rows[i]['speakerId'] for i in positions}),
                recordings=len({rows[i]['clipId'] for i in positions}), raterVotes=counts))
            total = sum(oracle[i][0] for i in positions)
            self.assertAlmostEqual(cell['phoneNLLContribution'], total / denominator, places=14)
            if positions:
                self.assertAlmostEqual(cell['meanNLLDelta'], total / len(positions), places=14)
            else:
                self.assertIsNone(cell['meanNLLDelta'])
        for phone, value in result['perPhone'].items():
            positions = [i for i, row in enumerate(rows) if row['targetPhone'] == phone]
            check_cell(value, positions, len(positions))
            self.assertAlmostEqual(value['pooledNLLContribution'], sum(oracle[i][0] for i in positions) / len(rows), places=14)
            self.assertEqual(list(value['speakerFolds']), list(map(str, range(5))))
            self.assertEqual(list(value['wordCells']), [f's{s}-w{w}' for s in range(5) for w in range(5)])
            self.assertEqual(list(value['children']), children)
            for fold, cell in value['speakerFolds'].items():
                check_cell(cell, [i for i in positions if folds[i] == int(fold)], len(positions))
            for key, cell in value['wordCells'].items():
                fold, group = int(key[1]), int(key[4])
                check_cell(cell, [i for i in positions if (folds[i], groups[i]) == (fold, group)], len(positions))
            for child, cell in value['children'].items():
                check_cell(cell, [i for i in positions if rows[i]['speakerId'] == child], len(positions))
            for rating, cell in value['ratingClasses'].items():
                k = int(rating)
                votes = sum(rows[i]['raterCounts'][k] for i in positions)
                total = sum(oracle[i][1][k] for i in positions)
                self.assertEqual(cell['votes'], votes)
                self.assertAlmostEqual(cell['conditionalNLLDelta'], total * 5 / votes, places=14)
                self.assertAlmostEqual(cell['phoneNLLContribution'], total / len(positions), places=14)
        self.assertAlmostEqual(sum(value['pooledNLLContribution'] for value in result['perPhone'].values()), result['pooled']['meanNLLDelta'], places=14)

    def test_absent_phone_empty_cells_classes_and_zero_effect_children_retained(self):
        rows = [dict(id='a', clipId='one', speakerId='a', targetPhone='B', raterCounts=[0, 0, 5]),
                dict(id='b', clipId='two', speakerId='b', targetPhone='P', raterCounts=[0, 0, 5])]
        logs = np.log([[.2, .3, .5]] * 2)
        result = a.analyze(rows, [0, 1], [4, 0], logs, logs)
        self.assertEqual(result['rowLossDelta'], [0., 0.])
        for phone, value in result['perPhone'].items():
            self.assertEqual(list(value['children']), ['a', 'b'])
            self.assertEqual(value['children']['a']['phoneNLLContribution'], 0.)
            self.assertEqual(value['children']['b']['phoneNLLContribution'], 0.)
            self.assertEqual(len(value['speakerFolds']), 5)
            self.assertEqual(len(value['wordCells']), 25)
            self.assertIsNone(value['ratingClasses']['0']['conditionalNLLDelta'])
        absent = result['perPhone']['NG']
        self.assertEqual(absent['support'], dict(positions=0, children=0, recordings=0, raterVotes=[0, 0, 0]))
        self.assertIsNone(absent['meanNLLDelta'])
        self.assertEqual(absent['pooledNLLContribution'], 0.)
        for name in ('speakerFolds', 'wordCells', 'children'):
            self.assertTrue(all(cell['meanNLLDelta'] is None and cell['phoneNLLContribution'] == 0 for cell in absent[name].values()))
        self.assertIsNone(result['perPhone']['B']['children']['b']['meanNLLDelta'])
        self.assertEqual(result['perPhone']['P']['children']['b']['meanNLLDelta'], 0.)

    def test_extreme_stable_logs_remain_unclipped(self):
        rows = [dict(id='one', clipId='one', speakerId='one', targetPhone='B', raterCounts=[0, 0, 5])]
        result = a.analyze(rows, [4], [4], [[0., -1000., -2000.]], [[0., -500., -1000.]])
        self.assertEqual(result['rowLossDelta'], [1000.])
        self.assertEqual(result['rowClassLossDelta'], [[0., 0., 1000.]])
        self.assertEqual(result['perPhone']['B']['ratingClasses']['2']['conditionalNLLDelta'], 1000.)
        self.assertEqual(result['perPhone']['B']['wordCells']['s4-w4']['phoneNLLContribution'], 1000.)

    def test_log_shape_finite_sign_and_normalization_guards(self):
        args = fixture()
        invalid = [np.zeros((230, 2)), args[3][:-1], np.zeros((230, 3)), args[3] + .01,
                   np.full((230, 3), np.nan), np.full((230, 3), -np.inf), np.full((230, 3), .1),
                   args[3].astype(complex) + 1j]
        for side in (3, 4):
            for value in invalid:
                changed = list(args)
                changed[side] = value
                with self.subTest(side=side, shape=value.shape), self.assertRaises(ValueError):
                    a.analyze(*changed)

    def test_row_identity_vote_and_phone_guards(self):
        for mutation in ('empty', 'duplicate-id', 'empty-id', 'missing-id', 'numeric-speaker', 'empty-clip',
                         'unknown-phone', 'float-votes', 'bool-votes', 'negative-votes', 'four-votes', 'wrong-width', 'null-votes'):
            args = list(fixture())
            row = args[0][0]
            if mutation == 'empty':
                args[0] = []
            elif mutation == 'duplicate-id':
                row['id'] = args[0][1]['id']
            elif mutation == 'empty-id':
                row['id'] = ''
            elif mutation == 'missing-id':
                del row['id']
            elif mutation == 'numeric-speaker':
                row['speakerId'] = 3
            elif mutation == 'empty-clip':
                row['clipId'] = ''
            elif mutation == 'unknown-phone':
                row['targetPhone'] = 'ZH'
            else:
                row['raterCounts'] = {'float-votes': [1., 1., 3.], 'bool-votes': [True, 1, 3],
                    'negative-votes': [-1, 1, 5], 'four-votes': [1, 1, 2], 'wrong-width': [2, 3], 'null-votes': None}[mutation]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                a.analyze(*args)

    def test_fold_group_integer_ranges_and_child_consistency(self):
        for side in (1, 2):
            for value in ([0], [5] * 230, [-1] * 230, [0.] * 230, [False] * 230, [False] + [0] * 229):
                args = list(fixture())
                args[side] = value
                with self.subTest(side=side, value=value[:2]), self.assertRaises(ValueError):
                    a.analyze(*args)
        args = list(fixture())
        args[1][0] = 1
        with self.assertRaisesRegex(ValueError, 'multiple folds'):
            a.analyze(*args)


if __name__ == '__main__':
    unittest.main()
