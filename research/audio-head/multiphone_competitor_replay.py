"""Independent process replay of all saved fixed competitor-study checkpoints."""
from pathlib import Path
import numpy as np
import torch
from multiphone_competitor_study import OUTPUT, HERE, PROTOCOL, inputs, model, predict, slices
from multiphone_local_train import read_json, digest, require
from multiphone_cache import atomic_json

EXPECTED = {(fold, arm) for fold in range(5) for arm in ('control', 'competitor')}
ARTIFACTS = {'config.json', 'best.pt', 'last.pt', 'history.json', 'predictions.json'}


def evidence_binding(output):
    """Validate the full saved run and bind every report/checkpoint identity."""
    report = read_json(output/'report.json')
    require(report.get('complete') is True and report['configSha256'] == digest(output/'config.json'), 'Incomplete study')
    require(report['competitorSha256'] == digest(output/'competitor.npy'), 'Feature digest differs')
    results = report['results']
    require(len(results) == 10 and {(r['fold'], r['arm']) for r in results} == EXPECTED,
            'Expected exactly five folds and two arms')
    config = read_json(output/'config.json')
    cohort_path = Path(config['binding']['cohortPath'])
    require(digest(cohort_path) == config['binding']['cohortSha256'], 'Cohort digest differs')
    splits_path = Path(config['binding']['splitsPath'])
    require(digest(splits_path) == config['binding']['splitsSha256'], 'Split digest differs')
    splits = read_json(splits_path)
    arms = []
    for result in results:
        path = output/f"fold-{result['fold']}-{result['arm']}"
        require(set(result['hashes']) == ARTIFACTS, 'Incomplete artifact set')
        require(all(digest(path/name) == sha for name, sha in result['hashes'].items()), 'Saved artifact differs')
        require(read_json(path/'report.json') == result, 'Arm report differs')
        arm_config = read_json(path/'config.json')
        fold = splits['folds'][result['fold']]
        require(arm_config['studyConfigSha256'] == report['configSha256'] and
                arm_config['fitRows'] == fold['innerFitRows'] and
                arm_config['validationRows'] == fold['innerValidationRows'], 'Arm row or study identity differs')
        require(read_json(path/'predictions.json')['rowIndices'] == arm_config['validationRows'], 'Prediction row identity differs')
        arms.append(dict(fold=result['fold'], arm=result['arm'], rows=len(arm_config['validationRows']),
                         hashes={**result['hashes'], 'report.json': digest(path/'report.json')}))
    return dict(reportSha256=digest(output/'report.json'), configSha256=digest(output/'config.json'),
                competitorSha256=digest(output/'competitor.npy'), arms=arms)


def validate_certificate(output):
    binding = evidence_binding(output)
    certificate = read_json(output/'independent-replay.json')
    require(certificate.get('exact') is True and certificate.get('binding') == binding and
            certificate.get('sourceSha256') == digest(HERE/'multiphone_competitor_replay.py'),
            'Missing, stale or invalid exact replay certificate')
    expected_checks = [dict(fold=a['fold'], arm=a['arm'], rows=a['rows'], maximumAbsoluteDifference=0.)
                       for a in binding['arms']]
    require(certificate.get('checks') == expected_checks, 'Replay checks are incomplete or differ')
    return certificate


def main():
    torch.set_num_threads(2)
    config, report = read_json(OUTPUT/'config.json'), read_json(OUTPUT/'report.json')
    require(report['complete'] and report['configSha256']==digest(OUTPUT/'config.json'), 'Incomplete study')
    require(all(digest(HERE/name)==sha for name,sha in config['sourceSha256'].items()), 'Source differs')
    require(digest(PROTOCOL)==config['protocolSha256'], 'Protocol differs')
    cohort, splits, scalars, competitor, positions, binding = inputs()
    require(binding==config['binding'], 'Input differs')
    require(digest(OUTPUT/'competitor.npy')==report['competitorSha256'] and
            np.array_equal(competitor, np.load(OUTPUT/'competitor.npy')), 'Feature replay differs')
    binding = evidence_binding(OUTPUT)
    checks=[]
    for result in report['results']:
        path=OUTPUT/f"fold-{result['fold']}-{result['arm']}"
        require(all(digest(path/name)==sha for name,sha in result['hashes'].items()), 'Saved artifact differs')
        config_arm=read_json(path/'config.json')
        require(config_arm['studyConfigSha256']==report['configSha256'], 'Arm binding differs')
        fold=splits['folds'][result['fold']]
        require(config_arm['fitRows']==fold['innerFitRows'] and config_arm['validationRows']==fold['innerValidationRows'], 'Rows differ')
        saved=torch.load(path/'best.pt',weights_only=True)
        require(saved['configSha256']==digest(path/'config.json') and saved['epoch']==result['bestEpoch'], 'Checkpoint differs')
        values=np.concatenate((scalars,competitor if result['arm']=='competitor' else np.zeros_like(competitor)),1)
        fitpos=[positions[i] for i in config_arm['fitRows']]
        from multiphone_competitor_study import normalize
        mean,std=normalize(values,fitpos)
        require(np.array_equal(mean,saved['mean'].numpy()) and np.array_equal(std,saved['std'].numpy()), 'Normalization differs')
        selected=config_arm['validationRows']
        rows=[cohort['rows'][i] for i in selected]
        x=(torch.from_numpy(values[[positions[i] for i in selected]])-saved['mean'])/saved['std']
        phones=torch.tensor([r['targetId'] for r in rows])
        net=model();net.load_state_dict(saved['model'])
        p=predict(net,x,phones)
        original=read_json(path/'predictions.json')
        require(original['rowIndices']==selected and np.array_equal(p,original['probabilities']), 'Prediction differs')
        require(slices(p,rows,set(config_arm['fitVocabulary']))==result['evaluation'], 'Metrics differ')
        checks.append(dict(fold=result['fold'],arm=result['arm'],rows=len(rows),maximumAbsoluteDifference=0.))
    require(evidence_binding(OUTPUT) == binding, 'Evidence changed during replay')
    atomic_json(OUTPUT/'independent-replay.json',dict(exact=True, binding=binding, checks=checks,sourceSha256=digest(HERE/'multiphone_competitor_replay.py')))
    print('Independent exact replay passed for',len(checks),'checkpoints')
if __name__=='__main__':main()
