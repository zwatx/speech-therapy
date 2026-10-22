"""Synthetic stopping, speaker-isolation and diagnostic regressions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch
from position_selection import study as s
from position_selection import audit as a

class SelectionTests(unittest.TestCase):
    def rows(self):
        return [dict(targetPhone=phone,raterCounts=count,age=age,speakerId=speaker,trainingEligible=True,
                     legacyRowIndex=legacy,clipId=f'c{i}',targetWord='WORD')
                for i,(phone,count,age,speaker,legacy) in enumerate([
                    ('B',[0,0,5],8,'a',1),('B',[1,0,4],8,'a',None),('T',[5,0,0],20,'b',2),
                    ('B',[0,1,4],9,'c',3),('T',[0,0,5],8,'d',4)])]

    def test_selection_macro_nll_matches_established_metric(self):
        rows=self.rows();p=np.array([[.1,.1,.8],[.2,.1,.7],[.7,.2,.1],[.1,.2,.7],[.1,.1,.8]])
        expected=s.previous.head.score_predictions(p,rows)
        self.assertEqual(s.selection_loss(p,rows,'all-age'),expected['allAges']['macroTargetLogLoss'])
        self.assertEqual(s.selection_loss(p,rows,'child-only'),expected['ages6to12']['macroTargetLogLoss'])
        with self.assertRaises(ValueError):s.selection_loss(p,rows,'unknown')
        with self.assertRaises(ValueError):s.selection_loss(p[:1],rows,'all-age')
        bad=p.copy();bad[2,0]=float('nan')
        with self.assertRaises(ValueError):s.selection_loss(bad,rows,'child-only')

    def test_stopping_first_best_tolerance_and_patience(self):
        history=[dict(epoch=1,selectionMacroNLL=1.),dict(epoch=2,selectionMacroNLL=1.-.5e-7)]
        self.assertEqual(s.stopping(history,patience=2),(1,1.,False))
        history.append(dict(epoch=3,selectionMacroNLL=1.))
        self.assertEqual(s.stopping(history,patience=2),(1,1.,True))
        with self.assertRaises(ValueError):s.stopping(history+[dict(epoch=4,selectionMacroNLL=.5)],patience=2)
        history[1]['selectionMacroNLL']=.9
        self.assertEqual(s.stopping(history,patience=2),(2,.9,False))
        self.assertTrue(s.stopping(history,maximum=3,patience=15)[2])

    def test_invalid_history_and_complete_lr_pair(self):
        for h in ([],[dict(epoch=0,selectionMacroNLL=1.)],[dict(epoch=1,selectionMacroNLL=float('nan'))]):
            with self.assertRaises(ValueError):s.stopping(h)
        trials=[dict(lr=.001,bestLoss=.2,bestEpoch=2),dict(lr=.0003,bestLoss=.2,bestEpoch=4)]
        self.assertEqual(s.select_candidate(trials)['lr'],.0003)
        trials[0]['bestLoss']=.19
        self.assertEqual(s.select_candidate(trials)['lr'],.001)
        with self.assertRaises(ValueError):s.select_candidate(trials[:1])

    def test_inner_partition_speaker_guard_and_age_filter(self):
        rows=self.rows();cohort={'rows':rows};splits={'folds':[dict(innerFitRows=[0,1,2],innerValidationRows=[3],outerHoldoutRows=[4],outerFitRows=[0,1,2,3])]}
        self.assertEqual(s.inner_rows(cohort,splits,0,'child-only'),([0,1],[3]))
        rows[4]['speakerId']='a'
        with self.assertRaises(ValueError):s.inner_rows(cohort,splits,0,'all-age')

    def test_reliability_preserves_empty_phone_cells_and_vote_mean(self):
        rows=self.rows()[:2];p=np.array([[.1,.1,.8],[.3,.1,.6]])
        result=a.reliability(p,rows);cell=result['all']['ages6to12']['B']
        self.assertEqual(cell['positions'],2);self.assertEqual(cell['votes'],[1,0,9])
        np.testing.assert_array_equal(cell['observedClassFrequency'],[.1,0.,.9])
        self.assertAlmostEqual(cell['rating0Bias'],.1);self.assertAlmostEqual(cell['below2Bias'],.2)
        self.assertIsNone(result['all']['ages6to12']['T']);self.assertIsNone(result['all']['ages13plus']['B'])
        self.assertEqual(result['original']['ages6to12']['B']['positions'],1)
        self.assertEqual(result['added']['ages6to12']['B']['positions'],1)

    def test_checkpoint_normalization_and_identity_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            model=s.previous.head.make_model(s.args(.001),1037);data=dict(mean=torch.zeros(1037),std=torch.ones(1037))
            config={'sha256':'config'};plan={'sha256':'plan'}
            pin=s.save_state(Path(tmp)/'state.pt',model,data,config,plan,3)
            clone=s.checked_model(pin,config,plan,data,.001,3)
            self.assertTrue(all(torch.equal(v,clone.state_dict()[k]) for k,v in model.state_dict().items()))
            with self.assertRaises(ValueError):s.checked_model(pin,config,plan,data,.001,4)
            with self.assertRaises(ValueError):s.checked_model(pin,config,plan,{**data,'mean':torch.ones(1037)},.001,3)
            with self.assertRaises(ValueError):s.save_state(Path(tmp)/'state.pt',model,data,config,plan,3)

    def test_inner_failure_is_recorded_and_cannot_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pin={'path':str(root/'plan.json'),'sha256':'synthetic'}
            with patch.object(s,'load_plan',return_value=({'jobs':[]},pin)),patch.object(s,'load_data',side_effect=ValueError('synthetic failure')) as load:
                with self.assertRaisesRegex(ValueError,'synthetic failure'):s.inner(root/'plan.json','synthetic')
                self.assertTrue((root/'inner-failure.json').exists())
                with self.assertRaises(FileExistsError):s.inner(root/'plan.json','synthetic')
                self.assertEqual(load.call_count,1)

if __name__=='__main__':unittest.main()
