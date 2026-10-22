"""Disposable, offline CPU worker using unchanged extraction and retained loaders."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from consumer_assessment.bridge import HERE, ROOT, MANIFEST_SHA, PHONES, Unavailable, prepare, sha, canonical_bytes

POSITION_SHA = 'f089324f893253f7dafb0b8920ed04eaf9d2e182e969645ccc7bcb1618d4d9ce'
PARENT_SHA = 'c077e68e37fa68da36a44194094e5c07c40e1866148834c68b6fbd24a5da9782'
INIT_SHA = 'cae696b6b14351155a0658eb38d910b584035ea78ac8e4d7766a7cac323a8b84'
LOADER_SHA = 'dd3009f5b923cb64ce4a6ddf161fdc48480fd0b8bc7cd103d54239c258f41b94'
BUNDLE = ROOT/'work/ages-6-12-bundle-20260927/portable/bundle'
SNAPSHOT = HERE/'outputs/model-cache/models--facebook--wav2vec2-lv-60-espeak-cv-ft/snapshots/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4'


def validate_sources():
    def pinned(path, expected):
        data = path.read_bytes()
        if sha(data) != expected: raise ValueError('source binding differs')
        return json.loads(data)
    parent = pinned(HERE/'experiments/multiphone-research-audio-v1.json',PARENT_SHA)
    position = pinned(HERE/'position_inference/contract-v2.json',POSITION_SHA)
    for name, expected in {**parent['dependencySha256'], **position['sourceSha256'],
                           'ages_6_12_bundle/inference.py':LOADER_SHA,
                           'ages_6_12_bundle/__init__.py':INIT_SHA}.items():
        if sha((HERE/name).read_bytes()) != expected: raise ValueError('source binding differs')


def run(stage):
    p = prepare((stage/'request.json').read_bytes())
    try:
        validate_sources()
        import numpy as np
        import torch
        import position_inference.audio as position
        from ages_6_12_bundle.inference import load_bundle
        contract, mapping, recipe, vocabulary, bindings = position.load_contract(position.CONTRACT,POSITION_SHA,SNAPSHOT)
        head = load_bundle(BUNDLE,MANIFEST_SHA)
        # Retained loader does not expose a feature binding property. Bind its
        # exact manifest/provenance bytes and the frozen extractor separately.
        bindings['headManifest'] = position.binding(BUNDLE/'manifest.json',MANIFEST_SHA)
        manifest = json.loads((BUNDLE/'manifest.json').read_text())
        for name, expected in manifest['files'].items(): bindings['head/'+name] = position.binding(BUNDLE/name,expected)
        bindings['source/ages_6_12_bundle/__init__.py'] = position.binding(HERE/'ages_6_12_bundle/__init__.py',INIT_SHA)
        bindings['source/ages_6_12_bundle/inference.py'] = position.binding(HERE/'ages_6_12_bundle/inference.py',LOADER_SHA)
        if len(contract['featureColumns']) != 1037 or manifest['targetPhones'] != list(PHONES):
            raise ValueError('feature/model interface differs')
    except Exception: raise Unavailable('model_unavailable') from None
    audio_path = stage/'audio.wav'; audio_path.write_bytes(p.audio); audio_path.chmod(0o600)
    bindings['audio'] = position.binding(audio_path,sha(p.audio))
    samples = position.read_rating_pcm(audio_path,sha(p.audio))
    frames = position.local.convolution_frames(len(samples),mapping)
    try: canonical = position.validate_prompt(p.request['prompt'],mapping,vocabulary,PHONES,frames)
    except ValueError: raise Unavailable('invalid_request') from None
    torch.set_num_threads(2)
    job = {'schemaVersion':1,'researchOnly':True,'audioPath':str(audio_path.absolute()),
           'audioSha256':sha(p.audio),'sampleCount':len(samples),'expectedFrames':frames,
           'bindings':bindings,'ctcCheckpoint':contract['ctcCheckpoint'],'sessionOptions':contract['ctcSessionOptions']}
    position.write_json(stage/'ctc-job.json',job)
    t0 = time.perf_counter()
    subprocess.run(['node',str(HERE/'multiphone_research_ctc.ts'),str(stage/'ctc-job.json'),position.digest(stage/'ctc-job.json')],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    ctc,_ = position.read_bound_json(stage/'ctc.json')
    position.require(ctc['complete'] is True and ctc['jobSha256'] == position.digest(stage/'ctc-job.json')
                     and ctc['audioSha256'] == sha(p.audio) and ctc['frames'] == frames
                     and ctc['checkpoint'] == contract['ctcCheckpoint'] and ctc['sessionOptions'] == contract['ctcSessionOptions']
                     and ctc['fetchAttempts'] == 0 and ctc['posteriorsPath'] == 'ctc.f32','CTC binding differs')
    payload = (stage/'ctc.f32').read_bytes()
    position.require(sha(payload) == ctc['posteriorsSha256'],'CTC posterior binding differs')
    logp = np.frombuffer(payload,dtype='<f4').reshape((-1,392))
    position.local.validate_log_prob(logp,frames)
    encoder = position.phonetic.PhoneticEncoder(SNAPSHOT,recipe)
    hidden = encoder(samples)
    values,rows,diagnostics = position.make_features(canonical,logp,hidden,mapping)
    ids = np.asarray([r['modelTargetId'] for r in rows],dtype=np.int64)
    output = head.predict(values,ids,age_years=p.request['ageYears'])
    position.guard(bindings)
    validate_sources()
    with (stage/'features.npy').open('xb') as f:
        (stage/'features.npy').chmod(0o600); np.save(f,values,allow_pickle=False)
    position.write_json(stage/'engineering.json',{'researchOnly':True,'bindings':bindings,
        'featureSourceBindingSha256':contract['featureSourceBindingSha256'],
        'featuresSha256':position.digest(stage/'features.npy'),'rows':rows,'canonicalPathDiagnostics':diagnostics,
        'ctc':ctc,'featureShape':list(values.shape),'encoderAndHeadMilliseconds':(time.perf_counter()-t0)*1000,
        'sourceBindingVerified':True,'clinicalUseEligible':False,'learnerFeedbackEligible':False,
        'productionUseEligible':False,'promptMatch':'unverified'})
    return {'targets':[{**target,'subjectiveCorpusRatingProbabilities':probs.tolist()}
                       for target,probs in zip(p.request['prompt']['targets'],output['probabilities'],strict=True)],
            'model':{'id':'ages-6-12-research-mixture','manifestSha256':MANIFEST_SHA}}


if __name__ == '__main__':
    stage = Path(sys.argv[1])
    try: result = run(stage)
    except Unavailable as exc:
        result = {'reason':exc.reason}; code = 1
    except Exception:
        result = {'reason':'inference_failed'}; code = 1
    else: code = 0
    (stage/'result.json').write_bytes(canonical_bytes(result)); (stage/'result.json').chmod(0o600)
    sys.exit(code)
