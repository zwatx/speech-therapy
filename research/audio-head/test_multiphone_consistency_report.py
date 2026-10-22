from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import multiphone_consistency_report as report


def example():
    rows = [dict(targetPhone=phone, speakerId=str(i), clipId=str(i), age=age, raterCounts=counts)
            for i, (phone, age, counts) in enumerate([
                ('B', 6, [1, 1, 3]), ('B', 8, [0, 0, 5]),
                ('P', 7, [0, 0, 5]), ('P', 20, [2, 1, 2])])]
    warm = np.array([[.15, .1, .75], [.02, .03, .95], [.05, .05, .9], [.2, .2, .6]])
    noise = .9 * warm + .1 / 3
    original = {'cleanMetrics': report.compact_metrics(report.score_predictions(warm, rows)),
                'sensitivity': report.trainer.sensitivity(warm, noise, warm, rows)}
    arms = []
    for regime in report.trainer.REGIMES:
        for coefficient in report.trainer.COEFFICIENTS:
            clean = (1 - coefficient * .01) * warm + coefficient * .01 / 3
            changed = (1 - coefficient * .2) * noise + coefficient * .2 * clean
            arms.append({'regime': regime, 'coefficient': coefficient, 'bestEpoch': 1, 'epochsRun': 3,
                'cleanMetrics': report.compact_metrics(report.score_predictions(clean, rows)),
                'sensitivity': report.trainer.sensitivity(clean, changed, warm, rows),
                'original': deepcopy(original)})
    return rows, warm, noise, arms


class ReportTests(unittest.TestCase):
    def test_all_six_retained_with_matched_controls_and_signed_differences(self):
        _, _, _, arms = example()
        result = report.summarize(arms)
        self.assertEqual(len(result['arms']), 6)
        self.assertEqual(len(result['originalModels']), 2)
        self.assertFalse(result['coefficientSelected'])
        control = result['comparisons'][0]['againstCoefficientZero']['ages6to12']
        self.assertEqual(control['macroTargetLogLoss'], 0)
        self.assertEqual(control['cleanToNoisy']['meanTotalVariation'], 0)
        expected = arms[2]['cleanMetrics']['ages6to12']['macroTargetLogLoss'] - arms[0]['cleanMetrics']['ages6to12']['macroTargetLogLoss']
        self.assertEqual(result['comparisons'][2]['againstCoefficientZero']['ages6to12']['macroTargetLogLoss'], expected)
        self.assertLess(result['comparisons'][2]['againstCoefficientZero']['ages6to12']['cleanToNoisy']['meanTotalVariation'], 0)

    def test_reject_missing_duplicate_and_reordered_arms(self):
        arms = example()[3]
        for changed in (arms[:-1], arms[:5] + [arms[0]], list(reversed(arms))):
            with self.assertRaises(ValueError):
                report.summarize(changed)

    def test_reject_original_or_support_changes(self):
        for category in ('original', 'cleanMetrics'):
            arms = example()[3]
            metrics = arms[1]['original']['cleanMetrics'] if category == 'original' else arms[1]['cleanMetrics']
            metrics['ages6to12']['examples'] += 1
            with self.assertRaises(ValueError):
                report.summarize(arms)
        arms = example()[3]
        arms[1]['cleanMetrics']['ages6to12']['rating0']['excludedPhones'] = []
        with self.assertRaises(ValueError):
            report.summarize(arms)

    def test_sparse_ranking_retains_denominators(self):
        result = report.summarize(example()[3])
        child = result['arms'][0]['cleanMetrics']['ages6to12']
        self.assertEqual(child['speakers'], 3)
        self.assertEqual(child['observedRaterCounts'], [1, 1, 13])
        self.assertEqual(child['rating0']['definedTargets'], 1)
        self.assertEqual(child['rating0']['excludedPhones'], ['P'])

    def test_prediction_validation(self):
        _, warm, noise, _ = example()
        value = dict(rowIndices=[0, 1, 2, 3], noisyHumanLabelsAvailable=False,
                     **{key: (noise if 'Noisy' in key or key.startswith('noisy') else warm).tolist()
                        for key in report.PROBABILITIES})
        report.checked_predictions(value, [0, 1, 2, 3])
        for key, replacement in [('rowIndices', [3, 2, 1, 0]), ('noisyHumanLabelsAvailable', True),
                                  ('noisyProbabilities', [[float('nan'), 0., 1.]] * 4),
                                  ('cleanProbabilities', [[-.1, .1, 1.]] * 4),
                                  ('warmNoisyProbabilities', [[.1, .1, .1]] * 4)]:
            changed = deepcopy(value)
            changed[key] = replacement
            with self.assertRaises(ValueError):
                report.checked_predictions(changed, [0, 1, 2, 3])

    def test_markdown_keeps_original_controls_and_limits(self):
        text = report.markdown(report.summarize(example()[3]))
        self.assertEqual(text.count('| Original |'), 2)
        for coefficient in ('0', '0.1', '1'):
            self.assertEqual(text.count(f'| Coefficient {coefficient} |'), 2)
        self.assertIn('No coefficient is selected', text)
        self.assertIn('no noisy pronunciation accuracy', text)

    def test_publish_rejects_mutated_ledger(self):
        arms = example()[3]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            base = root / 'outputs' / 'study'
            base.mkdir(parents=True)
            jobs = [{k: arm[k] for k in ('regime', 'coefficient')} | {'output': str(base / str(i))}
                    for i, arm in enumerate(arms)]
            plan = {'base': str(base), 'contract': {}, 'jobs': jobs}
            path = base / 'queue-plan.json'
            path.write_text(json.dumps(plan))
            ledger_path = base / 'queue-ledger.json'
            ledger = dict(planPath=str(path), planSha256=report.digest(path), contract={}, jobs=jobs, complete=True)
            ledger_path.write_text(json.dumps(ledger))
            sha = report.digest(ledger_path)
            output = root / 'outputs' / 'report'

            def mutate(*args):
                ledger_path.write_text('{}')

            with patch.object(report.trainer, 'HERE', root), patch.object(report.queue, 'guard_plan', return_value={}), \
                 patch.object(report.queue, 'guard_outputs', side_effect=mutate), patch.object(report, 'load_arms', return_value=arms):
                with self.assertRaises(ValueError):
                    report.build(ledger_path, sha, output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
