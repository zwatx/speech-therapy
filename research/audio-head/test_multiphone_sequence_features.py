"""Synthetic identity joins and undefined-feature rejection; no corpus extraction."""
import copy
from pathlib import Path
import tempfile
import hashlib
import unittest
from unittest.mock import patch
import numpy as np
from multiphone_sequence_ctc import SequenceCTC,summarize_slot
import multiphone_sequence_features as subject


class SequenceFeatureTests(unittest.TestCase):
    def fixture(self):
        recipe=dict(convKernel=[1],convStride=[1],consonants={'B':'b'},vowels={},stressOverrides={})
        vocabulary={'b':4}
        clips=[];rows=[];mapped=[];entries={}
        for i in range(2):
            clip=dict(id=str(i),speakerId=str(i),audioPath='/fake/'+str(i),audioSha256='fake',
                      sampleCount=2,canonicalPhoneCount=1)
            clips.append(clip)
            rows.append(dict(id=str(i)+':B',trainingEligible=True,clipIndex=i,clipId=str(i),
                             targetId=0,targetPhone='B',wordIndex=0,phoneIndex=0,raterCounts='not read'))
            target=dict(rowIndex=i,rowId=str(i)+':B',canonicalIndex=0,targetId=0,targetPhone='B',wordIndex=0,phoneIndex=0)
            mapped.append(dict(**clip,clipIndex=i,canonicalPhones=['B'],mappedTokens=['b'],mappedTokenIds=[4],
                               mappingAmbiguities=[],targetRows=[target]))
            entries[str(i)]=dict(clipId=str(i),sampleCount=2,audioSha256='fake',configSha256='config',
                                 vocabularySize=392,frames=2)
        return dict(authorPartition='train',rows=rows,clips=clips),dict(authorPartition='train',clips=mapped), \
            dict(entries=entries,configSha256='config'),recipe,vocabulary

    def test_full_join_preserves_eligible_order_without_ratings(self):
        cohort,manifest,index,recipe,vocab=self.fixture();manifest['clips'].reverse()
        eligible,clips=subject.joined_clips(cohort,manifest,index,recipe,vocab)
        self.assertEqual(eligible,[0,1]);self.assertEqual([c['id'] for c in clips],['1','0'])
        self.assertNotIn('raterCounts',str(clips))
        rows=[dict(rowIndex=1,features=[1.,2.,3.,4.]),dict(rowIndex=0,features=[4.,3.,2.,1.])]
        ordered,matrix=subject.arrange_rows(eligible,rows)
        self.assertEqual([r['rowIndex'] for r in ordered],[0,1])
        self.assertEqual(matrix.dtype,np.float32)
        self.assertEqual(matrix.tolist(),[[4.,3.,2.,1.],[1.,2.,3.,4.]])

    def test_missing_duplicate_or_mapped_identity_corruption_fails(self):
        for damage in ('missing','duplicate','token','slot','audio'):
            cohort,manifest,index,recipe,vocab=self.fixture()
            if damage=='missing':manifest['clips'].pop()
            elif damage=='duplicate':manifest['clips'].append(copy.deepcopy(manifest['clips'][0]))
            elif damage=='token':manifest['clips'][0]['mappedTokenIds']=[5]
            elif damage=='slot':manifest['clips'][0]['targetRows'][0]['rowIndex']=1
            else:index['entries']['0']['audioSha256']='changed'
            with self.subTest(damage=damage),self.assertRaises(ValueError):
                subject.joined_clips(cohort,manifest,index,recipe,vocab)

    def calculated(self,logp):
        _,manifest,_,_,_=self.fixture();clip=manifest['clips'][0];clip['frames']=len(logp)
        engine=SequenceCTC(logp,[4]);likelihoods=engine.slot_likelihoods(0,subject.preflight.CANDIDATES)
        computed=dict(canonicalLogLikelihood=engine.log_probability,slots=[dict(target=clip['targetRows'][0],
                      likelihoods=likelihoods,summary=summarize_slot(likelihoods))])
        return clip,computed

    def test_four_features_follow_fixed_order_and_float32_conversion(self):
        clip,computed=self.calculated(np.full((2,392),-np.log(392.)))
        rows=subject.feature_rows(computed,clip)
        expected=[computed['slots'][0]['summary'][name] for name in subject.FEATURE_NAMES[:3]]
        expected.append(computed['canonicalLogLikelihood']/2)
        self.assertEqual(rows[0]['features'],np.array(expected,dtype=np.float32).tolist())
        wrong=copy.deepcopy(computed);wrong['slots'][0]['target']['rowIndex']=99
        with self.assertRaises(ValueError):subject.feature_rows(wrong,clip)

    def test_zero_probability_undefined_deletion_and_other_fail_without_imputation(self):
        for blank in (float('-inf'),np.log(.2)):
            logp=np.full((1,392),float('-inf'));logp[0,0]=blank
            logp[0,4]=0. if not np.isfinite(blank) else np.log(.8)
            clip,computed=self.calculated(logp)
            with self.assertRaisesRegex(ValueError,'Undefined/nonfinite'):
                subject.feature_rows(computed,clip)
        clip,computed=self.calculated(np.full((2,392),-np.log(392.)))
        computed['slots'][0]['summary'][subject.FEATURE_NAMES[0]]=float('nan')
        with self.assertRaises(ValueError):subject.feature_rows(computed,clip)

    def test_matrix_coverage_rejects_duplicate_missing_or_nonfinite_rows(self):
        for rows in ([dict(rowIndex=0,features=[0.]*4)]*2,
                     [dict(rowIndex=0,features=[0.]*4)],
                     [dict(rowIndex=0,features=[0.]*4),dict(rowIndex=1,features=[float('inf')]*4)]):
            with self.assertRaises(ValueError):subject.arrange_rows([0,1],rows)

    def test_readonly_verifier_reconstructs_matrix_and_rejects_bound_corruption(self):
        clip,computed=self.calculated(np.full((2,392),-np.log(392.)))
        rows=subject.feature_rows(computed,clip)
        with tempfile.TemporaryDirectory(dir=subject.HERE/'outputs') as directory:
            root=Path(directory)
            original=subject.write_new(root/'approved.json',computed)
            artifact=subject.write_new(root/'clip.json',dict(clip=clip,computed=computed))
            plan=dict(clips=[clip],rowIndices=[0],inputBindings={'preflightArtifact/0/core':original},runtime={})
            plan_pin=subject.write_new(root/'plan.json',plan)
            matrix_path=root/'matrix.npy';np.save(matrix_path,np.array([rows[0]['features']],dtype=np.float32))
            certificate={'0':dict(exact=True,numericalSha256=hashlib.sha256(subject.numerical_bytes(computed)).hexdigest())}
            report=dict(complete=True,fullCohortCoverage=True,authorPartition='train',plan=plan_pin,
                inputBindings=plan['inputBindings'],runtime={},featureNames=subject.FEATURE_NAMES,
                candidateTokenIds=subject.preflight.CANDIDATES,rowIndices=[0],rows=rows,eligibleCohortRows=1,clips=1,
                featureCalculationPerformed=True,trainingPerformed=False,modelInferencePerformed=False,
                labelEvaluationPerformed=False,authorTestRead=False,clinicalUseEligible=False,learnerFeedbackEligible=False,
                clipArtifacts={'0':artifact},matrix=dict(**subject.binding(matrix_path),dtype='float32',shape=[1,4]),
                preflightVerification=certificate,repeatVerification=certificate)
            report_pin=subject.write_new(root/'report.json',report)
            with patch.object(subject,'load_plan',return_value=plan),patch.object(subject,'CLIP_COUNT',1), \
                 patch.object(subject,'ROW_COUNT',1),patch.object(subject.preflight,'EXPECTED_IDS',['0']), \
                 patch.object(subject.preflight,'core_clip',side_effect=AssertionError('No likelihood calculations')):
                self.assertEqual(subject.validate_export(report_pin['path'],report_pin['sha256']),report)
                # A changed matrix with its own updated digest must still fail numerical reconstruction.
                np.save(matrix_path,np.zeros((1,4),dtype=np.float32))
                report['matrix'].update(subject.binding(matrix_path))
                wrong=subject.write_new(root/'wrong-report.json',report)
                with self.assertRaisesRegex(ValueError,'Matrix/row identity'):
                    subject.validate_export(wrong['path'],wrong['sha256'])

    def test_failure_retains_raw_clip_and_never_publishes_matrix(self):
        clip,computed=self.calculated(np.full((2,392),-np.log(392.)))
        computed['slots'][0]['summary'][subject.FEATURE_NAMES[1]]=None
        with tempfile.TemporaryDirectory(dir=subject.HERE/'outputs') as directory:
            root=Path(directory);plan_path=root/'plan.json';plan_path.write_text('{}')
            plan=dict(clips=[clip],rowIndices=[0],inputBindings={})
            with patch.object(subject,'load_plan',return_value=plan), \
                 patch.object(subject,'read_posterior',return_value=np.zeros((2,392))), \
                 patch.object(subject.preflight,'core_clip',return_value=computed):
                with self.assertRaisesRegex(ValueError,'Undefined/nonfinite'):subject.run(plan_path,'mock-sha')
            self.assertTrue((root/'clips/0.json').exists())
            self.assertTrue((root/'failure.json').exists())
            self.assertFalse((root/'features.npy').exists());self.assertFalse((root/'features.json').exists())


if __name__=='__main__':unittest.main()
