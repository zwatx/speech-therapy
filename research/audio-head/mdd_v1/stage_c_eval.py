"""One-time recognition/posterior extraction, then restartable CPU-only GOP scoring."""
import argparse
from collections import Counter
import json
import time

import torch
from transformers import Wav2Vec2ForCTC
from . import train_ctc as base
from .stage_c import jibo_rows,load_frames,frame_path,create_model
from .jibo import RUN,read_interval
from .manifest import OUTPUT,load_manifest
from .inventory import ID_TO_PHONE,map_espeak
from .runtime import device_setup,ESPEAK_MODEL,snapshot,extractor,collapse
from .evaluate import evaluate
from .gop import phone_features,fit_calibration,summarize,labels


def recognition():
    if (RUN/'recognition-result.json').exists():
        raise FileExistsError('Stage C recognition already evaluated; use saved predictions')
    if not (RUN/'result.json').exists():
        raise FileNotFoundError('Stage C selection must complete first')
    start = time.monotonic()
    device = device_setup()
    rows = load_manifest()
    test = [r for r in jibo_rows() if r['split'] == 'test']
    dev = [r for r in rows if r['source']=='speechocean762' and r['split']=='test' and r['all_correct']]
    l2 = [r for r in rows if r['source']=='l2-arctic']
    model,backbone = create_model(device)
    del backbone
    frames = load_frames(test+dev+l2)
    result = {}
    for name,checkpoint,selected in [('A',OUTPUT/'candidate-A/best.pt',test),('C',RUN/'best.pt',test+dev+l2)]:
        model.load_state_dict(torch.load(checkpoint,weights_only=True)['state'])
        predictions = base.predict(model,selected,frames,device)
        (RUN/f'{name}-recognition-predictions.json').write_text(json.dumps(predictions))
        result[name] = {'jibo_test':evaluate(test,predictions)}
        if name == 'C':
            result[name].update(speech_dev=evaluate(dev,predictions),l2=evaluate(l2,predictions))
            # Checkpoint reload parity on every JIBO dev utterance.
            jdev = [r for r in jibo_rows() if r['split']=='dev']
            replay = base.predict(model,jdev,load_frames(jdev),device)
            if replay != json.loads((RUN/'dev-predictions.json').read_text()):
                raise ValueError('Stage C checkpoint replay mismatch')
            result['checkpoint_replay'] = 'exact greedy hypotheses, all JIBO dev'
    del model,frames
    if device.type=='mps':
        torch.mps.empty_cache()
    original = Wav2Vec2ForCTC.from_pretrained(str(snapshot(ESPEAK_MODEL)),local_files_only=True).eval().to(device)
    processor = extractor(ESPEAK_MODEL)
    inverse = {i:token for token,i in json.loads((snapshot(ESPEAK_MODEL)/'vocab.json').read_text()).items()}
    predictions,unknown,details = {},Counter(),[]
    with torch.inference_mode():
        for i,row in enumerate(test):
            inputs = processor(read_interval(row),sampling_rate=16000,return_tensors='pt')
            ids = original(**{k:v.to(device) for k,v in inputs.items()}).logits[0].argmax(-1).cpu().tolist()
            tokens = collapse(ids,inverse)
            phones,unmapped = map_espeak(tokens)
            details.append(dict(id=row['id'],raw_tokens=tokens,phones=phones,unmapped=unmapped))
            predictions[row['id']] = phones; unknown.update(unmapped)
            if (i+1)%100==0:
                print(f'A0 JIBO {i+1}/{len(test)} seconds={time.monotonic()-start:.1f}',flush=True)
    (RUN/'A0-recognition-predictions.json').write_text(json.dumps(predictions))
    (RUN/'A0-recognition-details.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in details))
    result['A0'] = dict(jibo_test=evaluate(test,predictions),unmapped=dict(unknown))
    result['wall_seconds'] = time.monotonic()-start
    (RUN/'recognition-result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps(result,indent=2,ensure_ascii=False),flush=True)


def detection_rows():
    split = json.loads((RUN/'speech-detection-split.json').read_text())
    calibration = set(split['calibration_speakers'])
    reporting = set(split['reporting_speakers'])
    if calibration&reporting:
        raise ValueError('Detection speaker leakage')
    rows = [r for r in load_manifest() if r['source']=='l2-arctic' or
            (r['source']=='speechocean762' and r['split']=='test' and
             (r['speaker'] in calibration or (r['speaker'] in reporting and r['age'] is not None and 6<=r['age']<=12)))]
    return rows,calibration


def posteriors():
    if (RUN/'posterior-summary.json').exists():
        raise FileExistsError('Posteriors complete; use saved files')
    if not (RUN/'result.json').exists():
        raise FileNotFoundError('Selection must complete first')
    start = time.monotonic()
    rows,_ = detection_rows()
    device = device_setup()
    model,backbone = create_model(device)
    model.load_state_dict(torch.load(RUN/'best.pt',weights_only=True)['state'])
    base.extract_features('A',rows,device,backbone)
    del backbone
    if device.type == 'mps':
        torch.mps.empty_cache()
    model.eval()
    dest = RUN/'posteriors'
    dest.mkdir(exist_ok=True)
    predictions = {}
    with torch.inference_mode():
        for i,row in enumerate(rows):
            frames = torch.load(frame_path(row),weights_only=True).to(device)
            logits = model(frames)
            predictions[row['id']] = collapse(logits.argmax(-1).cpu().tolist(),ID_TO_PHONE)
            torch.save(logits.float().log_softmax(-1).cpu(),dest/(row['id'].replace(':','_')+'.pt'))
            if (i+1)%100==0:
                print(f'C posteriors {i+1}/{len(rows)} seconds={time.monotonic()-start:.1f}',flush=True)
    (RUN/'detection-predictions.json').write_text(json.dumps(predictions))
    (RUN/'posterior-summary.json').write_text(json.dumps(dict(utterances=len(rows),wall_seconds=time.monotonic()-start),indent=2))


def detect():
    if (RUN/'detection-result.json').exists():
        raise FileExistsError('Detection complete; reanalyze saved features/curves')
    if not (RUN/'posterior-summary.json').exists():
        raise FileNotFoundError('Extract selected posteriors first')
    torch.set_num_threads(4)
    start = time.monotonic()
    rows,calibration_speakers = detection_rows()
    predictions = json.loads((RUN/'detection-predictions.json').read_text())
    feature_dir = RUN/'gop-features'
    feature_dir.mkdir(exist_ok=True)
    grouped = {'calibration':[],'speech_children':[],'l2':[]}
    excluded, fractions = [],Counter()
    for i,row in enumerate(rows):
        group = 'l2' if row['source']=='l2-arctic' else 'calibration' if row['speaker'] in calibration_speakers else 'speech_children'
        if row['source']=='speechocean762':
            fractions[group] += len(row['canonical'])-len(labels(row))
        feature_path = feature_dir/(row['id'].replace(':','_')+'.json')
        if feature_path.exists():
            cached = json.loads(feature_path.read_text())
            if isinstance(cached,dict):
                excluded.append(cached); continue
            grouped[group].extend(cached); continue
        log_probs = torch.load(RUN/'posteriors'/(row['id'].replace(':','_')+'.pt'),weights_only=True)
        try:
            records = phone_features(row,log_probs,predictions[row['id']])
        except ValueError as error:
            exclusion = dict(id=row['id'],group=group,reason=str(error),phones=len(labels(row)))
            excluded.append(exclusion)
            feature_path.write_text(json.dumps(exclusion))
            continue
        feature_path.write_text(json.dumps(records))
        grouped[group].extend(records)
        if (i+1)%25==0:
            print(f'GOP {i+1}/{len(rows)} seconds={time.monotonic()-start:.1f}',flush=True)
    child_ids = {r['id'] for r in rows if r['source']=='speechocean762' and r['age'] is not None and 6<=r['age']<=12}
    grouped['speech_all_children'] = [p for name in ('calibration','speech_children') for p in grouped[name] if p['id'] in child_ids]
    fractions['speech_all_children'] = sum(len(r['canonical'])-len(labels(r)) for r in rows if r['id'] in child_ids)
    calibration = fit_calibration(grouped['calibration'])
    (RUN/'calibration.json').write_text(json.dumps(calibration,indent=2))
    result = dict(calibration=calibration,excluded=excluded,excluded_fractional_score_phones=dict(fractions),
                  calibration_speakers=sorted(calibration_speakers),
                  l2=summarize(grouped['l2'],calibration),speech_children=summarize(grouped['speech_children'],calibration),
                  speech_all_children=summarize(grouped['speech_all_children'],calibration),
                  wall_seconds=time.monotonic()-start)
    for name,records in grouped.items():
        (RUN/f'detection-{name}-phones.json').write_text(json.dumps(records))
    (RUN/'detection-result.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    brief = {k:v for k,v in result.items() if k not in ('l2','speech_children','speech_all_children')}
    for group in ('l2','speech_children','speech_all_children'):
        brief[group] = {k:v for k,v in result[group].items() if not k.endswith('_curve')}
    print(json.dumps(brief,indent=2),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action',choices=['recognition','posteriors','detect'])
    args = parser.parse_args()
    {'recognition':recognition,'posteriors':posteriors,'detect':detect}[args.action]()
