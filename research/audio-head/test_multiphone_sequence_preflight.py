"""Metadata-selection and independent CTC-oracle tests; no real feature passes."""
import copy
import itertools
import math
from pathlib import Path
import tempfile
import unittest
import numpy as np
import multiphone_sequence_preflight as subject


class PreflightTests(unittest.TestCase):
    def fixture(self):
        clips=[];rows=[];manifest=[]
        for i,(name,length) in enumerate([('b',100),('a',100),('c',200),('d',300),('v',50),('o',400)]):
            clip=dict(id=name,speakerId=str(i),audioPath='/mock/'+name,audioSha256='mock',sampleCount=length)
            clips.append(clip)
            rows.append(dict(id=name+':B',clipIndex=i,age=8,trainingEligible=True,speakerId=str(i),
                             targetId=0,targetPhone='B',wordIndex=0,phoneIndex=0))
            target=dict(rowIndex=i,rowId=name+':B',canonicalIndex=0,targetId=0,targetPhone='B',wordIndex=0,phoneIndex=0)
            manifest.append(dict(**clip,clipIndex=i,canonicalPhones=['B'],mappedTokens=['b'],mappedTokenIds=[26],
                                 mappingAmbiguities=[],targetRows=[target]))
        return dict(authorPartition='train',clips=clips,rows=rows), \
            dict(authorPartition='train',folds=[dict(innerFitRows=[0,1,2,3],innerValidationRows=[4],outerHoldoutRows=[5])]), \
            dict(fold=0,regime='child-only',fitRows=[0,1,2,3]),dict(authorPartition='train',clips=manifest)

    def test_geometry_selection_ties_upper_median_and_no_labels(self):
        cohort,splits,warm,manifest=self.fixture()
        for row in cohort['rows']:row['raterCounts']='must never be read'
        selected=subject.select_clips(cohort,splits,warm,manifest)
        self.assertEqual([c['id'] for c in selected],['a','c','d'])
        self.assertEqual([c['targetRows'][0]['rowIndex'] for c in selected],[1,2,3])
        self.assertNotIn('raterCounts',str(selected))
        manifest['clips'].reverse()
        self.assertEqual(subject.select_clips(cohort,splits,warm,manifest),selected)

    def test_warm_membership_speaker_overlap_and_target_join_fail(self):
        for damage in ('membership','speaker','target','child'):
            cohort,splits,warm,manifest=self.fixture()
            if damage=='membership':warm['fitRows']=[0,1,2]
            if damage=='speaker':cohort['rows'][4]['speakerId']=cohort['rows'][0]['speakerId']
            if damage=='target':manifest['clips'][1]['targetRows'][0]['rowIndex']=4
            if damage=='child':cohort['rows'][1]['age']=13
            with self.subTest(damage=damage),self.assertRaises(ValueError):
                subject.select_clips(cohort,splits,warm,manifest)

    def test_oracle_matches_enumerated_ctc_paths_with_deletion_and_repeats(self):
        logp=np.log(np.array([[.2,.5,.3],[.3,.4,.3],[.5,.2,.3]],dtype=np.float64))
        hypotheses=[[],[1],[1,1],[1,2],[2,1],[2,2],[1,1,1]]
        oracle=subject.torch_ctc(logp,hypotheses,chunk=2)
        for target,actual in zip(hypotheses,oracle,strict=True):
            expected=float('-inf')
            for path in itertools.product(range(3),repeat=3):
                collapsed=[];previous=None
                for token in path:
                    if token!=previous and token!=0:collapsed.append(token)
                    previous=token
                if collapsed==target:expected=float(np.logaddexp(expected,sum(logp[i,t] for i,t in enumerate(path))))
            self.assertLessEqual(subject.difference(actual,expected),1e-12)

    def test_oracle_consumes_logprobabilities_without_underflow(self):
        logp=np.array([[0.,-1000.]],dtype=np.float64)
        scores=subject.torch_ctc(logp,[[1],[],[1,1]])
        self.assertEqual(scores,[-1000.,0.,float('-inf')])
        self.assertEqual(subject.serializable(scores),[-1000.,0.,'-Infinity'])
        self.assertEqual(subject.torch_ctc(np.array([[float('-inf'),0.]]),[[1],[]]),[0.,float('-inf')])

    def test_oracle_chunk_bound_and_invalid_probabilities(self):
        good=np.log(np.array([[.5,.5]],dtype=np.float64))
        for value in (0,33):
            with self.assertRaises(ValueError):subject.torch_ctc(good,[[1]],chunk=value)
        for matrix in (np.array([[float('nan'),0.]]),np.array([[0.,0.]])):
            with self.assertRaises(ValueError):subject.torch_ctc(matrix,[[1]])
        with self.assertRaises(ValueError):subject.torch_ctc(good,[[0]])
        with self.assertRaises(ValueError):subject.difference(float('-inf'),-1000.)

    def test_corrupted_binding_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'plan.json';pin=subject.write_new(path,dict(scope='fitting-only'))
            self.assertEqual(subject.read_bound(pin),dict(scope='fitting-only'))
            with self.assertRaises(FileExistsError):subject.write_new(path,{})
            path.write_text('{}')
            with self.assertRaises(ValueError):subject.read_bound(pin)


if __name__=='__main__':unittest.main()
