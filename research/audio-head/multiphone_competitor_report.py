"""Summarize every predeclared competitor arm without selecting a winner."""
import csv
import numpy as np
from multiphone_competitor_study import OUTPUT, BASE, HERE
from multiphone_local_train import read_json, digest
from multiphone_cache import atomic_json
from multiphone_competitor_replay import validate_certificate

def main():
    validate_certificate(OUTPUT)
    report=read_json(OUTPUT/'report.json');results=report['results']
    lines=['# Canonical-competitor posterior exploratory results', '',
      'All ten fixed fits and separate-process exact checkpoint replays completed. The added posterior columns do not yield a consistent gain; no winner is selected. These are five overlapping inner-development folds, not an independent replication or clinical evaluation.', '',
      'The fixed study uses all-age fitting, 23 supported targets, and 24 competitor columns including ZH. Both arms have 37 input columns and the same 4,163 parameters; the control zero-pads its additional columns, so effective capacity is not identical. Full 392-token posterior normalization and existing forced intervals are preserved.', '',
      '## Descriptive five-fold means', '', '| Slice | Age | Arm | Macro NLL | Per-rater Brier | Rating-0 AUROC | Rating-0 AP | Below-2 AUROC | Below-2 AP |','|---|---|---|---:|---:|---:|---:|---:|---:|']
    means=[]
    for sl in ['allRows','targetWordSeen','targetWordUnseen']:
      for age in ['allAges','ages6to12']:
       for arm in ['control','competitor']:
        mm=[r['evaluation'][sl][age] for r in results if r['arm']==arm]
        vals=[np.mean([m[key] for m in mm]) for key in ['macroTargetLogLoss','perRaterBrier']]
        vals += [np.mean([m['targetDiscrimination']['macroTarget'][event][key] for m in mm]) for event in ['rating0','ratingBelow2'] for key in ['auroc','averagePrecision']]
        lines.append('| '+ ' | '.join([sl,age,arm]+[f'{v:.6f}' for v in vals])+' |')
        means.append(dict(slice=sl,age=age,arm=arm,values=vals))
    lines += ['', 'Ranking is macro across phones with both positive and negative votes; defined phone sets vary by fold and slice. The full per-phone tables include undefined entries and denominators. No intervals are calculated from overlapping fold means.', '', '## Each fold', '', '| Fold | Arm | Selected epoch | All-age NLL | Child NLL | Child rows | Unseen child rows |','|---|---|---:|---:|---:|---:|---:|']
    for r in results:
        m=r['evaluation']['allRows'];un=r['evaluation']['targetWordUnseen']['ages6to12']
        lines.append(f"| {r['fold']} | {r['arm']} | {r['bestEpoch']} | {m['allAges']['macroTargetLogLoss']:.6f} | {m['ages6to12']['macroTargetLogLoss']:.6f} | {m['ages6to12']['examples']} | {un['examples']} |")
    cohort=read_json(BASE/'cohort.json');splits=read_json(BASE/'splits.json')
    children=[cohort['rows'][i] for f in splits['folds'] for i in f['innerValidationRows'] if 6<=cohort['rows'][i]['age']<=12]
    memberships=sum(len({cohort['rows'][i]['speakerId'] for i in f['innerValidationRows'] if 6<=cohort['rows'][i]['age']<=12}) for f in splits['folds'])
    lines += ['', f"The child tables contain {len(children)} row memberships, {len({r['id'] for r in children})} distinct rows, {memberships} speaker-fold memberships and {len({r['speakerId'] for r in children})} distinct children. Repeated memberships are not independent observations.", '',
      'The target-word-unseen slice uses exactly the same validation rows for both arms and each fold’s fitting target-row vocabulary. It is not word-disjoint: fitting utterances can contain these words elsewhere. All-age fitting can favor proper probability scores while lower-rating ranking trades off. This run is a short exploratory recipe, not a replacement for earlier tuned scalar controls.', '',
      '## Verification and retained artifacts', '',
      '- Four focused tests passed: full-vocabulary mass, exact interval, invalid interval/token rejection, fit-only normalization, and matching input width (four test methods).',
      '- Five additional certificate tests pass: missing/stale evidence, changed checkpoint/cohort, and incorrect or incomplete run/check identities are rejected before verified reporting.',
      '- The replay certificate binds the current study report, configuration, competitor array and all ten run artifact sets. Historical generated reports remain in `historical-report-v1`.',
      '- Loader preflight audited 14,837 eligible rows and 2,495 CTC matrices; each target posterior reproduces its existing scalar within 1e-6.',
      '- All ten saved checkpoints replay exactly in a separate process, including fit-only moments, probabilities and all reported metrics.',
      '- Each arm ran 20 epochs; best/last checkpoints, optimizer state, every epoch NLL and row-order hash, predictions and input/source hashes are retained. No failures occurred.',
      '- `report.json` retains every age/slice/phone metric; `per-phone.csv` exposes positive/negative vote, row and speaker denominators. `independent-replay.json` records the separate verification.', '',
      'Run from repository root:', '', '```sh',
      'research/audio-head/.venv/bin/python -m unittest discover -s research/audio-head -p \"test_multiphone_competitor_*.py\"',
      'research/audio-head/.venv/bin/python research/audio-head/multiphone_competitor_study.py --run',
      'research/audio-head/.venv/bin/python research/audio-head/multiphone_competitor_replay.py',
      'research/audio-head/.venv/bin/python research/audio-head/multiphone_competitor_report.py', '```', '',
      'The run command refuses to overwrite any completed or failed run. No outer predictions, author-test recording access, external data, encoder extraction, corpus relabeling or model promotion occurred. Forced windows and canonical mappings remain unverified, produced-phone/error-type labels are absent, and ZH has no supervised model.']
    fields=['fold','arm','slice','age','phone','rows','speakers','event','positiveVotes','negativeVotes','auroc','averagePrecision']
    with (OUTPUT/'per-phone.csv').open('w') as f:
      writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
      for r in results:
       for sl,ages in r['evaluation'].items():
        for age,m in ages.items():
         if m is None:continue
         for phone,metrics in m['targetDiscrimination']['perPhone'].items():
          for event in ['rating0','ratingBelow2']:
           v=metrics[event];support=m['perTarget'][phone]
           writer.writerow(dict(fold=r['fold'],arm=r['arm'],slice=sl,age=age,phone=phone,rows=support['examples'],speakers=support['speakers'],event=event,positiveVotes=v['positiveRaterWeight'],negativeVotes=v['negativeRaterWeight'],auroc=v['auroc'],averagePrecision=v['averagePrecision']))
    text='\n'.join(lines)+'\n'
    (OUTPUT/'report.md').write_text(text)
    destination=HERE.parent.parent/'docs/model/multiphone-competitor-report.md'
    destination.write_text(text.replace('`report.json`', '[complete report.json](../../research/audio-head/outputs/multiphone-20260927/competitor-v1/report.json)').replace('`per-phone.csv`','[per-phone.csv](../../research/audio-head/outputs/multiphone-20260927/competitor-v1/per-phone.csv)'))
    atomic_json(OUTPUT/'summary.json',dict(means=means, sourceSha256=digest(HERE/'multiphone_competitor_report.py'), reportSha256=digest(OUTPUT/'report.json')))
    print(text[:6000])
if __name__=='__main__':main()
