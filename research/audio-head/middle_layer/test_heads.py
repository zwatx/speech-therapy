"""Metadata-only partition checks and phase-barrier corruption checks."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from middle_layer import heads as h


class HeadStudyTest(unittest.TestCase):
    def test_actual_frozen_parent_partitions_without_features_or_training(self):
        parent = h.read(h.files.binding(h.OLD/'plan.json', h.OLD_PLAN))
        outer = h.read(h.files.binding(h.OLD/'outer-freeze.json', h.OLD_OUTER))
        cohort = h.read(parent['inputs']['cohort'])
        jobs = h.jobs_from_parent(parent, outer, cohort)
        self.assertEqual(len(jobs), 50)
        for a, b in zip(jobs[:25], jobs[25:], strict=True):
            self.assertEqual(a['fitRows'], b['fitRows'])
            self.assertEqual(a['selectionRows'], b['selectionRows'])
            self.assertEqual(a['refitRows'], b['refitRows'])
            self.assertEqual(a['outerRows'], b['outerRows'])
        bad = copy.deepcopy(parent)
        j = next(j for j in bad['jobs'] if j['id'] == 'child-only-pca16-scalars-s0-w0')
        j['fitRows'][0] = j['outerRows'][0]
        with self.assertRaises(ValueError): h.jobs_from_parent(bad, outer, cohort)

    def test_phase_barrier_rejects_partial_or_changed_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'freeze.json'
            plan = dict(jobs=[dict(id='a'), dict(id='b')]); pin = dict(path='plan', sha256='sha')
            h.files.write_json(path, dict(complete=True, plan=pin, phase='inner',
                runs=[dict(jobId='a')], outerPredictionsRead=False, **h.FLAGS))
            with patch.object(h, 'validate_run') as validate:
                with self.assertRaises(ValueError):
                    h.frozen(path, h.files.binding(path)['sha256'], plan, pin, 'inner', [])
                validate.assert_not_called()
            old_sha = h.files.binding(path)['sha256']; path.write_text('{}')
            with self.assertRaises(ValueError): h.frozen(path, old_sha, plan, pin, 'inner', [])


if __name__ == '__main__':
    unittest.main()
