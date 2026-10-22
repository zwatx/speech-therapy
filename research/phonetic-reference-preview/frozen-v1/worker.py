"""Inactive cold reference worker. No framework imports occur at module import."""
import json
import sys
import time

# contract is injected from verified source bytes by the root bootstrap.

def run(raw, envelope, snapshot, identities, admitted=False):
    if admitted is not True:
        raise contract.Rejected('inactive')
    payload = contract.wav_payload(raw, envelope)  # rejects before frameworks/model
    import numpy as np
    import torch
    import transformers
    from transformers import Wav2Vec2ForCTC, Wav2Vec2FeatureExtractor
    contract.require(sys.version_info[:3] == (3,13,14) and np.__version__ == '2.2.6' and
                     torch.__version__.split('+')[0] == '2.7.0' and transformers.__version__ == '4.57.6', 'integrity')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.monotonic()
    vocab = contract.vocabulary(json.loads((snapshot/'vocab.json').read_text()))
    extractor = Wav2Vec2FeatureExtractor.from_pretrained(str(snapshot), local_files_only=True, trust_remote_code=False)
    contract.require(extractor.do_normalize is True and extractor.return_attention_mask is True and
                     extractor.sampling_rate == 16000 and extractor.padding_value == 0 and
                     extractor.padding_side == 'right', 'loadingRejected')
    loading_metadata = {}
    model = loading(torch, Wav2Vec2ForCTC, snapshot, contract, loading_metadata)
    loaded = time.monotonic()
    waveform = np.frombuffer(payload, dtype='<i2').astype(np.float32)/np.float32(32768)
    contract.require(waveform.shape == (envelope['sample_count'],) and waveform.flags.c_contiguous and
                     np.isfinite(waveform).all() and waveform.min() >= -1 and waveform.max() <= 32767/32768, 'invalid_wav')
    features = extractor(waveform, sampling_rate=16000, padding='max_length', max_length=64000,
                         truncation=False, return_attention_mask=True, return_tensors='pt')
    values, mask = features.input_values, features.attention_mask
    expected = torch.arange(64000).unsqueeze(0) < envelope['sample_count']
    contract.require(list(values.shape) == [1,64000] and values.dtype == torch.float32 and
                     values.device.type == 'cpu' and bool(torch.isfinite(values).all()) and
                     list(mask.shape) == [1,64000] and mask.dtype in (torch.int32,torch.int64) and
                     mask.device.type == 'cpu' and torch.equal(mask, expected.to(mask.dtype)) and
                     bool((values[0,envelope['sample_count']:] == 0).all()), 'malformed_output')
    extracted = time.monotonic()
    with torch.inference_mode():
        logits = model(input_values=values, attention_mask=mask, return_dict=True).logits
    contract.require(list(logits.shape) == [1,199,392] and logits.dtype == torch.float32 and
                     logits.device.type == 'cpu' and bool(torch.isfinite(logits).all()), 'malformed_output')
    valid = contract.frames(envelope['sample_count'])
    ids = contract.collapse(logits[0,:valid].argmax(dim=-1).tolist())
    response = contract.result('model_hypothesis','complete','complete',envelope,identities,True,False)
    # These fields remain private. Terminal ownership is set only by the parent.
    response['private'] = dict(ids=ids, symbols=contract.symbols(ids,vocab), loading=loading_metadata,
                               logits=logits.detach().contiguous().numpy().astype('<f4',copy=False).tobytes(),
                               normalized=values.detach().contiguous().numpy().astype('<f4',copy=False).tobytes())
    response['timing_seconds'] = dict(load=loaded-started, extractor=extracted-loaded,
                                     forward=time.monotonic()-extracted)
    return response


def loading(torch, Wav2Vec2ForCTC, snapshot, p, output):
    model,info=Wav2Vec2ForCTC.from_pretrained(str(snapshot),local_files_only=True,trust_remote_code=False,
        use_safetensors=False,weights_only=True,attn_implementation='eager',output_loading_info=True)
    p.require(set(info) == {'missing_keys','unexpected_keys','mismatched_keys','error_msgs'}
              and all(type(v) is list and v == [] for v in info.values()),'loadingRejected')
    model=model.to(device='cpu',dtype=torch.float32).requires_grad_(False).eval()
    config=json.loads((snapshot/'config.json').read_text())
    p.require(model.config.model_type == config['model_type'] == 'wav2vec2' and
              model.config.architectures == ['Wav2Vec2ForCTC'] and model.config.vocab_size == 392 and
              model.config.add_adapter is False and model.config.adapter_attn_dim is None and
              model.config._attn_implementation == 'eager' and model.training is False,'loadingRejected')
    # Meta-only, weights_only checkpoint inspection accounts for legacy names without a second live weight allocation.
    checkpoint=torch.load(str(snapshot/'pytorch_model.bin'),map_location='meta',weights_only=True)
    p.require(isinstance(checkpoint,dict) and all(type(k) is str and torch.is_tensor(v) for k,v in checkpoint.items()),'loadingRejected')
    loaded=model.state_dict(); mapped={}; migrations=[]
    allowed={
        'wav2vec2.encoder.pos_conv_embed.conv.weight_g':'wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original0',
        'wav2vec2.encoder.pos_conv_embed.conv.weight_v':'wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original1'}
    for key,value in checkpoint.items():
        target,changed=model._fix_state_dict_key_on_load(key)
        p.require((target == key and changed is False) or (allowed.get(key) == target and changed is True),'loadingRejected')
        p.require(target not in mapped,'loadingRejected'); mapped[target]=value
        if changed: migrations.append({'from':key,'to':target})
    p.require(set(mapped) == set(loaded),'loadingRejected')
    count=0
    for key,value in loaded.items():
        original=mapped[key]
        p.require(value.dtype == original.dtype == torch.float32 and value.device.type == 'cpu'
                  and list(value.shape) == list(original.shape) and bool(torch.isfinite(value).all()),'loadingRejected')
        count+=value.numel()
    p.require(all(param.dtype == torch.float32 and param.device.type == 'cpu' and not param.requires_grad
                  and bool(torch.isfinite(param).all()) for param in model.parameters()),'loadingRejected')
    output.update({'schema':'NativePhoneticLoadingV1','missingKeys':0,'unexpectedKeys':0,
        'mismatchedKeys':0,'errorMessages':0,'stateTensorCount':len(loaded),'parameterElementCount':count,
        'allStateFP32Finite':True,'migrationPolicy':'OnlyPinnedHFPositionalWeightNormNamesV1','migrations':migrations,
        'checkpointMapping':[{ 'checkpointKey':key,'modelKey':model._fix_state_dict_key_on_load(key)[0],
                              'shape':list(value.shape),'dtype':str(value.dtype)} for key,value in checkpoint.items()]})
    del checkpoint,mapped,loaded
    return model
