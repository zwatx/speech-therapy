"""Stage D orchestration: prepare train/cal only, select, then evaluate once."""
import argparse
import hashlib
import json
import time

import torch

from . import train_ctc as base
from .inventory import normalize_arpabet
from .jibo import RUN as STAGE_C
from .manifest import OUTPUT, ROOT, load_manifest
from .runtime import device_setup
from .stage_d_features import SCHEMA, FEATURE_NAMES, extract

RUN = OUTPUT/'stage-d'
REPORT = ROOT.parents[1]/'work/mdd-v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def rows_by_group():
    split = json.loads((STAGE_C/'speech-detection-split.json').read_text())
    cal, reporting = set(split['calibration_speakers']), set(split['reporting_speakers'])
    if cal & reporting:
        raise ValueError('Calibration/reporting speaker overlap')
    rows = load_manifest()
    train = [r for r in rows if r['source'] == 'speechocean762' and r['split'] == 'train']
    train_speakers = {r['speaker'] for r in train}
    if len(train) != 2500 or train_speakers & (cal | reporting):
        raise ValueError('Unexpected official train split or speaker leakage')
    groups = dict(train=train, calibration=[], speech_children=[], l2=[])
    for row in rows:
        if row['source'] == 'l2-arctic':
            if row['speaker'] not in ('YDCK', 'ZHAA', 'ASI', 'YBAA'):
                raise ValueError('Unauthorized L2 speaker')
            groups['l2'].append(row)
        elif row['split'] == 'test':
            if row['speaker'] in cal:
                groups['calibration'].append(row)
            elif row['speaker'] in reporting and row['age'] is not None and 6 <= row['age'] <= 12:
                groups['speech_children'].append(row)
    if {r['speaker'] for r in groups['calibration']} != cal:
        raise ValueError('Missing calibration speaker')
    return groups


def identity():
    return dict(schema=SCHEMA, feature_names=FEATURE_NAMES,
                extractor_sha256=sha(ROOT/'mdd_v1/stage_d_features.py'),
                checkpoint_sha256=sha(STAGE_C/'best.pt'),
                manifest_sha256=sha(OUTPUT/'manifest.jsonl'),
                split_sha256=sha(STAGE_C/'speech-detection-split.json'),
                words_sha256=sha(ROOT/'outputs/speechocean762-metadata-v1/resource/scores.json'))


def check_identity():
    RUN.mkdir(exist_ok=True)
    path = RUN/'identity.json'
    current = identity()
    if path.exists() and json.loads(path.read_text()) != current:
        raise ValueError('Stage D cache identity mismatch; do not overwrite evidence')
    if not path.exists():
        save_json(path, current)


def train_posteriors(rows):
    """Only new train posteriors; calibration/reporting reuse frozen Stage C."""
    from .stage_c import create_model
    dest = RUN/'train-posteriors'
    dest.mkdir(exist_ok=True)
    missing = [r for r in rows if not (dest/(r['id'].replace(':', '_')+'.pt')).exists()]
    if not missing:
        return
    start = time.monotonic()
    device = device_setup(43)
    model, backbone = create_model(device)
    model.load_state_dict(torch.load(STAGE_C/'best.pt', weights_only=True)['state'])
    base.extract_features('A', missing, device, backbone)
    del backbone
    if device.type == 'mps':
        torch.mps.empty_cache()
    model.eval()
    with torch.inference_mode():
        for i, row in enumerate(missing):
            frames = torch.load(base.feature_path('A', row), weights_only=True).to(device)
            values = model(frames).float().log_softmax(-1).cpu()
            path = dest/(row['id'].replace(':', '_')+'.pt')
            torch.save(values, path.with_suffix('.tmp'))
            path.with_suffix('.tmp').replace(path)
            if (i+1) % 50 == 0:
                print(f'D train posteriors {i+1}/{len(missing)} seconds={time.monotonic()-start:.1f}', flush=True)
                if device.type == 'mps':
                    torch.mps.empty_cache()
    save_json(RUN/'posterior-summary.json', dict(utterances=len(rows), newly_extracted=len(missing),
                                               wall_seconds=time.monotonic()-start, device=str(device)))


def build_group(name, rows, scores):
    dataset_path = RUN/f'{name}.pt'
    if dataset_path.exists():
        return
    start = time.monotonic()
    dest = RUN/'phone-features'
    dest.mkdir(exist_ok=True)
    matrices, records, excluded = [], [], []
    fractional, clipped, missing_words = 0, 0, 0
    for i, row in enumerate(rows):
        path = dest/(row['id'].replace(':', '_')+'.pt')
        if path.exists():
            cached = torch.load(path, weights_only=True)
        else:
            word_groups = None
            if row['source'] == 'speechocean762':
                word_groups = [[normalize_arpabet(p) for p in w['phones']] for w in scores[row['id'][3:]]['words']]
            posterior_dir = RUN/'train-posteriors' if name == 'train' else STAGE_C/'posteriors'
            log_probs = torch.load(posterior_dir/(row['id'].replace(':', '_')+'.pt'), weights_only=True)
            try:
                x, phone_records, count = extract(row, log_probs, word_groups)
                cached = dict(x=torch.from_numpy(x), records=phone_records, clipped=count)
            except ValueError as error:
                # Fail explicitly rather than quietly change a fixed evaluation denominator.
                save_json(RUN/f'failure-{name}.json', dict(id=row['id'], reason=str(error)))
                raise
            torch.save(cached, path.with_suffix('.tmp'))
            path.with_suffix('.tmp').replace(path)
        keep = [j for j, record in enumerate(cached['records']) if record['error'] is not None]
        fractional += len(cached['records']) - len(keep)
        clipped += cached['clipped']
        missing_words += sum(float(cached['x'][j, FEATURE_NAMES.index('word_metadata_present')]) == 0 for j in keep)
        matrices.append(cached['x'][keep])
        records.extend(cached['records'][j] for j in keep)
        if (i+1) % 100 == 0:
            print(f'D features {name} {i+1}/{len(rows)} seconds={time.monotonic()-start:.1f}', flush=True)
    data = dict(x=torch.cat(matrices), records=records,
                summary=dict(utterances=len(rows), phones=len(records), errors=sum(r['error'] for r in records),
                             speakers=len({r['speaker'] for r in records}),
                             excluded_fractional=fractional, clipped_ratios=clipped,
                             missing_word_metadata_phones=missing_words, excluded=excluded,
                             wall_seconds=time.monotonic()-start))
    torch.save(data, dataset_path)
    save_json(RUN/f'{name}-summary.json', data['summary'])


def prepare():
    if (RUN/'prepare-result.json').exists():
        raise FileExistsError('Preparation complete; use saved features')
    check_identity()
    torch.set_num_threads(4)
    start = time.monotonic()
    groups = rows_by_group()
    train_posteriors(groups['train'])
    scores = json.loads((ROOT/'outputs/speechocean762-metadata-v1/resource/scores.json').read_text())
    for name in ('train', 'calibration'):
        build_group(name, groups[name], scores)
    save_json(RUN/'prepare-result.json', dict(wall_seconds=time.monotonic()-start))


def load_group(name):
    data = torch.load(RUN/f'{name}.pt', weights_only=True)
    return data['x'].numpy().astype('float64'), data['records']


def evaluate():
    from .stage_d_models import predict_selected
    from .stage_d_metrics import summarize
    from threadpoolctl import threadpool_limits
    if (RUN/'evaluation-started.json').exists() or (RUN/'evaluation-result.json').exists():
        raise FileExistsError('Stage D reporting already started; use saved selected predictions')
    if not (RUN/'selection.json').exists():
        raise FileNotFoundError('Freeze selection, Platt fit and threshold before reporting')
    check_identity()
    torch.set_num_threads(4)
    start = time.monotonic()
    groups = rows_by_group()
    scores = json.loads((ROOT/'outputs/speechocean762-metadata-v1/resource/scores.json').read_text())
    # Feature creation is label-blind; no model predictions until both caches exist.
    for name in ('speech_children', 'l2'):
        build_group(name, groups[name], scores)
    save_json(RUN/'evaluation-started.json', dict(selection_sha256=sha(RUN/'selection.json')))
    result = {}
    selection = json.loads((RUN/'selection.json').read_text())
    for name in ('speech_children', 'l2'):
        x, records = load_group(name)
        with threadpool_limits(limits=4):
            logits = predict_selected(x, selection)
        saved = [dict(**record, logit=float(score)) for record, score in zip(records, logits)]
        save_json(RUN/f'predictions-{name}.json', saved)
        result[name] = summarize(records, logits, selection['threshold'], bootstrap=True)
        save_json(RUN/f'result-{name}.json', result[name])
    result['wall_seconds'] = time.monotonic()-start
    save_json(RUN/'evaluation-result.json', result)
    print(json.dumps({k:{a:b for a,b in v.items() if a not in ('pr_curve','coverage_curve','per_phone')}
                      for k,v in result.items() if isinstance(v,dict)}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'fit', 'evaluate'])
    args = parser.parse_args()
    if args.action == 'fit':
        from .stage_d_models import fit
        fit()
    else:
        {'prepare': prepare, 'evaluate': evaluate}[args.action]()
