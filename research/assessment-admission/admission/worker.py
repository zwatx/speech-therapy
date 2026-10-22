"""Prompt-blind acoustic worker: stdin is only WAV bytes, no expected labels."""
import array,hashlib,io,json,math,os,resource,sys,time,wave
from pathlib import Path
from .models import MODEL_ROOT,check_models
from .policy import POLICY,canonical


def run(raw):
    import torch
    from transformers import WhisperProcessor,WhisperForConditionalGeneration
    check_models()
    torch.set_num_threads(2)
    with wave.open(io.BytesIO(raw),'rb') as wav:
        samples=array.array('h',wav.readframes(wav.getnframes()))
    if sys.byteorder!='little':samples.byteswap()
    tensor=torch.tensor(samples,dtype=torch.float32)/32768.0
    vad=torch.jit.load(str(MODEL_ROOT/'silero_vad.jit'),map_location='cpu').eval()
    vad.reset_states();probabilities=[];positive=0;consecutive=0;maximum=0
    with torch.inference_mode():
        for offset in range(0,len(tensor),512):
            chunk=tensor[offset:offset+512];count=len(chunk)
            if count<512:chunk=torch.nn.functional.pad(chunk,(0,512-count))
            probability=float(vad(chunk,16000).item())
            if not math.isfinite(probability) or not 0<=probability<=1:raise ValueError('vad_failed')
            probabilities.append(probability)
            if probability>=POLICY['vadThreshold']:
                positive+=count;consecutive+=count;maximum=max(maximum,consecutive)
            else:consecutive=0
        passed=positive>=POLICY['minimumPositiveSamples'] and maximum>=POLICY['minimumConsecutivePositiveSamples']
        speech={'method':'silero-vad','passed':passed,'positiveSamples':positive,'maximumConsecutivePositiveSamples':maximum,
                'windowCount':len(probabilities),'probabilities':probabilities,'speechPresenceVerified':False}
        if not passed:return {'speechEvidence':speech,'recognition':None,'status':'unavailable','reason':'speech_not_detected'}
        processor=WhisperProcessor.from_pretrained(str(MODEL_ROOT/'whisper'),local_files_only=True,trust_remote_code=False)
        model=WhisperForConditionalGeneration.from_pretrained(str(MODEL_ROOT/'whisper'),local_files_only=True,
                                                              use_safetensors=True,trust_remote_code=False).eval()
        inputs=processor(tensor.numpy(),sampling_rate=16000,return_tensors='pt',return_attention_mask=True)
        first=model(input_features=inputs.input_features,decoder_input_ids=torch.tensor([[model.config.decoder_start_token_id]])).logits[0,0].float()
        no_speech=float(torch.softmax(first,dim=-1)[50361].item())
        generated=model.generate(inputs.input_features,attention_mask=inputs.attention_mask,max_new_tokens=POLICY['maxNewTokens'],
                                 do_sample=False,num_beams=1,temperature=0.0,return_timestamps=False,
                                 return_dict_in_generate=True,output_scores=True,condition_on_prev_tokens=False,
                                 logprob_threshold=None,compression_ratio_threshold=None,no_speech_threshold=None)
        sequence=generated.sequences[0];tokens=sequence[-len(generated.scores):].tolist()
        special=set(processor.tokenizer.all_special_ids);chosen=[];posterior=[]
        for token,score in zip(tokens,generated.scores,strict=True):
            value=float(torch.log_softmax(score[0].float(),dim=-1)[token].item())
            if token not in special:
                if not math.isfinite(value):raise ValueError('posterior_failed')
                chosen.append(value);posterior.append({'tokenId':token,'selectedLogProbability':value})
        if not chosen:raise ValueError('recognition_empty')
        transcript=processor.batch_decode(generated.sequences,skip_special_tokens=True)[0].strip()
        if not isinstance(transcript,str) or len(transcript)>256:raise ValueError('recognition_invalid')
        recognition={'method':'whisper-base.en','transcript':transcript,'meanTokenLogProbability':sum(chosen)/len(chosen),
                     'noSpeechProbability':no_speech,'complete':int(sequence[-1])==model.config.eos_token_id,
                     'endTokenId':int(sequence[-1]),'generatedTokenCount':len(generated.scores),'selectedTokenPosteriors':posterior,
                     'requestedWordVerified':False}
        return {'speechEvidence':speech,'recognition':recognition,'status':'recognized','reason':None}


def main():
    stage=Path(sys.argv[1]);started=time.monotonic()
    try:
        raw=sys.stdin.buffer.read(132097)
        if len(raw)>132096:raise ValueError('invalid_audio')
        result=run(raw);code=0
    except Exception:
        result={'speechEvidence':None,'recognition':None,'status':'unavailable','reason':'recognition_failed'};code=1
    result['audioSha256']=hashlib.sha256(raw).hexdigest() if 'raw' in locals() else None
    result['workerElapsedSeconds']=time.monotonic()-started
    fd=os.open(stage/'result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:os.write(fd,canonical(result));os.fsync(fd)
    finally:os.close(fd)
    return code

if __name__=='__main__':raise SystemExit(main())
