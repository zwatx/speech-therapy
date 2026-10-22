"""Two fixed-budget candidates. Cached frozen features, single-clip CTC training.

Run candidate A then B, then select. No L2 inference happens until selection.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import random
import time

import torch
from torch import nn
from transformers import Wav2Vec2Model, WavLMModel
from .runtime import (device_setup, snapshot, extractor, waveform, ESPEAK_MODEL,
                      WAVLM_MODEL, collapse)
from .manifest import OUTPUT, load_manifest
from .inventory import PHONE_TO_ID, ID_TO_PHONE, VERSION
from .evaluate import evaluate

SEED = 17
BUDGET = 900
EPOCHS = 30
ACCUMULATION = 16


class UpperCTC(nn.Module):
    def __init__(self, backbone):
        super().__init__()
        self.layers = deepcopy(backbone.encoder.layers[-4:])
        self.norm = deepcopy(backbone.encoder.layer_norm)
        self.head = nn.Linear(backbone.config.hidden_size, 40)

    def forward(self, frames):
        x = frames.unsqueeze(0)
        for layer in self.layers:
            x = layer(x)[0]
        return self.head(self.norm(x))[0]


class LSTMCTC(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(768, 128, batch_first=True, bidirectional=True)
        self.head = nn.Linear(256, 40)

    def forward(self, frames):
        x, _ = self.lstm(frames.unsqueeze(0))
        return self.head(x)[0]


class StopAtUpper(Exception):
    pass


def feature_path(candidate, row):
    return OUTPUT/f'features-{candidate}'/(row['id'].replace(':', '_')+'.pt')


def extract_features(candidate, rows, device, backbone=None):
    """A caches input to stable block20; B caches final frozen WavLM frames."""
    model_id = ESPEAK_MODEL if candidate == 'A' else WAVLM_MODEL
    cache = OUTPUT/f'features-{candidate}'
    cache.mkdir(exist_ok=True)
    identity = dict(model=model_id, revision=snapshot(model_id).name,
                    kind='pre-block20' if candidate == 'A' else 'final-hidden',
                    preprocessing='single-clip-feature-extractor-polyphase16k-v1',
                    manifest_audio={r['id']: r['audio_sha256'] for r in rows})
    identity_path = cache/'identity.json'
    verified_ids = set()
    if identity_path.exists():
        old = json.loads(identity_path.read_text())
        verified_ids = set(old['manifest_audio'])
        for key in ('model', 'revision', 'kind', 'preprocessing'):
            if old[key] != identity[key]:
                raise ValueError('Feature cache configuration mismatch')
        for row in rows:
            previous = old['manifest_audio'].get(row['id'])
            if previous is not None and previous != row['audio_sha256']:
                raise ValueError('Feature cache audio mismatch')
        identity['manifest_audio'].update(old['manifest_audio'])
    missing = [r for r in rows if r['id'] not in verified_ids or not feature_path(candidate, r).exists()]
    if not missing:
        return
    start = time.monotonic()
    if backbone is None:
        cls = Wav2Vec2Model if candidate == 'A' else WavLMModel
        backbone = cls.from_pretrained(str(snapshot(model_id)), local_files_only=True)
    backbone.requires_grad_(False).eval().to(device)
    processor = extractor(model_id)
    captured = []

    def capture(_module, args, kwargs):
        captured.append(args[0].detach())
        raise StopAtUpper()

    hook = backbone.encoder.layers[20].register_forward_pre_hook(capture, with_kwargs=True) if candidate == 'A' else None
    try:
        with torch.inference_mode():
            for index, row in enumerate(missing):
                inputs = waveform(row, processor, device)
                if candidate == 'A':
                    try:
                        backbone(**inputs)
                    except StopAtUpper:
                        pass
                    if len(captured) != 1:
                        raise RuntimeError('Failed to capture frozen block input')
                    frames = captured.pop()[0].cpu().contiguous()
                else:
                    frames = backbone(**inputs).last_hidden_state[0].cpu().contiguous()
                torch.save(frames, feature_path(candidate, row))
                if (index+1) % 25 == 0:
                    print(f'features {candidate} {index+1}/{len(missing)} elapsed={time.monotonic()-start:.1f}s', flush=True)
    finally:
        if hook:
            hook.remove()
    identity_path.write_text(json.dumps(identity, indent=2))
    print(f'features {candidate} complete seconds={time.monotonic()-start:.2f}', flush=True)


def load_frames(candidate, rows):
    return {r['id']: torch.load(feature_path(candidate, r), weights_only=True) for r in rows}


def predict(model, rows, frames, device):
    model.eval()
    output = {}
    with torch.no_grad():
        for row in rows:
            ids = model(frames[row['id']].to(device)).argmax(-1).cpu().tolist()
            output[row['id']] = collapse(ids, ID_TO_PHONE)
    return output


def create_model(candidate, device):
    if candidate == 'B':
        return LSTMCTC().to(device), None
    backbone = Wav2Vec2Model.from_pretrained(str(snapshot(ESPEAK_MODEL)), local_files_only=True)
    if not backbone.config.do_stable_layer_norm:
        raise ValueError('Candidate A cache requires stable layer norm encoder')
    return UpperCTC(backbone).to(device), backbone


def verify_upper_cache(model, backbone, row, device):
    backbone.requires_grad_(False).eval().to(device)
    model.eval()
    with torch.no_grad():
        full = backbone(**waveform(row, extractor(ESPEAK_MODEL), device)).last_hidden_state[0]
        cached = torch.load(feature_path('A', row), weights_only=True).to(device).unsqueeze(0)
        for layer in model.layers:
            cached = layer(cached)[0]
        difference = (full-model.norm(cached)[0]).abs().max().item()
    if difference > 1e-4:
        raise ValueError(f'Cached/full encoder mismatch: {difference}')
    print(f'cache parity max_abs={difference}', flush=True)
    return difference


def train(candidate):
    preparation_start = time.monotonic()
    device = device_setup(SEED)
    rows = [r for r in load_manifest() if r['source'] == 'speechocean762' and r['all_correct']]
    train_rows = [r for r in rows if r['split'] == 'train']
    dev_rows = [r for r in rows if r['split'] == 'test']
    model, backbone = create_model(candidate, device)
    extract_features(candidate, rows, device, backbone)
    parity = verify_upper_cache(model, backbone, rows[0], device) if candidate == 'A' else None
    del backbone
    if device.type == 'mps':
        torch.mps.empty_cache()
    frames = load_frames(candidate, rows)
    targets = {r['id']: torch.tensor([PHONE_TO_ID[p] for p in r['perceived']], dtype=torch.long) for r in train_rows}
    for row in train_rows:
        labels = targets[row['id']].tolist()
        minimum = len(labels)+sum(a == b for a, b in zip(labels, labels[1:]))
        if len(frames[row['id']]) < minimum:
            raise ValueError('CTC target cannot align to encoder frames')
    if candidate == 'A':
        groups = [dict(params=list(model.layers.parameters())+list(model.norm.parameters()), lr=1e-5),
                  dict(params=model.head.parameters(), lr=1e-3)]
    else:
        groups = [dict(params=model.parameters(), lr=1e-3)]
    optimizer = torch.optim.AdamW(groups, weight_decay=.01)
    loss_fn = nn.CTCLoss(blank=0, zero_infinity=False)
    run = OUTPUT/f'candidate-{candidate}'
    run.mkdir(exist_ok=True)
    settings = dict(candidate=candidate, seed=SEED, budget_seconds=BUDGET, max_epochs=EPOCHS,
                    accumulation=ACCUMULATION, train_utterances=len(train_rows), dev_utterances=len(dev_rows),
                    trainable_parameters=sum(p.numel() for p in model.parameters() if p.requires_grad),
                    device=str(device), inventory=VERSION, cache_parity_max_abs=parity,
                    preparation_seconds=time.monotonic()-preparation_start)
    (run/'settings.json').write_text(json.dumps(settings, indent=2))
    # Cache extraction executes encoder RNG draws even in eval mode. Reset here
    # so warm and cold cache runs use the same training dropout sequence.
    torch.manual_seed(SEED)
    start = time.monotonic()
    best, history, steps, longest_update, dev_seconds = float('inf'), [], 0, 0., 0.
    for epoch in range(1, EPOCHS+1):
        # Reserve previous measured evaluation and update cost, plus checkpoint margin.
        if history and time.monotonic()-start+dev_seconds+longest_update+5 >= BUDGET:
            break
        order = list(train_rows)
        random.Random(SEED+epoch).shuffle(order)
        total_loss, seen = 0., 0
        model.train()
        for offset in range(0, len(order), ACCUMULATION):
            if time.monotonic()-start+dev_seconds+longest_update+5 >= BUDGET:
                break
            update_start = time.monotonic()
            group = order[offset:offset+ACCUMULATION]
            optimizer.zero_grad(set_to_none=True)
            for row in group:
                logits = model(frames[row['id']].to(device))
                # CPU CTC supports MPS autograd via the differentiable copy.
                log_probs = logits.float().log_softmax(-1).cpu().unsqueeze(1)
                target = targets[row['id']]
                loss = loss_fn(log_probs, target, torch.tensor([len(logits)]), torch.tensor([len(target)]))
                if not torch.isfinite(loss):
                    raise ValueError(f'Nonfinite CTC loss: {row["id"]}')
                (loss/len(group)).backward()
                total_loss += loss.item(); seen += 1
            nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optimizer.step(); steps += 1
            longest_update = max(longest_update, time.monotonic()-update_start)
        evaluation_start = time.monotonic()
        predictions = predict(model, dev_rows, frames, device)
        metrics = evaluate(dev_rows, predictions)
        dev_seconds = max(dev_seconds, time.monotonic()-evaluation_start)
        entry = dict(epoch=epoch, seen=seen, steps=steps, loss=total_loss/seen if seen else None,
                     dev_PER=metrics['PER'], seconds=time.monotonic()-start)
        history.append(entry)
        if metrics['PER'] < best:
            best = metrics['PER']
            torch.save(dict(state={k: v.detach().cpu() for k, v in model.state_dict().items()},
                            epoch=epoch, metrics=metrics, settings=settings), run/'best.pt')
            (run/'dev-predictions.json').write_text(json.dumps(predictions))
        (run/'history.json').write_text(json.dumps(history, indent=2))
        print(json.dumps(entry), flush=True)
        if seen < len(order):
            break
    result = dict(**settings, training_wall_seconds=time.monotonic()-start, steps=steps,
                  best_dev_PER=best, epochs=len(history), history=history)
    if result['training_wall_seconds'] > BUDGET:
        result['budget_overrun_seconds'] = result['training_wall_seconds']-BUDGET
    (run/'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)


def select():
    if any((OUTPUT/name).exists() for name in ('selected-result.json', 'selected-l2-predictions.json')):
        raise FileExistsError('Selected L2 evaluation artifacts already exist; refusing a repeat evaluation')
    device = device_setup(SEED)
    results = {c: json.loads((OUTPUT/f'candidate-{c}/result.json').read_text()) for c in ('A', 'B')}
    chosen = min(('B', 'A'), key=lambda c: results[c]['best_dev_PER'])
    model, backbone = create_model(chosen, device)
    checkpoint = torch.load(OUTPUT/f'candidate-{chosen}/best.pt', weights_only=True)
    model.load_state_dict(checkpoint['state'])
    rows = load_manifest()
    dev = [r for r in rows if r['source'] == 'speechocean762' and r['split'] == 'test' and r['all_correct']]
    # Reloaded checkpoint must reproduce the saved dev hypotheses exactly.
    dev_predictions = predict(model, dev, load_frames(chosen, dev), device)
    saved = json.loads((OUTPUT/f'candidate-{chosen}/dev-predictions.json').read_text())
    if dev_predictions != saved:
        raise ValueError('Checkpoint replay differs from saved dev predictions')
    l2 = [r for r in rows if r['source'] == 'l2-arctic']
    extract_features(chosen, l2, device, backbone)
    del backbone
    start = time.monotonic()
    predictions = predict(model, l2, load_frames(chosen, l2), device)
    result = dict(selected=chosen, selected_epoch=checkpoint['epoch'], selection_metric='SpeechOcean test-speaker dev PER',
                  checkpoint_replay='exact greedy token sequences on all dev utterances',
                  candidates={c: results[c]['best_dev_PER'] for c in results},
                  l2=evaluate(l2, predictions), speech_dev=evaluate(dev, dev_predictions),
                  l2_head_inference_seconds=time.monotonic()-start)
    result['per_speaker'] = {speaker: evaluate([r for r in l2 if r['speaker'] == speaker], predictions)
                             for speaker in sorted({r['speaker'] for r in l2})}
    (OUTPUT/'selected-l2-predictions.json').write_text(json.dumps(predictions))
    (OUTPUT/'selected-result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate', choices=['A', 'B', 'select'])
    args = parser.parse_args()
    select() if args.candidate == 'select' else train(args.candidate)
