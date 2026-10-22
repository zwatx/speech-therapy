"""Self-contained feature inference for pinned, research-only rating-head bundles.

Only the bundle and the frozen head implementation are loaded. Full training
provenance audit remains multiphone_phonetic_final.replay. No waveform adapter,
pronunciation decision, empirical calibration or learner feedback is provided.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import torch

import multiphone_models as models

TARGETS = ('B', 'P', 'M', 'T', 'D', 'N', 'K', 'G', 'F', 'V', 'S', 'Z',
           'SH', 'CH', 'JH', 'L', 'R', 'W', 'Y', 'HH', 'TH', 'DH', 'NG', 'ZH')
SCALARS = ('targetMeanLogPosterior', 'targetMeanPosterior', 'targetMaxPosterior',
    'meanLogMarginVsBestOtherPhone', 'meanLogFractionOfNonblankMass', 'targetArgmaxFraction',
    'meanBlankPosterior', 'meanSpecialPosterior', 'meanFullVocabularyEntropy',
    'ctcTargetOccupancySeconds', 'occupiedFrames', 'utteranceViterbiLogProbabilityPerFrame',
    'greedyCanonicalTokenErrorRate')
FILES = {'config.json', 'checkpoint.pt', 'history.json', 'verification.json', 'normalization.json', 'status.json'}
FALSE_FLAGS = ('outerOutcomesUsed', 'authorTestInferencePerformed', 'encoderUpdated',
    'clinicalUseEligible', 'learnerFeedbackEligible', 'empiricalCalibrationEstablished',
    'frameTimesValidated', 'producedPhoneLabelsAvailable', 'generalizationMeasured')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def class_weights(config):
    """Verify weights against the bundle's observed fit counts, without a corpus."""
    state = config['classWeightState']
    counts = np.asarray(state['observedRaterCounts'], dtype=np.float64)
    require(counts.shape == (3,) and np.isfinite(counts).all() and (counts >= 0).all()
            and np.equal(counts, np.floor(counts)).all() and counts.sum() > 0, 'Invalid fit class counts')
    prevalence = counts / counts.sum()
    weights = np.ones(3)
    if config['objective'] == 'weighted':
        require((counts > 0).all(), 'Weighted fit requires observations of every class')
        weights = 1 / np.sqrt(prevalence)
        weights = np.minimum(weights, weights.min() * 10)
        weights /= np.dot(prevalence, weights)
    require(np.allclose(state['observedPrevalence'], prevalence, rtol=0, atol=1e-12)
            and np.allclose(state['weights'], weights, rtol=0, atol=1e-12)
            and state['trainingPseudocounts'] == 0 and state['maximumWeightRatio'] == 10,
            'Class weights differ from the declared fit objective')
    return counts, torch.tensor(weights, dtype=torch.float32)


class ResearchHead:
    """CPU feature predictor; output columns are subjective rating classes 0/1/2."""

    def __init__(self, model, saved, config, manifest, manifest_sha256):
        self._model, self._mean, self._std = model.eval(), saved['mean'], saved['std']
        self._log_weights = saved['classWeights'].log()
        self._supported_ids = tuple(t['id'] for t in manifest['targets'] if t['supported'])
        self.variant, self.manifest_sha256 = config['variant'], manifest_sha256
        self.supported_phones = tuple(TARGETS[i] for i in self._supported_ids)
        self.feature_columns = tuple(manifest['featureContract']['columns'])
        self.feature_source_binding_sha256 = manifest['featureContract']['sourceBindingSha256']

    @torch.no_grad()
    def predict(self, features, target_ids):
        """Accept raw float32 [N,1037] features and integer [N] canonical IDs.

        The first 1024 columns are the pinned target-window phonetic embedding;
        the remaining 13 follow feature_columns. Shape alone cannot establish
        that a caller used the correct extractor or a singleton canonical target.
        """
        features, target_ids = np.asarray(features), np.asarray(target_ids)
        require(features.dtype == np.float32 and features.ndim == 2 and features.shape[1] == 1037
                and len(features) > 0 and np.isfinite(features).all()
                and target_ids.shape == (len(features),) and np.issubdtype(target_ids.dtype, np.integer)
                and set(target_ids.tolist()) <= set(self._supported_ids), 'Invalid features or unsupported canonical target')
        result = []
        for start in range(0, len(features), 64):
            x = ((torch.from_numpy(features[start:start+64].copy()) - self._mean) / self._std)[:, None]
            ids = torch.tensor(target_ids[start:start+64, None], dtype=torch.long)
            mask = torch.ones_like(ids, dtype=torch.bool)
            logits = self._model(x, mask, ids, mask)[:, 0]
            result.extend((logits - self._log_weights).softmax(-1).numpy())
        p = np.asarray(result, dtype=np.float64)
        require(np.isfinite(p).all() and (p >= 0).all() and np.allclose(p.sum(1), 1, rtol=0, atol=1e-6),
                'Nonfinite research probability output')
        return p


def load_head(directory: Path, expected_manifest_sha256: str) -> ResearchHead:
    """Verify a copied bundle without opening its original training paths.

    The caller must supply the manifest digest obtained from the completed
    export. A full provenance audit is separate; this verifies the pinned local
    files and their inference contract, not a new performance claim.
    """
    directory = Path(directory)
    manifest_bytes = (directory / 'manifest.json').read_bytes()
    require(sha(manifest_bytes) == expected_manifest_sha256, 'Caller-pinned research manifest differs')
    manifest = json.loads(manifest_bytes)
    require(manifest['complete'] is True and manifest['researchOnly'] is True
            and all(manifest[name] is False for name in FALSE_FLAGS)
            and set(manifest['filesSha256']) == FILES, 'Unsupported research export contract')
    # Parse and deserialize the same captured bytes whose digests were checked.
    payload = {name: (directory / name).read_bytes() for name in FILES}
    require(all(sha(value) == manifest['filesSha256'][name] for name, value in payload.items()),
            'Pinned bundle file changed')
    config, norm, status = [json.loads(payload[name]) for name in ('config.json', 'normalization.json', 'status.json')]
    require(config['phase'] == 'final-research-refit' and config['authorPartition'] == 'train'
            and config['family'] == 'target-scalars' and config['objective'] in ('weighted', 'unweighted')
            and config['regime'] in ('all-age', 'child-only')
            and config['variant'] == manifest['variant'] == config['objective'] + '-' + config['regime']
            and all(config[name] is False for name in FALSE_FLAGS)
            and config['sourceSha256']['multiphone_models.py'] == sha(Path(models.__file__).read_bytes()),
            'Unsupported model implementation or research scope')
    h = config['hyperparameters']
    require(h == dict(seed=7, hidden=128, dropout=.1, lr=config['selection']['lr'], weight_decay=.01,
                      batch_size=64, threads=2, device='cpu') and h['lr'] in (.001, .0003),
            'Unsupported head architecture or inference configuration')
    contract = manifest['featureContract']
    require(contract['dtype'] == 'float32' and contract['shape'] == ['N', 1037]
            and contract['columns'] == [f'targetPhonetic:{i}' for i in range(1024)] + list(SCALARS),
            'Feature layout differs from the trained head')
    counts, weights = class_weights(config)
    fit = config['fitRows']
    require(fit and all(type(i) is int and i >= 0 for i in fit) and fit == sorted(set(fit))
            and counts.sum() == 5 * len(fit), 'Invalid fit-row support')
    require(config['targets'] == manifest['targets'] and len(config['targets']) == 24, 'Target inventory differs')
    support, total_counts = 0, np.zeros(3)
    for i, (phone, target) in enumerate(zip(TARGETS, config['targets'], strict=True)):
        observed = config['priorState'][phone]['observedRows'] if i < 23 else 0
        require(type(observed) is int and observed >= 0 and target == dict(id=i, phone=phone,
            supported=i < 23 and observed > 0, fitRows=observed), 'Supported targets differ from actual fit support')
        if i < 23:
            c = np.asarray(config['priorState'][phone]['observedRaterCounts'], dtype=np.float64)
            require(c.shape == (3,) and np.isfinite(c).all() and (c >= 0).all()
                    and np.equal(c, np.floor(c)).all() and c.sum() == 5 * observed, 'Invalid target fit counts')
            total_counts += c
            support += observed
    require(support == len(fit) and np.array_equal(total_counts, counts), 'Target and class support disagree')
    saved = torch.load(io.BytesIO(payload['checkpoint.pt']), map_location='cpu', weights_only=True)
    require(saved['configSha256'] == sha(payload['config.json']) and saved['epoch'] == manifest['epochsRun']
            == config['selection']['fixedEpochs'] and type(saved['epoch']) is int and 1 <= saved['epoch'] <= 100
            and status == dict(complete=True, epoch=saved['epoch'], fixedEpochs=saved['epoch'],
                               exactCheckpointReplay=True, researchOnly=True)
            and saved['classWeightState'] == config['classWeightState']
            and torch.equal(saved['classWeights'], weights), 'Checkpoint status or objective binding differs')
    for name in ('mean', 'std'):
        require(saved[name].dtype == torch.float32 and saved[name].shape == (1037,)
                and torch.isfinite(saved[name]).all() and saved[name].tolist() == norm[name], 'Invalid frozen normalization')
    require((saved['std'] > 0).all() and norm['fitRows'] == fit and norm['priorState'] == config['priorState']
            and norm['classWeightState'] == config['classWeightState'], 'Normalization provenance differs')
    torch.set_num_threads(2)
    with torch.random.fork_rng(devices=[]):
        model = models.MeanPoolPhoneRatingHead(1037, 24, 128, .1)
    model.load_state_dict(saved['model'], strict=True)
    require(all(torch.isfinite(value).all() for value in model.state_dict().values()), 'Nonfinite head parameters')
    return ResearchHead(model, saved, config, manifest, expected_manifest_sha256)
