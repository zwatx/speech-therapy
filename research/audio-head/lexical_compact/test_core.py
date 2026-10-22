"""Synthetic fixed-eigensystem and fresh-training checks; no corpus access."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

from lexical_compact import core


def bundle():
    rows = [dict(targetId=i%2,targetPhone=('B','P')[i%2],raterCounts=[i%2,1,4-i%2],
                 speakerId=f'speaker{i}',trainingEligible=True) for i in range(40)]
    target=np.zeros((40,1024),dtype=np.float32)
    for k in range(16):
        target[2*k,k]=k+1
        target[2*k+1,k]=-k-1
    target[32:,:16]=np.random.default_rng(14).normal(size=(8,16)).astype(np.float32)
    scalars=np.random.default_rng(15).normal(size=(40,13)).astype(np.float32)
    scalars[:,2]=5
    return dict(cohort={'rows':rows},target=target,scalars=scalars,positions={i:i for i in range(40)})


class CoreTests(unittest.TestCase):
    def prepare(self,b=None):
        return core.prepare(bundle() if b is None else b,'pca16-scalars',list(range(32)))

    def test_known_eigensystem_projection_and_width(self):
        b=bundle();d=self.prepare(b);t=d['transform']
        self.assertEqual(d['values'].shape,(40,29))
        np.testing.assert_array_equal(t['center'].numpy(),np.zeros(1024))
        expected=np.r_[np.arange(16,0,-1,dtype=float)**2/16,np.zeros(1008)]
        np.testing.assert_array_equal(t['eigenvalues'].numpy(),expected)
        basis=np.zeros((1024,16));basis[np.arange(15,-1,-1),np.arange(16)]=1
        np.testing.assert_array_equal(t['basis'].numpy(),basis)
        np.testing.assert_allclose(t['basis'].T@t['basis'],np.eye(16),atol=1e-15)
        np.testing.assert_array_equal(d['values'][:,:16],b['target'][:,:16][:,::-1])
        np.testing.assert_array_equal(d['values'][:,16:],b['scalars'])
        self.assertEqual(t['varianceFraction'],1.)
        self.assertEqual(t['rank'],16)
        self.assertEqual(t['fitRows'],list(range(32)))
        self.assertEqual(d['std'][18],1)
        model,_=core.initialize(29)
        self.assertEqual(sum(p.numel() for p in model.parameters()),40195)
        with self.assertRaises(ValueError):core.initialize(13)

    def test_deterministic_fit_only_transform_and_label_invariance(self):
        b=bundle();d=self.prepare(b)
        altered=copy.deepcopy(b);altered['target'][32:]=1e4;altered['scalars'][32:]=-1e5
        for r in altered['cohort']['rows'][32:]:r['raterCounts']=[5,0,0]
        other=self.prepare(altered);again=self.prepare(b)
        self.assertTrue(core.same_transform(d['transform'],other['transform']))
        self.assertTrue(core.same_transform(d['transform'],again['transform']))
        self.assertTrue(torch.equal(d['mean'],other['mean']))
        self.assertTrue(torch.equal(d['std'],other['std']))
        self.assertEqual(d['priors'],other['priors'])
        np.testing.assert_array_equal(d['values'][:32],other['values'][:32])
        relabelled=copy.deepcopy(b)
        for r in relabelled['cohort']['rows']:r['raterCounts']=[5,0,0]
        self.assertTrue(core.same_transform(d['transform'],self.prepare(relabelled)['transform']))

    def test_rotated_projector_and_sign_convention(self):
        b=bundle()
        rotation=np.linalg.qr(np.random.default_rng(204).normal(size=(1024,16)))[0]
        b['target']=(b['target'][:,:16].astype(np.float64)@rotation.T).astype(np.float32)
        transform=self.prepare(b)['transform'];basis=transform['basis'].numpy()
        np.testing.assert_allclose(basis@basis.T,rotation@rotation.T,atol=2e-8,rtol=0)
        self.assertTrue(all(basis[np.abs(basis[:,k]).argmax(),k]>0 for k in range(16)))
        np.testing.assert_allclose(basis.T@basis,np.eye(16),atol=3e-15,rtol=0)

    def test_rank_and_nonfinite_guards(self):
        for variant in ['rank15','constant','nan']:
            b=bundle()
            if variant=='rank15':b['target'][:,15]=0
            elif variant=='constant':b['target'][:]=0
            else:b['target'][0,0]=np.nan
            with self.subTest(variant=variant),self.assertRaises(ValueError):self.prepare(b)

    def test_fresh_deterministic_refit_no_prediction(self):
        d=self.prepare()
        with tempfile.TemporaryDirectory() as tmp:
            roots=[Path(tmp)/str(i) for i in range(2)]
            for root in roots:
                with patch.object(core,'predict',side_effect=AssertionError('no refit selection')):
                    report=core.train(d,[],root,{'test':'fresh-refit'},epochs=2)
                self.assertEqual(report['epochsRun'],2)
                self.assertEqual(report['totalUpdates'],2)
                self.assertIsNone(report['bestLoss'])
                self.assertIn('transform.pt',report['artifacts'])
            self.assertEqual(json.loads((roots[0]/'history.json').read_text()),json.loads((roots[1]/'history.json').read_text()))
            a,b=[torch.load(root/'best.pt',weights_only=True) for root in roots]
            self.assertTrue(all(torch.equal(a['model'][k],b['model'][k]) for k in a['model']))
            self.assertEqual(a['transformSha256'],core.binding(roots[0]/'transform.pt')['sha256'])
            initial=torch.load(roots[0]/'initial.pt',weights_only=True)
            model,_=core.initialize(29)
            self.assertTrue(all(torch.equal(initial['model'][k],v) for k,v in model.state_dict().items()))
            self.assertEqual(core.replay(roots[0],d,list(range(32,40))),core.replay(roots[1],d,list(range(32,40))))

    def test_exact_inner_replay_and_transform_tampering(self):
        d=self.prepare();selection=list(range(32,40))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'inner';report=core.train(d,selection,root,{'test':'inner'})
            self.assertTrue(report['exactSelectionReplay'])
            self.assertEqual(core.replay(root,d,selection),json.loads((root/'selection.json').read_text()))
            wrong=copy.deepcopy(d);wrong['transform']['center'][0]+=1
            with self.assertRaisesRegex(ValueError,'PCA state'):core.replay(root,wrong,selection)
            state=torch.load(root/'transform.pt',weights_only=True);state['basis'][0,0]+=1
            with (root/'transform.pt').open('wb') as stream:torch.save(state,stream)
            with self.assertRaisesRegex(ValueError,'transform binding'):core.replay(root,d,selection)

    def test_failure_keeps_completed_history(self):
        d=self.prepare();original=core.predict;calls=0
        def predict(*args):
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('synthetic selection failure')
            return original(*args)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'failed'
            with patch.object(core,'predict',side_effect=predict),self.assertRaisesRegex(RuntimeError,'synthetic'):
                core.train(d,list(range(32,40)),root,{})
            self.assertEqual(len(json.loads((root/'history.json').read_text())),1)
            self.assertEqual(torch.load(root/'last.pt',weights_only=True)['epoch'],1)
            self.assertFalse((root/'report.json').exists())


if __name__=='__main__':unittest.main()
