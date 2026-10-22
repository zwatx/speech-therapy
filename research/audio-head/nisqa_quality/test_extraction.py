"""Synthetic model/input and mocked offline artifacts; never load real weights."""
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

from nisqa_ingest.test_waveform_audit import chunk, fmt, wave
from nisqa_quality import audio_features as a, extraction as e


class Processor:
    do_normalize=False
    return_attention_mask=True
    sampling_rate=16000
    feature_size=1

    def __init__(self): self.calls=[]; self.mutate=lambda inputs: inputs
    def __call__(self,samples,**kwargs):
        self.calls.append(kwargs)
        values=torch.from_numpy(samples.copy()).reshape(1,-1)
        return self.mutate(dict(input_values=values,attention_mask=torch.ones_like(values,dtype=torch.int32)))


class Model(torch.nn.Module):
    def __init__(self):
        super().__init__(); self.weight=torch.nn.Parameter(torch.ones(1),requires_grad=False)
        self.config=SimpleNamespace(hidden_size=768,num_hidden_layers=12,_attn_implementation='eager')
        self.hidden=torch.stack([torch.full((768,),x) for x in (1.,3.,5.)]).reshape(1,3,768)
        self.calls=0; self.eval()
    def _get_feat_extract_output_lengths(self,n): return 3
    def _get_feature_vector_attention_mask(self,n,mask): return torch.ones((1,n),dtype=torch.bool,device=mask.device)
    def forward(self,**inputs):
        self.calls+=1
        assert not torch.is_grad_enabled()
        assert tuple(inputs['input_values'].shape)==tuple(inputs['attention_mask'].shape)
        return SimpleNamespace(last_hidden_state=self.hidden)


def identity():
    return dict(modelId=e.POLICY['modelId'],revision=e.POLICY['revision'],
        artifactSha256=dict(e.POLICY['artifactSha256']),artifactBytes=dict(e.POLICY['artifactBytes']),
        policy=copy.deepcopy(e.POLICY),runtime=e.configure_runtime('cpu'))


def prepared():
    values=np.array([-.25,0,.5,0.125],dtype='<f4')
    return dict(samples=values,scalars=np.arange(6,dtype='<f8'),
                metadata=dict(derived=dict(modelInputFloat32Sha256=a._sha(values,'<f4')),
                              originalAudit={'synthetic':True}))


class ExtractionTests(unittest.TestCase):
    def test_hand_vectors_and_raw_metadata_preserved(self):
        p=Processor(); m=Model(); inputs=prepared()
        result=e.extract_prepared(inputs,m,p,identity())
        np.testing.assert_array_equal(result['features'][:768],np.full(768,3,dtype='f4'))
        np.testing.assert_allclose(result['features'][768:],np.sqrt(8/3),rtol=1e-7)
        np.testing.assert_array_equal(result['scalars'],inputs['scalars'])
        self.assertEqual(result['metadata']['waveform'],inputs['metadata'])
        self.assertEqual(result['metadata']['validFrames'],3)
        self.assertEqual(result['metadata']['hiddenShape'],[1,3,768])
        self.assertEqual(p.calls,[dict(sampling_rate=16000,return_tensors='pt',padding=False,return_attention_mask=True)])
        self.assertEqual(result['metadata']['featuresFloat32Sha256'],hashlib.sha256(result['features'].tobytes()).hexdigest())
        self.assertFalse(result['metadata']['targetsAccessed']); json.dumps(result['metadata'],allow_nan=False)

    def test_real_in_memory_processor_exact_float32_input_and_int32_mask(self):
        from transformers import Wav2Vec2FeatureExtractor
        processor=Wav2Vec2FeatureExtractor(feature_size=1,sampling_rate=16000,padding_value=0.0,
            do_normalize=False,return_attention_mask=True)
        inputs=prepared()
        inputs['samples'][1]=-0.0
        inputs['metadata']['derived']['modelInputFloat32Sha256']=a._sha(inputs['samples'],'<f4')
        actual=processor(inputs['samples'],sampling_rate=16000,return_tensors='pt',padding=False,
                         return_attention_mask=True)
        self.assertEqual(set(actual),{'input_values','attention_mask'})
        self.assertEqual(tuple(actual['input_values'].shape),(1,4))
        self.assertEqual(actual['attention_mask'].dtype,torch.int32)
        self.assertTrue(bool((actual['attention_mask']==1).all()))
        self.assertEqual(actual['input_values'].numpy().tobytes(),inputs['samples'].reshape(1,-1).tobytes())
        model=Model(); result=e.extract_prepared(inputs,model,processor,identity())
        self.assertEqual(model.calls,1)
        self.assertEqual(result['metadata']['attentionMaskDtype'],'torch.int32')
        canonical=np.ones((1,4),dtype='<i8')
        self.assertEqual(result['metadata']['attentionMaskInt64Sha256'],hashlib.sha256(canonical.tobytes()).hexdigest())

    def test_tiny_random_wavlm_real_frame_lengths_masks_and_eager_forward(self):
        from transformers import WavLMConfig,WavLMModel,Wav2Vec2FeatureExtractor
        e.configure_runtime('cpu')
        config=WavLMConfig(hidden_size=8,num_hidden_layers=1,num_attention_heads=2,intermediate_size=16,
            conv_dim=(4,4),conv_kernel=(3,3),conv_stride=(2,2),num_conv_pos_embeddings=4,
            num_conv_pos_embedding_groups=2,mask_time_prob=0.0,mask_feature_prob=0.0)
        config._attn_implementation='eager'
        with torch.random.fork_rng():
            torch.manual_seed(123); model=WavLMModel(config).requires_grad_(False).eval()
        processor=Wav2Vec2FeatureExtractor(feature_size=1,sampling_rate=16000,padding_value=0.0,
            do_normalize=False,return_attention_mask=True)
        samples=np.linspace(-.25,.5,35,dtype='<f4')
        inputs=processor(samples,sampling_rate=16000,return_tensors='pt',padding=False)
        expected=int(model._get_feat_extract_output_lengths(len(samples)))
        self.assertEqual(expected,8)
        mask=model._get_feature_vector_attention_mask(expected,inputs['attention_mask'])
        self.assertEqual(tuple(mask.shape),(1,expected)); self.assertTrue(bool(mask.all()))
        with torch.inference_mode(): output=model(**inputs).last_hidden_state
        self.assertEqual(model.config._attn_implementation,'eager')
        self.assertEqual(tuple(output.shape),(1,expected,8))
        self.assertEqual(output.dtype,torch.float32); self.assertTrue(bool(torch.isfinite(output).all()))

    def test_padding_mask_and_normalization_reject_before_forward(self):
        mutations=[lambda d:{**d,'attention_mask':torch.zeros_like(d['attention_mask'])},
                   lambda d:{**d,'attention_mask':d['attention_mask'].float()},
                   lambda d:{**d,'attention_mask':d['attention_mask'].long()},
                   lambda d:{**d,'input_values':torch.cat([d['input_values'],torch.zeros(1,1)],dim=1)},
                   lambda d:{**d,'input_values':d['input_values']*2},
                   lambda d:{**d,'input_values':torch.where(d['input_values']==0,-d['input_values'],d['input_values'])},
                   lambda d:{**d,'extra':torch.ones(1)}]
        for mutation in mutations:
            m=Model(); p=Processor(); p.mutate=mutation
            with self.assertRaises(ValueError): e.extract_prepared(prepared(),m,p,identity())
            self.assertEqual(m.calls,0)
        for name,value in [('do_normalize',True),('return_attention_mask',False),('sampling_rate',8000),('feature_size',2)]:
            p=Processor(); setattr(p,name,value)
            with self.assertRaisesRegex(ValueError,'processor'): e.extract_prepared(prepared(),Model(),p,identity())

    def test_frames_hidden_shape_finiteness_and_dtype_reject(self):
        for hidden in [torch.zeros(1,2,768),torch.zeros(1,3,767),torch.zeros(1,3,768,dtype=torch.float64),
                       torch.full((1,3,768),float('nan'))]:
            m=Model(); m.hidden=hidden
            with self.assertRaisesRegex(ValueError,'hidden'): e.extract_prepared(prepared(),m,Processor(),identity())
        m=Model(); m._get_feat_extract_output_lengths=lambda n:0
        with self.assertRaisesRegex(ValueError,'no valid'): e.extract_prepared(prepared(),m,Processor(),identity())
        self.assertEqual(m.calls,0)
        m=Model(); m._get_feature_vector_attention_mask=lambda n,mask:torch.zeros((1,n),dtype=torch.bool)
        with self.assertRaisesRegex(ValueError,'frame mask'): e.extract_prepared(prepared(),m,Processor(),identity())
        self.assertEqual(m.calls,0)

    def test_model_input_and_identity_guards(self):
        bad=prepared(); bad['samples'][0]=float('inf')
        with self.assertRaisesRegex(ValueError,'prepared'): e.extract_prepared(bad,Model(),Processor(),identity())
        bad=prepared(); bad['metadata']['derived']['modelInputFloat32Sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'hash'): e.extract_prepared(bad,Model(),Processor(),identity())
        m=Model().double()
        with self.assertRaisesRegex(ValueError,'dtype'): e.extract_prepared(prepared(),m,Processor(),identity())
        m=Model().train()
        with self.assertRaisesRegex(ValueError,'configuration'): e.extract_prepared(prepared(),m,Processor(),identity())
        bad=identity(); bad['revision']='other'
        with self.assertRaisesRegex(ValueError,'identity'): e.extract_prepared(prepared(),Model(),Processor(),bad)
        with patch.object(e.torch,'__version__','2.9.0'):
            with self.assertRaisesRegex(ValueError,'runtime'): e.configure_runtime('cpu')
        with patch.object(e.torch,'__version__','2.8.0+cu128'):
            self.assertEqual(e.configure_runtime('cpu')['torch'],'2.8.0+cu128')

    def test_synthetic_stereo_clip_keeps_original_scalar_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'synthetic.wav'
            samples=np.array([[16384,-16384],[0,0],[32767,-32768]],dtype='<i2')
            path.write_bytes(wave(chunk(b'fmt ',fmt(channels=2,rate=16000)),chunk(b'data',samples.tobytes())))
            result=e.extract_clip(path,Model(),Processor(),identity())
            self.assertGreater(result['scalars'][0],.5)
            self.assertEqual(result['metadata']['waveform']['originalAudit']['decoded']['shape'],[3,2])
            self.assertEqual(result['metadata']['validInputSamples'],3)

    def test_offline_three_hashes_checked_before_any_model_load(self):
        with tempfile.TemporaryDirectory() as directory:
            cache=Path(directory).resolve()/'cache'; repo=cache/'models--microsoft--wavlm-base-plus'
            snapshot=repo/'snapshots'/e.WAVLM_REVISION; snapshot.mkdir(parents=True)
            blobs=repo/'blobs'; blobs.mkdir()
            names=list(e.POLICY['artifactSha256'])
            for name in names:
                blob=blobs/hashlib.sha256(name.encode()).hexdigest(); blob.write_bytes(name.encode())
                (snapshot/name).symlink_to(blob)
            policy=copy.deepcopy(e.POLICY)
            policy['artifactSha256']={name:hashlib.sha256(name.encode()).hexdigest() for name in names}
            policy['artifactBytes']={name:len(name.encode()) for name in names}
            calls=[]
            def hub(model,name,**kwargs):
                calls.append((model,name,kwargs)); return str(snapshot/name)
            with patch.object(e,'POLICY',policy),patch('huggingface_hub.hf_hub_download',side_effect=hub), \
                 patch('transformers.WavLMModel.from_pretrained',return_value=Model()) as load, \
                 patch('transformers.Wav2Vec2FeatureExtractor.from_pretrained',return_value=Processor()) as processor:
                model,proc,meta=e.load_frozen_wavlm(cache)
                self.assertEqual(len(calls),3); self.assertEqual(load.call_count,1)
                self.assertTrue(all(c[2]['local_files_only'] is True and c[2]['revision']==e.WAVLM_REVISION for c in calls))
                self.assertEqual(load.call_args.kwargs['attn_implementation'],'eager')
                self.assertEqual(load.call_args.args,(str(snapshot),))
                self.assertEqual(processor.call_args.args,(str(snapshot),))
                self.assertEqual(processor.call_args.kwargs,{'local_files_only':True})
                self.assertEqual(meta['artifactSha256'],policy['artifactSha256'])
                for extra_name in ('adapter_config.json','pytorch_model.bin.index.json'):
                    extra=snapshot/extra_name; extra.write_text('{}')
                    load.reset_mock(); processor.reset_mock()
                    with self.assertRaisesRegex(ValueError,'Unbound files'): e.load_frozen_wavlm(cache)
                    load.assert_not_called(); processor.assert_not_called(); extra.unlink()
                # Recheck the snapshot after processor loading: an inserted
                # file must not reach the subsequent model loader either.
                extra=snapshot/'adapter_config.json'
                def inserted(*args,**kwargs):
                    extra.write_text('{}'); return Processor()
                processor.side_effect=inserted; load.reset_mock()
                with self.assertRaisesRegex(ValueError,'Unbound files'): e.load_frozen_wavlm(cache)
                load.assert_not_called(); extra.unlink(); processor.side_effect=None
                load.reset_mock(); bad_processor=Processor(); bad_processor.do_normalize=True
                processor.return_value=bad_processor
                with self.assertRaisesRegex(ValueError,'processor'): e.load_frozen_wavlm(cache)
                load.assert_not_called(); processor.return_value=Processor()
                (snapshot/names[-1]).write_bytes(b'X'*len(names[-1].encode()))
                load.reset_mock(); processor.reset_mock()
                with self.assertRaisesRegex(ValueError,'integrity'): e.load_frozen_wavlm(cache)
                load.assert_not_called(); processor.assert_not_called()

    def test_cuda_workspace_guard_precedes_any_availability_query(self):
        with patch.dict(os.environ,{'CUBLAS_WORKSPACE_CONFIG':':16:8'}), \
             patch.object(torch.cuda,'is_available') as available:
            with self.assertRaisesRegex(ValueError,'workspace'): e.configure_runtime('cuda')
            available.assert_not_called()
        with patch.dict(os.environ,{},clear=True),patch.object(torch.cuda,'is_initialized',return_value=True):
            with self.assertRaisesRegex(ValueError,'before CUDA'): e.configure_runtime('cuda')


if __name__=='__main__': unittest.main()
