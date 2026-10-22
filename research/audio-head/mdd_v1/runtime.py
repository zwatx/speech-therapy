"""Shared offline model loading and 16 kHz single-clip preprocessing."""
import os
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

from pathlib import Path
import math
import wave
import numpy as np
from scipy.signal import resample_poly
import torch
from transformers import Wav2Vec2FeatureExtractor
from .manifest import ROOT

CACHE = ROOT/'outputs/model-cache'
ESPEAK_MODEL = 'facebook/wav2vec2-lv-60-espeak-cv-ft'
WAVLM_MODEL = 'microsoft/wavlm-base-plus'


def snapshot(model_id):
    root = CACHE/('models--'+model_id.replace('/', '--'))
    revision = {ESPEAK_MODEL: 'ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4',
                WAVLM_MODEL: '4c66d4806a428f2e922ccfa1a962776e232d487b'}[model_id]
    path = root/'snapshots'/revision
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path


def device_setup(seed=17):
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    return torch.device('mps' if torch.backends.mps.is_available() else 'cpu')


def read_audio(path):
    with wave.open(str(path), 'rb') as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1 or wav.getcomptype() != 'NONE':
            raise ValueError(f'Expected mono PCM16: {path}')
        rate = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(np.float32)/32768
    if rate != 16000:
        gcd = math.gcd(rate, 16000)
        samples = resample_poly(samples, 16000//gcd, rate//gcd).astype(np.float32)
    if samples.size < 400 or not np.isfinite(samples).all():
        raise ValueError(f'Invalid waveform: {path}')
    return samples


def extractor(model_id):
    return Wav2Vec2FeatureExtractor.from_pretrained(str(snapshot(model_id)), local_files_only=True)


def waveform(row, processor, device):
    # No padding: preserves WavLM group norm behavior and avoids length artifacts.
    result = processor(read_audio(row['audio']), sampling_rate=16000, return_tensors='pt')
    return {k: v.to(device) for k, v in result.items()}


def collapse(ids, id_to_phone, blank=0):
    result, previous = [], None
    for value in ids:
        if value != previous and value != blank:
            result.append(id_to_phone[value])
        previous = value
    return result
