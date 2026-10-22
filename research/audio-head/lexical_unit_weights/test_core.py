"""Exact control training and independent weighted gradients on synthetic features."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import torch
from lexical_unit_weights import core


def bundle(repeated=False):
    rows=[];clips=[]
    for i in range(76):
        p=('B','P')[i%2]
        rows.append(dict(id=str(i),clipId=str(i),speakerId=f's{i}',age=8,canonicalIndex=0,wordIndex=0,phoneIndex=0,
            canonicalRaw=p,targetPhone=p,targetId=i%2,raterCounts=[i%2,1,4-i%2],trainingEligible=True))
        clips.append(dict(id=str(i),speakerId=f's{i}',age=8,words=[dict(phones=[p])],canonicalPhones=[p],canonicalPhoneCount=1))
    if repeated:
        clips=clips[2:]
        clips[0]=dict(id='2',speakerId='s2',age=8,words=[dict(phones=['B','B','P'])],canonicalPhones=['B','B','P'],canonicalPhoneCount=3)
        for i,p in enumerate(['B','B','P']):
            rows[i].update(clipId='2',speakerId='s2',canonicalIndex=i,phoneIndex=i,canonicalRaw=p,targetPhone=p,targetId=('B','P').index(p))
    rng=np.random.default_rng(43)
    target=np.zeros((76,1024),dtype=np.float32);target[:,:20]=rng.normal(size=(76,20)).astype(np.float32)
    return dict(cohort=dict(rows=rows,clips=clips),scalars=rng.normal(size=(76,13)).astype(np.float32),target=target,positions={i:i for i in range(76)})


def same(test,a,b):
    if torch.is_tensor(a):test.assertTrue(torch.equal(a,b))
    elif isinstance(a,dict):
        test.assertEqual(set(a),set(b))
        for key in a:same(test,a[key],b[key])
    elif isinstance(a,(list,tuple)):
        test.assertEqual(len(a),len(b))
        for x,y in zip(a,b):same(test,x,y)
    else:test.assertEqual(a,b)


class CoreTests(unittest.TestCase):
    def test_all_one_trajectories_match_both_frozen_trainers(self):
        # Full actual inner training and two-epoch refit. 65 fit rows exercise a partial batch.
        for family in ('scalars','pca16-scalars'):
            data=core.prepare(bundle(),family,list(range(65)));backend=core.implementation(family)
            self.assertEqual(data['weightState']['weights'],[1.]*65)
            for epochs in (2,None):
                selection=[] if epochs else list(range(65,76))
                with self.subTest(family=family,epochs=epochs),tempfile.TemporaryDirectory() as folder:
                    a,b=Path(folder)/'old',Path(folder)/'new'
                    old=backend.train(data,selection,a,{},epochs=epochs)
                    new=core.train(data,selection,b,{},epochs=epochs)
                    self.assertEqual(json.loads((a/'history.json').read_text()),json.loads((b/'history.json').read_text()))
                    for key in ('epochsRun','bestEpoch','bestLoss','totalUpdates','exactSelectionReplay'):
                        self.assertEqual(old[key],new[key])
                    for file in ('initial.pt','best.pt','last.pt'):
                        left,right=[torch.load(p/file,weights_only=True) for p in (a,b)]
                        # Only objective/artifact provenance differs between old and new checkpoints.
                        right.pop('weightsSha256');left.pop('configSha256');right.pop('configSha256')
                        same(self,left,right)
                    self.assertEqual(backend.replay(a,data,list(range(65,76))),core.replay(b,data,list(range(65,76))))

    def test_weighted_loss_manual_gradient_and_fixed_batch_denominator(self):
        logits=torch.tensor([[1.,-.4,.3],[-2.,1.,.1],[0.,0.,0.]],requires_grad=True)
        targets=torch.tensor([[.2,.2,.6],[0.,0.,1.],[.4,.2,.4]])
        weights=torch.tensor([.5,1.5,2.])
        value=core.weighted_loss(logits,targets,weights);value.backward()
        z=logits.detach().double().numpy();p=np.exp(z-z.max(1)[:,None]);p/=p.sum(1)[:,None]
        expected=(p-targets.numpy())*weights.numpy()[:,None]/3
        np.testing.assert_allclose(logits.grad.numpy(),expected,rtol=1e-6,atol=2e-8)
        expectedloss=sum(-float(weights[i])*sum(float(targets[i,k])*np.log(p[i,k]) for k in range(3)) for i in range(3))/3
        self.assertAlmostEqual(float(value.detach()),expectedloss,places=6)
        self.assertNotAlmostEqual(float(value.detach()),expectedloss*3/float(weights.sum()),places=5)
        for w in (torch.tensor([0.,1.,1.]),torch.tensor([float('nan'),1.,1.]),torch.ones(2),torch.ones(3,dtype=torch.float64)):
            with self.assertRaises(ValueError):core.weighted_loss(logits,targets,w)

    def test_weighted_adamw_matches_manual_four_step_reference(self):
        start=torch.tensor([[.2,-.1,.3],[.5,.2,-.7]],dtype=torch.float32)
        actual=torch.nn.Parameter(start.clone());manual=start.clone();m=torch.zeros_like(start);v=torch.zeros_like(start)
        opt=torch.optim.AdamW([actual],lr=.0003,weight_decay=.01)
        labels=torch.tensor([[.2,.2,.6],[.6,.0,.4]]);weight=torch.tensor([.75,1.5])
        for step in range(1,5):
            opt.zero_grad(set_to_none=True);core.weighted_loss(actual,labels,weight).backward();opt.step()
            g=(manual.softmax(-1)-labels)*weight[:,None]/len(manual)
            m=.9*m+.1*g;v=.999*v+.001*g.square()
            manual=manual*(1-.0003*.01)-.0003*(m/(1-.9**step))/((v/(1-.999**step)).sqrt()+1e-8)
            torch.testing.assert_close(actual,manual,rtol=1e-6,atol=1e-7)
            torch.testing.assert_close(opt.state[actual]['exp_avg'],m,rtol=1e-6,atol=2e-8)
            torch.testing.assert_close(opt.state[actual]['exp_avg_sq'],v,rtol=1e-6,atol=2e-10)

    def test_fit_only_moments_weights_and_transform(self):
        for family in ('scalars','pca16-scalars'):
            b=bundle(True);before=core.prepare(b,family,list(range(65)));changed=copy.deepcopy(b)
            changed['target'][65:]=1e5;changed['scalars'][65:]=-1e5
            for row in changed['cohort']['rows'][65:]:row['raterCounts']=[5,0,0]
            after=core.prepare(changed,family,list(range(65)))
            same(self,before['weightState'],after['weightState']);same(self,before['mean'],after['mean']);same(self,before['std'],after['std'])
            self.assertEqual(before['priors'],after['priors'])
            if family=='pca16-scalars':self.assertTrue(core.compact.same_transform(before['transform'],after['transform']))

    def test_nonuniform_training_replay_binding_and_refit_no_selection(self):
        for family in ('scalars','pca16-scalars'):
            data=core.prepare(bundle(True),family,list(range(65)));backend=core.implementation(family)
            self.assertGreater(max(data['weightState']['weights']),min(data['weightState']['weights']))
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'fit'
                with patch.object(backend,'predict',side_effect=AssertionError('No refit selection')):
                    result=core.train(data,[],path,{},epochs=2)
                self.assertEqual(result['totalUpdates'],4)
                self.assertEqual(core.replay(path,data,[65,66]),core.replay(path,data,[65,66]))
                cfg=json.loads((path/'config.json').read_text());state=torch.load(path/'best.pt',weights_only=True)
                self.assertEqual(state['weightsSha256'],cfg['weights']['sha256'])
                bad=copy.deepcopy(data);bad['weightState']['weights'][0]+=1
                with self.assertRaisesRegex(ValueError,'weight state'):core.replay(path,bad,[65])
                state['weightsSha256']='changed';torch.save(state,path/'best.pt')
                with self.assertRaisesRegex(ValueError,'Checkpoint weight'):core.replay(path,data,[65])
                with self.assertRaisesRegex(ValueError,'fresh'):core.train(data,[],path,{},epochs=2)

    def test_config_conflict_and_partition_guards(self):
        data=core.prepare(bundle(True),'scalars',list(range(65)))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for selection,epochs in [([0,65],None),([65],2),([],0),([],True),([],101)]:
                with self.assertRaises(ValueError):core.train(data,selection,root/'bad',{},epochs=epochs)
            with self.assertRaisesRegex(ValueError,'conflicts'):core.train(data,[],root/'bad',dict(weightRecipe={}),epochs=2)
            self.assertFalse((root/'bad').exists())


if __name__=='__main__':unittest.main()
