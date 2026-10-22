"""New corrected-projection lineage and declaration guards; shared math tested upstream."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lexical_projection_mixture import study as s


class ProjectionMixtureTests(unittest.TestCase):
    def test_matched_partitions_and_original_pca_identity_required(self):
        scalar = dict(id='all-age.scalars.f0.g0', family='scalars', regime='all-age',
                      speakerFold=0, wordGroup=0, fitRows=[0], selectionRows=[1], refitRows=[0, 1], outerRows=[2])
        corrected = {k: v for k, v in scalar.items() if k not in ('id', 'family')}
        corrected['sourceJobId'] = 'all-age.pca16-scalars.f0.g0'
        s.check_pair(scalar, corrected)
        for key in ('fitRows', 'selectionRows', 'refitRows', 'outerRows', 'regime', 'speakerFold', 'wordGroup', 'sourceJobId'):
            bad = copy.deepcopy(corrected)
            bad[key] = [99] if key.endswith('Rows') else 'wrong'
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'membership'):
                s.check_pair(scalar, bad)

    def test_prediction_checkpoint_anchor_rows_and_priors_required(self):
        pred = dict(rowIndices=[2], probabilities=[[.1, .2, .7]], logProbabilities=[[-2.3, -1.6, -.35]])
        job = dict(scalarPrediction='a', projectionPrediction='b', scalarJobId='s', projectionJobId='p',
                   scalarCheckpoint='sc', projectionCheckpoint='pc', projectionSourceOuter='po', outerRows=[2])
        a = dict(jobId='s', refitCheckpoint='sc', prediction=pred, prior={'same': True})
        b = dict(jobId='p', checkpoint='pc', sourceOuter='po', zeroDeltaSourceReplayExact=True,
                 prediction=copy.deepcopy(pred), prior={'same': True})
        with patch.object(s, 'read', side_effect=[a, b]):
            self.assertEqual(s.checked_predictions(job), (pred, pred))
        for key in ('jobId', 'checkpoint', 'sourceOuter', 'zeroDeltaSourceReplayExact', 'prediction', 'prior'):
            bad = copy.deepcopy(b)
            bad[key] = dict(rowIndices=[3]) if key == 'prediction' else 'wrong'
            with self.subTest(key=key), patch.object(s, 'read', side_effect=[a, bad]), self.assertRaises(ValueError):
                s.checked_predictions(job)
        bad = dict(a, refitCheckpoint='wrong')
        with patch.object(s, 'read', side_effect=[bad, b]), self.assertRaises(ValueError):
            s.checked_predictions(job)

    def test_invalid_declaration_prevents_calculation(self):
        with patch.object(s, 'load_plan', side_effect=ValueError('bad declaration')), patch.object(s, 'calculate') as calculate:
            with self.assertRaisesRegex(ValueError, 'bad declaration'):
                s.run(Path('plan'), 'sha')
            calculate.assert_not_called()

    def test_fresh_declaration_does_not_read_or_mix_predictions(self):
        with tempfile.TemporaryDirectory(dir=s.BASE) as tmp:
            dest = Path(tmp) / 'fresh'
            with patch.object(s, 'inputs', return_value=({}, [])), \
                 patch.object(s, 'checked_predictions', side_effect=AssertionError('prediction read')), \
                 patch.object(s.mixture, 'mixture', side_effect=AssertionError('mixture calculation')):
                pin = s.declare(dest)
                value = s.read(pin)
                self.assertFalse(value['mixtureCalculated'])
                self.assertFalse(value['outerPredictionsRead'])
                self.assertFalse(value['trainingPerformed'])
                with self.assertRaisesRegex(ValueError, 'Fresh ignored'):
                    s.declare(dest)


if __name__ == '__main__':
    unittest.main()
