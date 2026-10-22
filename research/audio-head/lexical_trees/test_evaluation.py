import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lexical_trees import evaluation as ev, study


class EvaluationTest(unittest.TestCase):
    def test_tied_vote_ap(self):
        # First tie group: 3 positives of 10; next adds 5 positives of 5.
        ap = ev.average_precision(np.array([.8, .8, .2]), np.array([1, 2, 5]), np.array([4, 3, 0]))
        self.assertAlmostEqual(ap, (3*.3+5*8/15)/8)
        self.assertIsNone(ev.average_precision(np.array([.5]), np.array([0]), np.array([5])))
        self.assertIsNone(ev.average_precision(np.array([.5]), np.array([5]), np.array([0])))

    def test_per_rater_brier_and_nll(self):
        rows=[dict(raterCounts=[2, 1, 2], targetPhone='B', speakerId='a', clipId='c', targetWord='BAT')]
        p=np.array([[.2, .3, .5]])
        result=ev.metrics(np.log(p), rows)
        expanded=np.array([0, 0, 1, 2, 2])
        expected=np.mean(np.sum((p-np.eye(3)[expanded])**2, axis=1))
        self.assertAlmostEqual(result['brier'], expected)
        self.assertAlmostEqual(result['nll'], -np.log(p[0, expanded]).mean())
        self.assertEqual(result['events']['rating0']['positiveVotes'], 2)

    def test_screen_requires_every_endpoint_and_fold(self):
        delta=dict(nll=-.06, macroNll=-.01, brier=-.01, rating0Ap=.02, below2Ap=.01)
        self.assertTrue(ev.screen(delta, [dict(nll=-.01)]*5, 1.)['materialGainPass'])
        self.assertFalse(ev.screen(delta, [dict(nll=.001)], 1.)['directionalPass'])
        for key in delta:
            changed=dict(delta); changed[key]=0.
            self.assertFalse(ev.screen(changed, [dict(nll=-.01)]*5, 1.)['directionalPass'])
        delta['rating0Ap']=.005
        self.assertTrue(ev.screen(delta, [dict(nll=0.)]*5, 1.)['directionalPass'])
        self.assertFalse(ev.screen(delta, [dict(nll=0.)]*5, 1.)['materialGainPass'])

    def test_phase_freeze_rejects_incomplete_or_changed_artifact(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); data=root/'data'; data.write_text('original')
            freeze=root/'freeze.json'
            value=dict(complete=True, phase='inner', planSha256='plan',
                       runs=[dict(jobId='a', files=dict(data=study.pin(data)))])
            study.write(freeze, value); digest=study.sha(freeze)
            study.checked_freeze(freeze, digest, 'plan', 'inner', [dict(id='a')])
            with self.assertRaises(ValueError):
                study.checked_freeze(freeze, digest, 'plan', 'inner', [dict(id='a'),dict(id='b')])
            data.write_text('changed')
            with self.assertRaises(ValueError):
                study.checked_freeze(freeze, digest, 'plan', 'inner', [dict(id='a')])


if __name__=='__main__':
    unittest.main()
