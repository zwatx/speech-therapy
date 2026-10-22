"""Synthetic metadata and phase-boundary checks; no corpus fitting."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rare0_proper_loss import study


class StudyTests(unittest.TestCase):
    def test_missing_control_cell_fails_before_plan(self):
        with self.assertRaisesRegex(ValueError, 'Historical control cell missing'):
            study.make_jobs({'jobs': []}, [])

    def test_ordered_control_rows_must_match(self):
        final = dict(id='seed17-unweighted-child-only-pca16-scalars-s0-w0', seed=17,
                     speakerFold=0, wordGroup=0, objective='unweighted', regime='child-only',
                     family='pca16-scalars', fitRows=[0, 1], selectionRows=[2],
                     addedValidationRows=[3], refitRows=[0, 1, 2, 3], outerRows=[])
        scalar = dict(final, id='seed17-unweighted-child-only-scalars-s0-w0',
                      family='scalars', fitRows=[1, 0])
        with self.assertRaisesRegex(ValueError, 'Ordered control membership differs'):
            study.make_jobs({'jobs': [final, scalar]}, [])

    def test_no_implicit_restart_preserves_partial_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study.fresh_phase(root, 'inner')
            (root/'inner'/'partial.txt').write_text('preserve me')
            with self.assertRaisesRegex(ValueError, 'Preserve partial phase'):
                study.fresh_phase(root, 'inner')
            self.assertEqual((root/'inner'/'partial.txt').read_text(), 'preserve me')

    def test_candidate_config_separates_training_objective_from_control_identity(self):
        job = dict(id='rare0-seed17-unweighted-child-only-pca16-scalars-s0-w0',
                   seed=17, objective='unweighted', family='pca16-scalars', regime='child-only',
                   speakerFold=0, wordGroup=0, fitRows=[1], selectionRows=[2],
                   addedValidationRows=[3], refitRows=[1, 2, 3], outerRows=[4], baseJobId='base')
        with patch.object(study, 'read', return_value={'inputs': {'historicalFeatureReport': {'path': 'feature'}}}):
            config = study.config_value(job, {'path': 'plan', 'sha256': 'sha'}, 'inner')
        self.assertEqual(job['objective'], 'unweighted')
        self.assertEqual(config['objective'], study.core.OBJECTIVE)
        self.assertEqual(config['binaryCoefficient'], 1)
        self.assertEqual(config['historicalObjective'], 'unweighted')
        self.assertEqual(config['addedValidationRowsNotUsedForSelection'], [3])


if __name__ == '__main__':
    unittest.main()
