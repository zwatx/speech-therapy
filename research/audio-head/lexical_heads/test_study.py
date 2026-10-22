"""Supervised lexical membership and phase-order regression checks."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lexical_heads import study as s


class StudyTests(unittest.TestCase):
    def fixture(self):
        rows=[]
        for speaker,word,age in [('fit','FIT',8),('select','SELECT',9),('outer','OUTER',10)]:
            rows.extend(dict(clipId=speaker, speakerId=speaker, targetPhone=p, targetWord=word,
                             age=age, trainingEligible=True, raterCounts=[0,1,4]) for p in s.membership.PHONES)
        job=dict(id='x',family='scalars',regime='child-only',speakerFold=0,wordGroup=0,
                 fitRows=list(range(23)),selectionRows=list(range(23,46)),refitRows=list(range(46)),outerRows=list(range(46,69)))
        return job,rows,{'fit':['FIT'],'select':['SELECT'],'outer':['OUTER']},{'FIT':1,'SELECT':2,'OUTER':0,'INCIDENTAL':0}

    def test_exact_split_allows_missing_selection_phone(self):
        job,rows,tokens,groups=self.fixture()
        s.check_job(job,rows,tokens,groups)
        job['selectionRows'].pop();job['refitRows'].remove(45)
        s.check_job(job,rows,tokens,groups)

    def test_incidental_word_in_fit_or_selection_utterance_rejected(self):
        for clip in ['fit','select']:
            job,rows,tokens,groups=self.fixture();tokens[clip].append('INCIDENTAL')
            with self.subTest(clip=clip),self.assertRaisesRegex(ValueError,'Held-out word'):
                s.check_job(job,rows,tokens,groups)

    def test_partition_age_phone_and_outer_group_guards(self):
        job,rows,tokens,groups=self.fixture();rows[0]['age']=30
        with self.assertRaisesRegex(ValueError,'age restriction'):s.check_job(job,rows,tokens,groups)
        job,rows,tokens,groups=self.fixture();rows[0]['targetPhone']=rows[1]['targetPhone']
        with self.assertRaisesRegex(ValueError,'phone inventory'):s.check_job(job,rows,tokens,groups)
        job,rows,tokens,groups=self.fixture();groups['OUTER']=4
        with self.assertRaisesRegex(ValueError,'Outer target'):s.check_job(job,rows,tokens,groups)
        job,rows,tokens,groups=self.fixture();rows[46]['speakerId']='select'
        with self.assertRaisesRegex(ValueError,'speakers overlap'):s.check_job(job,rows,tokens,groups)

    def test_no_refit_or_outer_inference_before_valid_complete_freeze(self):
        with patch.object(s,'load_plan',return_value=({}, {}, {})), \
             patch.object(s,'check_freeze',side_effect=ValueError('missing frozen selections')), \
             patch.object(s.core,'train') as train,patch.object(s.core,'replay') as replay:
            for action in [s.refit,s.outer]:
                with self.assertRaisesRegex(ValueError,'missing frozen'):
                    action(Path('plan'),'p',Path('freeze'),'f')
            train.assert_not_called();replay.assert_not_called()

    def test_refit_config_matches_core_phase_and_binds_inner_selection(self):
        job,_,_,_=self.fixture()
        selection=dict(innerFreeze={},checkpoint={},epoch=3)
        value=s.config_value(job,{},'outer-refit',selection)
        self.assertEqual(value['phase'],'outer-refit')
        self.assertEqual(value['innerSelection'],selection)
        self.assertFalse(value['outerInferencePerformed'])

    def test_history_validation_rejects_corruption_and_premature_stop(self):
        import hashlib
        import json
        import numpy as np
        job,rows,_,_=self.fixture()
        artifacts={name:dict(path=name,sha256=name) for name in ['config.json','history.json','selection.json','selected-replay.json']}
        cfg=dict(s.config_value(job,{},'inner'),recipe=s.core.RECIPE,family=job['family'],fitRows=job['fitRows'],
                 selectionRows=job['selectionRows'],priorState=s.core.fit_priors([rows[i] for i in job['fitRows']]))
        p=np.tile([.1,.2,.7],(23,1));lp=np.log(p);counts=np.tile([0,1,4],(23,1))
        prediction=dict(rowIndices=job['selectionRows'],probabilities=p.tolist(),logProbabilities=lp.tolist(),
                        NLL=float(-(counts*lp).sum()/115))
        rng=np.random.default_rng(7);history=[]
        for epoch in range(1,17):
            order=rng.permutation(job['fitRows']).tolist()
            history.append(dict(epoch=epoch,orderSha256=hashlib.sha256(json.dumps(order,separators=(',',':')).encode()).hexdigest(),
                                updates=1,totalUpdates=epoch,trainLoss=.2,selection=copy.deepcopy(prediction)))
        report=dict(complete=True,configSha256='config.json',fitRows=job['fitRows'],selectionRows=job['selectionRows'],
                    artifacts=artifacts,epochsRun=16,bestEpoch=1,bestLoss=prediction['NLL'],totalUpdates=16)
        values={'config.json':cfg,'history.json':history,'selection.json':prediction,'selected-replay.json':prediction}
        run=dict(artifacts=artifacts,selectedEpoch=1)
        def check(v,r):
            with patch.object(s,'check_manifest',return_value=r),patch.object(s,'read',side_effect=lambda pin:v[pin['path']]):
                return s.validate_history(job,run,{},'inner',rows)
        self.assertEqual(check(values,report),report)
        for key,value in [('orderSha256','bad'),('updates',2),('totalUpdates',2)]:
            corrupted=copy.deepcopy(values);corrupted['history.json'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'history differs'):check(corrupted,report)
        early=copy.deepcopy(values);early['history.json'].pop()
        early_report=dict(report,epochsRun=15,totalUpdates=15)
        with self.assertRaisesRegex(ValueError,'stopped before'):check(early,early_report)
        wrong=copy.deepcopy(values);wrong['history.json'][0]['selection']['NLL']+=.1
        with self.assertRaisesRegex(ValueError,'NLL differs'):check(wrong,report)

    def model(self,nll=.2,macro=.2,brier=.1,ap0=.1,ap2=.2):
        summary={'measures':{'allWords':{'metrics':{'ages6to12':dict(perRaterLogLoss=nll,macroTargetLogLoss=macro,
          perRaterBrier=brier,discrimination={'rating0':{'averagePrecision':ap0},'ratingBelow2':{'averagePrecision':ap2}})}}}}
        return dict(pooled=summary,speakerFolds=[dict(summary=copy.deepcopy(summary)) for _ in range(5)])

    def test_consistency_retains_fold_and_rare_ranking_losses(self):
        base=self.model();better=self.model(nll=.19,macro=.19)
        self.assertTrue(s.consistency(better,base)['consistentDevelopmentGain'])
        better['speakerFolds'][2]=self.model(nll=.21)['speakerFolds'][2]
        self.assertFalse(s.consistency(better,base)['checks']['everySpeakerFoldChildNLLNoWorse'])
        self.assertFalse(s.consistency(self.model(nll=.19,macro=.19,ap0=.09),base)['checks']['pooledChildRating0APNoWorse'])
        self.assertFalse(s.consistency(base,base)['checks']['pooledChildNLLImproves'])


if __name__=='__main__':unittest.main()
