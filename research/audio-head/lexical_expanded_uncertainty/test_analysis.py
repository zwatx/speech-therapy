"""Synthetic paired-draw and direct explicit-vote numerical oracles only."""
import unittest

import numpy as np

from lexical_expanded_uncertainty import analysis as a


def model(probabilities, logs=None):
    p = np.asarray(probabilities, dtype=np.float64)
    return dict(probabilities=p, logProbabilities=np.log(p) if logs is None else np.asarray(logs, dtype=np.float64))


def fixture():
    rows, folds, groups, candidate, reference = [], [], [], [], []
    for speaker in range(10):
        for phone_index, phone in enumerate(a.PHONES):
            rows.append(dict(speakerId=f'child-{speaker}', targetPhone=phone,
                             raterCounts=([1, 1, 3], [0, 0, 5], [3, 1, 1])[(speaker + phone_index) % 3]))
            folds.append(speaker // 2)
            groups.append(phone_index % 5)
            candidate.append(([.4, .2, .4], [.4, .3, .3], [.1, .2, .7])[phone_index % 3])
            reference.append(([.3, .3, .4], [.2, .3, .5])[(phone_index + speaker) % 2])
    sampling = dict(speakerIds=[f'child-{s}' for s in range(10)], speakerFolds=[s // 2 for s in range(10)],
                    weights=np.asarray([[1] * 10, [2, 0] * 5, [0, 2] * 5], dtype=np.int64))
    return rows, folds, groups, model(candidate), model(reference), sampling


def explicit_vote_metrics(rows, probabilities, logs):
    """Separate elementary oracle on physically duplicated rows and five votes."""
    losses, briers, phones = [], [], {}
    events = {name: [] for name in ('rating0AP', 'below2AP')}
    for row, p, lp in zip(rows, probabilities, logs, strict=True):
        row_losses, row_briers = [], []
        for rating, count in enumerate(row['raterCounts']):
            for _ in range(count):
                row_losses.append(-lp[rating])
                row_briers.append(sum((p[k] - int(k == rating)) ** 2 for k in range(3)))
                events['rating0AP'].append((p[0], rating == 0))
                events['below2AP'].append((p[:2].sum(), rating < 2))
        loss = sum(row_losses) / 5
        losses.append(loss)
        briers.append(sum(row_briers) / 5)
        phones.setdefault(row['targetPhone'], []).append(loss)
    result = dict(NLL=sum(losses) / len(rows), Brier=sum(briers) / len(rows),
                  macroNLL=sum(sum(phones[p]) / len(phones[p]) for p in a.PHONES) / 23
                  if set(phones) == set(a.PHONES) else None)
    for name, votes in events.items():
        positives = sum(positive for _, positive in votes)
        if not positives:
            result[name] = None
            continue
        seen, seen_positive, precision_sum = 0, 0, 0.
        for score in sorted({score for score, _ in votes}, reverse=True):
            tied = [positive for value, positive in votes if value == score]
            seen += len(tied)
            seen_positive += sum(tied)
            precision_sum += sum(tied) * seen_positive / seen
        result[name] = precision_sum / positives
    return result


class AnalysisTests(unittest.TestCase):
    def test_shared_weighted_draws_match_explicit_duplicate_rows_and_votes(self):
        rows, folds, groups, candidate, reference, sampling = fixture()
        result = a.analyze(rows, folds, groups, candidate, reference, sampling)
        self.assertEqual(set(result['perPhone']), set(a.PHONES))
        for draw, weights in enumerate(sampling['weights']):
            repeated = np.repeat(np.arange(len(rows)), np.repeat(weights, 23))
            duplicated = [rows[i] for i in repeated]
            expected = [explicit_vote_metrics(duplicated, value['probabilities'][repeated], value['logProbabilities'][repeated])
                        for value in (candidate, reference)]
            for key in a.ENDPOINTS:
                with self.subTest(draw=draw, endpoint=key):
                    self.assertAlmostEqual(result['replicates'][key][draw], expected[0][key] - expected[1][key], places=13)
            for phone in a.PHONES:
                selected = [i for i in repeated if rows[i]['targetPhone'] == phone]
                losses = [explicit_vote_metrics([rows[i] for i in selected], value['probabilities'][selected],
                                               value['logProbabilities'][selected])['NLL'] for value in (candidate, reference)]
                self.assertAlmostEqual(result['perPhone'][phone]['replicates'][draw], losses[0] - losses[1], places=13)
        for name, value in (('candidate', candidate), ('reference', reference)):
            expected = explicit_vote_metrics(rows, value['probabilities'], value['logProbabilities'])
            for key in a.ENDPOINTS:
                self.assertAlmostEqual(result['observed'][name][key], expected[key], places=13)
        # Fixed exact-score ties remain present rather than being jittered.
        self.assertEqual(len(set(candidate['probabilities'][:, 0])), 2)

    def test_every_fold_and_leave_one_child_out_identity(self):
        args = fixture()
        rows, folds, _, candidate, reference, sampling = args
        result = a.analyze(*args)
        influence = result['influence']
        self.assertEqual(list(influence['speakerFolds']), list(map(str, range(5))))
        self.assertEqual(list(influence['leaveOneChildOut']), sampling['speakerIds'])
        loss_delta = -np.sum(np.asarray([r['raterCounts'] for r in rows]) / 5
                             * (candidate['logProbabilities'] - reference['logProbabilities']), axis=1)
        for fold, value in influence['speakerFolds'].items():
            mask = np.asarray(folds) == int(fold)
            self.assertEqual(value['positions'], 46)
            self.assertEqual(value['children'], 2)
            self.assertEqual(value['raterVotes'], np.asarray([r['raterCounts'] for r, keep in zip(rows, mask) if keep]).sum(0).tolist())
            self.assertAlmostEqual(value['NLLDelta'], loss_delta[mask].mean(), places=14)
            self.assertAlmostEqual(value['additiveNLLContribution'], loss_delta[mask].sum() / len(rows), places=14)
        self.assertAlmostEqual(sum(v['additiveNLLContribution'] for v in influence['speakerFolds'].values()),
                               result['pairedIntervals']['NLL']['observed'], places=14)
        for speaker, value in influence['leaveOneChildOut'].items():
            keep = np.asarray([row['speakerId'] != speaker for row in rows])
            self.assertEqual(value['removedPositions'], 23)
            self.assertEqual(value['remainingPositions'], 207)
            self.assertAlmostEqual(value['NLLDelta'], loss_delta[keep].mean(), places=14)

    def test_absent_phone_retention_and_draw_specific_undefined_counts(self):
        rows = [dict(speakerId='a', targetPhone='B', raterCounts=[1, 1, 3]),
                dict(speakerId='b', targetPhone='P', raterCounts=[0, 0, 5])]
        sampling = dict(speakerIds=['a', 'b'], speakerFolds=[0, 0], weights=np.array([[2, 0], [0, 2]]))
        result = a.analyze(rows, [0, 0], [0, 1], model([[.2, .3, .5]] * 2), model([[.3, .3, .4]] * 2), sampling)
        self.assertEqual(len(result['perPhone']), 23)
        self.assertIsNone(result['pairedIntervals']['macroNLL']['observed'])
        self.assertEqual(result['replicates']['macroNLL'], [None, None])
        for phone in ('B', 'P'):
            self.assertEqual(result['perPhone'][phone]['positions'], 1)
            self.assertEqual(result['perPhone'][phone]['children'], 1)
            self.assertEqual(result['perPhone'][phone]['validReplicates'], 1)
            self.assertEqual(result['perPhone'][phone]['undefinedReplicates'], 1)
        absent = result['perPhone']['NG']
        self.assertEqual(absent['raterVotes'], [0, 0, 0])
        self.assertEqual(absent['positions'], 0)
        self.assertIsNone(absent['observed'])
        self.assertIsNone(absent['interval95'])
        self.assertEqual(absent['replicates'], [None, None])
        self.assertEqual(result['replicates']['rating0AP'][1], None)
        for fold in ('1', '2', '3', '4'):
            value = result['influence']['speakerFolds'][fold]
            self.assertIsNone(value['NLLDelta'])
            self.assertEqual(value['additiveNLLContribution'], 0.)

    def test_stable_underflow_and_no_positive_votes_single_child(self):
        rows = [dict(speakerId='a', targetPhone='B', raterCounts=[0, 0, 5])]
        logs = [[0., -1000., -2000.]]
        sampling = dict(speakerIds=['a'], speakerFolds=[4], weights=np.ones((2, 1), dtype=int))
        result = a.analyze(rows, [4], [2], model(np.exp(logs), logs), model([[.2, .3, .5]]), sampling)
        self.assertEqual(result['observed']['candidate']['NLL'], 2000.)
        for key in ('macroNLL', 'rating0AP', 'below2AP'):
            self.assertEqual(result['replicates'][key], [None, None])
            self.assertIsNone(result['pairedIntervals'][key]['interval95'])
        self.assertGreater(result['pairedIntervals']['NLL']['observed'], 1999.)
        self.assertEqual(result['influence']['leaveOneChildOut']['a'],
                         dict(removedPositions=1, remainingPositions=0, NLLDelta=None))

    def test_linear_quantiles_sign_fractions_and_explicit_nulls(self):
        result = a.interval([-2., 0., 4., None], 1.)
        np.testing.assert_allclose(result['interval95'], [-1.9, 3.8])
        self.assertEqual(result['validReplicates'], 3)
        self.assertEqual(result['undefinedReplicates'], 1)
        self.assertEqual(result['fractionBelowZero'], 1/3)
        self.assertEqual(result['fractionAboveZero'], 1/3)
        self.assertEqual(a.interval([], None)['validReplicates'], 0)
        self.assertIsNone(a.interval([None], None)['fractionAboveZero'])
        for values, observed in (([np.nan], 0), ([np.inf], 0), ([1], np.nan)):
            with self.assertRaises(ValueError):
                a.interval(values, observed)

    def test_pair_sampling_guards(self):
        for mutation in ('reordered-ids', 'duplicate-ids', 'missing-id', 'wrong-fold', 'wrong-width',
                         'empty', 'float', 'bool', 'negative', 'stratum-total', 'cross-stratum'):
            args = list(fixture())
            sample = args[-1]
            if mutation == 'reordered-ids':
                sample['speakerIds'].reverse()
            elif mutation == 'duplicate-ids':
                sample['speakerIds'][1] = sample['speakerIds'][0]
            elif mutation == 'missing-id':
                sample['speakerIds'].pop()
            elif mutation == 'wrong-fold':
                sample['speakerFolds'][0] = 4
            elif mutation == 'wrong-width':
                sample['weights'] = sample['weights'][:, :-1]
            elif mutation == 'empty':
                sample['weights'] = sample['weights'][:0]
            elif mutation in ('float', 'bool'):
                sample['weights'] = sample['weights'].astype(float if mutation == 'float' else bool)
            elif mutation == 'negative':
                sample['weights'][0, 0] = -1
            elif mutation == 'stratum-total':
                sample['weights'][0, 0] = 0
            else:
                sample['weights'][0, 0] = 0
                sample['weights'][0, 2] = 2
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                a.analyze(*args)

    def test_row_array_vote_phone_and_fold_guards(self):
        for slot, bad in ((1, [0]), (2, [0]), (1, [5] * 230), (2, [-1] * 230),
                          (1, [False] * 230), (2, [0.] * 230)):
            args = list(fixture())
            args[slot] = bad
            with self.subTest(slot=slot, bad=bad[:2]), self.assertRaises(ValueError):
                a.analyze(*args)
        for mutation in ('invalid-phone', 'float-votes', 'boolean-votes', 'bad-votes', 'logs', 'p-shape', 'speaker-fold', 'mixed-speakers'):
            args = list(fixture())
            if mutation == 'invalid-phone':
                args[0][0]['targetPhone'] = 'ZH'
            elif mutation == 'float-votes':
                args[0][0]['raterCounts'] = [1., 1., 3.]
            elif mutation == 'boolean-votes':
                args[0][0]['raterCounts'] = [True, 1, 3]
            elif mutation == 'bad-votes':
                args[0][0]['raterCounts'] = [1, 1, 2]
            elif mutation == 'logs':
                args[3]['logProbabilities'][0, 0] = -100.
            elif mutation == 'p-shape':
                args[4]['probabilities'] = args[4]['probabilities'][:-1]
            elif mutation == 'speaker-fold':
                args[1][0] = 1
            else:
                args[0][0]['speakerId'] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                a.analyze(*args)


if __name__ == '__main__':
    unittest.main()
