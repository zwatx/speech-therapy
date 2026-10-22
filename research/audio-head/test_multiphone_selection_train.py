"""Selection direction, artifact integrity and fixed-horizon persistence without real data."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import torch
import multiphone_selection_train as subject


def entry(epoch,nll=.2,ap=.1):
    return dict(epoch=epoch,selectionMacroNLL=nll,evaluation={'ages6to12':dict(macroTargetLogLoss=nll,
        targetDiscrimination={'macroTarget':{'ratingBelow2':{'averagePrecision':ap}}})})


class SelectionTests(unittest.TestCase):
    def test_runtime_accepts_executable_string_path(self):
        runtime = subject.runtime()
        executable = runtime['executable']
        self.assertTrue(Path(executable['path']).is_file())
        self.assertEqual(executable['sha256'], subject.digest(Path(executable['path'])))

    def test_directions_and_earlier_ties(self):
        history=[entry(i) for i in range(7)]
        history[1]=entry(1,.1,.2);history[2]=entry(2,.1,.2)
        history[3]=entry(3,.1-1e-8,.2+1e-8)
        history[4]=entry(4,.15,.3)
        selected=subject.selections(history)
        self.assertEqual(selected['nll']['epoch'],1)
        self.assertEqual(selected['ap']['epoch'],4)

    def test_epoch_zero_eligible(self):
        self.assertEqual({r:v['epoch'] for r,v in subject.selections([entry(i) for i in range(7)]).items()},
                         dict(nll=0,ap=0))

    def test_undefined_nonfinite_and_incomplete_fail(self):
        for value in (None,float('nan'),float('inf'),-float('inf')):
            for metric in ('nll','ap'):
                history=[entry(i) for i in range(7)]
                history[3]=entry(3,value,.1) if metric=='nll' else entry(3,.2,value)
                with self.subTest(value=value,metric=metric),self.assertRaises(ValueError): subject.selections(history)
        with self.assertRaises(ValueError):subject.selections([entry(i) for i in range(6)])
        with self.assertRaises(ValueError):subject.selections([entry(i) for i in reversed(range(7))])

    def fixture(self,root):
        config=subject.write_new(root/'config.json',dict(fold=0,coefficient=0.,validationRows=[1],declaration={'path':'p','sha256':'s'}))
        history=[entry(i) for i in range(7)];epochs=[]
        for i,e in enumerate(history):
            checkpoint=root/f'{i}.pt';checkpoint.write_bytes(b'checkpoint')
            epochs.append(dict(epoch=i,checkpoint=subject.binding(checkpoint),
                predictions=subject.write_new(root/f'{i}-p.json',dict(rowIndices=[1],probabilities=[[.1,.2,.7]])),
                metrics=subject.write_new(root/f'{i}-m.json',e)))
        selected={r:{**v,**{k:epochs[v['epoch']][k] for k in ('checkpoint','predictions')}}
                  for r,v in subject.selections(history).items()}
        return dict(complete=True,fold=0,coefficient=0.,config=config,history=subject.write_new(root/'history.json',history),
                    epochs=epochs,selections=selected,declaration={'path':'p','sha256':'s'},outerPredictionsPerformed=False,authorTestRead=False)

    def test_artifact_corruption_and_missing_epoch_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest=self.fixture(Path(directory))
            subject.validate_run_artifacts(manifest)
            incomplete=copy.deepcopy(manifest);incomplete['epochs'].pop()
            with self.assertRaises(ValueError):subject.validate_run_artifacts(incomplete)
            wrong=copy.deepcopy(manifest);wrong['selections']['nll']['epoch']=1
            with self.assertRaises(ValueError):subject.validate_run_artifacts(wrong)
            Path(manifest['epochs'][4]['checkpoint']['path']).write_bytes(b'corrupt')
            with self.assertRaises(ValueError):subject.validate_run_artifacts(manifest)

    def test_freeze_rejects_relabeling_one_valid_manifest_as_other_arm(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);manifest=self.fixture(root)
            pin=subject.write_new(root/'manifest.json',manifest)
            verified=dict(selectedPredictionsReplayExact=True,historicalPrefixExact=True,speakerPartitionsVerified=True)
            frozen=dict(complete=True,declaration=manifest['declaration'],declarationPath='p',declarationSha256='s',
                outerPredictionsPerformed=False,authorTestRead=False,selections=[],
                runs=[dict(**arm,**pin,selections=manifest['selections'],verification=verified) for arm in subject.arms()])
            freeze_pin=subject.write_new(root/'freeze.json',frozen)
            with patch.object(subject,'load_declaration',return_value={}):
                with self.assertRaisesRegex(ValueError,'Frozen run verification'):
                    subject.validate_freeze(freeze_pin['path'],freeze_pin['sha256'])

    def test_historical_prefix_mismatch_fails_before_checkpoint_read(self):
        with self.assertRaisesRegex(ValueError,'Historical prefix'):
            subject.check_prefix(entry(0,.3),np.zeros((1,3)),{}, {},[entry(0,.2)],0.)

    def mock_fit(self,failure=False):
        with tempfile.TemporaryDirectory(dir=subject.HERE/'outputs') as directory:
            root=Path(directory);plan_path=root/'declaration.json';plan_path.write_text('{}')
            pop=dict(fold=0,fitRows=[0],validationRows=[1],selectionRows=[1],outerRows=[2],inputFiles={},support={})
            old=subject.write_new(root/'old-history.json',[])
            plan=dict(populations={'0':pop},historical={'fold-0-coefficient-0':{'history.json':old}})
            net=torch.nn.Linear(1,1);p=np.array([[.1,.2,.7]])
            data=dict(warmState=net.state_dict(),mean=torch.zeros(1),std=torch.ones(1),fitCount=1,
                clean=torch.zeros(2,1),ids=torch.zeros(2,dtype=torch.long),labels=torch.tensor([[.1,.2,.7]]),
                sampler=SimpleNamespace(row_indices=np.array([0])),warmPredictions=p,validation=[1],
                cohort={'rows':[{'age':8},{'age':8}]})
            objective=dict(updates=1,sampledPairs=0,nllOrderDigest='fake',pairIdentityDigest='fake',cleanSupervisedNLL=.2)
            with patch.object(subject,'load_declaration',return_value=plan), \
                 patch.object(subject,'population',return_value=pop), \
                 patch.object(subject.original,'load_data',return_value=data), \
                 patch.object(subject.original,'model',side_effect=lambda:torch.nn.Linear(1,1)), \
                 patch.object(subject.original,'train_epoch',return_value=objective,
                              side_effect=ValueError('training failure') if failure else None) as train, \
                 patch.object(subject.original,'clean_prediction',return_value=p), \
                 patch.object(subject.original,'score_predictions',return_value=entry(0)['evaluation']), \
                 patch.object(subject.original.baseline,'selection_loss',return_value=.2), \
                 patch.object(subject,'check_prefix',return_value=[]):
                if failure:
                    with self.assertRaisesRegex(ValueError,'training failure'):subject.fit(plan_path,'test-sha',0,0.)
                    run=root/'runs/fold-0-coefficient-0'
                    self.assertTrue((run/'epoch-0.pt').exists());self.assertTrue((run/'failure.json').exists())
                    self.assertFalse((run/'manifest.json').exists())
                    return
                pin=subject.fit(plan_path,'test-sha',0,0.)
                manifest=subject.read_bound(pin)
                self.assertEqual(train.call_count,6)
                self.assertEqual(len(manifest['epochs']),7)
                self.assertEqual(manifest['selections']['nll']['epoch'],0)
                subject.validate_run_artifacts(manifest)
                saved=torch.load(manifest['epochs'][6]['checkpoint']['path'],weights_only=True)
                self.assertEqual(saved['declarationSha256'],'test-sha')
                self.assertIn('optimizer',saved)

    def test_fixed_horizon_saves_every_epoch_despite_no_improvement(self):self.mock_fit()
    def test_failure_retains_partial_artifacts_without_complete_manifest(self):self.mock_fit(failure=True)


if __name__=='__main__': unittest.main()
