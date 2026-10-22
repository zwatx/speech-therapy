import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import torch
from lexical_projection import core
from lexical_compact import core as old

class ProjectionTests(unittest.TestCase):
 def fixture(self,root,phase='inner',flat=False):
  rng=np.random.default_rng(2);n=72
  rows=[dict(targetId=0,targetPhone='B',raterCounts=[1,1,3]) for _ in range(n)]
  bundle=dict(cohort={'rows':rows},positions={i:i for i in range(n)},scalars=rng.normal(size=(n,13)).astype('float32'),target=rng.normal(size=(n,1024)).astype('float32'))
  fit=list(range(66));selection=list(range(66,72));data=old.prepare(bundle,'pca16-scalars',fit);model,_=old.initialize(29)
  if flat:
   with torch.no_grad():
    for p in model.parameters():p.zero_()
  root.mkdir();torch.save(data['transform'],root/'transform.pt');tp=core.binding(root/'transform.pt')
  cfg=dict(recipe=old.RECIPE,transformRecipe=old.TRANSFORM_RECIPE,family='pca16-scalars',featureWidth=29,phase=phase,fitRows=fit,selectionRows=selection if phase=='inner' else [],transform=tp,priorState=data['priors'])
  core._json(root/'config.json',cfg);cp=core.binding(root/'config.json')
  torch.save(dict(model=model.state_dict(),configSha256=cp['sha256'],transformSha256=tp['sha256'],mean=data['mean'],std=data['std'],priorState=data['priors']),root/'best.pt')
  pins=(core.binding(root/'best.pt'),tp,cp)
  prepared=core.prepare(bundle,*pins,fit)
  return prepared,data,model,selection,bundle,pins
 def test_zero_exact_and_gradient_updates_only_delta(self):
  with tempfile.TemporaryDirectory() as tmp:
   d,original,m,sel,_,_=self.fixture(Path(tmp)/'source','outer-refit')
   self.assertEqual(core.predict(d,sel),old.predict(m,original,sel))
   before={k:v.clone() for k,v in d['model'].state_dict().items()}
   delta=torch.nn.Parameter(torch.zeros((1024,16),dtype=torch.float64));v,p,mask,y=core._batch(d,d['fit'][:64],delta)
   loss=-(y*d['model'](v,mask,p,mask)[:,0].log_softmax(-1)).sum(1).mean();loss.backward()
   self.assertGreater(float(delta.grad.abs().sum()),0)
   self.assertTrue(all(p.grad is None for p in d['model'].parameters()))
   result=core.train(d,[],Path(tmp)/'adapt',{},epochs=1)
   state=torch.load(Path(tmp)/'adapt/best.pt',weights_only=True)
   self.assertGreater(float(state['delta'].abs().sum()),0);self.assertEqual(result['totalUpdates'],2)
   self.assertTrue(all(torch.equal(v,d['model'].state_dict()[k]) for k,v in before.items()))
   self.assertEqual(core.replay(Path(tmp)/'adapt',d,sel),core.predict(d,sel,state['delta']))
 def test_zero_refit_no_prediction(self):
  with tempfile.TemporaryDirectory() as tmp:
   d,_,_,sel,_,_=self.fixture(Path(tmp)/'source','outer-refit')
   with patch.object(core,'predict',side_effect=AssertionError('no refit prediction')):
    result=core.train(d,[],Path(tmp)/'adapt',{},epochs=0)
   self.assertEqual((result['epochsRun'],result['bestEpoch'],result['totalUpdates']),(0,0,0))
   self.assertFalse((Path(tmp)/'adapt/selection.json').exists())
   self.assertEqual(core.replay(Path(tmp)/'adapt',d,sel),core.predict(d,sel))
 def test_epoch_zero_eligible_and_patience(self):
  with tempfile.TemporaryDirectory() as tmp:
   d,_,_,sel,_,_=self.fixture(Path(tmp)/'source',flat=True)
   result=core.train(d,sel,Path(tmp)/'adapt',{})
   self.assertEqual(result['bestEpoch'],0);self.assertEqual(result['epochsRun'],5)
   history=json.loads((Path(tmp)/'adapt/history.json').read_text());self.assertEqual(len(history),6)
   self.assertEqual(core.replay(Path(tmp)/'adapt',d,sel),history[0]['selection'])
   self.assertEqual(history[0]['updates'],0);self.assertIsNone(history[0]['orderSha256'])
 def test_phase_config_and_source_guards(self):
  with tempfile.TemporaryDirectory() as tmp:
   d,_,_,sel,bundle,pins=self.fixture(Path(tmp)/'source')
   for selection,epochs in [([],None),(sel,1),([],True),([],21),([],0)]:
    with self.assertRaises(ValueError):core.train(d,selection,Path(tmp)/'bad',{},epochs=epochs)
   with self.assertRaises(ValueError):core.train(d,sel,Path(tmp)/'bad',{'recipe':{}})
   with self.assertRaises(ValueError):core.prepare(bundle,*pins,list(range(65)))
   Path(pins[2]['path']).write_text('{}')
   with self.assertRaisesRegex(ValueError,'Source binding'):core.prepare(bundle,*pins,d['fit'])
   with self.assertRaisesRegex(ValueError,'Source binding'):core.train(d,sel,Path(tmp)/'bad',{})
 def test_reproducible_and_mutated_head_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   d,_,_,_,_,_=self.fixture(Path(tmp)/'source','outer-refit')
   for name in ['a','b']:core.train(d,[],Path(tmp)/name,{},epochs=1)
   a=torch.load(Path(tmp)/'a/best.pt',weights_only=True);b=torch.load(Path(tmp)/'b/best.pt',weights_only=True)
   self.assertTrue(torch.equal(a['delta'],b['delta']))
   with torch.no_grad():next(d['model'].parameters()).add_(1)
   with self.assertRaisesRegex(ValueError,'Frozen head changed'):core.train(d,[],Path(tmp)/'c',{},epochs=0)

if __name__=='__main__':unittest.main()
