"""Declared queue coverage, selection and history tests; no model runs."""
from copy import deepcopy
from pathlib import Path
import unittest

import multiphone_phonetic_head_queue as queue


class PhoneticHeadQueueTests(unittest.TestCase):
    def setUp(self):
        self.recipe = queue.trainer.read_json(queue.trainer.RECIPE)
        self.jobs = queue.plan(self.recipe, Path('/tmp/phonetic-queue-synthetic'))

    def test_all80_unique_cpu_default_commands_are_fold_first(self):
        self.assertEqual(len(self.jobs), 80)
        self.assertEqual([row['fold'] for row in self.jobs], [fold for fold in range(5) for _ in range(16)])
        self.assertEqual(len({(row['family'], row['regime']) for row in self.jobs[:16]}), 8)
        command = queue.command(self.jobs[0], Path('/tmp/binding.json'))
        self.assertEqual(command[2], 'train')
        self.assertEqual(command[command.index('--binding') + 1], '/tmp/binding.json')
        self.assertEqual(command[command.index('--lr') + 1], '0.001')
        # No flags override the independently approved trainer's fixed CPU2 defaults.
        self.assertNotIn('--device', command)
        self.assertNotIn('--threads', command)

    def test_no_selection_until_both_declared_rates_are_verified_and_replayed(self):
        self.assertEqual(queue.selected_groups(self.jobs, self.recipe), [])
        for row in self.jobs[:2]:
            row.update(state='complete', verified={'selectionMacroLogLoss': .4, 'bestEpoch': 3},
                       replay={'verifiedExact': True})
        selected = queue.selected_groups(self.jobs, self.recipe)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][0]['lr'], .0003)
        self.jobs[0]['verified']['selectionMacroLogLoss'] -= 1e-10
        self.assertEqual(queue.selected_groups(self.jobs, self.recipe)[0][0]['lr'], .001)
        self.jobs[1]['replay']['verifiedExact'] = False
        self.assertEqual(queue.selected_groups(self.jobs, self.recipe), [])
        with self.assertRaisesRegex(ValueError, 'both declared'):
            queue.selected_groups(self.jobs[:-1], self.recipe)

    def test_history_reconstructs_regime_metric_and_patience(self):
        recipe = {**self.recipe, 'patienceEpochs': 2}
        history = [{'epoch': i, 'trainPerRaterLogLoss': .1, 'selectionMacroTargetLogLoss': loss,
                    'evaluation': {'ages6to12': {'macroTargetLogLoss': loss}, 'allAges': {'macroTargetLogLoss': 1/i}}}
                   for i, loss in enumerate([.4, .3, .35, .4], 1)]
        report = {'epochsRun': 4, 'bestEpoch': 2, 'bestSelectionMacroLogLoss': .3}
        queue.verify_history(history, report, 'child-only', recipe)
        with self.assertRaises(ValueError):
            queue.verify_history(history, report, 'all-age', recipe)
        changed = deepcopy(history)
        changed[0]['trainPerRaterLogLoss'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'Invalid history'):
            queue.verify_history(changed, report, 'child-only', recipe)
        with self.assertRaisesRegex(ValueError, 'stopping rule'):
            queue.verify_history(history[:2], {**report, 'epochsRun': 2}, 'child-only', recipe)


if __name__ == '__main__':
    unittest.main()
