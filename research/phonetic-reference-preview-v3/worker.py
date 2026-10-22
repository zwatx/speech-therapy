"""Inactive cold reference worker. No framework imports occur at module import."""
import json
import sys
import time

# contract is injected from verified source bytes by the root bootstrap.

def run(raw, envelope, snapshot, identities, output, admitted=False, guard=None):
    if admitted is not True or guard is None:
        raise contract.Rejected('inactive')
    output('PHASE-input.json',{'phase':'input'})
    payload = contract.wav_payload(raw, envelope)  # rejects before frameworks/model
    output('PHASE-loading.json',{'phase':'loading'})
    import numpy as np
    import torch
    import transformers
    from transformers import Wav2Vec2ForCTC, Wav2Vec2FeatureExtractor
    contract.require(sys.version_info[:3] == (3,13,14) and np.__version__ == '2.2.6' and
                     torch.__version__.split('+')[0] == '2.7.0' and transformers.__version__ == '4.57.6', 'integrity')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.monotonic()
    guard()  # fresh full closure after framework import, before loader paths
    vocab = contract.vocabulary(json.loads((snapshot/'vocab.json').read_text()))
    extractor = Wav2Vec2FeatureExtractor.from_pretrained(str(snapshot), local_files_only=True, trust_remote_code=False)
    contract.require(extractor.do_normalize is True and extractor.return_attention_mask is True and
                     extractor.sampling_rate == 16000 and extractor.padding_value == 0 and
                     extractor.padding_side == 'right', 'loadingRejected')
    loading_metadata = {}
    model = loading(torch, Wav2Vec2ForCTC, snapshot, contract, loading_metadata, guard)
    loaded = time.monotonic()
    output('PHASE-extractor.json',{'phase':'extractor'})
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
    output('PHASE-forward.json',{'phase':'forward'})
    output('CALL-COMMITTED.json', dict(request=envelope, model_call_state='invocation_committed'))
    forward_started = time.monotonic()
    with torch.inference_mode():
        logits = model(input_values=values, attention_mask=mask, return_dict=True).logits
    forward_ended = time.monotonic()
    output('CALL-COMPLETED.json',dict(request=envelope,model_call_state='completed'))
    output('PHASE-decode.json',{'phase':'decode'})
    contract.require(list(logits.shape) == [1,199,392] and logits.dtype == torch.float32 and
                     logits.device.type == 'cpu' and bool(torch.isfinite(logits).all()), 'malformed_output')
    valid = contract.frames(envelope['sample_count'])
    ids = contract.collapse(logits[0,:valid].argmax(dim=-1).tolist())
    response = contract.result('model_hypothesis','complete','complete',envelope,identities,True,False,'completed')
    output('PHASE-persist.json',{'phase':'persist'})
    response['artifacts'] = {
        'logits.f32':output('logits.f32',logits.detach().contiguous().numpy().astype('<f4',copy=False).tobytes()),
        'normalized.f32':output('normalized.f32',values.detach().contiguous().numpy().astype('<f4',copy=False).tobytes()),
        'hypothesis.json':output('hypothesis.json',dict(ids=ids,symbols=contract.symbols(ids,vocab))),
        'loading.json':output('loading.json',loading_metadata)}
    response['timing_seconds'].update(load=loaded-started,extractor=extracted-loaded,forward=forward_ended-forward_started)
    return contract.response(response,envelope,identities)



def loading(torch, Wav2Vec2ForCTC, snapshot, p, output, guard):
    guard()
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
    guard()
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
    p.require(set(mapped) == set(loaded) and len(migrations) == 2 and
              {x['from']:x['to'] for x in migrations} == allowed,'loadingRejected')
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


def main(settings):
    """Root bootstrap calls once. Structured failures never include exception text."""
    from pathlib import Path
    import os
    import stat
    envelope, identities = settings['request'], settings['identities']
    staging = Path(settings['staging'])
    def output(name, value):
        raw = value if type(value) is bytes else (json.dumps(value,sort_keys=True,allow_nan=False)+'\n').encode()
        fd = os.open(staging/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        return contract.pin(raw)
    started = time.monotonic()
    try:
        admission = settings['admission']
        def guard():
            integrity.preflight(Path(settings['root']),Path(settings['here']),admission['source_sha'],admission['bindings_sha'],
                time.monotonic()+admission['integrity_seconds'],admission['system'])
        guard()  # immediately before package/model path consumption
        fd = os.open(staging/'input.wav',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info = os.fstat(stream.fileno())
            contract.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= contract.MAX_WAV,'invalid_wav')
            raw = stream.read(contract.MAX_WAV+1)
        guard()
        value = run(raw,envelope,Path(settings['snapshot']),identities,output,True,guard)
        guard()
    except BaseException as error:
        committed = (staging/'CALL-COMMITTED.json').exists()
        completed = (staging/'CALL-COMPLETED.json').exists()
        phase = 'unknown'
        for candidate in ('input','loading','extractor','forward','decode','persist'):
            if (staging/('PHASE-'+candidate+'.json')).exists(): phase=candidate
        reason = error.code if isinstance(error,contract.Rejected) and error.code in contract.REASONS else 'runtime_failure'
        value = contract.result('input_rejected' if reason in {'invalid_wav','identity_mismatch','invalid_request'} else 'unavailable',
                                'input' if reason in {'invalid_wav','identity_mismatch','invalid_request'} else phase,reason,envelope,identities,committed,
                                False,'completed' if completed else 'invocation_committed' if committed else 'not_started')
    value['timing_seconds']['cold'] = time.monotonic()-started
    output('RESPONSE.json',value)
