"""Small process/ledger tests; no speech data or model fitting."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import multiphone_local_head_queue as queue


class LocalHeadQueueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='cadence-local-queue-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_fixed_matrix_is_fold_first_and_cpu_two_threads(self):
        recipe = queue.trainer.read_json(queue.trainer.RECIPE)
        jobs = queue.plan(recipe, self.root)
        self.assertEqual(len(jobs), 40)
        self.assertEqual([job['fold'] for job in jobs], [fold for fold in range(5) for _ in range(8)])
        self.assertEqual(len({(job['family'], job['regime']) for job in jobs[:8]}), 4)
        command = queue.command(jobs[0], self.root, recipe)
        self.assertEqual(command[command.index('--device')+1], 'cpu')
        self.assertEqual(command[command.index('--threads')+1], '2')
        self.assertEqual(command[command.index('--batch-size')+1], '64')

    def test_child_waits_until_pid_is_persisted_then_records_exit(self):
        marker = self.root/'ran.txt'
        record, saved = {}, []
        def save():
            saved.append(json.loads(json.dumps(record)))
            if record['state'] == 'running':
                self.assertIsInstance(record['pid'], int)
                self.assertFalse(marker.exists())
        queue.run_child([sys.executable, '-c', f'from pathlib import Path; Path({str(marker)!r}).write_text("ran")'],
                        record, self.root/'success.log', save)
        self.assertEqual(record['state'], 'complete')
        self.assertEqual(record['exitCode'], 0)
        self.assertEqual(marker.read_text(), 'ran')
        self.assertEqual(saved[1]['state'], 'running')
        self.assertGreaterEqual(record['finishedAt'], record['startedAt'])

    def test_nonzero_exit_is_durable_and_raises(self):
        record, states = {}, []
        with self.assertRaisesRegex(RuntimeError, 'Child exited 3'):
            queue.run_child([sys.executable, '-c', 'raise SystemExit(3)'], record, self.root/'failed.log',
                            lambda: states.append(record['state']))
        self.assertEqual(record['state'], 'failed')
        self.assertEqual(record['exitCode'], 3)
        self.assertEqual(states[-1], 'failed')

    def test_failed_pid_save_never_releases_child_to_fit(self):
        marker = self.root/'must-not-exist'
        record = {}
        def save():
            if record['state'] == 'running':
                raise OSError('ledger write failed')
        with self.assertRaisesRegex(OSError, 'ledger write failed'):
            queue.run_child([sys.executable, '-c', f'from pathlib import Path; Path({str(marker)!r}).touch()'],
                            record, self.root/'gate.log', save)
        self.assertFalse(marker.exists())
        self.assertEqual(record['state'], 'failed')
        self.assertIsNotNone(record['exitCode'])


if __name__ == '__main__':
    unittest.main()
