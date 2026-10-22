"""Synthetic pair distribution, update equivalence and replay guards."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_ranking_train as ranking
from test_multiphone_consistency_train import synthetic_data


def rows_fixture(count=130):
    votes = ([5,0,0],[0,5,0],[0,0,5],[1,1,3],[2,1,2])
    return [dict(id=f'r{i}',age=8,targetPhone='B' if i%2 else 'P',targetId=i%2,
        speakerId=f's{i%7}',raterCounts=list(votes[i%len(votes)]),clipId=f'clip{i//2}') for i in range(count)]


def large_data():
    rows=rows_fixture();torch.manual_seed(92)
    net=ranking.model();clean=torch.randn(len(rows),1037);ids=torch.tensor([r['targetId'] for r in rows])
    return dict(cohort={'rows':rows},fit=list(range(len(rows))),fitCount=len(rows),clean=clean,ids=ids,
        labels=torch.tensor([r['raterCounts'] for r in rows],dtype=torch.float32)/5,
        warmState=deepcopy(net.state_dict()),mean=torch.zeros(1037),std=torch.ones(1037),
        warmMean=torch.zeros(1037),warmStd=torch.ones(1037),sampler=ranking.PairSampler(rows,list(range(len(rows)))))


class RankingMechanicsTests(unittest.TestCase):
    def setUp(self):torch.set_num_threads(1)

    def test_analytical_distinct_joint_distribution_and_reverse_mixed_pairs(self):
        rows=rows_fixture(5)
        for r in rows:r['targetPhone']='B'
        sampler=ranking.PairSampler(rows,list(range(5)))
        for cell in sampler.cells:
            q=cell['q'];joint=q[:,None]*(1-q[None,:]);np.fill_diagonal(joint,0)
            computed=np.zeros_like(joint)
            for i in range(5):
                neg=cell['negative'].copy();neg[i]=0
                if cell['first'][i]>0:computed[i]=cell['first'][i]/cell['mass']*neg/neg.sum()
            np.testing.assert_allclose(computed,joint/joint.sum(),rtol=0,atol=2e-16)
            self.assertGreater(computed[3,4],0);self.assertGreater(computed[4,3],0)
            self.assertTrue(np.all(np.diag(computed)==0))
        draws=sampler.sample(np.random.default_rng(99),6000)
        self.assertFalse(np.any(draws[:,1]==draws[:,2]))
        self.assertGreater(np.count_nonzero(draws[:,0]==0),2500)
        self.assertLess(np.count_nonzero(draws[:,0]==0),3500)

    def test_each_pair_draws_event_and_active_phone_not_one_choice_per_update(self):
        sampler=ranking.PairSampler(rows_fixture(),list(range(130)))
        draws=sampler.sample(np.random.default_rng(20260926),64)
        self.assertEqual(set(draws[:,0]),{0,1})
        phones={sampler.rows[i]['targetPhone'] for i in draws[:,1]}
        self.assertEqual(phones,{'B','P'})
        self.assertTrue(all(sampler.rows[i]['targetPhone']==sampler.rows[j]['targetPhone'] for _,i,j in draws))
        self.assertTrue(any(sampler.rows[i]['speakerId']==sampler.rows[j]['speakerId'] for _,i,j in sampler.sample(np.random.default_rng(5),1000)))

    def test_single_mixed_row_has_zero_distinct_pair_mass_and_stays_in_inventory(self):
        rows=rows_fixture(5)
        for r in rows[:4]:r['targetPhone']='B'
        rows[4]['targetPhone']='R';rows[4]['raterCounts']=[1,1,3]
        sampler=ranking.PairSampler(rows,list(range(5)))
        cells=[c for c in sampler.cells if c['phone']=='R']
        self.assertEqual(len(cells),2);self.assertTrue(all(c['mass']==0 for c in cells))
        self.assertTrue(all(c['phone']!='R' for group in sampler.active for c in group))
        self.assertFalse(np.any(sampler.sample(np.random.default_rng(3),500)[:,1:]==4))

    def test_extreme_logits_are_stable_and_pair_mean_has_no_second_vote_weight(self):
        z=torch.tensor([[1000.,-1000.,0.],[-1000.,0.,1000.]],requires_grad=True)
        scores=ranking.stable_scores(z)
        self.assertTrue(torch.isfinite(scores).all())
        loss=torch.nn.functional.softplus(scores[1,0]-scores[0,0])+torch.nn.functional.softplus(scores[0,1]-scores[1,1])
        loss.backward();self.assertTrue(torch.isfinite(z.grad).all())
        pairs=np.array([[0,0,1],[1,1,0]],np.int64)
        mocked=torch.tensor([[.7,-.3,.2],[-.8,.4,.1],[-.8,.4,.1],[.7,-.3,.2]])
        expected=torch.nn.functional.softplus(ranking.stable_scores(mocked)[[2,3],[0,1]]-
                                               ranking.stable_scores(mocked)[[0,1],[0,1]]).mean()
        with patch.object(ranking,'logits',return_value=mocked):
            self.assertEqual(ranking.pair_loss(None,torch.zeros(2,1037),torch.zeros(2,dtype=torch.long),pairs),expected)

    def test_disabled_auxiliary_matches_frozen_control_exactly_with_small_final_batch(self):
        data=large_data();result=ranking.equivalence(data)
        self.assertTrue(all(result['exactChecks'].values()));self.assertEqual(result['comparedUpdates'],3)

    def test_separate_pair_rng_keeps_nll_order_and_64_pairs_on_last_update(self):
        data=large_data();n=data['fitCount'];outputs=[];states=[]
        for coefficient in (0.,.1):
            network=ranking.model();network.load_state_dict(data['warmState'])
            optimizer=torch.optim.AdamW(network.parameters(),lr=3e-5,weight_decay=.01)
            nll_rng,pair_rng=np.random.default_rng(7),np.random.default_rng(20260926)
            result=ranking.train_epoch(network,optimizer,data['clean'],data['ids'],data['labels'],
                nll_rng.permutation(n),data['sampler'],pair_rng,coefficient)
            outputs.append(result);states.append(nll_rng.bit_generator.state)
            self.assertFalse(network.training)
        self.assertEqual(outputs[0]['nllOrderDigest'],outputs[1]['nllOrderDigest']);self.assertEqual(states[0],states[1])
        self.assertEqual(outputs[1]['sampledPairs'],192);self.assertEqual(outputs[0]['sampledPairs'],0)
        self.assertGreater(outputs[1]['pairwiseLossMeanPerUpdate'],0)

    def test_pair_population_must_be_fit_child_rows_and_unique_ids(self):
        rows=rows_fixture(5);rows[0]['age']=20
        with self.assertRaisesRegex(ValueError,'child fitting'):ranking.PairSampler(rows,list(range(5)))
        rows[0]['age']=8
        rows[0]['raterCounts']=[.2,.8,5]
        with self.assertRaisesRegex(ValueError,'vote counts'):ranking.PairSampler(rows,list(range(5)))
        rows[0]['raterCounts']=[5,0,0]
        with self.assertRaisesRegex(ValueError,'distinct'):ranking.PairSampler(rows,[0,0,1,2,3])


class RankingArtifactTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        (self.root/'outputs').mkdir();self.path=self.root/'outputs/plan.json'
        self.data=synthetic_data('child-only')
        # Add explicit mixed votes; the shared fixture's child fit rows are otherwise all class2.
        for i in self.data['fit']:self.data['cohort']['rows'][i]['raterCounts']=[1,1,3]
        self.data['labels']=torch.tensor([self.data['cohort']['rows'][i]['raterCounts'] for i in self.data['fit']],dtype=torch.float32)/5
        self.data['sampler']=ranking.PairSampler([self.data['cohort']['rows'][i] for i in self.data['fit']],self.data['fit'])
        self.data['support']=self.data['sampler'].support()
        self.data['warmMean'],self.data['warmStd']=self.data['mean'].clone(),self.data['std'].clone()
        self.plan={'complete':True,'recipeSha256':ranking.digest(ranking.RECIPE),'sourceSha256':{'test':'fixed'},
            'inputFiles':{},'arms':ranking.arms(),'populations':{'0':{**{k+'Rows':self.data[k] for k in ('fit','validation','selection')},
                'inputFiles':{},'support':self.data['support'],'meanDigest':ranking.tensor_digest(self.data['mean']),
                'stdDigest':ranking.tensor_digest(self.data['std'])}},**{k:False for k in ranking.FALSE_FLAGS}}
        ranking.atomic_json(self.path,self.plan)
        self.enterContext(patch.object(ranking,'HERE',self.root))
        self.enterContext(patch.object(ranking,'source_hashes',return_value={'test':'fixed'}))
        self.enterContext(patch.object(ranking,'plan_guard',return_value=None))
        self.enterContext(patch.object(ranking,'load_data',side_effect=lambda *_args,**_kwargs:deepcopy(self.data)))

    def args(self,name='trial'):
        return SimpleNamespace(plan=self.path,plan_sha256=ranking.digest(self.path),fold=0,output=self.root/'outputs'/name)

    def test_fit_checkpoint_history_support_and_exact_selected_replay(self):
        args=self.args();report=ranking.fit(args)
        self.assertFalse(report['complete']);self.assertTrue(report['fitComplete'])
        self.assertEqual(set(report['filesSha256']),{'config.json','support.json','best.pt','last.pt','history.json','predictions.json','status.json'})
        replay=ranking.replay(args.output);self.assertTrue(replay['exact']);self.assertTrue(replay['complete'])
        history=ranking.read_json(args.output/'history.json')
        self.assertTrue(all('evaluation' in h and 'confidence' in h for h in history))
        self.assertTrue(all(h['sampledPairs']==64*h['updates'] for h in history[1:]))
        self.assertTrue(all('noisy' not in k.lower() for k in ranking.read_json(args.output/'predictions.json')))

    def test_epoch_zero_retained_under_ties_and_no_ranking_selection(self):
        args=self.args()
        initial=ranking.score_predictions(self.data['warmPredictions'],[self.data['cohort']['rows'][i] for i in self.data['validation']])
        with patch.object(ranking,'score_predictions',return_value=initial):
            report=ranking.fit(args)
            self.assertEqual(report['bestEpoch'],0);self.assertEqual(report['epochsRun'],2)
            self.assertTrue(ranking.replay(args.output)['exact'])
        saved=torch.load(args.output/'best.pt',weights_only=True)
        self.assertTrue(ranking.trees_equal(saved['model'],self.data['warmState']))

    def test_rehashed_pair_order_or_metric_tampering_rejected(self):
        args=self.args();ranking.fit(args)
        history=ranking.read_json(args.output/'history.json');history[1]['pairIdentityDigest']='0'*64
        ranking.atomic_json(args.output/'history.json',history)
        report=ranking.read_json(args.output/'report.json');report['filesSha256']['history.json']=ranking.digest(args.output/'history.json')
        ranking.atomic_json(args.output/'report.json',report)
        with self.assertRaisesRegex(ValueError,'pair identities'):ranking.replay(args.output)

    def test_changed_owned_file_during_training_blocks_report(self):
        args=self.args();original=ranking.clean_prediction;calls=0
        def mutate(network,data):
            nonlocal calls
            calls+=1
            if calls==2:(args.output/'support.json').write_text('{}')
            return original(network,data)
        with patch.object(ranking,'clean_prediction',side_effect=mutate),self.assertRaisesRegex(ValueError,'output changed'):
            ranking.fit(args)
        self.assertFalse((args.output/'report.json').exists())

    def test_actual_preflight_interface_forwards_only_fitting_population(self):
        captured=[]
        def loader(fold,recipe,validation=True):
            captured.append(validation);return deepcopy(self.data)
        with patch.object(ranking,'load_data',side_effect=loader),patch.object(ranking,'validate_recipe'),\
             patch.object(ranking,'equivalence',return_value={'exactChecks':{k:True for k in
                ('NLL','model','optimizer','moments','targetIDs','rowOrder','pairRNGUntouched')}}):
            result=ranking.preflight(self.root/'outputs/preflight.json')
        self.assertEqual(captured,[False]);self.assertTrue(result['fitOnly']);self.assertFalse(result['validationInferencePerformed'])


if __name__=='__main__':unittest.main()
