"""Synthetic joins and guards only; no corpus artifacts or inference are opened."""
import copy
import unittest
from unittest.mock import patch

import numpy as np

from lexical_expanded_heads import evaluation as e


def lightweight_summary(prediction, rows):
    # Join tests avoid constructing thousands of reliability bins. Numerical
    # summaries and the six fixed checks have separate real-scoring tests below.
    metrics = dict(perRaterLogLoss=1., macroTargetLogLoss=1., perRaterBrier=.5,
                   discrimination=dict(rating0=dict(averagePrecision=.2),
                                       ratingBelow2=dict(averagePrecision=.4)))
    return dict(measures=dict(allWords=dict(metrics=dict(ages6to12=metrics))))


def row(index, phone):
    return dict(id=f'old-{index}', clipId=f'clip-{index}', speakerId=f'speaker-{index}',
                age=8, wordIndex=0, phoneIndex=0, targetPhone=phone, targetWord=f'WORD{index}',
                trainingEligible=True, raterCounts=[1, 1, 3])


def prediction(indices, probabilities):
    p = np.asarray(probabilities, dtype=np.float64)
    return dict(rowIndices=indices, probabilities=p.tolist(), logProbabilities=np.log(p).tolist())


def fixture():
    original, expanded, cells = [], [], {}
    for number, cell in enumerate(e.CELL_KEYS):
        original.append(dict(trainingEligible=False))  # Preserve old-index gaps.
        old = len(original)
        r = row(number, e.scoring.metrics.PHONES[number % 23])
        original.append(r)
        expanded.append(dict(r, id=f'expanded-{number}', legacyRowIndex=old, legacyRowId=r['id']))
        cells[old] = cell
    expanded.reverse()  # Expanded order intentionally disagrees with old order.
    expanded.append(dict(row(25, e.scoring.metrics.PHONES[0]), legacyRowIndex=None, legacyRowId=None))
    jobs, records = [], {}
    for regime in e.REGIMES:
        for family in e.FAMILIES:
            for s, w in e.CELL_KEYS:
                ids = [i for i, r in enumerate(expanded)
                       if (cells[r['legacyRowIndex']] if r['legacyRowIndex'] is not None else (0, 0)) == (s, w)]
                job = dict(id=f'{regime}-{family}-s{s}-w{w}', regime=regime, family=family,
                           speakerFold=s, wordGroup=w, fitRows=[], selectionRows=[], refitRows=[], outerRows=ids)
                p = [[.1 + i * .002, .3, .6 - i * .002] if family == 'scalars' else [.2, .2, .6] for i in ids]
                pred = prediction(ids, p)
                pred['rawProbabilities'] = np.asarray(p, dtype=np.float32).tolist()
                pred['NLL'] = e.mixture.mixture(pred, pred, [expanded[i] for i in ids])['NLL']
                jobs.append(job)
                records[job['id']] = dict(jobId=job['id'], prediction=pred,
                                         prior=prediction(ids, [[1/3] * 3 for _ in ids]))
    oldids = sorted(cells)
    reference = dict(**prediction(oldids, [[.2, .3, .5] for _ in oldids]),
        rowFolds=[cells[i][0] for i in oldids], rowWordGroups=[cells[i][1] for i in oldids],
        cells=[dict(speakerFold=s, wordGroup=w, rowIndices=[i for i in oldids if cells[i] == (s, w)])
               for s, w in e.CELL_KEYS],
        speakerFolds=[dict(speakerFold=s, rowIndices=[i for i in oldids if cells[i][0] == s],
                           summary=lightweight_summary(None, None)) for s in range(5)],
        pooled=lightweight_summary(None, None))
    references = {regime: {family: copy.deepcopy(reference)
                           for family in (*e.FAMILIES, 'equal-mixture', 'corrected-mixture')}
                  for regime in e.REGIMES}
    return expanded, original, jobs, records, references


class EvaluationTests(unittest.TestCase):
    def run_evaluation(self, values):
        with patch.object(e, 'summarize', side_effect=lightweight_summary):
            return e.evaluate(*values)

    def test_original_order_gaps_population_views_and_fixed_comparisons(self):
        values = fixture()
        result = self.run_evaluation(values)
        models = result['models']['all-age']
        scalar = models['scalars']['original']
        self.assertEqual(scalar['rowIndices'], list(range(1, 50, 2)))
        self.assertEqual(scalar['probabilities'][0], values[3][values[2][0]['id']]['prediction']['probabilities'][0])
        self.assertEqual(models['scalars']['all']['rowIndices'], list(range(26)))
        self.assertEqual(models['scalars']['added']['rowIndices'], [25])
        self.assertEqual(models['scalars']['added']['cells'][1]['rowIndices'], [])
        self.assertEqual(len(scalar['cells']), 25)
        self.assertEqual(len(scalar['speakerFolds']), 5)
        for s, p, mixed in zip(scalar['probabilities'], models['pca16-scalars']['original']['probabilities'],
                               models['equal-mixture']['original']['probabilities'], strict=True):
            np.testing.assert_allclose(mixed, (np.asarray(s) + p) / 2, rtol=1e-14)
        comp = result['comparisons']['all-age']
        self.assertEqual(set(comp), {'primary', 'secondary'})
        self.assertEqual(set(comp['primary']), {*e.FAMILIES, 'equal-mixture'})
        for check in comp['primary'].values():
            self.assertEqual(len(check['checks']), 6)
            self.assertFalse(check['promotionEligible'])
        self.assertNotIn('added', comp)
        self.assertNotIn('all', comp)

    def test_duplicate_omitted_or_renamed_jobs_and_records_fail(self):
        for mutation in ('duplicate-cell', 'missing-cell', 'bad-id', 'missing-record', 'extra-record'):
            values = fixture()
            jobs, records = values[2:4]
            if mutation == 'duplicate-cell':
                jobs[1] = copy.deepcopy(jobs[0])
            elif mutation == 'missing-cell':
                jobs.pop()
            elif mutation == 'bad-id':
                jobs[0]['id'] = 'wrong'
            elif mutation == 'missing-record':
                records.pop(jobs[0]['id'])
            else:
                records['extra'] = records[jobs[0]['id']]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.run_evaluation(values)

    def test_duplicate_omitted_and_misordered_rows_fail(self):
        for mutation in ('duplicate', 'omitted', 'prediction-order'):
            values = fixture()
            jobs, records = values[2:4]
            if mutation == 'prediction-order':
                records[jobs[0]['id']]['prediction']['rowIndices'].reverse()
            else:
                for family in e.FAMILIES:
                    job = next(j for j in jobs if j['regime'] == 'all-age' and j['family'] == family
                               and j['speakerFold'] == j['wordGroup'] == 0)
                    record = records[job['id']]
                    for key in ('prediction', 'prior'):
                        pred = record[key]
                        for field in ('rowIndices', 'probabilities', 'logProbabilities', 'rawProbabilities'):
                            if field in pred:
                                pred[field] = pred[field][:1]
                        pred.pop('NLL', None)
                    job['outerRows'] = job['outerRows'][:1]
                    if mutation == 'duplicate':
                        job['outerRows'] *= 2
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.run_evaluation(values)

    def test_changed_legacy_identity_and_invalid_votes_fail(self):
        for field, value in (('raterCounts', [2, 0, 3]), ('legacyRowId', 'changed'),
                             ('legacyRowIndex', 0), ('clipId', 'changed')):
            values = fixture()
            values[0][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_evaluation(values)
        for votes in ([1, 1, 2], [1., 1., 3.], [-1, 3, 3]):
            values = fixture()
            values[0][-1]['raterCounts'] = votes
            with self.subTest(votes=votes), self.assertRaises(ValueError):
                self.run_evaluation(values)

    def test_different_priors_and_pair_memberships_fail(self):
        values = fixture()
        key = values[2][25]['id']
        values[3][key]['prior'] = prediction(values[2][25]['outerRows'], [[.2, .3, .5]] * 2)
        with self.assertRaisesRegex(ValueError, 'priors differ'):
            self.run_evaluation(values)
        values = fixture()
        values[2][25]['refitRows'] = [0]
        with self.assertRaisesRegex(ValueError, 'Component membership'):
            self.run_evaluation(values)

    def test_reference_identity_and_probability_failures(self):
        for field in ('rowIndices', 'rowFolds', 'rowWordGroups', 'cells', 'speakerFolds'):
            values = fixture()
            values[4]['all-age']['corrected-mixture'][field].reverse()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'Reference'):
                self.run_evaluation(values)
        for field, value in (('logProbabilities', float('-inf')), ('probabilities', float('nan')),
                             ('rawProbabilities', .9), ('logProbabilities', -7.)):
            values = fixture()
            values[3][values[2][0]['id']]['prediction'][field][0][0] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.run_evaluation(values)
        values = fixture()
        values[3][values[2][0]['id']]['prediction']['NLL'] += .1
        with self.assertRaisesRegex(ValueError, 'Saved NLL'):
            self.run_evaluation(values)
        values = fixture()
        values[4]['child-only']['scalars']['logProbabilities'][0][0] = -9.
        with self.assertRaisesRegex(ValueError, 'stable probability/log pair'):
            self.run_evaluation(values)

    def test_finite_underflow_logs_remain_unclipped(self):
        rows = [row(0, e.scoring.metrics.PHONES[0])]
        logs = np.asarray([[-1000., np.log(.4), np.log(.6)]])
        p = np.exp(logs)
        pred = dict(rowIndices=[0], probabilities=p.tolist(), logProbabilities=logs.tolist(),
                    rawProbabilities=p.astype(np.float32).tolist())
        pred['NLL'] = e.mixture.mixture(pred, pred, rows)['NLL']
        e.checked_prediction(pred, [0], rows)
        summary = e.summarize(pred, rows)
        self.assertGreater(summary['measures']['allWords']['metrics']['allAges']['perRaterLogLoss'], 200.)

    def test_real_summaries_retain_23_phones_every_age_and_empty_cells(self):
        rows = [row(i, phone) for i, phone in enumerate(e.scoring.metrics.PHONES)]
        pred = prediction(list(range(23)), [[.2, .3, .5]] * 23)
        nonempty = e.summarize(pred, rows)
        empty = e.summarize(dict(probabilities=[], logProbabilities=[]), [])
        for summary in (nonempty, empty):
            for word in ('allWords', 'seenWords', 'unseenWords'):
                for age in e.scoring.AGES:
                    support = summary['measures'][word]['support'][age]
                    self.assertEqual(set(support['perPhone']), set(e.scoring.metrics.PHONES))
            for age in e.scoring.AGES:
                self.assertEqual(len(summary['reliability'][age]), 24)
        for age in e.scoring.AGES:
            self.assertIsNone(empty['measures']['allWords']['metrics'][age])
            self.assertEqual(empty['measures']['allWords']['support'][age]['positions'], 0)
        self.assertIsNone(nonempty['measures']['allWords']['metrics']['ages13plus'])
        model = dict(pooled=nonempty, speakerFolds=[dict(summary=nonempty) for _ in range(5)])
        decision = e.compact.consistency(model, model)
        self.assertEqual(len(decision['checks']), 6)
        self.assertFalse(decision['consistentDevelopmentGain'])
        self.assertTrue(all(v == 0 for v in decision['childDelta'].values()))


if __name__ == '__main__':
    unittest.main()
