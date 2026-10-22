"""Execute the fixed frozen-head matrix with durable child-process records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from multiphone_cache import atomic_json,digest

HERE=Path(__file__).resolve().parent
BASE=HERE/'outputs/multiphone-20260926'
RECIPE=HERE/'experiments/multiphone-heads-v1.json'
CACHE={'wav2vec2-base':'wav2vec-frames','wavlm-base-plus':'wavlm-frames'}
SHORT={'wav2vec2-base':'wav2vec','wavlm-base-plus':'wavlm'}


def run(encoder: str) -> None:
    recipe=json.loads(RECIPE.read_text())
    if (digest(BASE/'cohort.json')!=recipe['cohortSha256'] or
            digest(BASE/'splits.json')!=recipe['splitsSha256']):
        raise ValueError('Matrix data/split binding changed')
    if not (BASE/CACHE[encoder]/'index.json').is_file():
        raise ValueError('Encoder cache must finish before starting its queue')
    queue_path=BASE/(SHORT[encoder]+'-queue.json')
    trainer=HERE/'multiphone_train.py'
    source_sha=digest(trainer)
    started=time.time()
    jobs=[]
    for seed in recipe['initializationSeeds']:
        for fold in recipe['folds']:
            for head in recipe['heads']:
                for rate in recipe['learningRates']:
                    label='001' if rate==0.001 else '0003'
                    output=BASE/f'inner-{SHORT[encoder]}-{head}-f{fold}-s{seed}-lr{label}'
                    expected={'seed':seed,'fold':fold,'head':head,'lr':rate,'phase':'inner'}
                    report_path=output/'report.json'
                    if report_path.exists():
                        config=json.loads((output/'config.json').read_text())
                        report=json.loads(report_path.read_text())
                        if (any(config.get(k)!=v for k,v in expected.items()) or
                                config['cohortSha256']!=recipe['cohortSha256'] or
                                config['splitsSha256']!=recipe['splitsSha256'] or
                                config['sourceSha256']['multiphone_train.py']!=source_sha or
                                report['configSha256']!=digest(output/'config.json') or
                                report['checkpointSha256']!=digest(output/'best.pt')):
                            raise ValueError('Completed run does not match the matrix')
                        jobs.append({'run':output.name,'state':'already-complete'})
                        continue
                    if output.exists():
                        raise ValueError(f'Incomplete run requires explicit recovery: {output.name}')
                    if digest(trainer)!=source_sha:
                        raise ValueError('Trainer source changed during matrix execution')
                    command=[sys.executable,str(trainer),'--cohort',str(BASE/'cohort.json'),
                             '--splits',str(BASE/'splits.json'),'--cache',str(BASE/CACHE[encoder]),
                             '--output',str(output),'--head',head,'--fold',str(fold),
                             '--device','cpu','--seed',str(seed),'--lr',str(rate),
                             '--epochs',str(recipe['maximumEpochs']),
                             '--patience',str(recipe['patienceEpochs']),'--threads','2']
                    with (BASE/(output.name+'.log')).open('w') as log:
                        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
                        job={'run':output.name,'state':'running','pid':process.pid,'startedAt':time.time()}
                        jobs.append(job)
                        atomic_json(queue_path,{'encoder':encoder,'recipeSha256':digest(RECIPE),
                                               'startedAt':started,'complete':False,'jobs':jobs})
                        print(json.dumps(job),flush=True)
                        code=process.wait()
                    job.update({'exitCode':code,'finishedAt':time.time(),
                                'state':'complete' if code==0 and report_path.exists() else 'failed'})
                    atomic_json(queue_path,{'encoder':encoder,'recipeSha256':digest(RECIPE),
                                           'startedAt':started,'complete':False,'jobs':jobs})
                    print(json.dumps(job),flush=True)
                    if job['state']=='failed':
                        raise RuntimeError(f'Training failed; inspect {output.name}.log')
    atomic_json(queue_path,{'encoder':encoder,'recipeSha256':digest(RECIPE),
                           'startedAt':started,'finishedAt':time.time(),'complete':True,'jobs':jobs})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--encoder',choices=list(CACHE),required=True)
    run(parser.parse_args().encoder)
