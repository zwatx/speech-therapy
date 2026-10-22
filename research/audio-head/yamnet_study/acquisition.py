"""Predeclare and acquire the next source-disjoint ESC-10 panel."""
import argparse
import csv
import shutil
import subprocess
from pathlib import Path
import multiphone_environment_challenge as original
import multiphone_environment_extension as extension
from yamnet_study import common as c

CATEGORIES = ('dog','rain','sea_waves','crackling_fire','helicopter','chainsaw')
OUT = c.OUTPUT/'acquisition'


def select(rows, excluded):
    c.require(len({r['filename'] for r in rows}) == len(rows), 'Duplicate filename')
    seen, result = set(excluded), []
    for category in CATEGORIES:
        chosen = []
        for r in sorted(rows, key=lambda r:r['filename']):
            if r['category'] != category or r['esc10'].lower()!='true' or r['fold']!='5' or r['src_file'] in seen:
                continue
            c.require(r['src_file'] and Path(r['filename']).name==r['filename'] and '\\' not in r['filename'], 'Invalid metadata')
            chosen.append(r); seen.add(r['src_file'])
            if len(chosen)==4:
                break
        c.require(len(chosen)==4, 'Insufficient fresh sources: '+category)
        result.extend(chosen)
    return result


def declare():
    c.require(not OUT.exists(), 'Fresh acquisition required')
    oldpin=c.pin(c.BASE/'environment-v1/plan.json'); old=c.read(oldpin)
    priorpin=c.pin(c.BASE/'environment-extension-v1/plan.json'); prior=c.read(priorpin)
    c.require(old['commit']==prior['commit']==original.COMMIT, 'Wrong ESC commit')
    excluded={r['metadata']['src_file'] for r in old['clips']+prior['clips']}
    c.require(len(excluded)==36, 'Expected 36 prior sources')
    ffmpeg=shutil.which('ffmpeg'); c.require(ffmpeg is not None, 'ffmpeg missing')
    bindings={k:old['inputBindings'][k] for k in ('meta/esc50.csv','LICENSE','README.md')}
    bindings.update(prior12=oldpin, prior24=priorpin, source=c.pin(__file__),
                    tests=c.pin(Path(__file__).with_name('test_acquisition.py')),
                    common=c.pin(c.__file__), conversion=c.pin(original.__file__),
                    attribution=c.pin(extension.__file__), protocol=c.pin(c.PROTOCOL), ffmpeg=c.pin(ffmpeg))
    for binding in bindings.values(): c.guard(binding)
    rows=list(csv.DictReader(Path(bindings['meta/esc50.csv']['path']).read_text().splitlines()))
    selected=select(rows, excluded); license_text=Path(bindings['LICENSE']['path']).read_text()
    attributions={r['filename']:extension.attribution(r, license_text) for r in selected}
    OUT.mkdir(parents=True)
    c.write(OUT/'selection.json', dict(commit=original.COMMIT, rows=selected,
            excludedSources=sorted(excluded), attributions=attributions, inputs=bindings,
            ffmpegVersion=subprocess.run([ffmpeg,'-version'],capture_output=True,text=True,check=True).stdout, **c.FLAGS))
    return c.pin(OUT/'selection.json')


def acquire(digest):
    binding=dict(path=str(OUT/'selection.json'), sha256=digest); plan=c.read(binding)
    for b in plan['inputs'].values(): c.guard(b)
    c.require(plan['inputs']['source']==c.pin(__file__), 'Acquisition source changed')
    c.require(not (OUT/'original').exists() and not (OUT/'pcm16').exists(), 'No implicit restart')
    metadata=list(csv.DictReader(Path(plan['inputs']['meta/esc50.csv']['path']).read_text().splitlines()))
    c.require(plan['rows']==select(metadata, plan['excludedSources']), 'Selection changed')
    (OUT/'original').mkdir(); (OUT/'pcm16').mkdir(); clips=[]
    for row in plan['rows']:
        filename=row['filename']; src=OUT/'original'/filename; dst=OUT/'pcm16'/filename
        source=original.download('audio/'+filename, src)
        command=original.convert(src, dst, plan['inputs']['ffmpeg']['path'])
        clips.append(dict(metadata=row, original=source, audio=c.pin(dst),
                          conversionCommand=command, attribution=plan['attributions'][filename]))
    for b in plan['inputs'].values(): c.guard(b)
    c.write(OUT/'complete.json', dict(complete=True, selection=binding, clips=clips, **c.FLAGS))
    return c.pin(OUT/'complete.json')


if __name__=='__main__':
    import json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['declare','acquire'])
    p.add_argument('--sha256'); a=p.parse_args()
    print(json.dumps(declare() if a.command=='declare' else acquire(a.sha256)))
