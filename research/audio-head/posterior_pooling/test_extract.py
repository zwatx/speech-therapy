"""Synthetic-only identities, posterior arrays, encoder stubs and preflight IO."""
import copy
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from multiphone_phonetic_features import pooled_vectors,file_binding
from posterior_pooling import extract as e


def recipe():
    return dict(convKernel=[1],convStride=[1],poolingContextFrames=2,stressOverrides={},
                consonants={'T':'t'},vowels={'AA':'a'})


def vocabulary():
    return dict({'<pad>':0,'<s>':1,'</s>':2,'<unk>':3,'a':4,'t':5},
                **{f'other{i}':i for i in range(6,392)})


def identity_fixture():
    clip=dict(id='clip',audioPath='synthetic.wav',audioSha256='a'*64,sampleCount=5,frames=5)
    row=dict(id='clip:0:1',clipId='clip',targetId='T',rowIndex=0,outputIndex=0,
             intervalFrames=[1,2],estimatedPoolingWindowFrames=[0,4])
    full=dict(clip,rows=[dict(row,canonicalIndex=1,wordIndex=0,phoneIndex=1,targetPhone='T')])
    manifest=dict(clips=[dict(clip,rows=[row])],rowIds=[row['id']],rowIndices=[0])
    scalar=dict(**{k:clip[k] for k in ('id','audioPath','audioSha256','sampleCount')},speakerId='child',age=6,
                canonicalPhones=['AA','T'],words=[{'text':'CAT','phones':['AA','T']}])
    binding=dict(path='ctc.f32',sha256='b'*64)
    metadata=dict(frames=5,vocabularySize=392,audioSha256='a'*64,sampleCount=5)
    return manifest,[full],[scalar],{'clip':binding},{'clip':metadata},recipe(),vocabulary()


def pool_fixture():
    clip=e.join_clips(*identity_fixture())[0]
    hidden=np.arange(5*1024,dtype=np.float32).reshape(5,1024)/100
    logits=np.full((5,392),-30.,dtype=np.float64)
    logits[:,0]=0; logits[0,4]=3; logits[2,5]=2; logits[4,5]=1
    logp=(logits-np.logaddexp.reduce(logits,axis=1)[:,None]).astype('<f4')
    return clip,hidden,logp


class ExtractTests(unittest.TestCase):
    def test_full_prompt_vowels_and_exact_identity_geometry_join(self):
        clips=e.join_clips(*identity_fixture()); row=clips[0]['rows'][0]
        self.assertEqual(clips[0]['fullTokens'],[4,5]); self.assertEqual(row['canonicalIndex'],1)
        self.assertEqual(row['tokenId'],5); self.assertNotIn('ratings',repr(clips))
        self.assertEqual(clips[0]['posterior']['sha256'],'b'*64)
        for change in ('drop','duplicate','frame','canonical','window','vocabulary','mapping','audiohash'):
            args=copy.deepcopy(identity_fixture())
            if change=='drop': args[1].clear()
            if change=='duplicate': args[0]['clips'].append(args[0]['clips'][0])
            if change=='frame': args[4]['clip']['frames']=6
            if change=='canonical': args[1][0]['rows'][0]['canonicalIndex']=0
            if change=='window': args[0]['clips'][0]['rows'][0]['estimatedPoolingWindowFrames']=[1,4]
            if change=='vocabulary': args[6]['t']=4
            if change=='mapping': args[5]['consonants']['T']='not in vocabulary'
            if change=='audiohash': args[4]['clip']['audioSha256']='c'*64
            with self.subTest(change=change),self.assertRaises(ValueError): e.join_clips(*args)

    def test_fixed_lower_median_fit_rule_whole_utterance_purge_and_hardware_role(self):
        base=e.join_clips(*identity_fixture())[0]; clips=[]
        # Pick one synthetic word that is not in blocked group0, without scores.
        allowed=next(w for w in ('CAT','DOG','HAT','TOY','BOOK') if e.word_group(w)!=0)
        blocked=next(w for w in ('CAT','DOG','HAT','TOY','BOOK','FISH','MAN','CUP','RED') if e.word_group(w)==0)
        for i in range(5):
            clip=copy.deepcopy(base); clip['id']=f'clip{i}'; clip['sampleCount']=10+i
            clip['rows'][0]['rowIndex']=i; clip['words'][0]['text']=allowed; clips.append(clip)
        selected=e.select_preflight(clips,[0,1,2,3])
        self.assertEqual(selected['fitClipIds'],['clip0','clip1','clip3'])
        self.assertEqual(selected['selectedClipIds'],['clip0','clip1','clip3','clip4'])
        self.assertEqual(selected['roles']['clip4'],['global-longest-hardware-only'])
        self.assertEqual(selected['repeatClipIds'],['clip0','clip4'])
        bad=copy.deepcopy(clips); bad[1]['words'].append({'text':blocked,'phones':['AA']})
        with self.assertRaisesRegex(ValueError,'purging'): e.select_preflight(bad,[0,1,2,3])
        bad=copy.deepcopy(clips); bad[0]['rows'].append(dict(bad[0]['rows'][0],rowIndex=10))
        with self.assertRaisesRegex(ValueError,'purging'): e.select_preflight(bad,[0,1,2,3])
        with self.assertRaises(ValueError): e.select_preflight(clips,[0,1,2,99])

    def test_original_hard_mean_is_separate_from_posterior_weighted_pool(self):
        clip,hidden,logp=pool_fixture(); values,audit=e.pool_clip(hidden,logp,clip)
        np.testing.assert_array_equal(values['hard'],pooled_vectors(hidden,clip['rows'],5)[0])
        self.assertFalse(np.array_equal(values['candidate'],values['hard']))
        self.assertEqual(audit['rows'][0]['canonicalIndex'],1)
        self.assertAlmostEqual(audit['rows'][0]['qMass'],1)
        self.assertGreaterEqual(audit['rows'][0]['expectedOccupancy'],1-1e-10)
        # Weights change when quantized posterior inputs change; the acoustic
        # historical mean does not depend on the alignment model probabilities.
        alternate=np.log(np.full((5,392),1/392,dtype=np.float64)).astype('<f4')
        other,_=e.pool_clip(hidden,alternate,clip)
        np.testing.assert_array_equal(values['hard'],other['hard'])
        self.assertFalse(np.array_equal(values['candidate'],other['candidate']))
        for bad in (logp[:4],logp.astype(np.float64),np.full_like(logp,float('nan')),np.zeros_like(logp)):
            with self.assertRaises(ValueError): e.pool_clip(hidden,bad,clip)
        bad=copy.deepcopy(clip); bad['rows'][0]['tokenId']=4
        with self.assertRaises(ValueError): e.pool_clip(hidden,logp,bad)

    def test_payload_hash_and_frame_size_guard_before_encoder_or_audio_reader(self):
        clip,hidden,logp=pool_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); audio=root/'audio.wav'; audio.write_bytes(b'synthetic')
            posterior=root/'ctc.f32'; logp.tofile(posterior)
            clip['audioPath']=str(audio); clip['audioSha256']=e.digest(audio)
            clip['posterior']=file_binding(posterior)
            encoder=lambda samples: hidden
            with patch.object(e,'read_rating_pcm',side_effect=AssertionError('Audio reader closed')) as reader:
                posterior.write_bytes(b'bad')
                with self.assertRaisesRegex(ValueError,'hash'): e.extract_clip(encoder,clip)
                reader.assert_not_called()
                clip['posterior']=file_binding(posterior)
                with self.assertRaisesRegex(ValueError,'byte size'): e.extract_clip(encoder,clip)
                reader.assert_not_called()

    def test_distinct_passing_reference_paths_same_content_and_exact_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            original=root/'reference.npy'; passing=root/'features-final.npy'
            np.save(original,np.arange(4,dtype=np.float32)); passing.write_bytes(original.read_bytes())
            plan=dict(artifacts=dict(reference=file_binding(original)))
            report=dict(complete=True,cachedFinalExactAllRows=True,matrices=dict(final=file_binding(passing)))
            self.assertNotEqual(plan['artifacts']['reference']['path'],report['matrices']['final']['path'])
            self.assertEqual(e.passing_reference(plan,report),file_binding(passing))
            passing.write_bytes(b'changed')
            report['matrices']['final']=file_binding(passing)
            with self.assertRaisesRegex(ValueError,'content SHA'): e.passing_reference(plan,report)
        # Replay must compare both arrays, rather than trusting matching declarations.
        pins={key:dict(path=key,sha256='a'*64) for key in
              ('reference','passingFinal','scalars','rowIndices','parentTarget','parentScalars','manifest')}
        def array(path,shape,dtype):
            if path=='rowIndices': return np.arange(9891,dtype=np.int64)
            return np.broadcast_to(np.array(1 if path=='passingFinal' else 0,dtype=dtype),shape)
        with patch.object(e,'guard'),patch.object(e.base,'array',side_effect=array),patch.object(e.np,'load') as parent:
            with self.assertRaises(ValueError): e.checked_references(dict(inputs=pins))
            parent.assert_not_called()

    def test_normalization_before_audio_and_consumed_hashes_after_forward(self):
        clip,hidden,logp=pool_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); audio=root/'audio.wav'; audio.write_bytes(b'synthetic')
            posterior=root/'ctc.f32'; np.zeros_like(logp).tofile(posterior)
            clip.update(audioPath=str(audio),audioSha256=e.digest(audio),posterior=file_binding(posterior))
            with patch.object(e,'read_rating_pcm') as reader:
                with self.assertRaises(ValueError): e.extract_clip(lambda samples:hidden,clip)
                reader.assert_not_called()
            logp.tofile(posterior); clip['posterior']=file_binding(posterior)
            class Samples:
                def numel(self): return 5
            def mutate(samples):
                audio.write_bytes(b'changed during forward'); return hidden
            with patch.object(e,'read_rating_pcm',return_value=Samples()):
                with self.assertRaisesRegex(ValueError,'hash'): e.extract_clip(mutate,clip)

    def runner_fixture(self,root):
        root=root.resolve(); outputs=root/'outputs'; outputs.mkdir(); plan_path=outputs/'plan.json'
        clip,hidden,logp=pool_fixture(); values,audit=e.pool_clip(hidden,logp,clip)
        plan=dict(clips=[clip],probes=dict(repeatClipIds=['clip'],selectedClipIds=['clip'],roles={'clip':['fit-duration-probe']}),runtime={},model={})
        e.write_new(plan_path,plan); pin=file_binding(plan_path)
        review=outputs/'review.json'; e.write_new(review,dict(planSha256=pin['sha256'],verdict='clear',blockingFindings=[],independent=True,reviewer='synthetic'))
        @contextmanager
        def loader(plan): yield object()
        return pin,review,plan,values,audit,loader,outputs/'run'

    def test_run_preserves_failure_parity_and_repeat_no_hidden_resume(self):
        for failure in ('parity','repeat'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                pin,review,plan,values,audit,loader,out=self.runner_fixture(Path(directory)); calls=[0]
                def compute(encoder,clip):
                    calls[0]+=1; result={k:v.copy() for k,v in values.items()}
                    if failure=='repeat' and calls[0]==2: result['candidate'][0,0]+=1
                    return result,copy.deepcopy(audit)
                reference=values['hard'].copy()
                if failure=='parity': reference[0,0]+=1
                with patch.object(e,'HERE',Path(directory).resolve()),patch.object(e,'checked_plan',return_value=plan), \
                     patch.object(e,'environment',return_value={}),patch.object(e,'checked_references',return_value=reference), \
                     patch.object(e,'load_encoder',side_effect=loader),patch.object(e,'guard_clip'),patch.object(e,'extract_clip',side_effect=compute):
                    with self.assertRaises(ValueError): e.run(pin['path'],pin['sha256'],review,out)
                    self.assertTrue((out/'failure.json').exists()); self.assertFalse((out/'report.json').exists())
                    with self.assertRaisesRegex(ValueError,'no implicit restart'): e.run(pin['path'],pin['sha256'],review,out)
                self.assertEqual(calls[0],1 if failure=='parity' else 2)
                if failure=='repeat': self.assertTrue((out/'clip.npz').exists())

    def test_review_source_and_runtime_barriers_precede_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            pin,review,plan,values,audit,loader,out=self.runner_fixture(Path(directory))
            review.write_text('{}')
            with patch.object(e,'checked_plan') as checked,patch.object(e,'load_encoder') as encoder:
                with self.assertRaises(ValueError): e.run(pin['path'],pin['sha256'],review,out)
                checked.assert_not_called(); encoder.assert_not_called()
            self.assertFalse(out.exists())
        with tempfile.TemporaryDirectory() as directory:
            pin,review,plan,*_=self.runner_fixture(Path(directory))
            with patch.object(e,'HERE',Path(directory).resolve()),patch.object(e,'declaration',return_value=dict(plan,drift=True)):
                with self.assertRaisesRegex(ValueError,'changed'): e.checked_plan(Path(pin['path']),pin['sha256'])
        with patch.object(e.base,'environment',return_value={'platform':'x86','python':'3.13.14'}):
            with self.assertRaisesRegex(ValueError,'platform'): e.environment({'platform':'arm64','python':'3.13.14'})

    def test_synthetic_success_exclusive_artifacts_and_bit_exact_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            pin,review,plan,values,audit,loader,out=self.runner_fixture(Path(directory))
            with patch.object(e,'HERE',Path(directory).resolve()),patch.object(e,'checked_plan',return_value=plan), \
                 patch.object(e,'environment',return_value={}),patch.object(e,'checked_references',return_value=values['hard']), \
                 patch.object(e,'load_encoder',side_effect=loader),patch.object(e,'guard_clip'),patch.object(e,'extract_clip',return_value=(values,audit)) as forward:
                report=e.read_json(Path(e.run(pin['path'],pin['sha256'],review,out)['path']))
            self.assertEqual(forward.call_count,2)
            self.assertTrue(report['cachedHardExact'] and report['repeatsExact'])
            self.assertFalse(report['labelsUsedForExtraction'] or report['trainingPerformed'] or report['clinicalUseEligible'])
            with np.load(out/'clip.npz',allow_pickle=False) as arrays:
                self.assertEqual(set(arrays.files),{'candidate','hard'})
            self.assertTrue((out/'clip-repeat.npz').exists())


if __name__=='__main__': unittest.main()
