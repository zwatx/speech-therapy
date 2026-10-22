"""Synthetic canonical geometry, PCM preservation and diagnostic failure gates."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import multiphone_word_context_sensitivity as context


def word_fixture():
    targets=[{'rowIndex':0,'rowId':'r0','clipId':'000000001','targetId':0,'targetPhone':'B','wordIndex':0,'phoneIndex':0,'canonicalIndex':0},
             {'rowIndex':1,'rowId':'r1','clipId':'000000001','targetId':1,'targetPhone':'P','wordIndex':1,'phoneIndex':1,'canonicalIndex':3}]
    clip={'id':'000000001','canonicalPhones':['B','AH0','AH0','P'],'mappedTokenIds':[4,7,7,5],
          'sampleCount':16000,'targets':targets}
    score={'words':[{'text':'ba','phones':['B','AH0']},{'text':'up','phones':['AH0','P']}]}
    cohort={'rows':[{**t,'id':t['rowId'],'trainingEligible':True,'targetWord':score['words'][t['wordIndex']]['text']} for t in targets]}
    return clip,score,cohort


class ContextGeometryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.mapping=context.read_json(context.local.RECIPE)

    def test_word_offsets_preserve_repeated_boundary_phone_and_crop_local_identity(self):
        clip,score,cohort=word_fixture();words=context.word_inventory(clip,score,cohort)
        self.assertEqual([w['canonicalRange'] for w in words],[[0,2],[2,4]])
        self.assertEqual(words[1]['mappedTokenIds'],[7,5])
        local=context.crop_clip(clip,words[1])['targets'][0]
        self.assertEqual(local['sourceCanonicalIndex'],3);self.assertEqual(local['canonicalIndex'],1)
        self.assertEqual(local['sourceWordIndex'],1);self.assertEqual(local['wordIndex'],0)
        bad=deepcopy(score);bad['words'][1]['phones'].reverse()
        with self.assertRaisesRegex(ValueError,'flattening'):context.word_inventory(clip,bad,cohort)
        bad=deepcopy(cohort);bad['rows'][1]['targetWord']='different'
        with self.assertRaisesRegex(ValueError,'identity'):context.word_inventory(clip,score,bad)

    def test_multi_target_word_keeps_original_target_order(self):
        clip,score,cohort=word_fixture()
        score={'words':[{'text':'bup','phones':clip['canonicalPhones']}]}
        clip['targets'][1].update(wordIndex=0,phoneIndex=3)
        cohort['rows'][1].update(wordIndex=0,phoneIndex=3)
        for row in cohort['rows']:row['targetWord']='bup'
        words=context.word_inventory(clip,score,cohort)
        self.assertEqual(len(words),1);self.assertEqual([t['rowId'] for t in words[0]['targets']],['r0','r1'])

    def test_exact_receptive_field_padding_and_first_last_clipping(self):
        self.assertEqual(context.convolution_geometry(self.mapping),(320,400))
        self.assertEqual(context.crop_samples([10,12],16000),[1600,5520])
        self.assertEqual(context.crop_samples([0,1],16000),[0,2000])
        self.assertEqual(context.crop_samples([47,49],16000),[13440,16000])
        with self.assertRaises(context.CropAlignmentFailure):context.crop_samples([49,50],16000)
        with self.assertRaisesRegex(ValueError,'fixed crop'):context.crop_samples([0,1],16000,padding=3200)
        with self.assertRaisesRegex(ValueError,'interval type'):context.crop_samples([0.,1.],16000)

    def test_span_includes_internal_blanks_and_failed_geometry_retains_word(self):
        clip,score,cohort=word_fixture();words=context.word_inventory(clip,score,cohort)
        states=[{'intervalFrames':x} for x in ([1,2],[3,4],[6,7],[9,10])]
        with patch.object(context,'occupancy',return_value=(states,{})):
            result=context.declare_geometry(clip,words,None,self.mapping)
        self.assertEqual([r['sourceWordOccupancyFrames'] for r in result],[[1,4],[6,10]])
        self.assertEqual(result[0]['cropSampleRange'],[0,2960])
        with patch.object(context,'occupancy',side_effect=context.CropAlignmentFailure('no path')):
            failed=context.declare_geometry(clip,words,None,self.mapping)
        self.assertEqual(len(failed),2);self.assertTrue(all(r['status']=='failed' for r in failed))
        with patch.object(context,'occupancy',side_effect=ValueError('source changed')):
            with self.assertRaisesRegex(ValueError,'source changed'):context.declare_geometry(clip,words,None,self.mapping)

    def test_repeated_phone_path_requires_extra_frame_and_invalid_posteriors_abort(self):
        values=np.full((4,392),-np.log(392),np.float32)
        with self.assertRaisesRegex(context.CropAlignmentFailure,'cannot fit'):
            context.occupancy(values,[4,7,7,5],[0,3],self.mapping)
        values=np.full((5,392),-np.log(392),np.float32)
        estimates,_=context.occupancy(values,[4,7,7,5],[0,3],self.mapping)
        self.assertEqual(len(estimates),2)
        values[0,0]=np.nan
        with self.assertRaisesRegex(ValueError,'posterior'):context.occupancy(values,[4],[0],self.mapping)

    def test_pcm_crop_exactly_preserves_samples_and_original_bytes(self):
        x=.2*np.sin(np.arange(16000)*.07)
        source=self.root/'source.wav';payload,_=context.capture.pcm16_bytes(x);source.write_bytes(payload)
        before=source.read_bytes();sha=context.digest(source)
        entry=context.write_crop(source,sha,[1600,5520],self.root/'crop.wav')
        a=context.capture.read_rating_pcm(source,sha).numpy()[1600:5520]
        b=context.capture.read_rating_pcm(Path(entry['audioPath']),entry['audioSha256']).numpy()
        np.testing.assert_array_equal(a,b);self.assertEqual(source.read_bytes(),before)
        with self.assertRaises(FileExistsError):context.write_crop(source,sha,[1600,5520],self.root/'crop.wav')


class ContextRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.plan_path=self.root/'plan.json';self.marker=self.root/'source-pin';self.marker.write_text('fixed')
        clips,words,base_rows=[],[],[];row_index=0;word_ordinal=0
        mapping=context.read_json(context.local.RECIPE)
        for n,word_count in enumerate([4,4,3,3,3]):
            cid=f'{n+1:09d}';source=self.root/(cid+'.wav');source.write_bytes(context.capture.pcm16_bytes(np.zeros(16000))[0])
            clip={'id':cid,'speakerId':str(n),'age':8,'audioPath':str(source),'audioSha256':context.digest(source),'sampleCount':16000,
                  'canonicalPhones':[],'mappedTokenIds':[],'targets':[]}
            for w in range(word_count):
                targets=[];first=len(clip['targets'])
                for j in range(2 if word_ordinal<6 else 1):
                    t={'rowIndex':row_index,'rowId':f'r{row_index}','clipId':cid,'targetId':j,'targetPhone':'B' if j==0 else 'P',
                       'wordIndex':w,'phoneIndex':j,'canonicalIndex':len(clip['targets'])}
                    clip['targets'].append(t);targets.append(t);clip['canonicalPhones'].append(t['targetPhone']);clip['mappedTokenIds'].append(4+j)
                    base_rows.append({**t,'intervalFrames':[1,2],'estimatedPoolingWindowFrames':[0,3]});row_index+=1
                words.append({'wordId':cid+'-word-'+str(w),'clipId':cid,'wordIndex':w,'text':'word','phones':[t['targetPhone'] for t in targets],
                    'canonicalRange':[first,len(clip['targets'])],'mappedTokenIds':[4+t['targetId'] for t in targets],
                    'targets':targets,'status':'prepared','sourceWordOccupancyFrames':[1,2],'cropSampleRange':[0,4000]})
                word_ordinal+=1
            clips.append(clip)
        self.assertEqual(row_index,23);self.assertEqual(len(words),17)
        recipe=context.read_json(context.RECIPE)
        self.plan={'clips':clips,'words':words,'recipe':recipe,'recipeSha256':context.digest(context.RECIPE)}
        context.atomic_json(self.plan_path,self.plan)
        self.inputs={'marker':context.pin(self.marker),'plan':context.pin(self.plan_path)}
        previous={'recipe':{},'bindings':{}}
        for clip in clips:
            p=self.root/(clip['id']+'.f32');np.zeros((3,392),dtype='<f4').tofile(p)
            previous['bindings']['originalCTC/'+clip['id']]=context.pin(p)
        self.bound={'positions':{i:i for i in range(23)},'scalars':np.zeros((23,13),np.float32),
                    'arrays':{'target':np.zeros((23,1024),np.float32)}}
        self.original={'rows':base_rows}
        self.calls=[]
        def ctc(audio,contract,inputs,directory,node):
            self.calls.append(('full' if '/full/' in str(directory) else 'crop',audio['audioPath']))
            directory.mkdir(parents=True)
            return np.zeros((3,392),np.float32),{}, {'fetchAttempts':0}
        def features(logp,hidden,clip,mapping):
            targets=[{**t,'intervalFrames':[1,2],'estimatedPoolingWindowFrames':[0,3]} for t in clip['targets']]
            return targets,np.zeros((len(targets),13),np.float32),np.zeros((len(targets),1024),np.float32),{}
        heads={k:{'predictions':{i:[.1,.2,.7] for i in range(23)}} for k in ('all-age','child-only')}
        self.enterContext(patch.object(context,'validate_plan',return_value=(previous,self.bound,self.original,{},mapping,self.root,self.inputs)))
        self.enterContext(patch.object(context,'ctc_forward',side_effect=ctc))
        self.enterContext(patch.object(context,'features_for',side_effect=features))
        self.enterContext(patch.object(context.extraction,'PhoneticEncoder',return_value=lambda _:None))
        self.enterContext(patch.object(context.capture,'load_heads',return_value=heads))
        self.enterContext(patch.object(context.capture,'probabilities',side_effect=lambda head,v,t:np.tile([.1,.2,.7],(len(t),1))))

    def run_case(self):return context.run(self.plan_path,context.digest(self.plan_path))

    def test_all_five_original_gates_precede_crops_and_exact_full_denominator(self):
        result=self.run_case()
        self.assertEqual([kind for kind,_ in self.calls],['full']*5+['crop']*17)
        self.assertEqual(result['successfulWords'],17);self.assertEqual(result['successfulTargets'],23)
        report=context.read_json(Path(result['reportPath']))
        self.assertFalse(report['labelsTransferred']);self.assertEqual(report['plannedTargets'],23)
        self.assertNotIn('accuracy',report['summaryTargetWeighted'])

    def test_original_parity_failure_stops_before_any_crop(self):
        self.bound['scalars'][0,0]=1
        with self.assertRaisesRegex(ValueError,'parity failed'):self.run_case()
        self.assertTrue(all(k=='full' for k,_ in self.calls))
        self.assertFalse((self.root/'diagnostic/report.json').exists());self.assertTrue((self.root/'diagnostic/failure.json').exists())

    def test_expected_crop_failure_retained_runtime_error_aborts(self):
        original=context.features_for.side_effect
        def fail_crop(logp,hidden,clip,mapping):
            if '-word-' in clip['id']:raise context.CropAlignmentFailure('unalignable word')
            return original(logp,hidden,clip,mapping)
        with patch.object(context,'features_for',side_effect=fail_crop):result=self.run_case()
        report=context.read_json(Path(result['reportPath']))
        self.assertEqual(report['failedWords'],17);self.assertEqual(report['failedTargets'],23);self.assertEqual(report['summaryTargetWeighted'],{})

    def test_runtime_or_late_prior_crop_mutation_prevents_publication(self):
        real=context.save_feature_array;calls=0;first=None
        def mutate(path,values):
            nonlocal calls,first
            p=real(path,values);calls+=1
            if first is None and '/words/' in str(path):first=path
            if calls==22:first.write_bytes(b'changed prior feature')
            return p
        with patch.object(context,'save_feature_array',side_effect=mutate),self.assertRaisesRegex(ValueError,'changed'):
            self.run_case()
        self.assertFalse((self.root/'diagnostic/report.json').exists())

    def test_model_runtime_failure_cannot_be_counted_as_alignment_failure(self):
        with patch.object(context.extraction,'PhoneticEncoder',side_effect=RuntimeError('model failed')):
            with self.assertRaisesRegex(RuntimeError,'model failed'):self.run_case()
        self.assertFalse((self.root/'diagnostic/report.json').exists())


if __name__=='__main__':unittest.main()
