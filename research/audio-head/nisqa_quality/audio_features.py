"""Pure, pinned original-waveform features and WavLM input preparation."""
import hashlib
import math
from pathlib import Path

import numpy as np
import scipy
from scipy.signal import resample_poly

from nisqa_ingest.waveform_audit import audit_wav

ACCEPTED_RATES = (8000, 16000, 22050, 24000, 32000, 44100, 48000, 96000)
SCALAR_NAMES = ('RMS', 'peak', 'zeroFraction', 'absLe1eMinus4Fraction',
                'digitalRailFraction', 'duration')
POLICY = {
    'version': 'nisqa-quality-audio-v1', 'acceptedSampleRates': list(ACCEPTED_RATES),
    'decoder': 'frozen nisqa_ingest.waveform_audit; original decoded SHA256 must match',
    'rawChannelScope': 'all original channels, all original frames',
    'rawScalarOrder': list(SCALAR_NAMES),
    'digitalRailFraction': 'PCM valid-bit rails, or IEEE float absolute amplitude >=1; digital diagnostic only',
    'downmix': 'arithmetic mean across all channels, float64',
    'resample': {'library': 'scipy', 'version': '1.17.1', 'function': 'signal.resample_poly',
                 'targetSampleRate': 16000, 'ratio': 'gcd-reduced up/down',
                 'window': ['kaiser', 5.0], 'padtype': 'constant', 'cval': 0,
                 'outputLength': 'ceil(original mono frames * 16000 / original rate)',
                 'dtype': 'float64 then little-endian float32',
                 '16000Hz': 'copy and float32 cast, no interpolation'},
    'pooling': {'input': 'finite float32 valid frames x 768, no padded frames',
                'output': 'mean768 then populationStd768; float64 accumulation then float32',
                'ddof': 0, 'layer': 'final hidden only'},
    'processor': {'do_normalize': False, 'return_attention_mask': True,
                  'sampling_rate': 16000, 'padding': False, 'oneClipPerForward': True},
    'encoder': {'modelId': 'microsoft/wavlm-base-plus',
                'revision': '4c66d4806a428f2e922ccfa1a962776e232d487b',
                'artifactSha256': {
                    'config.json': 'fea6df1c2700a3954fc07e70588aecc9055eeb28db2ff57151a2db0d19180ed4',
                    'preprocessor_config.json': '99272fe8ccfab114b68b478681ea47ee3a1ce62bb788cb92dd6e4f69fb1f1da2',
                    'pytorch_model.bin': '3bb273a6ace99408b50cfc81afdbb7ef2de02da2eab0234e18db608ce692fe51'},
                'evaluationMode': True, 'gradients': False, 'width': 768},
    'gainNormalization': False, 'clipping': False, 'trimming': False,
    'outputDependentExclusion': False,
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(array, dtype):
    return hashlib.sha256(np.ascontiguousarray(array, dtype=dtype).tobytes(order='C')).hexdigest()


def decoded_audio(path):
    """Return original frames x channels <f8 samples and the unchanged audit.

    RIFF validation remains owned by the frozen auditor. Decode its identified
    payload, then verify both original bytes and decoded bytes against its hashes.
    """
    audit = audit_wav(path)
    with Path(path).open('rb') as stream:
        raw = stream.read(audit['input']['sizeBytes'] + 1)
    _require(len(raw) == audit['input']['sizeBytes']
             and hashlib.sha256(raw).hexdigest() == audit['input']['sha256'],
             'Original waveform changed after audit')
    fmt = audit['format']
    start = fmt['dataOffset']
    payload = memoryview(raw)[start:start + fmt['dataBytes']]
    bits = fmt['bitsPerSample']
    if fmt['encoding'] == 'PCM':
        if bits == 8:
            integers = np.frombuffer(payload, dtype=np.uint8).astype(np.int64) - 128
        elif bits == 24:
            octets = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 3).astype(np.int64)
            integers = octets[:, 0] | (octets[:, 1] << 8) | (octets[:, 2] << 16)
            integers = (integers ^ (1 << 23)) - (1 << 23)
        else:
            integers = np.frombuffer(payload, dtype='<i2' if bits == 16 else '<i4').astype(np.int64)
        integers = integers >> (bits - fmt['validBitsPerSample'])
        decoded = integers.astype('<f8') / (1 << (fmt['validBitsPerSample'] - 1))
    else:
        decoded = np.frombuffer(payload, dtype='<f4' if bits == 32 else '<f8').astype('<f8')
    decoded = np.ascontiguousarray(decoded.reshape(audit['decoded']['shape']), dtype='<f8')
    _require(_sha(decoded, '<f8') == audit['decoded']['sha256'], 'Decoded waveform hash differs from frozen audit')
    return decoded, audit


def raw_descriptors(audit):
    """Ordered six float64 descriptors of every original channel/frame."""
    metrics = audit['metrics']
    rail = metrics['integerRailFraction']
    if rail is None:
        rail = metrics['floatDigitalFullScaleFraction']
    values = np.array([metrics['rms'], metrics['peakAbs'], metrics['exactZeroFraction'],
                       metrics['absLe1eMinus4Fraction'], rail, metrics['durationSeconds']], dtype='<f8')
    _require(values.shape == (6,) and np.isfinite(values).all(), 'Invalid raw descriptors')
    return values


def downmix(decoded):
    """Arithmetic channel mean only; preserve level and cancellation."""
    values = np.asarray(decoded)
    _require(values.ndim == 2 and values.shape[0] > 0 and 0 < values.shape[1] <= 64
             and values.dtype == np.dtype('float64') and np.isfinite(values).all(),
             'Expected finite positive frames x channels float64 audio')
    with np.errstate(over='ignore', invalid='ignore'):
        mono = np.mean(values, axis=1, dtype=np.float64)
    _require(np.isfinite(mono).all(), 'Channel mean overflow')
    return np.ascontiguousarray(mono, dtype='<f8')


def resample_mono(mono, sample_rate):
    """Return 16kHz <f4 model input and auditable deterministic derived hashes."""
    _require(type(sample_rate) is int and sample_rate in ACCEPTED_RATES, 'Unsupported selected sample rate')
    _require(scipy.__version__ == POLICY['resample']['version'], 'Pinned SciPy version required')
    values = np.asarray(mono)
    _require(values.ndim == 1 and values.size > 0 and values.dtype == np.dtype('float64')
             and np.isfinite(values).all(), 'Expected finite positive mono float64 audio')
    divisor = math.gcd(sample_rate, 16000)
    up, down = 16000 // divisor, sample_rate // divisor
    resampled = values.copy() if sample_rate == 16000 else resample_poly(
        values, up, down, window=('kaiser', 5.0), padtype='constant', cval=0)
    length = (values.size * 16000 + sample_rate - 1) // sample_rate
    _require(resampled.shape == (length,) and np.isfinite(resampled).all(), 'Invalid resampled waveform')
    with np.errstate(over='ignore', invalid='ignore'):
        final = np.ascontiguousarray(resampled, dtype='<f4')
    _require(np.isfinite(final).all(), 'Float32 model-input conversion overflow')
    metadata = {'sourceSampleRate': sample_rate, 'targetSampleRate': 16000,
                'sourceFrames': int(values.size), 'targetFrames': int(final.size), 'up': up, 'down': down,
                'scipyVersion': scipy.__version__, 'sourceMonoFloat64Sha256': _sha(values, '<f8'),
                'resampledFloat64Sha256': _sha(resampled, '<f8'), 'modelInputFloat32Sha256': _sha(final, '<f4'),
                'interpolationApplied': sample_rate != 16000, 'gainNormalization': False,
                'clipping': False, 'trimming': False}
    return final, metadata


def prepare_audio(path):
    """Return samples/scalars arrays plus JSON-safe original and derived metadata."""
    decoded, audit = decoded_audio(path)
    samples, derived = resample_mono(downmix(decoded), audit['metrics']['sampleRate'])
    return {'samples': samples, 'scalars': raw_descriptors(audit),
            'metadata': {'originalAudit': audit, 'derived': derived, 'scalarOrder': list(SCALAR_NAMES),
                         'rawChannelScope': POLICY['rawChannelScope']}}


def pool_hidden(hidden):
    """Pool all valid final-layer frames into mean768 + population std768."""
    values = np.asarray(hidden)
    _require(values.ndim == 2 and values.shape[0] > 0 and values.shape[1] == 768
             and values.dtype == np.dtype('float32') and np.isfinite(values).all(),
             'Expected finite positive valid frames x 768 float32 hidden states')
    double = values.astype(np.float64)
    pooled = np.concatenate((double.mean(axis=0), double.std(axis=0, ddof=0))).astype('<f4')
    _require(pooled.shape == (1536,) and np.isfinite(pooled).all(), 'Invalid pooled representation')
    return np.ascontiguousarray(pooled)
