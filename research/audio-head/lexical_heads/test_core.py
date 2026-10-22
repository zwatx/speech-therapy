"""Synthetic-only checks of fresh fitting, isolated moments, and stopping semantics."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

from lexical_heads import core


def bundle():
    rows = [dict(targetId=i%2, targetPhone=('B','P')[i%2], raterCounts=[i%2,1,4-i%2],
                 speakerId=f'speaker{i}', trainingEligible=True) for i in range(8)]
    values = np.arange(8*13,dtype=np.float32).reshape(8,13)/30
    values[:,2] = 4
    return dict(cohort={'rows':rows}, scalars=values, target=np.zeros((8,1024),dtype=np.float32),
                positions={i:i for i in range(8)})


class CoreTests(unittest.TestCase):
    def test_fit_only_moments_and_priors(self):
        b = bundle(); data = core.prepare(b,'scalars',[0,1,2,3])
        altered = copy.deepcopy(b); altered['scalars'][4:] = 1e8
        for row in altered['cohort']['rows'][4:]: row['raterCounts']=[5,0,0]
        other = core.prepare(altered,'scalars',[0,1,2,3])
        self.assertTrue(torch.equal(data['mean'],other['mean']))
        self.assertTrue(torch.equal(data['std'],other['std']))
        self.assertEqual(data['priors'],other['priors'])
        expected=b['scalars'][:4].astype(np.float64)
        np.testing.assert_array_equal(data['mean'].numpy(),expected.mean(0).astype(np.float32))
        np.testing.assert_array_equal(data['std'].numpy(),np.where(expected.std(0)<1e-6,1,expected.std(0)).astype(np.float32))
        self.assertEqual(data['std'][2],1)
        self.assertEqual(data['priors']['B']['observedRaterCounts'],[0,2,8])
        self.assertEqual(data['priors']['D']['probabilities'],[1/3]*3)
        wide=core.prepare(b,'target-scalars',[0,1,2,3])
        self.assertEqual(wide['values'].shape,(8,1037))
        np.testing.assert_array_equal(wide['values'][:,-13:],b['scalars'])

    def test_stable_extreme_logits(self):
        logits=torch.tensor([[1000.,0.,-1000.]],dtype=torch.float32)
        p,logs,raw,loss=core.stable_outputs(logits,[[0,0,5]])
        self.assertEqual(loss,2000)
        self.assertTrue(np.isfinite(logs).all())
        self.assertEqual(p.dtype,np.float64)
        self.assertEqual(logs.dtype,np.float64)
        self.assertEqual(raw.dtype,np.float32)
        np.testing.assert_array_equal(p,np.exp(logs))
        with self.assertRaises(ValueError): core.stable_outputs(logits,[[1,1,1]])

    def test_fresh_initialization_and_deterministic_refit(self):
        data=core.prepare(bundle(),'scalars',[0,1,2,3])
        with tempfile.TemporaryDirectory() as tmp:
            roots=[Path(tmp)/str(i) for i in range(2)]
            histories=[]
            for root in roots:
                with patch.object(core,'predict',side_effect=AssertionError('refit must not evaluate')):
                    report=core.train(data,[],root,{'test':'determinism'},epochs=2)
                self.assertEqual(report['epochsRun'],2)
                self.assertEqual(report['totalUpdates'],2)
                self.assertIsNone(report['bestLoss'])
                histories.append(json.loads((root/'history.json').read_text()))
            self.assertEqual(histories[0],histories[1])
            for name in ['initial.pt','best.pt','last.pt']:
                left,right=[torch.load(root/name,weights_only=True) for root in roots]
                for key in left['model']:
                    self.assertTrue(torch.equal(left['model'][key],right['model'][key]))
                self.assertEqual(left['epoch'],right['epoch'])
                self.assertIn('optimizer',left); self.assertIn('rng',left)
            initial=torch.load(roots[0]/'initial.pt',weights_only=True)
            fresh,_=core.initialize(13)
            for key,value in fresh.state_dict().items():
                self.assertTrue(torch.equal(value,initial['model'][key]))
            best=torch.load(roots[0]/'best.pt',weights_only=True)
            self.assertTrue(any(not torch.equal(initial['model'][k],v) for k,v in best['model'].items()))
            first=core.replay(roots[0],data,[4,5]); second=core.replay(roots[1],data,[4,5])
            self.assertEqual(first,second)
            with self.assertRaisesRegex(ValueError,'fresh'):
                core.train(data,[],roots[0],{},epochs=2)

    def test_stopping_strict_min_delta_and_exact_selected_replay(self):
        data=core.prepare(bundle(),'scalars',[0,1,2,3])
        # Same effective parameter state each epoch makes actual replay deterministic;
        # mocked selection losses test threshold/stopping, replay stub only here.
        sequence=[2.,2.-.5e-7,2.-2e-7]+[2.]*15
        predictions=[]
        for loss in sequence:
            predictions.append(dict(rowIndices=[4,5],probabilities=[[.2,.3,.5]]*2,
                                    rawProbabilities=[[.2,.3,.5]]*2,
                                    logProbabilities=[[np.log(.2),np.log(.3),np.log(.5)]]*2,NLL=loss))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'inner'
            with patch.object(core,'predict',side_effect=predictions) as predict, patch.object(core,'replay',return_value=predictions[2]):
                report=core.train(data,[4,5],root,{'test':'stopping'})
            self.assertEqual(predict.call_count,18)
            self.assertEqual(report['bestEpoch'],3)
            self.assertEqual(report['epochsRun'],18)
            best=torch.load(root/'best.pt',weights_only=True)
            last=torch.load(root/'last.pt',weights_only=True)
            self.assertEqual(best['epoch'],3); self.assertEqual(last['epoch'],18)
            self.assertEqual(last['bestEpoch'],3)
            self.assertEqual(report['bestLoss'],sequence[2])

    def test_completed_epoch_history_survives_later_failure(self):
        data=core.prepare(bundle(),'scalars',[0,1,2,3])
        actual_predict=core.predict
        calls=0
        def failing_predict(model,data,indices):
            nonlocal calls
            calls+=1
            if calls==2:
                raise RuntimeError('synthetic failure')
            return actual_predict(model,data,indices)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'failure'
            with patch.object(core,'predict',side_effect=failing_predict), self.assertRaisesRegex(RuntimeError,'synthetic failure'):
                core.train(data,[4,5],root,{'test':'durability'})
            history=json.loads((root/'history.json').read_text())
            self.assertEqual(len(history),1)
            self.assertEqual(history[0]['epoch'],1)
            self.assertFalse((root/'history.writing').exists())
            self.assertFalse((root/'report.json').exists())
            self.assertEqual(torch.load(root/'last.pt',weights_only=True)['epoch'],1)

    def test_actual_inner_selected_replay_and_leakage_guard(self):
        data=core.prepare(bundle(),'scalars',[0,1,2,3])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'inner'
            result=core.train(data,[4,5,6,7],root,{'test':'actual'})
            self.assertTrue(result['exactSelectionReplay'])
            self.assertGreaterEqual(result['bestEpoch'],1)
            self.assertEqual(core.replay(root,data,[4,5,6,7]),json.loads((root/'selection.json').read_text()))
            bad=copy.copy(data); bad['mean']=data['mean']+1
            with self.assertRaisesRegex(ValueError,'normalization'):
                core.replay(root,bad,[4,5])
            for selection,epochs in [([0,4],None),([4],2),([],True),([],0),([],101)]:
                with self.subTest(selection=selection,epochs=epochs),self.assertRaises(ValueError):
                    core.train(data,selection,Path(tmp)/'bad',{},epochs=epochs)


if __name__=='__main__': unittest.main()
