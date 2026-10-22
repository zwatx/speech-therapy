"""Sequence fitting contract checks using synthetic data only."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import torch
import multiphone_sequence_train as subject


def entry(epoch,nll=.2):
    return dict(epoch=epoch,selectionMacroNLL=nll,evaluation={'ages6to12':{'macroTargetLogLoss':nll}})


class SequenceTrainTests(unittest.TestCase):
    def test_nll_only_earlier_ties_and_warm(self):
        history=[entry(i) for i in range(7)]
        self.assertEqual(subject.selection(history)['epoch'],0)
        history[2]=entry(2,.1);history[3]=entry(3,.1-1e-8)
        self.assertEqual(subject.selection(history)['epoch'],2)
        for value in (None,float('nan'),float('inf')):
            bad=copy.deepcopy(history);bad[4]=entry(4,value)
            with self.assertRaises(ValueError):subject.selection(bad)
        with self.assertRaises(ValueError):subject.selection(history[:-1])

    def test_fit_only_moments_and_row_order(self):
        data=dict(cohort={'rows':[dict(trainingEligible=True) for _ in range(3)]},positions={0:0,1:1,2:2},
            fit=[0,1],validation=[2],clean=torch.zeros(3,1037),ids=torch.zeros(3,dtype=torch.long))
        matrix=np.array([[1,2,3,4],[3,4,5,6],[1000,1000,1000,1000]],dtype=np.float32)
        result=subject.prepare_data(data,matrix)
        self.assertTrue(torch.equal(result['sequenceMean'],torch.tensor([2.,3.,4.,5.])))
        self.assertTrue(torch.equal(result['sequenceStd'],torch.ones(4)))
        self.assertEqual(result['clean'].shape,(3,1041))
        self.assertTrue(torch.equal(result['clean'][:,:1037],data['clean']))
        fit_only=dict(data,clean=data['clean'][:2],ids=data['ids'][:2])
        self.assertEqual(subject.prepare_data(fit_only,matrix)['clean'].shape,(2,1041))
        data['positions']={0:1,1:0,2:2}
        with self.assertRaises(ValueError):subject.prepare_data(data,matrix)

    def test_disabled_branch_one_epoch_matches_original(self):
        torch.set_num_threads(2);torch.manual_seed(7)
        old=subject.original.model();new=subject.model(enabled=False);new.load_warm(old.state_dict())
        x=torch.randn(8,1037);combined=torch.cat((x,torch.randn(8,4)),1)
        ids=torch.arange(8);labels=torch.softmax(torch.randn(8,3),1)
        a=torch.optim.AdamW(old.parameters(),lr=3e-5,weight_decay=.01)
        b=torch.optim.AdamW(new.parameters(),lr=3e-5,weight_decay=.01)
        sampler=SimpleNamespace(row_indices=np.arange(8));order=np.arange(8)
        first=subject.original.train_epoch(old,a,x,ids,labels,order,sampler,np.random.default_rng(1),0.)
        second=subject.original.train_epoch(new,b,combined,ids,labels,order,sampler,np.random.default_rng(1),0.)
        self.assertEqual(first,second)
        self.assertTrue(all(torch.equal(v,new.state_dict()[k]) for k,v in old.state_dict().items()))
        subject.disabled_optimizer_equal(b.state_dict(),a.state_dict())
        self.assertTrue(np.array_equal(subject.original.predict(old,x,ids),subject.original.predict(new,combined,ids)))
        changed=copy.deepcopy(b.state_dict());next(iter(changed['state'].values()))['exp_avg'].add_(1)
        with self.assertRaises(ValueError):subject.disabled_optimizer_equal(changed,a.state_dict())

    def fixture(self,root):
        declaration=dict(path='p',sha256='s')
        config=subject.write_new(root/'config.json',dict(fold=0,arm='sequence',coefficient=0.,validationRows=[1],declaration=declaration))
        history=[entry(i) for i in range(7)];epochs=[]
        for i,e in enumerate(history):
            checkpoint=root/f'{i}.pt';checkpoint.write_bytes(b'checkpoint')
            epochs.append(dict(epoch=i,checkpoint=subject.binding(checkpoint),
                predictions=subject.write_new(root/f'{i}-p.json',dict(rowIndices=[1],probabilities=[[.1,.2,.7]])),
                metrics=subject.write_new(root/f'{i}-m.json',e)))
        chosen=subject.selection(history);chosen.update({k:epochs[chosen['epoch']][k] for k in ('checkpoint','predictions')})
        return dict(complete=True,fold=0,arm='sequence',coefficient=0.,config=config,history=subject.write_new(root/'history.json',history),
            epochs=epochs,selection=chosen,declaration=declaration,outerPredictionsPerformed=False,authorTestRead=False)

    def test_manifest_rejects_tampered_checkpoint_missing_epoch_and_wrong_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest=self.fixture(Path(directory));subject.validate_run_artifacts(manifest)
            bad=copy.deepcopy(manifest);bad['epochs'].pop()
            with self.assertRaises(ValueError):subject.validate_run_artifacts(bad)
            bad=copy.deepcopy(manifest);bad['selection']['epoch']=2
            with self.assertRaises(ValueError):subject.validate_run_artifacts(bad)
            Path(manifest['epochs'][2]['checkpoint']['path']).write_bytes(b'changed')
            with self.assertRaises(ValueError):subject.validate_run_artifacts(manifest)

    def test_frozen_population_and_feature_mismatch_rejected_before_outer_use(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);manifest=self.fixture(root)
            pin=subject.write_new(root/'manifest.json',manifest)
            frozen=dict(complete=True,declaration=manifest['declaration'],outerPredictionsPerformed=False,authorTestRead=False,
                runs=[dict(fold=f,**pin) for f in range(5)],controls=[dict(fold=f) for f in range(5)])
            freeze_pin=subject.write_new(root/'freeze.json',frozen)
            config=subject.read_bound(manifest['config']);config['features']=dict(path='a',sha256='a')
            for population,features in ((dict(validationRows=[9]),config['features']),
                                        (dict(validationRows=[1]),dict(path='b',sha256='b'))):
                plan=dict(populations={'0':population},features=features)
                with patch.object(subject,'load_declaration',return_value=plan), \
                     patch.object(subject,'validate_run_artifacts',return_value=(config,[])):
                    with self.assertRaisesRegex(ValueError,'population/features'):
                        subject.validate_freeze(freeze_pin['path'],freeze_pin['sha256'])

    def mock_fit(self,failure=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plan_path=root/'declaration.json';plan_path.write_text('{}')
            control={'history':[dict(epoch=i,**subject.zero_objective()) for i in range(7)]}
            pop=dict(fold=0,validationRows=[1])
            plan=dict(features=dict(path='features',sha256='f'),controls={'0':{'path':'control','sha256':'c'}})
            data=dict(warmState={},mean=torch.zeros(1),std=torch.ones(1),sequenceMean=torch.zeros(4),sequenceStd=torch.ones(4),
                fitCount=1,clean=torch.zeros(2,1041),ids=torch.zeros(2,dtype=torch.long),labels=torch.tensor([[.1,.2,.7]]),
                sampler=SimpleNamespace(row_indices=np.array([0])),warmPredictions=np.array([[.1,.2,.7]]),validation=[1],
                cohort={'rows':[dict(age=8),dict(age=8)]})
            class Network(torch.nn.Linear):
                def __init__(self):super().__init__(1,1)
                def load_warm(self,state):pass
            actual_read=subject.read_bound
            with patch.object(subject,'load_declaration',return_value=plan),patch.object(subject,'load_features',return_value=({},None)),\
                 patch.object(subject,'equivalence',return_value=dict(path='eq',sha256='e')),\
                 patch.object(subject.original,'load_data',return_value=data),patch.object(subject,'prepare_data',return_value=data),\
                 patch.object(subject,'check_population',return_value=pop),patch.object(subject,'model',side_effect=Network),\
                 patch.object(subject,'read_bound',side_effect=lambda pin:control if pin['path']=='control' else actual_read(pin)),\
                 patch.object(subject.retained,'validate_run_artifacts',return_value=({},control['history'])),\
                 patch.object(subject.original,'train_epoch',side_effect=ValueError('fit failed') if failure else None,return_value=subject.zero_objective()) as train,\
                 patch.object(subject.original,'clean_prediction',return_value=data['warmPredictions']),\
                 patch.object(subject,'entry_for',side_effect=lambda epoch,p,rows,obj:dict(**entry(epoch),**obj)):
                if failure:
                    with self.assertRaisesRegex(ValueError,'fit failed'):subject.fit(plan_path,'s',0)
                    out=root/'runs/fold-0-sequence'
                    self.assertTrue((out/'epoch-0.pt').exists());self.assertTrue((out/'failure.json').exists())
                    self.assertFalse((out/'manifest.json').exists())
                else:
                    pin=subject.fit(plan_path,'s',0);manifest=actual_read(pin)
                    self.assertEqual(train.call_count,6);self.assertEqual(len(manifest['epochs']),7)
                    subject.validate_run_artifacts(manifest)
                    with self.assertRaisesRegex(ValueError,'Fresh run'):subject.fit(plan_path,'s',0)

    def test_fixed_six_epochs_even_without_improvement(self):self.mock_fit()
    def test_failure_retains_partial_artifacts(self):self.mock_fit(True)


if __name__=='__main__':unittest.main()
