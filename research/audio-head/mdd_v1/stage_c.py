"""Single declared JIBO adaptation run; frozen features reused from candidate A."""
import argparse
import hashlib
import json
import random
import os
import time

import torch
from torch import nn
from . import train_ctc as base
from .jibo import RUN, read_interval
from .manifest import OUTPUT, load_manifest
from .runtime import device_setup, extractor, ESPEAK_MODEL, collapse
from .inventory import PHONE_TO_ID, ID_TO_PHONE
from .evaluate import evaluate
from torch.nn import functional as F
from transformers import Wav2Vec2Model
from .runtime import snapshot

BUDGET = 1910
PRIOR_FITTING_SECONDS = 667
RESOURCE_PROBE_RESERVE_SECONDS = 120
EPOCHS = 8



class BucketedUpperCTC(base.UpperCTC):
    """Mask padding to bound MPS attention graph shapes; true frames unchanged."""
    mask_value = -10000.

    def forward(self, frames):
        length = len(frames)
        padded_length = ((length+63)//64)*64
        x = F.pad(frames,(0,0,0,padded_length-length)).unsqueeze(0)
        mask = x.new_zeros((1,1,1,padded_length))
        mask[...,length:] = self.mask_value
        for layer in self.layers:
            x = layer(x,attention_mask=mask)[0]
        return self.head(self.norm(x))[0,:length]


def create_model(device):
    backbone = Wav2Vec2Model.from_pretrained(str(snapshot(ESPEAK_MODEL)),local_files_only=True)
    if not backbone.config.do_stable_layer_norm:
        raise ValueError('Stage C requires stable layer norm')
    model = BucketedUpperCTC(backbone).to(device)
    for layer in model.layers:
        layer.attention.config._attn_implementation = 'eager'
    return model,backbone


def jibo_rows():
    return load_manifest(RUN/'manifest.jsonl')


def prepare(rows, model, backbone, device):
    """Reuse canonical A cache format; only new JIBO crops need custom reading."""
    speech = [r for r in rows if r['source'] != 'jibo']
    base.extract_features('A', speech, device, backbone)
    cache = RUN/'features'
    cache.mkdir(exist_ok=True)
    identity_path = cache/'identity.json'
    identity = dict(kind='pre-block20', interval_rounding='nearest-sample-clamped-v1',
                    rows={r['id']: r['audio_sha256'] for r in rows if r['source'] == 'jibo'})
    if identity_path.exists() and json.loads(identity_path.read_text()) != identity:
        raise ValueError('Stage C feature identity mismatch')
    processor = extractor(ESPEAK_MODEL)
    backbone.requires_grad_(False).eval().to(device)
    captured = []

    def capture(_module, args):
        captured.append(args[0].detach())
        raise base.StopAtUpper()

    hook = backbone.encoder.layers[20].register_forward_pre_hook(capture)
    start = time.monotonic()
    try:
        with torch.inference_mode():
            for i, row in enumerate(r for r in rows if r['source'] == 'jibo'):
                path = cache/(row['id'].replace(':', '_')+'.pt')
                if path.exists() and identity_path.exists():
                    continue
                inputs = processor(read_interval(row), sampling_rate=16000, return_tensors='pt')
                try:
                    backbone(**{k:v.to(device) for k,v in inputs.items()})
                except base.StopAtUpper:
                    pass
                if len(captured) != 1:
                    raise ValueError('Missing frozen frames')
                torch.save(captured.pop()[0].cpu().contiguous(), path)
                if (i+1)%100 == 0:
                    print(f'C features {i+1} seconds={time.monotonic()-start:.1f}', flush=True)
    finally:
        hook.remove()
    identity_path.write_text(json.dumps(identity))


def frame_path(row):
    return RUN/'features'/(row['id'].replace(':', '_')+'.pt') if row['source'] == 'jibo' else base.feature_path('A', row)


def load_frames(rows):
    return {r['id']: torch.load(frame_path(r), weights_only=True) for r in rows}


def train():
    if (RUN/'result.json').exists() or (RUN/'best.pt').exists():
        raise FileExistsError('Stage C fit already started/completed')
    (RUN/'train.pid').write_text(str(os.getpid()))
    prep_start = time.monotonic()
    device = device_setup(17)
    jibo = jibo_rows()
    speech = [r for r in load_manifest() if r['source'] == 'speechocean762' and r['all_correct']]
    train_rows = [r for r in jibo+speech if r['split'] == 'train']
    dev = [r for r in jibo if r['split'] == 'dev']
    # Prepare held-out feature frames without using their labels or inference;
    # model selection remains restricted to JIBO dev.
    model, backbone = create_model(device)
    checkpoint = torch.load(OUTPUT/'candidate-A/best.pt', weights_only=True)
    model.load_state_dict(checkpoint['state'])
    prepare(jibo+speech, model, backbone, device)
    del backbone
    if device.type == 'mps':
        torch.mps.empty_cache()
    frames = load_frames(train_rows+dev)
    targets = {r['id']: torch.tensor([PHONE_TO_ID[p] for p in r['perceived']], dtype=torch.long) for r in train_rows}
    invalid = []
    for r in train_rows:
        t = targets[r['id']].tolist()
        if len(frames[r['id']]) < len(t)+sum(a == b for a,b in zip(t,t[1:])):
            invalid.append(r['id'])
    if invalid:
        raise ValueError(f'Impossible training CTC targets: {invalid}')
    settings = dict(seed=17, budget_seconds=BUDGET, max_epochs=EPOCHS, accumulation=16,
                    encoder_lr=1e-5, head_lr=1e-4, train_utterances=len(train_rows),
                    prior_fitting_seconds=PRIOR_FITTING_SECONDS,resource_probe_reserve_seconds=RESOURCE_PROBE_RESERVE_SECONDS,
                    padding_bucket_frames=64,
                    jibo_train=sum(r['source']=='jibo' for r in train_rows), speech_train=222,
                    initialization_sha256=hashlib.sha256((OUTPUT/'candidate-A/best.pt').read_bytes()).hexdigest(),
                    preparation_seconds=time.monotonic()-prep_start, device=str(device),
                    trainable_parameters=sum(p.numel() for p in model.parameters()))
    (RUN/'settings.json').write_text(json.dumps(settings, indent=2))
    optimizer = torch.optim.AdamW([
        dict(params=list(model.layers.parameters())+list(model.norm.parameters()), lr=1e-5),
        dict(params=model.head.parameters(), lr=1e-4)], weight_decay=.01)
    loss_fn = nn.CTCLoss(blank=0, zero_infinity=False)
    torch.manual_seed(17)
    start = time.monotonic()
    predictions = base.predict(model, dev, frames, device)
    metrics = evaluate(dev, predictions)
    best = metrics['PER']
    best_epoch = 0
    torch.save(dict(state={k:v.detach().cpu() for k,v in model.state_dict().items()}, epoch=0, metrics=metrics), RUN/'best.pt')
    (RUN/'dev-predictions.json').write_text(json.dumps(predictions))
    history = [dict(epoch=0, dev_PER=best, seconds=time.monotonic()-start)]
    dev_seconds = time.monotonic()-start
    longest_update, steps = 0., 0
    for epoch in range(1,EPOCHS+1):
        if time.monotonic()-start+dev_seconds+longest_update+10 >= BUDGET:
            break
        order = list(train_rows)
        random.Random(17+epoch).shuffle(order)
        model.train()
        seen, total = 0, 0.
        for offset in range(0,len(order),16):
            if time.monotonic()-start+dev_seconds+longest_update+10 >= BUDGET:
                break
            update_start = time.monotonic()
            group = order[offset:offset+16]
            optimizer.zero_grad(set_to_none=True)
            for r in group:
                logits = model(frames[r['id']].to(device))
                target = targets[r['id']]
                loss = loss_fn(logits.float().log_softmax(-1).cpu().unsqueeze(1), target,
                               torch.tensor([len(logits)]), torch.tensor([len(target)]))
                if not torch.isfinite(loss):
                    raise ValueError(f'Nonfinite loss: {r["id"]}')
                (loss/len(group)).backward()
                total += loss.item(); seen += 1
            nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True)
            optimizer.step(); steps += 1
            del logits,loss
            if device.type == 'mps':
                torch.mps.empty_cache()
            longest_update = max(longest_update,time.monotonic()-update_start)
            if steps%50 == 0:
                print(f'C epoch={epoch} seen={seen} steps={steps} seconds={time.monotonic()-start:.1f} '+
                      (f'mps_tensor_GB={torch.mps.current_allocated_memory()/1e9:.2f} driver_GB={torch.mps.driver_allocated_memory()/1e9:.2f}' if device.type=='mps' else ''),flush=True)
        evaluation_start = time.monotonic()
        predictions = base.predict(model, dev, frames, device)
        metrics = evaluate(dev,predictions)
        dev_seconds = max(dev_seconds,time.monotonic()-evaluation_start)
        if metrics['PER'] < best:
            best, best_epoch = metrics['PER'], epoch
            torch.save(dict(state={k:v.detach().cpu() for k,v in model.state_dict().items()}, epoch=epoch, metrics=metrics), RUN/'best.pt')
            (RUN/'dev-predictions.json').write_text(json.dumps(predictions))
        entry = dict(epoch=epoch,seen=seen,steps=steps,loss=total/seen if seen else None,
                     dev_PER=metrics['PER'],seconds=time.monotonic()-start)
        history.append(entry)
        (RUN/'history.json').write_text(json.dumps(history,indent=2))
        print(json.dumps(entry),flush=True)
        if seen < len(order):
            break
    result = dict(**settings, best_dev_PER=best, best_epoch=best_epoch, steps=steps,
                  training_wall_seconds=time.monotonic()-start,history=history)
    result['cumulative_budget_charge_seconds'] = result['training_wall_seconds']+PRIOR_FITTING_SECONDS+RESOURCE_PROBE_RESERVE_SECONDS
    (RUN/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__':
    train()
