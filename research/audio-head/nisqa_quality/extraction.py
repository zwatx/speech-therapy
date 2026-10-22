"""Offline pinned WavLM loading and one-clip extraction, without target inputs."""
import copy
import hashlib
import os
from pathlib import Path
import platform
import sys

import numpy as np
import scipy
import torch
import transformers

from encoders import WAVLM_MODEL_ID, WAVLM_REVISION, WAVLM_FILES, WAVLM_BYTES, WAVLM_LICENSE
from nisqa_quality import audio_features as audio

POLICY = {
    'version': 'nisqa-quality-extraction-v1', 'offlineOnly': True,
    'modelId': WAVLM_MODEL_ID, 'revision': WAVLM_REVISION,
    'artifactSha256': dict(WAVLM_FILES), 'artifactBytes': dict(WAVLM_BYTES),
    'processor': copy.deepcopy(audio.POLICY['processor']),
    'attentionMaskDtype': 'int32', 'attentionMaskHashEncoding': 'little-endian int64 C-order',
    'snapshotEntries': sorted(WAVLM_FILES),
    'width': 768, 'layers': 12, 'dtype': 'float32', 'attention': 'eager',
    'gradients': False, 'evaluationMode': True, 'oneClipPerForward': True,
    'tf32': False, 'cudnnEnabled': True, 'deterministicAlgorithms': True,
    'cublasWorkspaceConfig': ':4096:8',
    'torchThreads': 1, 'pooling': copy.deepcopy(audio.POLICY['pooling']),
    'runtime': {'torch': '2.8.0', 'transformers': '4.57.6', 'numpy': '2.2.6', 'scipy': '1.17.1'},
    'targetsAccessed': False,
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b''):
            digest.update(block)
    return digest.hexdigest()


def configure_runtime(device):
    """Configure before tensor operations; record the exact installed backend."""
    _require(device in ('cpu', 'cuda'), 'Only CPU or CUDA extraction is declared')
    _require(device != 'cuda' or not torch.cuda.is_initialized()
             or os.environ.get('CUBLAS_WORKSPACE_CONFIG') == POLICY['cublasWorkspaceConfig'],
             'cuBLAS workspace must be configured before CUDA initialization')
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', POLICY['cublasWorkspaceConfig'])
    _require(os.environ['CUBLAS_WORKSPACE_CONFIG'] == POLICY['cublasWorkspaceConfig'],
             'Declared deterministic cuBLAS workspace required before CUDA initialization')
    _require(torch.__version__ in ('2.8.0', '2.8.0+cu128')
             and transformers.__version__ == POLICY['runtime']['transformers']
             and np.__version__ == POLICY['runtime']['numpy']
             and scipy.__version__ == POLICY['runtime']['scipy'], 'Pinned extraction runtime required')
    _require(device != 'cuda' or torch.cuda.is_available(), 'Declared CUDA device unavailable')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.enabled = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    return dict(python=sys.version, platform=platform.platform(), torch=torch.__version__,
                transformers=transformers.__version__, numpy=np.__version__, scipy=scipy.__version__,
                device=device, cudaVersion=torch.version.cuda,
                cudaDeviceName=torch.cuda.get_device_name(0) if device == 'cuda' else None,
                cudnnVersion=torch.backends.cudnn.version(), cudnnEnabled=torch.backends.cudnn.enabled,
                cudnnDeterministic=torch.backends.cudnn.deterministic,
                cudnnBenchmark=torch.backends.cudnn.benchmark,
                cublasWorkspaceConfig=os.environ['CUBLAS_WORKSPACE_CONFIG'],
                float32MatmulPrecision=torch.get_float32_matmul_precision(),
                tf32Matmul=torch.backends.cuda.matmul.allow_tf32,
                tf32Cudnn=torch.backends.cudnn.allow_tf32,
                deterministicAlgorithms=torch.are_deterministic_algorithms_enabled(),
                torchThreads=torch.get_num_threads())


def _check_processor(processor):
    _require(processor.do_normalize is False and processor.return_attention_mask is True
             and processor.sampling_rate == 16000 and processor.feature_size == 1,
             'Pinned processor settings differ')


def _check_model(model, device):
    _require(model.training is False and model.config.hidden_size == 768
             and model.config.num_hidden_layers == 12
             and model.config._attn_implementation == 'eager', 'Pinned model configuration differs')
    parameters = list(model.parameters())
    _require(bool(parameters) and all(p.dtype == torch.float32 and not p.requires_grad
             and p.device.type == device for p in parameters), 'Frozen model dtype, gradients or device differ')
    _require(all(b.device.type == device and (not b.is_floating_point() or b.dtype == torch.float32)
                 for b in model.buffers()),
             'Model buffer dtype differs')


def load_frozen_wavlm(cache_dir, device='cpu'):
    """Resolve only three cached immutable assets and verify all before loading.

    The future driver binds cache/source identities. This function never enables
    hub downloads, and never accepts an alternative checkpoint or processor.
    """
    from huggingface_hub import hf_hub_download
    from transformers import Wav2Vec2FeatureExtractor, WavLMModel
    runtime = configure_runtime(device)
    paths = {}
    cache = Path(cache_dir).resolve()
    for name, sha in POLICY['artifactSha256'].items():
        path = Path(hf_hub_download(POLICY['modelId'], name, revision=POLICY['revision'],
                                   cache_dir=str(cache), local_files_only=True)).absolute()
        _require(path.name == name and path.parent.name == POLICY['revision']
                 and path.parent.parent.name == 'snapshots' and path.parent.resolve().is_relative_to(cache)
                 and path.resolve().is_relative_to(cache) and path.is_file()
                 and path.stat().st_size == POLICY['artifactBytes'][name]
                 and _sha_file(path) == sha, 'Pinned cached encoder integrity failure')
        paths[name] = path
    _require(len({p.parent.resolve() for p in paths.values()}) == 1, 'Cached encoder snapshot differs')
    snapshot = paths['config.json'].parent.resolve()
    def check_snapshot():
        _require({p.name for p in snapshot.iterdir()} == set(POLICY['snapshotEntries']),
                 'Unbound files in cached encoder snapshot')
        _require(all(path.is_file() and path.stat().st_size == POLICY['artifactBytes'][name]
                     and _sha_file(path) == POLICY['artifactSha256'][name]
                     for name, path in paths.items()), 'Pinned cached encoder changed during loading')
    check_snapshot()
    processor = Wav2Vec2FeatureExtractor.from_pretrained(str(snapshot), local_files_only=True)
    _check_processor(processor)
    check_snapshot()
    model = WavLMModel.from_pretrained(str(snapshot), local_files_only=True, use_safetensors=False,
        weights_only=True, torch_dtype=torch.float32, attn_implementation='eager')
    check_snapshot()
    model.to(device=device, dtype=torch.float32).requires_grad_(False).eval()
    _check_model(model, device)
    identity = dict(modelId=POLICY['modelId'], revision=POLICY['revision'],
        artifactSha256=dict(POLICY['artifactSha256']), artifactBytes=dict(POLICY['artifactBytes']),
        licenseEvidence=copy.deepcopy(WAVLM_LICENSE), runtime=runtime, policy=copy.deepcopy(POLICY),
        parameterDtypes=sorted({str(p.dtype) for p in model.parameters()}))
    return model, processor, identity


def extract_prepared(prepared, model, processor, identity, device='cpu'):
    """Extract one already-audited waveform; suitable for injected synthetic models."""
    runtime = configure_runtime(device)
    _check_processor(processor); _check_model(model, device)
    _require(identity['modelId'] == POLICY['modelId'] and identity['revision'] == POLICY['revision']
             and identity['artifactSha256'] == POLICY['artifactSha256']
             and identity['artifactBytes'] == POLICY['artifactBytes']
             and identity['policy'] == POLICY and identity['runtime'] == runtime,
             'Frozen encoder identity or runtime differs')
    samples, scalars = prepared['samples'], prepared['scalars']
    _require(isinstance(samples, np.ndarray) and samples.ndim == 1 and samples.size > 0
             and samples.dtype == np.dtype('<f4') and np.isfinite(samples).all(), 'Invalid prepared model input')
    _require(isinstance(scalars, np.ndarray) and scalars.shape == (6,) and scalars.dtype == np.dtype('<f8')
             and np.isfinite(scalars).all(), 'Invalid original-waveform descriptors')
    _require(prepared['metadata']['derived']['modelInputFloat32Sha256'] == audio._sha(samples, '<f4'),
             'Prepared waveform hash differs')
    inputs = processor(samples, sampling_rate=16000, return_tensors='pt', padding=False,
                       return_attention_mask=True)
    _require(set(inputs) == {'input_values', 'attention_mask'}, 'Unexpected processor tensor keys')
    values, mask = inputs['input_values'], inputs['attention_mask']
    _require(isinstance(values, torch.Tensor) and values.device.type == 'cpu'
             and not values.requires_grad
             and values.dtype == torch.float32 and tuple(values.shape) == (1, samples.size)
             and bool(torch.isfinite(values).all()) and values.numpy().tobytes(order='C') == samples.tobytes(order='C'),
             'Processor changed, padded or normalized the waveform')
    _require(isinstance(mask, torch.Tensor) and mask.device.type == 'cpu' and mask.dtype == torch.int32
             and tuple(mask.shape) == tuple(values.shape) and bool((mask == 1).all()),
             'One-clip attention mask must contain only valid samples')
    expected = model._get_feat_extract_output_lengths(samples.size)
    expected = int(expected)
    _require(expected > 0, 'Waveform has no valid encoder frames')
    frame_mask = model._get_feature_vector_attention_mask(expected, mask.to(device))
    _require(tuple(frame_mask.shape) == (1, expected) and bool(frame_mask.all()),
             'Encoder frame mask contains padding or invalid frames')
    with torch.inference_mode():
        output = model(input_values=values.to(device), attention_mask=mask.to(device)).last_hidden_state
    _require(isinstance(output, torch.Tensor) and output.dtype == torch.float32
             and output.device.type == device and tuple(output.shape) == (1, expected, 768)
             and bool(torch.isfinite(output).all()), 'Invalid final hidden states or valid-frame count')
    hidden = output[0].detach().cpu().contiguous().numpy()
    features = audio.pool_hidden(hidden)
    metadata = dict(waveform=copy.deepcopy(prepared['metadata']), model=copy.deepcopy(identity),
        runtime=runtime, inputShape=list(values.shape), attentionMaskShape=list(mask.shape),
        validInputSamples=int(samples.size), expectedFrames=expected, validFrames=expected,
        hiddenShape=list(output.shape), hiddenDtype=str(output.dtype), pooledDtype=str(features.dtype),
        processorDoNormalize=False, padding=False, oneClipPerForward=True,
        attentionMaskDtype=str(mask.dtype), attentionMaskHashEncoding=POLICY['attentionMaskHashEncoding'],
        processorInputFloat32Sha256=audio._sha(values.numpy(), '<f4'),
        attentionMaskInt64Sha256=audio._sha(mask.numpy(), '<i8'),
        hiddenFloat32Sha256=audio._sha(hidden, '<f4'), featuresFloat32Sha256=audio._sha(features, '<f4'),
        rawScalarsFloat64Sha256=audio._sha(scalars, '<f8'), targetsAccessed=False)
    return dict(features=features, scalars=scalars.copy(), metadata=metadata)


def extract_clip(path, model, processor, identity, device='cpu'):
    """Audit/prepare one original clip with the unchanged audio-feature recipe."""
    return extract_prepared(audio.prepare_audio(path), model, processor, identity, device=device)
