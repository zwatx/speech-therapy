"""Grouped-speaker training of research-only multi-phone rating distributions.

Only inner speaker validation can select an epoch. Outer folds are evaluated
separately after an explicit fixed-epoch refit. No author-test data is loaded.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import random
import time

import numpy as np
import torch
from torch.nn.utils.rnn import pad_sequence

from multiphone_cache import atomic_json, digest, valid_frames
from multiphone_models import MeanPoolPhoneRatingHead, AttentionPhoneRatingHead

HERE = Path(__file__).resolve().parent
HEADS = {'mean': MeanPoolPhoneRatingHead, 'attention': AttentionPhoneRatingHead}


def valid_counts(counts: np.ndarray) -> bool:
    return (counts.ndim == 2 and counts.shape[1] == 3 and np.isfinite(counts).all()
            and (counts >= 0).all() and (counts == np.floor(counts)).all()
            and (counts.sum(1) == 5).all())


def save_checkpoint(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    torch.save(value, temporary)
    temporary.replace(path)


def verify_partitions(cohort: dict, fold: dict) -> None:
    rows = cohort['rows']
    for left, right in [('outerFitRows', 'outerHoldoutRows'), ('innerFitRows', 'innerValidationRows')]:
        a, b = fold[left], fold[right]
        if (not a or not b or len(set(a)) != len(a) or len(set(b)) != len(b) or set(a) & set(b)
                or any(not 0 <= i < len(rows) for i in a+b)):
            raise ValueError('Invalid row partitions')
        for key in ('clipId', 'speakerId'):
            if {rows[i][key] for i in a} & {rows[i][key] for i in b}:
                raise ValueError(f'{key} crosses split boundary')
    if set(fold['innerFitRows']) | set(fold['innerValidationRows']) != set(fold['outerFitRows']):
        raise ValueError('Inner partition does not exactly subdivide outer fit')


class StudyData:
    def __init__(self, cohort: dict, cache: Path, selected_rows: list[int]):
        self.cohort = cohort
        self.rows = cohort['rows']
        self.grouped = defaultdict(list)
        for i in selected_rows:
            row = self.rows[i]
            if not row['trainingEligible'] or not valid_counts(np.asarray([row['raterCounts']], dtype=float)):
                raise ValueError('Unsupported target or invalid five-rater label')
            self.grouped[row['clipIndex']].append(i)
        self.clip_ids = sorted(self.grouped)
        config = json.loads((cache/'config.json').read_text())
        index = json.loads((cache/'index.json').read_text())
        if index.get('complete') is not True or index['configSha256'] != digest(cache/'config.json'):
            raise ValueError('Feature cache is incomplete or config changed')
        self.features = {}
        for i in self.clip_ids:
            clip = cohort['clips'][i]
            entry = index['entries'][clip['id']]
            path = cache/entry['path']
            if not path.resolve().is_relative_to(cache.resolve()) or digest(path) != entry['sha256']:
                raise ValueError('Feature path or digest invalid')
            with np.load(path, allow_pickle=False) as saved:
                frames = saved['frames']
                if (not valid_frames(frames) or str(saved['audio_sha256']) != clip['audioSha256']
                        or str(saved['config_sha256']) != index['configSha256']):
                    raise ValueError('Feature/WAV binding mismatch')
            self.features[i] = torch.from_numpy(frames.copy())
        self.config = config
        self.index_sha256 = digest(cache/'index.json')

    def normalization(self, clip_ids: list[int]) -> tuple[torch.Tensor, torch.Tensor]:
        # Fit-only frame moments; no held-out features contribute.
        sums = torch.zeros(768, dtype=torch.float64)
        squares = torch.zeros(768, dtype=torch.float64)
        count = 0
        for i in clip_ids:
            frames = self.features[i].double()
            sums += frames.sum(0)
            squares += frames.square().sum(0)
            count += len(frames)
        mean = sums/count
        std = (squares/count-mean.square()).clamp_min(1e-8).sqrt()
        return mean.float(), std.float()

    def batch(self, clip_ids: list[int], selected: set[int], mean: torch.Tensor,
              std: torch.Tensor, device: str):
        frames = [(self.features[i]-mean)/std for i in clip_ids]
        features = pad_sequence(frames, batch_first=True).to(device)
        frame_mask = torch.arange(features.shape[1])[None, :] < torch.tensor([len(f) for f in frames])[:, None]
        row_lists = [[r for r in self.grouped[i] if r in selected] for i in clip_ids]
        if not all(row_lists):
            raise ValueError('Batch contains a clip with no selected targets')
        max_targets = max(map(len, row_lists))
        phones = torch.full((len(clip_ids), max_targets), -1, dtype=torch.long)
        targets = torch.zeros((len(clip_ids), max_targets, 3))
        target_mask = torch.zeros((len(clip_ids), max_targets), dtype=torch.bool)
        row_ids = []
        for b, row_list in enumerate(row_lists):
            for k, r in enumerate(row_list):
                row = self.rows[r]
                phones[b,k] = row['targetId']
                targets[b,k] = torch.tensor(row['raterCounts'], dtype=torch.float32)/5
                target_mask[b,k] = True
                row_ids.append(r)
        return features, frame_mask.to(device), phones.to(device), target_mask.to(device), targets.to(device), row_ids


def distribution_metrics(probabilities: np.ndarray, counts: np.ndarray) -> dict:
    if (probabilities.shape != counts.shape or probabilities.ndim != 2 or probabilities.shape[1] != 3
            or not len(counts) or not np.isfinite(probabilities).all()
            or not np.allclose(probabilities.sum(1), 1, atol=1e-5) or np.any(probabilities < 0)
            or not valid_counts(counts)):
        raise ValueError('Invalid metrics input')
    truth = counts/5.0
    prediction = probabilities@np.array([0.,1.,2.])
    expected = truth@np.array([0.,1.,2.])
    correlation = (float(np.corrcoef(prediction, expected)[0,1])
                   if np.std(prediction)>1e-12 and np.std(expected)>1e-12 else None)
    return {'examples': len(counts),
            'perRaterLogLoss': float(-(truth*np.log(probabilities.clip(1e-12,1))).sum(1).mean()),
            'perRaterBrier': float((probabilities**2-2*probabilities*truth).sum(1).mean()+1),
            'meanRatingMSE': float(np.square(prediction-expected).mean()),
            'meanRatingMAE': float(np.abs(prediction-expected).mean()), 'meanRatingPCC': correlation}


@torch.no_grad()
def evaluate(model, data: StudyData, selected_rows: list[int], mean, std, device: str, batch_size: int) -> tuple[dict,dict]:
    selected = set(selected_rows)
    clips = sorted({data.rows[r]['clipIndex'] for r in selected_rows})
    model.eval()
    outputs = {}
    for offset in range(0,len(clips),batch_size):
        features, frame_mask, phones, target_mask, _, row_ids = data.batch(clips[offset:offset+batch_size],selected,mean,std,device)
        logits = model(features,frame_mask,phones,target_mask)
        values = logits.softmax(-1)[target_mask].cpu().numpy()
        outputs.update(zip(row_ids,values))
    ordered = sorted(outputs)
    p = np.asarray([outputs[i] for i in ordered],dtype=np.float64)
    counts = np.asarray([data.rows[i]['raterCounts'] for i in ordered],dtype=np.float64)
    metrics = distribution_metrics(p,counts)
    per_target = {}
    for target in sorted({data.rows[i]['targetPhone'] for i in ordered}):
        mask = np.asarray([data.rows[i]['targetPhone']==target for i in ordered])
        per_target[target] = distribution_metrics(p[mask],counts[mask])
    metrics['perTarget'] = per_target
    metrics['macroTargetLogLoss'] = float(np.mean([v['perRaterLogLoss'] for v in per_target.values()]))
    for name, condition in [('ages6to12',lambda row:6<=row['age']<=12),('ages13plus',lambda row:row['age']>=13)]:
        mask = np.asarray([condition(data.rows[i]) for i in ordered])
        metrics[name] = distribution_metrics(p[mask],counts[mask]) if mask.any() else None
    predictions = {'rowIndices':ordered,'probabilities':p.tolist()}
    return metrics,predictions


def train(args) -> dict:
    if args.epochs<1 or args.batch_size<1 or args.patience<1 or not 0<args.lr<=0.1:
        raise ValueError('Invalid optimizer budget')
    if args.device=='mps' and not torch.backends.mps.is_available():
        raise ValueError('MPS unavailable')
    if not args.output.resolve().is_relative_to((HERE/'outputs').resolve()):
        raise ValueError('Keep artifacts in ignored research outputs')
    if args.output.exists():
        raise ValueError('Output exists; choose a unique run directory')
    torch.set_num_threads(args.threads)
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    cohort = json.loads(args.cohort.read_text())
    splits = json.loads(args.splits.read_text())
    cohort_sha = hashlib.sha256(json.dumps(cohort, sort_keys=True, separators=(',', ':'),
                                          allow_nan=False).encode()).hexdigest()
    if splits['cohortCanonicalSha256'] != cohort_sha:
        raise ValueError('Split indices are not bound to this exact cohort')
    fold = splits['folds'][args.fold]
    verify_partitions(cohort,fold)
    fit_rows = fold['innerFitRows'] if args.phase=='inner' else fold['outerFitRows']
    eval_rows = fold['innerValidationRows'] if args.phase=='inner' else fold['outerHoldoutRows']
    all_rows = fit_rows + eval_rows
    started = time.perf_counter()
    data = StudyData(cohort,args.cache,all_rows)
    if data.config['cohortSha256'] != digest(args.cohort):
        raise ValueError('Cohort differs from feature extraction')
    fit_clips = sorted({data.rows[r]['clipIndex'] for r in fit_rows})
    selected = set(fit_rows)
    mean,std = data.normalization(fit_clips)
    model = HEADS[args.head](hidden_dim=args.hidden,dropout=args.dropout).to(args.device)
    optimizer = torch.optim.AdamW(model.parameters(),lr=args.lr,weight_decay=args.weight_decay)
    args.output.mkdir(parents=True)
    config = {k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()}
    config.update({'cohortSha256':digest(args.cohort),'splitsSha256':digest(args.splits),
                   'cacheIndexSha256':data.index_sha256,'torch':torch.__version__,
                   'sourceSha256':{p.name:digest(p) for p in [Path(__file__),HERE/'multiphone_models.py',HERE/'multiphone_cache.py']},
                   'authorPartition':'train','label':'five-rater subjective canonical-position rating distribution',
                   'clinicalUseEligible':False,'learnerFeedbackEligible':False,
                   'fitSpeakers':len({data.rows[r]['speakerId'] for r in fit_rows}),
                   'validationSpeakers':len({data.rows[r]['speakerId'] for r in eval_rows})})
    atomic_json(args.output/'config.json',config)
    best_loss = math.inf
    best_epoch = 0
    history = []
    generator = np.random.default_rng(args.seed)
    for epoch in range(1,args.epochs+1):
        epoch_started = time.perf_counter()
        model.train()
        order = generator.permutation(fit_clips).tolist()
        losses = []; target_count = 0
        for offset in range(0,len(order),args.batch_size):
            features,frame_mask,phones,target_mask,targets,_ = data.batch(order[offset:offset+args.batch_size],selected,mean,std,args.device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(features,frame_mask,phones,target_mask)
            per_target = -(targets*logits.log_softmax(-1)).sum(-1)[target_mask]
            loss = per_target.mean()
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite training loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),5,error_if_nonfinite=True)
            optimizer.step()
            losses.append(float(per_target.detach().sum().cpu()));target_count += int(target_mask.sum())
        record = {'epoch':epoch,'trainPerRaterLogLoss':sum(losses)/target_count,'seconds':time.perf_counter()-epoch_started}
        # Outer labels never select epochs or influence scheduling.
        if args.phase=='inner':
            validation,_ = evaluate(model,data,eval_rows,mean,std,args.device,args.batch_size)
            record['validation'] = validation
            value = validation['macroTargetLogLoss']
        else:
            value = -float(epoch)  # Save final fixed epoch; never consult outer metrics here.
        improved = value < best_loss-1e-7
        if improved:
            best_loss,best_epoch = value,epoch
        checkpoint = {'model':model.state_dict(),'optimizer':optimizer.state_dict(),'mean':mean,'std':std,
                      'epoch':epoch,'bestEpoch':best_epoch,'bestLoss':best_loss,
                      'torchRng':torch.get_rng_state(),'numpyRng':generator.bit_generator.state,
                      'configSha256':digest(args.output/'config.json')}
        save_checkpoint(args.output/'last.pt',checkpoint)
        if improved: save_checkpoint(args.output/'best.pt',checkpoint)
        history.append(record)
        with (args.output/'history.jsonl').open('a') as log:log.write(json.dumps(record,allow_nan=False)+'\n')
        atomic_json(args.output/'status.json',{'pid':os.getpid(),'epoch':epoch,'bestEpoch':best_epoch,
                                               'elapsedSeconds':time.perf_counter()-started,'complete':False})
        print(json.dumps({'epoch':epoch,'trainLoss':record['trainPerRaterLogLoss'],
                          'validationMacroLogLoss':value if args.phase=='inner' else None,
                          'bestEpoch':best_epoch,'elapsedSeconds':time.perf_counter()-started}),flush=True)
        if args.phase=='inner' and epoch-best_epoch>=args.patience:break
    saved = torch.load(args.output/'best.pt',map_location=args.device,weights_only=True)
    model.load_state_dict(saved['model'])
    result,predictions = evaluate(model,data,eval_rows,mean,std,args.device,args.batch_size)
    if any(digest(HERE/name)!=value for name,value in config['sourceSha256'].items()):
        raise ValueError('Source changed while training')
    atomic_json(args.output/'predictions.json',predictions)
    report = {'configSha256':digest(args.output/'config.json'),'checkpointSha256':digest(args.output/'best.pt'),
              'bestEpoch':best_epoch,'epochsRun':len(history),'evaluation':result,
              'evaluationRole':'inner selection' if args.phase=='inner' else 'exploratory outer speaker holdout',
              'elapsedSeconds':time.perf_counter()-started,'clinicalUseEligible':False,'learnerFeedbackEligible':False}
    atomic_json(args.output/'report.json',report)
    atomic_json(args.output/'status.json',{'complete':True,'bestEpoch':best_epoch,'epochsRun':len(history),
                                         'elapsedSeconds':report['elapsedSeconds']})
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('cohort','splits','cache','output'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--head',choices=list(HEADS),default='mean')
    parser.add_argument('--phase',choices=['inner','outer'],default='inner')
    parser.add_argument('--fold',type=int,choices=range(5),default=0)
    parser.add_argument('--device',choices=['cpu','mps'],default='mps')
    parser.add_argument('--seed',type=int,default=7)
    parser.add_argument('--hidden',type=int,default=128)
    parser.add_argument('--dropout',type=float,default=0.1)
    parser.add_argument('--lr',type=float,default=0.001)
    parser.add_argument('--weight-decay',type=float,default=0.01)
    parser.add_argument('--epochs',type=int,default=100)
    parser.add_argument('--patience',type=int,default=15)
    parser.add_argument('--batch-size',type=int,default=16)
    parser.add_argument('--threads',type=int,default=4)
    train(parser.parse_args())
