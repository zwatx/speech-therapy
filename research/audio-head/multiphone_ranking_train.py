"""Five fixed child-only clean NLL + marginal-vote pairwise ranking fits.

Same warm checkpoints, stopping rule and supervised order as the retained NLL
controls. Pair draws have a separate RNG; no noisy, outer or test predictions.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch
import torch.nn.functional as F

import multiphone_consistency_train as pilot
import multiphone_phonetic_head as baseline
from multiphone_cache import atomic_json, digest
from multiphone_child_train import score_predictions
from multiphone_train import save_checkpoint, verify_partitions

HERE = Path(__file__).resolve().parent
RECIPE = HERE / 'experiments/multiphone-ranking-v1.json'
FOLDS, REGIME, COEFFICIENT = (0, 1, 2, 3, 4), 'child-only', .1
EVENTS = ('rating0', 'ratingBelow2')
PROTOCOL_SHA = 'dc94968abf6497516e67cea3df764fe5d0c47c40c9005345336765dba8aad2ac'
ASSESSMENT_SHA = 'cefb950e7cfddc80ca3de7bbbc1775240f3fbd31c199085668545cfbc60c7d92'
PILOT_SHA = '7058da214a4f072eb008be5975c9c50786fff4ee4d5528d48bf0ee71286d116f'
FALSE_FLAGS = ('outerPerformanceEvaluationPerformed', 'authorTestInferencePerformed', 'labelsTransferred',
               'noisyInferencePerformed', 'encoderUpdated', 'clinicalUseEligible', 'learnerFeedbackEligible')
read_json, require, guard_files = pilot.read_json, pilot.require, pilot.guard_files
model, logits, predict = pilot.model, pilot.logits, pilot.predict
selection_value, validate_history = pilot.selection_value, pilot.validate_history


def arms(): return [dict(fold=f, regime=REGIME, coefficient=COEFFICIENT) for f in FOLDS]


def source_hashes():
    require(digest(HERE / 'multiphone_consistency_train.py') == PILOT_SHA, 'Frozen control update changed')
    return {name: digest(HERE / name) for name in sorted(set(pilot.source_hashes()) | {'multiphone_ranking_train.py'})}


def validate_recipe(recipe):
    expected = dict(schemaVersion=1, experiment='multiphone-child-pairwise-ranking-v1', folds=list(FOLDS), regime=REGIME,
        coefficient=.1, seed=7, pairSeed=20260926, pairsPerUpdate=64, learningRate=3e-5, weightDecay=.01,
        batchSizeTargetRows=64, maximumEpochs=6, patienceEpochs=2, minimumImprovement=1e-7, gradientNormLimit=5,
        epochZeroEligible=True, dropoutEnabled=False, device='cpu', threads=2, pairEvents=list(EVENTS),
        sameSpeakerPairsRetained=True, identicalRowsPaired=False, protocolSha256=PROTOCOL_SHA,
        supportAssessmentSha256=ASSESSMENT_SHA, pilotTrainerSha256=PILOT_SHA)
    require(all(recipe[k] == v for k, v in expected.items()) and all(recipe[k] is False for k in FALSE_FLAGS)
            and set(recipe['warmHeads']) == set(recipe['existingControlDeclarations']) == {str(f) for f in FOLDS},
            'Recipe differs from fixed five-arm ranking study')
    guard_files({'protocol': {'path': recipe['protocolPath'], 'sha256': PROTOCOL_SHA},
                 'assessment': {'path': recipe['supportAssessmentPath'], 'sha256': ASSESSMENT_SHA}})


def order_digest(indices):
    return hashlib.sha256(json.dumps({'batchSize':64, 'rowIndices':list(map(int, indices))},
                                    separators=(',', ':')).encode()).hexdigest()


def tensor_digest(value):
    array = value.detach().cpu().contiguous().numpy()
    return hashlib.sha256(str((str(array.dtype), array.shape)).encode() + array.tobytes()).hexdigest()


class PairSampler:
    """Exact event/phone mixture, then q_i(1-q_j) conditional on distinct rows."""
    def __init__(self, rows, row_indices):
        require(len(rows) == len(row_indices) == len(set(row_indices)) and len(rows) > 1
                and all(6 <= r['age'] <= 12 for r in rows), 'Pair sampling requires distinct child fitting rows')
        self.row_indices = np.asarray(row_indices, dtype=np.int64)
        raw_counts = np.asarray([r['raterCounts'] for r in rows])
        require(raw_counts.shape == (len(rows), 3) and raw_counts.dtype.kind in 'iuf'
                and np.isfinite(raw_counts).all() and (raw_counts >= 0).all() and (raw_counts <= 5).all()
                and (raw_counts == np.floor(raw_counts)).all() and (raw_counts.sum(1) == 5).all(), 'Invalid five-rater vote counts')
        counts = raw_counts.astype(np.int64)
        self.rows, self.cells, self.active = rows, [], [[], []]
        phones = sorted({r['targetPhone'] for r in rows})
        for event, label in enumerate(EVENTS):
            for phone in phones:
                positions = np.array([i for i, r in enumerate(rows) if r['targetPhone'] == phone], dtype=np.int64)
                votes = counts[positions, 0] if event == 0 else counts[positions, :2].sum(1)
                q = votes.astype(np.float64) / 5
                negative = 1 - q
                first = q * (negative.sum() - negative)
                mass = float(first.sum())
                require(mass >= 0 and np.isfinite(mass), 'Invalid pair mass')
                speakers = np.array([rows[i]['speakerId'] for i in positions])
                per_speaker = []
                for speaker in sorted(set(speakers)):
                    mask = speakers == speaker
                    same = float(q[mask].sum()*negative[mask].sum() - np.dot(q[mask], negative[mask]))
                    positive_endpoint = float(first[mask].sum())
                    negative_endpoint = float((negative[mask] * (q.sum() - q[mask])).sum())
                    per_speaker.append({'speakerId': str(speaker), 'positiveEndpointProbability': positive_endpoint/mass if mass else None,
                        'negativeEndpointProbability': negative_endpoint/mass if mass else None,
                        'sameSpeakerPairProbability': same/mass if mass else None,
                        'pairInvolvementProbability': (positive_endpoint+negative_endpoint-same)/mass if mass else None})
                support = {'event': label, 'phone': phone, 'positions':len(positions), 'speakers':len(set(speakers)),
                    'positiveRaterVotes':int(votes.sum()), 'negativeRaterVotes':int((5-votes).sum()),
                    'positiveSpeakers':len(set(speakers[votes > 0])), 'negativeSpeakers':len(set(speakers[votes < 5])),
                    'eligibleOrderedPairMass':mass,
                    'sameSpeakerPairProbability':sum(s['sameSpeakerPairProbability'] for s in per_speaker) if mass else None,
                    'perSpeaker':per_speaker}
                cell = {'event':event, 'phone':phone, 'positions':positions, 'q':q, 'negative':negative,
                        'first':first, 'mass':mass, 'support':support}
                self.cells.append(cell)
                if mass > 0: self.active[event].append(cell)
        require(all(self.active), 'An event has no positive-mass phone cells')

    def sample(self, rng, count=64):
        result = np.empty((count, 3), dtype=np.int64)
        for p in range(count):
            event = int(rng.integers(2)); cells = self.active[event]
            c = cells[int(rng.integers(len(cells)))]
            i = int(rng.choice(len(c['positions']), p=c['first']/c['mass']))
            negative = c['negative'].copy(); negative[i] = 0
            j = int(rng.choice(len(negative), p=negative/negative.sum()))
            require(i != j, 'A target row cannot pair with itself')
            result[p] = [event, c['positions'][i], c['positions'][j]]
        return result

    def support(self):
        fractions = [np.mean([c['support']['sameSpeakerPairProbability'] for c in cells]) for cells in self.active]
        return {'fitRows':len(self.rows), 'fitChildren':len({r['speakerId'] for r in self.rows}),
                'cells':[c['support'] for c in self.cells],
                'activePhonesByEvent':{EVENTS[e]:[c['phone'] for c in cells] for e,cells in enumerate(self.active)},
                'expectedSameSpeakerPairFraction':float(np.mean(fractions)), 'rowsNeverPairedWithThemselves':True,
                'sameSpeakerPairsRetained':True, 'massIsNotIndependentSampleSize':True}

    def identities(self, pairs):
        return np.column_stack((pairs[:, 0], self.row_indices[pairs[:, 1]], self.row_indices[pairs[:, 2]])).astype('<i8')


def check_support(sampler, fold, assessment):
    old = next(a for a in assessment['folds'] if a['fold'] == fold)
    new = sampler.support()
    require(old['fitRows'] == new['fitRows'] and old['fitChildren'] == new['fitChildren']
            and len(old['cells']) == len(new['cells']), 'Fitting support assessment population differs')
    old_cells = {(c['event'],c['phone']):c for c in old['cells']}
    for c in new['cells']:
        previous = old_cells[(c['event'],c['phone'])]
        for key in ('positions','speakers','positiveRaterVotes','negativeRaterVotes','positiveSpeakers','negativeSpeakers'):
            require(c[key] == previous[key], 'Fitting support counts differ')
        require(np.isclose(c['eligibleOrderedPairMass'],previous['eligibleOrderedPairMass'],rtol=2e-14,atol=1e-12), 'Pair mass differs')
        if c['eligibleOrderedPairMass'] == 0: continue
        require(np.isclose(c['sameSpeakerPairProbability'],previous['sameSpeakerPairProbability'],rtol=0,atol=1e-12), 'Same-speaker mass differs')
        by_speaker = {s['speakerId']:s for s in previous['perSpeaker']}
        for item in c['perSpeaker']:
            require(all(np.isclose(item[k],by_speaker[item['speakerId']][k],rtol=0,atol=1e-12)
                        for k in item if k != 'speakerId'), 'Speaker endpoint support differs')
    require(np.isclose(new['expectedSameSpeakerPairFraction'],old['expectedSameSpeakerPairFraction'],rtol=0,atol=1e-12), 'Sampler mixture support differs')
    return new


def stable_scores(z):
    return torch.stack((z[:,0]-torch.logsumexp(z[:,1:],dim=1), torch.logsumexp(z[:,:2],dim=1)-z[:,2]), dim=1)


def pair_loss(student, clean, ids, pairs):
    # Deliberately no vote multiplication here: those weights are already in sampling.
    pair_ids = np.concatenate((pairs[:,1],pairs[:,2]))
    scores = stable_scores(logits(student, clean[pair_ids], ids[pair_ids]))
    event = torch.tensor(pairs[:,0],dtype=torch.long)
    position = torch.arange(len(pairs))
    return F.softplus(scores[len(pairs)+position,event]-scores[position,event]).mean()


def train_epoch(student, optimizer, clean, ids, labels, order, sampler, pair_rng, coefficient=.1):
    require(coefficient in (0., COEFFICIENT) and len(order) == len(labels)
            and np.array_equal(np.sort(order),np.arange(len(labels))), 'Invalid ranking objective or NLL permutation')
    student.eval()
    total_nll, total_pair, updates = 0., 0., 0
    pair_hash = hashlib.sha256()
    for start in range(0,len(order),64):
        selected=order[start:start+64]
        optimizer.zero_grad(set_to_none=True)
        z=logits(student,clean[selected],ids[selected])
        nll=-(labels[selected]*z.log_softmax(-1)).sum(-1)
        auxiliary=torch.zeros((),dtype=nll.dtype)
        if coefficient:
            pairs=sampler.sample(pair_rng,64)
            pair_hash.update(sampler.identities(pairs).tobytes())
            auxiliary=pair_loss(student,clean,ids,pairs)
        loss=nll.mean()+coefficient*auxiliary
        require(bool(torch.isfinite(nll).all() and torch.isfinite(loss)), 'Nonfinite ranking objective')
        loss.backward();torch.nn.utils.clip_grad_norm_(student.parameters(),5.,error_if_nonfinite=True);optimizer.step()
        total_nll+=float(nll.detach().sum());total_pair+=float(auxiliary.detach());updates+=1
    return {'cleanSupervisedNLL':total_nll/len(order), 'pairwiseLossMeanPerUpdate':total_pair/updates,
            'updates':updates,'sampledPairs':updates*64 if coefficient else 0,
            'nllOrderDigest':order_digest(sampler.row_indices[order]),'pairIdentityDigest':pair_hash.hexdigest()}


def confidence(p, rows):
    masks={'allAges':np.ones(len(rows),bool),'ages6to12':np.array([6<=r['age']<=12 for r in rows]),
           'ages13plus':np.array([r['age']>=13 for r in rows])}
    return {k:{'targets':int(mask.sum()),'meanClassProbabilities':p[mask].mean(0).tolist(),
        'meanEntropy':float(-(p[mask]*np.log(p[mask].clip(1e-12,1))).sum(1).mean()),
        'meanMaximumProbability':float(p[mask].max(1).mean()),
        'argmaxCounts':np.bincount(p[mask].argmax(1),minlength=3).tolist()} if mask.any() else None for k,mask in masks.items()}


def load_data(fold, recipe, validation=True):
    require(fold in FOLDS, 'Undeclared ranking fold')
    warm=recipe['warmHeads'][str(fold)];directory=Path(warm['directory'])
    files={f'warm/{fold}/{name}':{'path':str(directory/name),'sha256':sha} for name,sha in warm['files'].items()}
    declaration=recipe['existingControlDeclarations'][str(fold)]
    files['controlDeclaration/'+str(fold)]={'path':declaration['recipePath'],'sha256':declaration['recipeSha256']}
    files['supportAssessment']={'path':recipe['supportAssessmentPath'],'sha256':ASSESSMENT_SHA}
    files['protocol']={'path':recipe['protocolPath'],'sha256':PROTOCOL_SHA}
    guard_files(files)
    control=read_json(Path(declaration['recipePath']))
    control_warm=control['warmHeads'][declaration['warmPopulationKey']]
    require(all(control_warm[k]==warm[k] for k in ('directory','files')) and declaration['coefficient']==0
            and declaration['regime']==REGIME,'Retained NLL control warm binding differs')
    config=read_json(directory/'config.json')
    require(config['family']=='target-scalars' and config['regime']==REGIME and config['fold']==fold
            and config['lr']==.0003 and config['seed']==7 and config['phase']=='inner'
            and config['bindingSha256']==recipe['cleanFeatureBindingSha256'],'Ranking warm identity differs')
    baseline.source_guard(config)
    args=argparse.Namespace(**config);args.binding=Path(args.binding)
    data=baseline.setup(args)
    verify_partitions(data['cohort'],data['splits']['folds'][fold])
    require(all(data[k]==config[k+'Rows'] for k in ('fit','validation','selection'))
            and data['bindings']==config['inputFiles'] and config['priorState']==data['priors']
            and all(6<=data['cohort']['rows'][i]['age']<=12 for i in data['fit']), 'Warm fitting population differs')
    saved=torch.load(directory/'best.pt',map_location='cpu',weights_only=True)
    report,replay=read_json(directory/'report.json'),read_json(directory/'replay.json')
    require(saved['configSha256']==digest(directory/'config.json') and saved['epoch']==saved['bestEpoch']==warm['selectedEpoch']==report['bestEpoch']
            and torch.equal(saved['mean'],data['mean']) and torch.equal(saved['std'],data['std'])
            and report['complete'] is True and report['phase']=='inner' and report['configSha256']==saved['configSha256']
            and report['bestSelectionMacroLogLoss']==saved['bestLoss'] and replay['exact'] is True
            and replay['checkpointSha256']==digest(directory/'best.pt') and replay['rows']==len(data['validation'])
            and all(report[k+'Sha256']==digest(directory/n) for k,n in
                (('checkpoint','best.pt'),('predictions','predictions.json'),('history','history.json'),('prior','prior.json'))),
            'Warm checkpoint/moments/report lineage differs')
    selected=data['fit']+data['validation'] if validation else data['fit']
    clean=(torch.from_numpy(data['values'][[data['positions'][i] for i in selected]].copy())-data['mean'])/data['std']
    ids=torch.tensor([data['cohort']['rows'][i]['targetId'] for i in selected],dtype=torch.long)
    fit_rows=[data['cohort']['rows'][i] for i in data['fit']]
    sampler=PairSampler(fit_rows,data['fit'])
    support=check_support(sampler,fold,read_json(Path(recipe['supportAssessmentPath'])))
    network=model();network.load_state_dict(saved['model'],strict=True)
    warm_p=None
    if validation:
        warm_p=predict(network,clean[len(data['fit']):],ids[len(data['fit']):])
        predictions=read_json(directory/'predictions.json')
        require(predictions['rowIndices']==data['validation'] and np.array_equal(warm_p,predictions['probabilities']),
                'Warm validation probabilities do not replay exactly')
    files.update({'clean/'+k:v for k,v in data['bindings'].items()})
    files['cleanHeadRecipe']={'path':str(baseline.RECIPE),'sha256':digest(baseline.RECIPE)}
    files['cleanHeadBinding']={'path':str(args.binding),'sha256':config['bindingSha256']}
    guard_files(files)
    return {**data,'clean':clean,'ids':ids,'fitCount':len(data['fit']),'warmPredictions':warm_p,
        'warmState':copy.deepcopy(saved['model']),'warmMean':saved['mean'].clone(),'warmStd':saved['std'].clone(),
        'allBindings':files,'sampler':sampler,'support':support,
        'labels':torch.tensor([r['raterCounts'] for r in fit_rows],dtype=torch.float32)/5}


def trees_equal(a,b):
    if isinstance(a,torch.Tensor):return isinstance(b,torch.Tensor) and torch.equal(a,b)
    if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(trees_equal(a[k],b[k]) for k in a)
    if isinstance(a,(tuple,list)):return isinstance(b,type(a)) and len(a)==len(b) and all(trees_equal(x,y) for x,y in zip(a,b))
    return a==b


def equivalence(data):
    students=[];optimizers=[]
    for _ in range(2):
        s=model();s.load_state_dict(data['warmState']);students.append(s)
        optimizers.append(torch.optim.AdamW(s.parameters(),lr=3e-5,weight_decay=.01))
    n=data['fitCount'];order=np.random.default_rng(7).permutation(n)
    rng=np.random.default_rng(20260926);initial=copy.deepcopy(rng.bit_generator.state)
    a=pilot.train_epoch(students[0],optimizers[0],data['clean'][:n],None,data['ids'][:n],data['labels'],None,order,0.)
    b=train_epoch(students[1],optimizers[1],data['clean'][:n],data['ids'][:n],data['labels'],order,data['sampler'],rng,0.)
    checks={'NLL':a['cleanSupervisedNLL']==b['cleanSupervisedNLL'],
            'model':trees_equal(students[0].state_dict(),students[1].state_dict()),
            'optimizer':trees_equal(optimizers[0].state_dict(),optimizers[1].state_dict()),
            'moments':torch.equal(data['mean'],data['warmMean']) and torch.equal(data['std'],data['warmStd']),
            'targetIDs':all(int(data['ids'][j])==data['cohort']['rows'][i]['targetId'] for j,i in enumerate(data['fit'])),
            'rowOrder':b['nllOrderDigest']==order_digest(np.asarray(data['fit'])[order]),
            'pairRNGUntouched':initial==rng.bit_generator.state}
    require(all(checks.values()),'Disabled ranking auxiliary differs from frozen NLL control')
    return {'exactChecks':checks,'comparedUpdates':b['updates'],'cleanSupervisedNLL':b['cleanSupervisedNLL'],
            'nllOrderDigest':b['nllOrderDigest'],'fitRows':data['fit'],
            'meanDigest':tensor_digest(data['mean']),'stdDigest':tensor_digest(data['std']),'targetIDsDigest':tensor_digest(data['ids'][:n])}


def preflight(output):
    require(not output.exists() and output.resolve().is_relative_to(HERE/'outputs'),'Choose fresh fitting-only preflight output')
    source,recipe_sha=source_hashes(),digest(RECIPE);recipe=read_json(RECIPE);validate_recipe(recipe)
    torch.set_num_threads(2);torch.manual_seed(7)
    data=load_data(0,recipe,validation=False)
    result={'complete':True,'exact':True,'fold':0,'regime':REGIME,'coefficient':0,'fitOnly':True,
        'validationInferencePerformed':False,'recipeSha256':recipe_sha,'sourceSha256':source,
        'inputFiles':data['allBindings'],**equivalence(data)}
    guard_files(data['allBindings'])
    require(source==source_hashes() and recipe_sha==digest(RECIPE),'Source changed during actual equivalence preflight')
    atomic_json(output,result);return result


def validate_preflight(path,sha):
    result,_=pilot.noise_source.read_bound(path,sha)
    require(result['complete'] is True and result['exact'] is True and result['fold']==0
            and result['regime']==REGIME and result['coefficient']==0 and result['fitOnly'] is True
            and result['validationInferencePerformed'] is False and result['sourceSha256']==source_hashes()
            and result['recipeSha256']==digest(RECIPE)
            and set(result['exactChecks'])=={'NLL','model','optimizer','moments','targetIDs','rowOrder','pairRNGUntouched'}
            and all(v is True for v in result['exactChecks'].values()),'Actual fitting equivalence proof differs')
    guard_files(result['inputFiles']);return result


def plan_guard(plan,path,expected_sha):
    require(digest(path)==expected_sha and plan['complete'] is True and plan['sourceSha256']==source_hashes()
            and plan['recipeSha256']==digest(RECIPE) and plan['arms']==arms()
            and all(plan[k] is False for k in FALSE_FLAGS),'Ranking declaration changed')
    validate_recipe(read_json(RECIPE));guard_files(plan['inputFiles'])
    validate_preflight(Path(plan['preflight']['path']),plan['preflight']['sha256'])


def declare(preflight_path,preflight_sha,output):
    require(not output.exists() and output.resolve().is_relative_to(HERE/'outputs'),'Choose fresh ranking declaration')
    source,recipe_sha=source_hashes(),digest(RECIPE);recipe=read_json(RECIPE);validate_recipe(recipe)
    proof=validate_preflight(preflight_path,preflight_sha)
    files={'preflight':{'path':str(preflight_path.resolve()),'sha256':preflight_sha}};populations={}
    torch.set_num_threads(2)
    for fold in FOLDS:
        data=load_data(fold,recipe)
        require(all(k not in files or files[k]==v for k,v in data['allBindings'].items()),'Shared ranking pins disagree')
        files.update(data['allBindings'])
        populations[str(fold)]={'fold':fold,'regime':REGIME,**{k+'Rows':data[k] for k in ('fit','validation','selection')},
            'inputFiles':data['allBindings'],'support':data['support'],
            'meanDigest':tensor_digest(data['mean']),'stdDigest':tensor_digest(data['std']),
            'warmCleanSelectionNLL':selection_value(data['warmPredictions'],[data['cohort']['rows'][i] for i in data['validation']],REGIME)}
        if fold==0:
            require(proof['fitRows']==data['fit'] and proof['inputFiles']==data['allBindings']
                    and proof['meanDigest']==tensor_digest(data['mean']) and proof['stdDigest']==tensor_digest(data['std'])
                    and proof['targetIDsDigest']==tensor_digest(data['ids'][:data['fitCount']]),'Preflight fitting data differs')
    require(source==source_hashes() and recipe_sha==digest(RECIPE),'Source changed during ranking declaration')
    guard_files(files)
    result={'complete':True,'recipeSha256':recipe_sha,'sourceSha256':source,'arms':arms(),'inputFiles':files,
        'populations':populations,'preflight':files['preflight'],'researchOnly':True,**{k:False for k in FALSE_FLAGS}}
    atomic_json(output,result);return result


def clean_prediction(student,data): return predict(student,data['clean'][data['fitCount']:],data['ids'][data['fitCount']:])


def fit(args):
    require(args.fold in FOLDS and not args.output.exists() and args.output.resolve().is_relative_to(HERE/'outputs'),
            'Choose declared ranking fold and fresh output')
    plan=read_json(args.plan);plan_guard(plan,args.plan,args.plan_sha256)
    torch.set_num_threads(2);torch.manual_seed(7)
    data=load_data(args.fold,read_json(RECIPE));pop=plan['populations'][str(args.fold)]
    require(all(data[k]==pop[k+'Rows'] for k in ('fit','validation','selection')) and data['allBindings']==pop['inputFiles']
            and data['support']==pop['support'] and pop['meanDigest']==tensor_digest(data['mean'])
            and pop['stdDigest']==tensor_digest(data['std']),'Declared ranking population differs')
    student=model();student.load_state_dict(data['warmState'],strict=True)
    optimizer=torch.optim.AdamW(student.parameters(),lr=3e-5,weight_decay=.01)
    nll_rng,pair_rng=np.random.default_rng(7),np.random.default_rng(20260926)
    rows=[data['cohort']['rows'][i] for i in data['validation']]
    args.output.mkdir(parents=True,mode=0o700)
    config={'planPath':str(args.plan.resolve()),'planSha256':args.plan_sha256,'fold':args.fold,'regime':REGIME,'coefficient':COEFFICIENT,
        **{k+'Rows':data[k] for k in ('fit','validation','selection')},'inputFiles':data['allBindings'],
        'sourceSha256':plan['sourceSha256'],'recipeSha256':plan['recipeSha256'],
        'meanDigest':tensor_digest(data['mean']),'stdDigest':tensor_digest(data['std']),
        'studentTrainingMode':'eval-with-gradients','nllSeed':7,'pairSeed':20260926,'pairsPerUpdate':64,
        **{k:False for k in FALSE_FLAGS}}
    atomic_json(args.output/'config.json',config);config_sha=digest(args.output/'config.json')
    atomic_json(args.output/'support.json',data['support'])
    owned={name:digest(args.output/name) for name in ('config.json','support.json')}
    def capture(*names):
        for name in names:owned[name]=digest(args.output/name)
    def output_guard():require(all(digest(args.output/n)==sha for n,sha in owned.items()),'Ranking output changed after publication')
    best_loss=selection_value(data['warmPredictions'],rows,REGIME);best_epoch=0
    history=[{'epoch':0,'selectionMacroNLL':best_loss,'evaluation':score_predictions(data['warmPredictions'],rows),
              'confidence':confidence(data['warmPredictions'],rows)}]
    def checkpoint(epoch):
        return {'model':student.state_dict(),'optimizer':optimizer.state_dict(),'epoch':epoch,'bestEpoch':best_epoch,'bestLoss':best_loss,
                'mean':data['mean'],'std':data['std'],'configSha256':config_sha,'nllRngState':nll_rng.bit_generator.state,
                'pairRngState':pair_rng.bit_generator.state}
    save_checkpoint(args.output/'best.pt',checkpoint(0));capture('best.pt');started=time.perf_counter()
    for epoch in range(1,7):
        objective=train_epoch(student,optimizer,data['clean'][:data['fitCount']],data['ids'][:data['fitCount']],data['labels'],
            nll_rng.permutation(data['fitCount']),data['sampler'],pair_rng)
        p=clean_prediction(student,data);evaluation=score_predictions(p,rows);loss=baseline.selection_loss(evaluation,REGIME)
        require(np.isfinite(loss),'Nonfinite clean ranking selection loss')
        improved=loss<best_loss-1e-7
        if improved:best_epoch,best_loss=epoch,loss
        history.append({'epoch':epoch,'selectionMacroNLL':loss,'evaluation':evaluation,'confidence':confidence(p,rows),**objective})
        save_checkpoint(args.output/'last.pt',checkpoint(epoch));capture('last.pt')
        if improved:save_checkpoint(args.output/'best.pt',checkpoint(epoch));capture('best.pt')
        require(source_hashes()==plan['sourceSha256'] and digest(args.output/'config.json')==config_sha,'Ranking source/config changed')
        atomic_json(args.output/'history.json',history);capture('history.json')
        atomic_json(args.output/'status.json',{'complete':False,'epoch':epoch,'bestEpoch':best_epoch})
        print(json.dumps({'epoch':epoch,'cleanChildMacroNLL':loss,'bestEpoch':best_epoch,'pairLoss':objective['pairwiseLossMeanPerUpdate']}),flush=True)
        if epoch-best_epoch>=2:break
    output_guard();saved=torch.load(args.output/'best.pt',map_location='cpu',weights_only=True)
    student.load_state_dict(saved['model'],strict=True);p=clean_prediction(student,data)
    require(selection_value(p,rows,REGIME)==best_loss,'Selected ranking checkpoint does not replay')
    atomic_json(args.output/'predictions.json',{'rowIndices':data['validation'],'probabilities':p.tolist(),
                                            'warmProbabilities':data['warmPredictions'].tolist()});capture('predictions.json')
    report={'complete':False,'fitComplete':True,'state':'fitted-awaiting-independent-replay','fold':args.fold,'regime':REGIME,
        'coefficient':COEFFICIENT,'bestEpoch':best_epoch,'epochsRun':len(history)-1,'bestCleanSelectionNLL':best_loss,
        'evaluation':score_predictions(p,rows),'warmEvaluation':score_predictions(data['warmPredictions'],rows),
        'confidence':confidence(p,rows),'warmConfidence':confidence(data['warmPredictions'],rows),
        'elapsedSeconds':time.perf_counter()-started,**{k:False for k in FALSE_FLAGS}}
    plan_guard(plan,args.plan,args.plan_sha256);guard_files(data['allBindings']);output_guard()
    atomic_json(args.output/'status.json',{'complete':False,'fitComplete':True,'state':'fitted-awaiting-independent-replay',
        'bestEpoch':best_epoch,'epochsRun':len(history)-1});capture('status.json');output_guard()
    report['filesSha256']=owned.copy();atomic_json(args.output/'report.json',report);return report


def audit_orders(history,sampler):
    nll_rng,pair_rng=np.random.default_rng(7),np.random.default_rng(20260926)
    states={0:(copy.deepcopy(nll_rng.bit_generator.state),copy.deepcopy(pair_rng.bit_generator.state))}
    for h in history[1:]:
        order=nll_rng.permutation(len(sampler.rows));sha=hashlib.sha256();updates=0
        for start in range(0,len(order),64):
            sha.update(sampler.identities(sampler.sample(pair_rng,64)).tobytes());updates+=1
        require(h['nllOrderDigest']==order_digest(sampler.row_indices[order]) and h['pairIdentityDigest']==sha.hexdigest()
                and h['updates']==updates and h['sampledPairs']==updates*64,'Saved NLL order or pair identities differ')
        states[h['epoch']]=(copy.deepcopy(nll_rng.bit_generator.state),copy.deepcopy(pair_rng.bit_generator.state))
    return states


def replay(output):
    report_sha=digest(output/'report.json');config,report=read_json(output/'config.json'),read_json(output/'report.json')
    require(report['complete'] is False and report['fitComplete'] is True and report['state']=='fitted-awaiting-independent-replay'
            and report['fold']==config['fold'] and report['regime']==config['regime']==REGIME
            and report['coefficient']==config['coefficient']==COEFFICIENT
            and all(report[k] is False and config[k] is False for k in FALSE_FLAGS)
            and set(report['filesSha256'])=={'config.json','support.json','best.pt','last.pt','history.json','predictions.json','status.json'}
            and all(digest(output/n)==sha for n,sha in report['filesSha256'].items()),'Ranking artifact binding differs')
    plan_path=Path(config['planPath']);plan=read_json(plan_path);plan_guard(plan,plan_path,config['planSha256'])
    require(config['sourceSha256']==plan['sourceSha256'] and config['recipeSha256']==plan['recipeSha256'],'Ranking replay source differs')
    torch.set_num_threads(2);data=load_data(config['fold'],read_json(RECIPE))
    require(all(config[k+'Rows']==data[k] for k in ('fit','validation','selection')) and config['inputFiles']==data['allBindings']
            and read_json(output/'support.json')==data['support'] and config['meanDigest']==tensor_digest(data['mean'])
            and config['stdDigest']==tensor_digest(data['std']),'Replayed fitting membership/support differs')
    saved=torch.load(output/'best.pt',map_location='cpu',weights_only=True)
    require(saved['configSha256']==digest(output/'config.json') and saved['epoch']==saved['bestEpoch']==report['bestEpoch']
            and saved['bestLoss']==report['bestCleanSelectionNLL'] and torch.equal(saved['mean'],data['mean'])
            and torch.equal(saved['std'],data['std']),'Ranking selected checkpoint differs')
    student=model();student.load_state_dict(saved['model'],strict=True);p=clean_prediction(student,data)
    prediction=read_json(output/'predictions.json');rows=[data['cohort']['rows'][i] for i in data['validation']]
    require(prediction['rowIndices']==data['validation'] and np.array_equal(p,prediction['probabilities'])
            and np.array_equal(data['warmPredictions'],prediction['warmProbabilities'])
            and report['evaluation']==score_predictions(p,rows) and report['warmEvaluation']==score_predictions(data['warmPredictions'],rows)
            and report['confidence']==confidence(p,rows) and report['warmConfidence']==confidence(data['warmPredictions'],rows),
            'Ranking saved predictions or metrics do not replay exactly')
    history=read_json(output/'history.json')
    best,epoch=validate_history(history,selection_value(data['warmPredictions'],rows,REGIME))
    require(best==saved['bestLoss'] and epoch==saved['epoch'] and len(history)-1==report['epochsRun']
            and history[0]['evaluation']==report['warmEvaluation'] and history[0]['confidence']==report['warmConfidence']
            and history[epoch]['evaluation']==report['evaluation'] and history[epoch]['confidence']==report['confidence']
            and all(h['selectionMacroNLL']==baseline.selection_loss(h['evaluation'],REGIME) for h in history),
            'Ranking clean-only stopping history differs')
    states=audit_orders(history,data['sampler'])
    require((saved['nllRngState'],saved['pairRngState'])==states[epoch],'Selected checkpoint RNG state differs')
    last=torch.load(output/'last.pt',map_location='cpu',weights_only=True)
    require(last['configSha256']==digest(output/'config.json') and last['epoch']==len(history)-1
            and (last['nllRngState'],last['pairRngState'])==states[last['epoch']],'Last checkpoint/order state differs')
    require(read_json(output/'status.json')==dict(complete=False,fitComplete=True,state='fitted-awaiting-independent-replay',
            bestEpoch=epoch,epochsRun=len(history)-1),'Ranking status differs')
    plan_guard(plan,plan_path,config['planSha256']);guard_files(data['allBindings'])
    require(digest(output/'report.json')==report_sha and all(digest(output/n)==sha for n,sha in report['filesSha256'].items()),
            'Ranking artifacts changed during replay')
    result={'complete':True,'exact':True,'state':'verified','fold':config['fold'],'regime':REGIME,'coefficient':COEFFICIENT,
        'rows':len(p),'checkpointSha256':digest(output/'best.pt'),'reportSha256':report_sha}
    atomic_json(output/'replay.json',result);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('preflight');p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('declare');p.add_argument('--preflight',type=Path,required=True);p.add_argument('--preflight-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('fit');p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True)
    p.add_argument('--fold',type=int,choices=FOLDS,required=True);p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('replay');p.add_argument('--output',type=Path,required=True)
    a=parser.parse_args()
    result=preflight(a.output) if a.command=='preflight' else (declare(a.preflight,a.preflight_sha256,a.output) if a.command=='declare'
        else fit(a) if a.command=='fit' else replay(a.output))
    print(json.dumps({'fitComplete':True,'replayRequired':True} if a.command=='fit' else {'complete':result.get('complete')}),flush=True)
