"""Synthetic gate, guard, mixture and coverage tests; no artifacts, ratings or model inference."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from posterior_pooling import evaluation as ev

UNIFORM = [1/3, 1/3, 1/3]


def grid(extra=None):
    """Seven ages x 23 consonants of alternating rating-0 and rating-2 positions."""
    rows = [dict(raterCounts=[5, 0, 0] if i % 2 == 0 else [0, 0, 5], targetPhone=phone, speakerId=f'child{age}',
                 clipId=str(i), age=age, legacyRowIndex=i)
            for i, (age, phone) in enumerate((a, p) for a in range(6, 13) for p in ev.TARGETS[:23])]
    for row in rows:
        row.update(extra(row) if extra else {})
    return rows


def logs(rows, correct=None, wrong=(), mix=1.):
    """Uniform, or a mixture toward a confident correct class; listed rows are confidently wrong."""
    out = []
    for i, row in enumerate(rows):
        truth = int(np.argmax(row['raterCounts']))
        if i in wrong:
            p = [1e-12, .005, 1-.005-1e-12] if truth == 0 else [1-.005-1e-12, .005, 1e-12]
        elif correct is None:
            p = UNIFORM
        else:
            confident = [.1, .1, .1]; confident[truth] = correct
            p = [(1-mix)*u + mix*c for u, c in zip(UNIFORM, confident)]
        out.append(np.log(np.asarray(p, dtype=np.float64) / np.sum(p)).tolist())
    return out


def seed(rows, candidate, hard=None, scalar=None):
    n = len(rows)
    return ev.evaluate_seed(rows, list(range(n)), [i % 5 for i in range(n)],
                            dict(candidate=candidate, freshHard=hard or logs(rows), scalar=scalar or logs(rows)))


class SeedGateTests(unittest.TestCase):
    def test_exact_material_and_directional_boundaries(self):
        base = dict(nll=-.05, macroNll=1e-7, brier=1e-7, rating0Ap=.01, below2Ap=-1e-7)
        folds = [dict(nll=1e-7)] * 5
        self.assertTrue(ev.screen(base, folds, 1.)['materialGainPass'])
        for change, directional in ((dict(nll=-.0499999), True), (dict(rating0Ap=.0099999), True), (dict(nll=-1e-7), False),
                                    (dict(macroNll=1.1e-7), False), (dict(brier=1.1e-7), False), (dict(below2Ap=-1.1e-7), False)):
            result = ev.screen(base | change, folds, 1.)
            self.assertFalse(result['materialGainPass'])
            self.assertEqual(result['directionalPass'], directional)
        self.assertFalse(ev.screen(base, folds[:4] + [dict(nll=1.1e-7)], 1.)['materialGainPass'])

    def test_material_pass_with_compact_gain_and_age_six_display(self):
        rows = grid()
        result = seed(rows, logs(rows, correct=.8))
        self.assertTrue(result['screen']['materialGainPass'] and result['compactCoCondition'] and result['seedPass'])
        self.assertEqual(len(result['groups']['phone']), 23)
        self.assertEqual(set(result['ageSix']['rating0Ap']), {'candidate', 'freshHard', 'scalar', 'candidateMixture', 'freshHardMixture'})
        self.assertIn('candidateMixture', result['ageSix']['macroNll'])

    def test_directional_gain_without_material_gain_fails_the_seed(self):
        rows = grid()
        result = seed(rows, logs(rows, correct=.8, mix=.03))
        self.assertTrue(result['screen']['directionalPass'] and result['compactCoCondition'])
        self.assertLess(result['screen']['relativeNllReduction'], .05)
        self.assertFalse(result['screen']['materialGainPass'] or result['seedPass'])

    def test_compact_nll_gain_is_required(self):
        rows = grid()
        result = seed(rows, logs(rows, correct=.99, wrong=set(range(0, len(rows), 16))))
        self.assertTrue(result['screen']['materialGainPass'])
        self.assertFalse(result['compactCoCondition'] or result['seedPass'])

    def test_same_seed_hard_mixture_denominator_and_shared_scalar(self):
        rows = grid()
        candidate, hard, scalar = logs(rows, correct=.8), logs(rows, correct=.8, mix=.2), logs(rows, correct=.8, mix=.1)
        result = seed(rows, candidate, hard, scalar)
        pooled = result['pooled']
        self.assertEqual(result['screen']['relativeNllReduction'],
                         -pooled['deltas']['primary']['nll'] / pooled['metrics']['freshHardMixture']['nll'])
        self.assertNotEqual(pooled['metrics']['freshHardMixture']['nll'], pooled['metrics']['scalar']['nll'])
        counts = np.asarray([r['raterCounts'] for r in rows], dtype=np.float64)
        mixture = np.logaddexp(np.asarray(candidate), np.asarray(scalar)) - np.log(2.)
        self.assertAlmostEqual(pooled['metrics']['candidateMixture']['nll'], float((-(counts*mixture).sum(1)/5).mean()), places=12)
        same = seed(rows, hard, hard, scalar)
        self.assertTrue(all(v == 0 for v in same['pooled']['deltas']['primary'].values()))

    def test_undefined_primary_is_invalid_and_undefined_subgroup_ap_is_null(self):
        rows = grid(lambda r: dict(raterCounts=[0, 0, 5]))
        with self.assertRaises(ev.InvalidEvaluation):
            seed(rows, logs(rows, correct=.8))
        rows = grid(lambda r: dict(speakerId='onlyTwo') if r['age'] == 12 and r['raterCounts'][2] == 5 else {})
        child = seed(rows, logs(rows, correct=.8))['groups']['child']['onlyTwo']
        self.assertIsNone(child['metrics']['candidateMixture']['events']['rating0']['averagePrecision'])
        self.assertIsNone(child['deltas']['primary']['rating0Ap'])
        self.assertEqual((child['support']['events']['rating0']['positiveChildren'],
                          child['support']['events']['rating0']['negativeChildren']), (0, 1))


class AcrossSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = grid()
        cls.passing = seed(rows, logs(rows, correct=.8))

    def seeds(self):
        return {str(v): copy.deepcopy(self.passing) for v in ev.SEEDS}

    def test_one_failing_seed_is_never_rescued_by_the_mean(self):
        seeds = self.seeds()
        self.assertTrue(ev.summarize(seeds)['developmentPass'])
        seeds['29']['screen']['materialGainPass'] = False
        with self.assertRaisesRegex(ValueError, 'Seed pass'):
            ev.summarize(seeds)
        seeds['29']['seedPass'] = False
        result = ev.summarize(seeds)
        self.assertLess(result['changes']['primary']['nll']['mean'], 0)
        self.assertFalse(result['allSeedsPass'] or result['developmentPass'])
        with self.assertRaises(ValueError):
            ev.summarize({k: v for k, v in self.seeds().items() if k != '43'})

    def test_consistent_age_and_phone_regressions_fail_smaller_ones_are_descriptive(self):
        phone = ev.TARGETS[4]
        for axis, key in (('age', '9'), ('phone', phone)):
            seeds = self.seeds()
            for count, value in enumerate(ev.SEEDS, 1):
                seeds[str(value)]['groups'][axis][key]['deltas']['primary']['nll'] = .001
                result = ev.summarize(seeds)
                self.assertEqual(result['groups'][axis][key]['seedsWithWorseNll'], count)
                self.assertEqual(result['developmentPass'], count < 3)
                if count < 3:
                    self.assertEqual(result['lessConsistentRegressions'][axis], {key: count})
            guard = result['ageGuard' if axis == 'age' else 'phoneGuard']
            self.assertEqual((guard['passed'], guard['agesWorseAtEverySeed' if axis == 'age' else 'phonesWorseAtEverySeed']),
                             (False, [key]))
        seeds = self.seeds()
        for value in ev.SEEDS:
            seeds[str(value)]['groups']['child']['child8']['deltas']['primary']['nll'] = .001
        result = ev.summarize(seeds)
        self.assertTrue(result['developmentPass'])
        self.assertEqual(result['regressionsAtEverySeed']['child'], ['child8'])

    def test_support_must_be_identical_across_seeds_and_all_phones_present(self):
        seeds = self.seeds()
        seeds['43']['groups']['age']['8']['support']['positions'] += 1
        with self.assertRaisesRegex(ValueError, 'support'):
            ev.summarize(seeds)
        seeds = self.seeds()
        for value in ev.SEEDS:
            del seeds[str(value)]['groups']['phone'][ev.TARGETS[0]]
        with self.assertRaisesRegex(ValueError, '23 consonants'):
            ev.summarize(seeds)


class CoverageTests(unittest.TestCase):
    def test_every_cell_matched_on_identical_ordered_child_rows(self):
        rows = grid(); n = len(rows)
        candidate, uniform = logs(rows, correct=.8), logs(rows)
        cells, predictions, scalars = [], {}, {}
        for value in ev.SEEDS:
            for number in range(25):
                ids = [i for i in range(n) if i % 25 == number]
                cell = dict(id=f'seed{value}-{number}', seed=value, speakerFold=number // 5, wordGroup=number % 5, outerRows=ids,
                            jobs=dict(candidate=f'c{value}-{number}', freshHard=f'h{value}-{number}', scalar=f's{value}-{number}'))
                cells.append(cell)
                for arm, source in (('candidate', candidate), ('freshHard', uniform)):
                    predictions[cell['jobs'][arm]] = dict(prediction=dict(rowIndices=ids, logProbabilities=[source[i] for i in ids]))
                scalars[cell['id']] = dict(prediction=dict(rowIndices=ids, logProbabilities=[uniform[i] for i in ids]))
        result = ev.evaluate(rows, cells, predictions, scalars, positions=n)
        self.assertTrue(result['acrossSeeds']['developmentPass'])
        self.assertEqual(result['rowIndices'], list(range(n)))
        broken = copy.deepcopy(predictions); key = cells[3]['jobs']['candidate']
        broken[key]['prediction']['rowIndices'] = broken[key]['prediction']['rowIndices'][:-1]
        reordered = copy.deepcopy(scalars); record = reordered[cells[50]['id']]['prediction']
        record['rowIndices'] = list(reversed(record['rowIndices']))
        for arguments in ((rows, cells, broken, scalars), (rows, cells, predictions, reordered),
                          (rows, cells[:-1], predictions, scalars)):
            with self.assertRaises(ValueError):
                ev.evaluate(*arguments, positions=n)
        with self.assertRaises(ValueError):
            ev.evaluate(rows, cells, predictions, scalars)


class ResultIntegrityTests(unittest.TestCase):
    def test_late_consumed_prediction_change_blocks_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prediction = root/'prediction.json'; prediction.write_text('{}')
            controls_path = root/'controls.json'; controls_path.write_text('{}')
            controls_pin = ev.s.files.binding(controls_path)
            outer_path = root/'outer.json'
            outer_path.write_text(json.dumps(dict(controls=controls_pin,
                predictions=[dict(jobId='synthetic', artifact=ev.s.files.binding(prediction))])))
            outer_pin = ev.s.files.binding(outer_path)
            plan = dict(gates=ev.s.GATES, cells=[], support={'children': 1})
            controls = dict(decision=dict(scalarReuse=False))
            result = dict(seeds={str(seed): {'groups': {'child': {'only': {}}}} for seed in ev.SEEDS})

            def mutate(*args):
                prediction.write_text('late change after predictions were consumed')
                return {}

            with patch.object(ev.s, 'load_plan', return_value=(plan, {}, None, {'cohort': {'rows': []}})), \
                 patch.object(ev.s, 'checked_control_freeze', return_value=(controls, controls_pin)), \
                 patch.object(ev.s, 'checked_outer', return_value=({}, outer_pin)), \
                 patch.object(ev.s, 'scalar_component', return_value={}), patch.object(ev, 'evaluate', return_value=result), \
                 patch.object(ev, 'diagnostics', side_effect=mutate), patch.object(ev.s, 'final_guards'):
                with self.assertRaises(ValueError):
                    ev.calculate('plan', 'sha', outer_path, outer_pin['sha256'])


if __name__ == '__main__':
    unittest.main()
