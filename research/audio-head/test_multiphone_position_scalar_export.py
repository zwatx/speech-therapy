import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import multiphone_position_scalar_export as export


class ScalarExportTests(unittest.TestCase):
    def test_cached_posterior_never_starts_worker(self):
        pin = {'path': '/already-pinned/clip.f32', 'sha256': 'a'*64}
        with patch.object(export.subprocess, 'run', side_effect=AssertionError('Unexpected inference')):
            self.assertEqual(export.posterior({'id': 'old'}, {'inputs': {'posterior/old': pin}},
                {}, Path('/unused'), True), (pin, None))

    def test_new_worker_result_must_match_job_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); directory = root/'new-ctc'/'new'; directory.mkdir(parents=True)
            job = {'expectedFrames': 2}
            export.write_new(directory/'job.json', job)
            export.write_new(directory/'ctc.json', {'complete': False})
            with patch.object(export, 'expected_job', return_value=job), \
                 patch.object(export.subprocess, 'run', side_effect=AssertionError('Verify must not infer')):
                with self.assertRaises(ValueError):
                    export.posterior({'id': 'new'}, {'inputs': {}}, {}, root, False)

    def test_saved_job_corruption_rejected_before_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); directory = root/'new-ctc'/'new'; directory.mkdir(parents=True)
            export.write_new(directory/'job.json', {'expectedFrames': 3})
            with patch.object(export, 'expected_job', return_value={'expectedFrames': 2}):
                with self.assertRaisesRegex(ValueError, 'job differs'):
                    export.posterior({'id': 'new'}, {'inputs': {}}, {}, root, False)

    def test_replay_compares_complete_report_without_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); plan_path = root/'plan.json'; plan_path.write_text('{}')
            expected = {'complete': True, 'positions': 2}
            export.write_new(root/'report.json', expected)
            with patch.object(export, 'load_plan', return_value={}), \
                 patch.object(export, 'assemble', return_value=expected) as assembled:
                self.assertTrue(export.execute(plan_path, 'a'*64, verify=True)['verified'])
                self.assertFalse(assembled.call_args.args[-1])
                (root/'report.json').write_text(json.dumps(dict(expected, positions=1)))
                with self.assertRaisesRegex(ValueError, 'report differs'):
                    export.execute(plan_path, 'a'*64, verify=True)

    def test_failure_evidence_and_no_implicit_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root/'plan.json'; path.write_text('{}')
            def fail(*args):
                (root/'clips').mkdir()
                raise ValueError('Unusable source')
            with patch.object(export, 'load_plan', return_value={}), patch.object(export, 'assemble', side_effect=fail):
                with self.assertRaisesRegex(ValueError, 'Unusable source'): export.execute(path, 'a'*64)
                self.assertFalse(json.loads((root/'failure.json').read_text())['complete'])
                with self.assertRaisesRegex(ValueError, 'No implicit restart'): export.execute(path, 'a'*64)


if __name__ == '__main__': unittest.main()
