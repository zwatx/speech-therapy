"""Frozen features. The real encoder is pinned and hash-verified before loading."""
from pathlib import Path

import torch

from data import SAMPLE_RATE, digest

MODEL_ID = "facebook/wav2vec2-base"
REVISION = "0b5b8e868dd84f03fd87d01f9c4ff0f080fecfe8"
FILES = {
    "config.json": "4937977e24d12d1bba70cdce8709c3c04807a8e4ae8ddac4229c48c436ae99ae",
    "preprocessor_config.json": "b225d617c025463b9e157e06afea8b90dc7078fc70b013c533328423e0486b4a",
    "pytorch_model.bin": "3249fe98bfc62fcbc26067f724716a6ec49d12c4728a2af1df659013905dff21",
}
WAVLM_MODEL_ID = "microsoft/wavlm-base-plus"
WAVLM_REVISION = "4c66d4806a428f2e922ccfa1a962776e232d487b"
WAVLM_FILES = {
    "config.json": "fea6df1c2700a3954fc07e70588aecc9055eeb28db2ff57151a2db0d19180ed4",
    "preprocessor_config.json": "99272fe8ccfab114b68b478681ea47ee3a1ce62bb788cb92dd6e4f69fb1f1da2",
    "pytorch_model.bin": "3bb273a6ace99408b50cfc81afdbb7ef2de02da2eab0234e18db608ce692fe51",
}
WAVLM_BYTES = {"config.json": 2232, "preprocessor_config.json": 215, "pytorch_model.bin": 377_617_425}
WAVLM_LICENSE = {
    "basis": "CC-BY-SA-3.0 linked by the exact model card; not the separate UniLM code MIT license",
    "modelCardUrl": f"https://huggingface.co/{WAVLM_MODEL_ID}/blob/{WAVLM_REVISION}/README.md",
    "modelCardSha256": "d417fc16b08e2f66f0af6b371e47a5f9f1f596f6c1c593f1214d360c41d7a27e",
    "licenseUrl": "https://github.com/microsoft/UniSpeech/blob/6112826ac13a4327f4c9a7afa2a505e35b763514/LICENSE",
    "licenseSha256": "74295d561f60f770a4aa7525b71c0d119ec70422e9f5c601ee3c77e1b7822c91",
    "scope": "Private engineering only; no redistribution or production authorization",
}
HUBERT_MODEL_ID = "facebook/hubert-base-ls960"
HUBERT_REVISION = "dba3bb02fda4248b6e082697eee756de8fe8aa8a"
HUBERT_FILES = {
    "config.json": "56be398848bbd9cbc720172b0d45b2f01cac7652f2968f0f31f5faf9f2986acc",
    "preprocessor_config.json": "4a93853b74278b7c769d07f5a861e5d12ceb5db2bced5620d335f87238cb9e86",
    "pytorch_model.bin": "062249fffb353eab67547a2fbc129f7c31a2f459faf641b19e8fb007cc5c48ad",
}
HUBERT_BYTES = {"config.json": 1385, "preprocessor_config.json": 213, "pytorch_model.bin": 377_569_754}
HUBERT_LICENSE = {
    "basis": "Apache-2.0 tag in the exact official model card; no separate LICENSE file in its snapshot",
    "modelCardUrl": f"https://huggingface.co/{HUBERT_MODEL_ID}/blob/{HUBERT_REVISION}/README.md",
    "modelCardSha256": "c59fb00d253ab5ae5d288f130c64dddf3b7af3d5ce35c96395ac7a3db5db88f5",
    "scope": "Private engineering only; no redistribution or production authorization",
}


class SpectralEncoder:
    """Cheap deterministic test baseline, not an open-weight speech model."""
    identity = {"kind": "spectral-engineering-v1", "width": 65, "preprocessing": "pcm16-stft256-hop160-log1p-v1"}

    def __call__(self, samples):
        spectrum = torch.stft(samples, n_fft=256, hop_length=160,
                              window=torch.hann_window(256), return_complex=True, center=False)
        return torch.log1p(spectrum.abs()[:65]).T.contiguous()


class _FrozenSpeechEncoder:
    def __init__(self, cache: Path, allow_download: bool = False):
        from huggingface_hub import hf_hub_download
        from transformers import HubertModel, Wav2Vec2FeatureExtractor, Wav2Vec2Model, WavLMModel

        paths = {}
        for filename, expected in self.identity["artifactSha256"].items():
            path = Path(hf_hub_download(self.identity["modelId"], filename, revision=self.identity["revision"],
                                       cache_dir=str(cache), local_files_only=not allow_download))
            size = self.identity.get("artifactBytes", {}).get(filename)
            if (size is not None and path.stat().st_size != size) or digest(path.read_bytes()) != expected:
                raise ValueError(f"Pinned encoder integrity failure: {filename}")
            paths[filename] = path
        snapshot = paths["config.json"].parent
        self.processor = Wav2Vec2FeatureExtractor.from_pretrained(str(snapshot), local_files_only=True)
        if self.identity["kind"] == "hubert-base-ls960":
            if (self.processor.do_normalize is not True or
                    self.processor.sampling_rate != SAMPLE_RATE or
                    self.processor.return_attention_mask is not False or
                    self.processor.feature_size != 1):
                raise ValueError("Pinned HuBERT feature extractor preprocessing mismatch")
        model_class = {"wav2vec2-base": Wav2Vec2Model,
                       "wavlm-base-plus": WavLMModel,
                       "hubert-base-ls960": HubertModel}[self.identity["kind"]]
        self.model = model_class.from_pretrained(str(snapshot), local_files_only=True,
                                               use_safetensors=False, weights_only=True)
        self.model.requires_grad_(False).eval()

    @torch.no_grad()
    def __call__(self, samples):
        # One clip at a time avoids group-norm/padding interactions in this checkpoint.
        inputs = self.processor(samples.numpy(), sampling_rate=SAMPLE_RATE, return_tensors="pt")
        return self.model(**inputs).last_hidden_state[0].detach().cpu().contiguous()


class Wav2VecEncoder(_FrozenSpeechEncoder):
    # Keep the established identity byte-for-byte compatible with saved heads.
    identity = {"kind": "wav2vec2-base", "modelId": MODEL_ID, "revision": REVISION,
                "artifactSha256": FILES, "width": 768, "preprocessing": "pinned-feature-extractor-single-clip-v1"}


class WavLMEncoder(_FrozenSpeechEncoder):
    identity = {"kind": "wavlm-base-plus", "modelId": WAVLM_MODEL_ID, "revision": WAVLM_REVISION,
                "artifactSha256": WAVLM_FILES, "artifactBytes": WAVLM_BYTES, "width": 768,
                "preprocessing": "pinned-feature-extractor-single-clip-v1-no-waveform-normalization",
                "licenseEvidence": WAVLM_LICENSE}


class HubertEncoder(_FrozenSpeechEncoder):
    identity = {"kind": "hubert-base-ls960", "modelId": HUBERT_MODEL_ID, "revision": HUBERT_REVISION,
                "artifactSha256": HUBERT_FILES, "artifactBytes": HUBERT_BYTES, "width": 768,
                "preprocessing": "pinned-feature-extractor-single-clip-v1-waveform-normalized-no-attention-mask",
                "licenseEvidence": HUBERT_LICENSE}


def load_encoder(kind: str, cache: Path, allow_download: bool = False):
    if kind == "spectral-engineering-v1":
        return SpectralEncoder()
    if kind == "wav2vec2-base":
        return Wav2VecEncoder(cache, allow_download)
    if kind == "wavlm-base-plus":
        return WavLMEncoder(cache, allow_download)
    if kind == "hubert-base-ls960":
        return HubertEncoder(cache, allow_download)
    raise ValueError("Unsupported encoder")
