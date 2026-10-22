"""Fixed, inner-only exploratory canonical competitor posterior study."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import traceback
import numpy as np
import torch
from multiphone_cache import atomic_json
from multiphone_child_train import score_predictions
from multiphone_data import TARGETS
from multiphone_local_features import validate_log_prob, canonical_mapping
from multiphone_local_train import load_inputs, read_json, digest, require
from multiphone_models import MeanPoolPhoneRatingHead
from multiphone_train import save_checkpoint

HERE = Path(__file__).resolve().parent
BASE = HERE/'outputs/multiphone-20260926'
OUTPUT = HERE/'outputs/multiphone-20260927/competitor-v1'
PROTOCOL = HERE.parent.parent/'docs/model/multiphone-competitor-protocol.md'
RECIPE = dict(seed=7, hidden=32, dropout=.1, lr=.001, weightDecay=.01, batch=128, epochs=20, threads=2,
              selection='all-age inner macro-phone NLL; earliest improvement >1e-7', phase='inner',
              outerOutcomesUsed=False, authorTestInferencePerformed=False, learnerFeedbackEligible=False)

def posterior_means(logp, interval, tokens):
    start, end = interval
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(logp), 'Invalid interval')
    require(len(tokens) == 24 and len(set(tokens)) == 24 and all(3 < t < 392 for t in tokens), 'Invalid tokens')
    return np.exp(logp[start:end].astype(np.float64))[:, tokens].mean(0).astype(np.float32)

def normalize(values, fit):
    mean = values[fit].astype(np.float64).mean(0)
    std = values[fit].astype(np.float64).std(0)
    std[std < 1e-6] = 1
    return mean.astype(np.float32), std.astype(np.float32)

def inputs():
    cp, sp, fp = BASE/'cohort.json', BASE/'splits.json', BASE/'ctc-local-full/features/features.json'
    cohort, splits, scalars, positions, binding = load_inputs(cp, sp, fp)
    meta = read_json(fp)
    manifest = read_json(Path(binding['upstream']['manifest']['path']))
    vocab_path = Path(manifest['vocabularyPath'])
    require(digest(vocab_path) == manifest['vocabularySha256'], 'Vocabulary hash differs')
    recipe = read_json(Path(binding['upstream']['recipe']['path']))
    _, tokens, _ = canonical_mapping(list(TARGETS), read_json(vocab_path), recipe)
    cache = Path(binding['upstream']['ctcIndex']['path']).parent
    index = read_json(cache/'index.json')
    values = np.empty((len(scalars), 24), dtype=np.float32)
    grouped = {}
    for position, row in enumerate(meta['rows']):
        grouped.setdefault(row['clipId'], []).append((position, row))
    hashes = {}
    for clip_id, rows in grouped.items():
        entry = index['entries'][clip_id]
        path = (cache/entry['path']).resolve()
        require(path.is_relative_to(cache) and digest(path) == entry['sha256'] and
                entry['configSha256'] == index['configSha256'], 'CTC file binding differs')
        clip = cohort['clips'][cohort['rows'][rows[0][1]['rowIndex']]['clipIndex']]
        require(entry['audioSha256'] == clip['audioSha256'], 'Audio binding differs')
        logp = np.fromfile(path, dtype='<f4').reshape(entry['frames'], 392)
        validate_log_prob(logp, entry['frames'])
        hashes[str(path)] = entry['sha256']
        for position, row in rows:
            require(row['tokenId'] == tokens[row['targetId']], 'Target token mapping differs')
            values[position] = posterior_means(logp, row['intervalFrames'], tokens)
            require(abs(float(values[position, row['targetId']])-float(scalars[position, 1])) < 1e-6,
                    'Target posterior does not reproduce existing scalar')
    binding.update(ctcFiles=hashes, vocabularyPath=str(vocab_path), vocabularySha256=digest(vocab_path), tokens=tokens)
    return cohort, splits, np.asarray(scalars), values, positions, binding

def model():
    return MeanPoolPhoneRatingHead(feature_dim=37, hidden_dim=32, dropout=.1)

def predict(net, x, phones):
    net.eval()
    result = []
    with torch.no_grad():
        for start in range(0, len(x), 128):
            xx, pp = x[start:start+128, None], phones[start:start+128, None]
            mask = torch.ones(pp.shape, dtype=torch.bool)
            result.append(net(xx, mask, pp, mask)[:, 0].softmax(-1).numpy())
    return np.concatenate(result).astype(np.float64)

def slices(p, rows, words):
    result = {'allRows': score_predictions(p, rows)}
    for name, seen in [('targetWordSeen', True), ('targetWordUnseen', False)]:
        mask = np.asarray([(r['targetWord'] in words) == seen for r in rows])
        result[name] = score_predictions(p[mask], [r for r, keep in zip(rows, mask) if keep]) if mask.any() else None
    return result

def run_arm(output, fold_id, arm, cohort, splits, scalars, competitor, positions, config_sha):
    torch.manual_seed(7)
    rng = np.random.default_rng(7)
    fold = splits['folds'][fold_id]
    fit, validation = fold['innerFitRows'], fold['innerValidationRows']
    require(not set(fit)&set(validation), 'Row overlap')
    require(not {cohort['rows'][i]['speakerId'] for i in fit}&{cohort['rows'][i]['speakerId'] for i in validation}, 'Speaker overlap')
    values = np.concatenate([scalars, competitor if arm == 'competitor' else np.zeros_like(competitor)], 1)
    fpos, vpos = [positions[i] for i in fit], [positions[i] for i in validation]
    mean, std = normalize(values, fpos)
    x = torch.from_numpy((values-mean)/std)
    rows = [cohort['rows'][i] for i in validation]
    fx, vx = x[fpos], x[vpos]
    phones = torch.tensor([cohort['rows'][i]['targetId'] for i in fit])
    vp = torch.tensor([r['targetId'] for r in rows])
    y = torch.tensor([cohort['rows'][i]['raterCounts'] for i in fit], dtype=torch.float32)/5
    net = model()
    optimizer = torch.optim.AdamW(net.parameters(), lr=.001, weight_decay=.01)
    path = output/f'fold-{fold_id}-{arm}'
    path.mkdir()
    history, best, best_epoch = [], float('inf'), None
    words = {cohort['rows'][i]['targetWord'] for i in fit}
    atomic_json(path/'config.json', dict(studyConfigSha256=config_sha, fitRows=fit, validationRows=validation,
                parameters=sum(p.numel() for p in net.parameters()), fitVocabulary=sorted(words)))
    for epoch in range(1, 21):
        net.train()
        order = rng.permutation(len(fit))
        for offset in range(0, len(order), 128):
            batch = order[offset:offset+128]
            pp = phones[batch, None]
            mask = torch.ones(pp.shape, dtype=torch.bool)
            optimizer.zero_grad(set_to_none=True)
            logits = net(fx[batch, None], mask, pp, mask)[:, 0]
            loss = -(y[batch]*logits.log_softmax(-1)).sum(-1).mean()
            require(bool(torch.isfinite(loss)), 'Nonfinite loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
        predictions = predict(net, vx, vp)
        metrics = score_predictions(predictions, rows)
        nll = metrics['allAges']['macroTargetLogLoss']
        history.append(dict(epoch=epoch, macroNLL=nll, orderSha256=hashlib.sha256(order.tobytes()).hexdigest()))
        state = dict(model=net.state_dict(), mean=torch.from_numpy(mean), std=torch.from_numpy(std),
                     optimizer=optimizer.state_dict(), epoch=epoch, configSha256=digest(path/'config.json'))
        save_checkpoint(path/'last.pt', state)
        if nll < best-1e-7:
            best, best_epoch = nll, epoch
            save_checkpoint(path/'best.pt', state)
        atomic_json(path/'history.json', history)
    saved = torch.load(path/'best.pt', weights_only=True)
    net.load_state_dict(saved['model'])
    p = predict(net, vx, vp)
    atomic_json(path/'predictions.json', dict(rowIndices=validation, probabilities=p.tolist()))
    replay_net = model()
    replay_net.load_state_dict(torch.load(path/'best.pt', weights_only=True)['model'])
    replay_x = (torch.from_numpy(values[vpos])-saved['mean'])/saved['std']
    replay = predict(replay_net, replay_x, vp)
    require(np.array_equal(p, replay), 'Saved checkpoint replay differs')
    result = dict(fold=fold_id, arm=arm, bestEpoch=best_epoch, epochs=20, updates=20*((len(fit)+127)//128),
                  evaluation=slices(p, rows, words), exactReplay=True, maximumReplayDifference=float(np.max(abs(p-replay))),
                  hashes={p.name:digest(p) for p in path.iterdir() if p.is_file()})
    atomic_json(path/'report.json', result)
    print(json.dumps(dict(fold=fold_id, arm=arm, bestEpoch=best_epoch, nll=best)), flush=True)
    return result

def run():
    require(not OUTPUT.exists(), 'Fresh output required; failed artifacts must be retained')
    OUTPUT.mkdir(parents=True)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    try:
        cohort, splits, scalars, competitor, positions, binding = inputs()
        sources = {p.name:digest(p) for p in HERE.glob('*.py')}
        config = dict(recipe=RECIPE, binding=binding, sourceSha256=sources, protocolSha256=digest(PROTOCOL),
                      torch=str(torch.__version__), numpy=np.__version__)
        atomic_json(OUTPUT/'config.json', config)
        np.save(OUTPUT/'competitor.npy', competitor, allow_pickle=False)
        results = []
        for fold in range(5):
            for arm in ('control', 'competitor'):
                results.append(run_arm(OUTPUT, fold, arm, cohort, splits, scalars, competitor, positions, digest(OUTPUT/'config.json')))
        require(all(digest(HERE/name)==sha for name, sha in sources.items()), 'Source changed during run')
        require(inputs()[-1] == binding and digest(PROTOCOL)==config['protocolSha256'], 'Input/protocol changed during run')
        atomic_json(OUTPUT/'report.json', dict(complete=True, results=results, configSha256=digest(OUTPUT/'config.json'),
                                             competitorSha256=digest(OUTPUT/'competitor.npy')))
    except Exception:
        (OUTPUT/'failure.txt').write_text(traceback.format_exc())
        raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.run:
        run()
