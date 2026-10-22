"""Read-only saved-result/source/selection/count invariants for a completed Stage C."""
from collections import Counter,defaultdict
import json
import math

from .jibo import RUN,split_children,DATA
from .manifest import OUTPUT,load_manifest
from .stage_c import frame_path
from .evaluate import evaluate
from .gop import calibrated_logits,operating_counts,labels


def main():
    fit = json.loads((RUN/'result.json').read_text())
    recognition = json.loads((RUN/'recognition-result.json').read_text())
    detection = json.loads((RUN/'detection-result.json').read_text())
    jibo = load_manifest(RUN/'manifest.jsonl')
    split = json.loads((RUN/'child-split.json').read_text())['children']
    assert len(split)==109 and Counter(split.values())==dict(train=87,dev=11,test=11)
    assert len({r['id'] for r in jibo})==len(jibo)==7294
    assert all(r['split']==split[r['speaker']] for r in jibo)
    hashes = defaultdict(set)
    for row in jibo:
        hashes[row['audio_sha256']].add(row['split'])
        assert row['perceived'] and 'xxx' not in row['raw']['phonetic_text_normalized']
    assert all(len(s)==1 for s in hashes.values())
    ledger = json.loads((RUN/'budget-ledger.json').read_text())
    prior = sum(a['charge_seconds'] for a in ledger['attempts'])
    assert fit['budget_seconds']==ledger['final_loop_budget_seconds']
    assert fit['training_wall_seconds']<=fit['budget_seconds']
    assert fit['prior_fitting_seconds']==prior and fit['resource_probe_reserve_seconds']==120
    assert abs(fit['cumulative_budget_charge_seconds']-fit['training_wall_seconds']-prior-120)<1e-8
    assert fit['cumulative_budget_charge_seconds']<=2700
    for attempt in ledger['attempts']:
        failed = RUN/attempt['folder']
        if attempt['folder']=='interrupted-eager':
            evidence = json.loads((failed/'failure.json').read_text())
            assert evidence['last_recorded_fitting_seconds']<=attempt['charge_seconds']
        else:
            measured = (failed/'train.log').stat().st_mtime-(failed/'settings.json').stat().st_mtime
            assert measured <= attempt['charge_seconds']
    best = min(fit['history'],key=lambda e:e['dev_PER'])
    assert best['epoch']==fit['best_epoch'] and best['dev_PER']==fit['best_dev_PER']
    assert fit['jibo_train']==5865 and fit['speech_train']==222
    rows = load_manifest()
    groups = dict(jibo_test=[r for r in jibo if r['split']=='test'],
                  speech_dev=[r for r in rows if r['source']=='speechocean762' and r['split']=='test' and r['all_correct']],
                  l2=[r for r in rows if r['source']=='l2-arctic'])
    assert {r['speaker'] for r in groups['l2']}=={'YDCK','ZHAA','ASI','YBAA'}
    for name in ('A0','A','C'):
        predictions = json.loads((RUN/f'{name}-recognition-predictions.json').read_text())
        for group in groups if name=='C' else ['jibo_test']:
            # JSON stores confusion tuples as lists; compare the saved schema.
            recomputed = json.loads(json.dumps(evaluate(groups[group],predictions)))
            assert recomputed==recognition[name][group]
    details = load_manifest(RUN/'A0-recognition-details.jsonl')
    a0_predictions = json.loads((RUN/'A0-recognition-predictions.json').read_text())
    assert len(details)==876 and {r['id'] for r in details}=={r['id'] for r in groups['jibo_test']}
    assert all(r['phones']==a0_predictions[r['id']] for r in details)
    assert Counter(t for r in details for t in r['unmapped'])==recognition['A0']['unmapped']
    detection_predictions = json.loads((RUN/'detection-predictions.json').read_text())
    c_predictions = json.loads((RUN/'C-recognition-predictions.json').read_text())
    shared = set(detection_predictions)&set(c_predictions)
    assert len(shared)>=597
    assert all(detection_predictions[k]==c_predictions[k] for k in shared)
    speech_split = json.loads((RUN/'speech-detection-split.json').read_text())
    calibration = set(speech_split['calibration_speakers'])
    reporting = set(speech_split['reporting_speakers'])
    assert not calibration&reporting
    assert len(calibration)==62 and len(reporting)==63
    for name in ('calibration','speech_children','speech_all_children','l2'):
        records = json.loads((RUN/f'detection-{name}-phones.json').read_text())
        assert all(math.isfinite(r['gop']) for r in records)
        skipped = {r['id'] for r in detection['excluded'] if r['group']==name or name=='speech_all_children'}
        expected_rows = [r for r in rows if r['id'] not in skipped and (
            (name=='l2' and r['source']=='l2-arctic') or
            (r['source']=='speechocean762' and r['split']=='test' and
             ((name=='calibration' and r['speaker'] in calibration) or
              (name=='speech_children' and r['speaker'] in reporting and r['age'] is not None and 6<=r['age']<=12) or
              (name=='speech_all_children' and r['age'] is not None and 6<=r['age']<=12))))]
        expected_labels = {(r['id'],i):error for r in expected_rows for i,error in labels(r).items()}
        assert {(r['id'],r['index']):r['error'] for r in records}==expected_labels
        assert len(records)==len(expected_labels)
        if name=='calibration':
            assert all(r['id'].startswith('so:') and r['speaker'] in calibration for r in records)
            assert len(records)==detection['calibration']['phones']
        else:
            allowed = (reporting if name=='speech_children' else calibration|reporting if name=='speech_all_children' else {'YDCK','ZHAA','ASI','YBAA'})
            assert all(r['speaker'] in allowed for r in records)
            logits = calibrated_logits(records,detection['calibration'])
            counts = operating_counts([r['error'] for r in records],logits>=detection['calibration']['threshold'])
            assert counts==detection[name]['at_frozen_threshold']
            assert len(records)==detection[name]['phones']
            assert abs(detection[name]['coverage_curve'][-1]['end_to_end_recall']-counts['recall'])<1e-12
    print('PASS: split/source/count/selection/budget/recognition/calibration/coverage invariants')


if __name__ == '__main__':
    main()
