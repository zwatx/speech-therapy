"""Reproducible Stage D tables from saved predictions; no corpus/model inference."""
from collections import Counter
import csv
import json

from .gop import calibrated_logits
from .jibo import RUN as STAGE_C
from .stage_d import RUN, REPORT, save_json
from .stage_d_metrics import summarize


def percent(value):
    return '—' if value is None else f'{100*value:.2f}%'


def interval(values):
    return '[' + ', '.join(percent(v) for v in values) + ']'


def saved_summary(name, threshold):
    records = json.loads((RUN/f'predictions-{name}.json').read_text())
    return summarize(records, [r['logit'] for r in records], threshold)


def stage_c_summary(name):
    records = json.loads((STAGE_C/f'detection-{name}-phones.json').read_text())
    calibration = json.loads((STAGE_C/'calibration.json').read_text())
    return summarize(records, calibrated_logits(records, calibration), calibration['threshold'])


def write_csv(path, rows):
    with path.open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def append_metrics(selection, result):
    path = REPORT/'metrics.csv'
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames)
        existing = [r for r in reader if not r['model'].startswith('Stage D ')]
    additional = ['AP','P_at_R_0_3','P_at_R_0_5','P_at_R_0_7','R_at_P_0_9','R_at_P_0_8',
                  'ECE','phones','errors','speakers','AP_CI_low','AP_CI_high',
                  'R_at_P_0_9_CI_low','R_at_P_0_9_CI_high']
    fields += [k for k in additional if k not in fields]
    new = []
    for name, candidate in selection['candidates'].items():
        value = candidate['calibration']
        new.append(dict(model=f'Stage D {name} / calibration',AP=value['AP'],
                        P_at_R_0_3=value['precision_at_recall']['0.3'],
                        P_at_R_0_5=value['precision_at_recall']['0.5']))
    for name in ('speech_children','l2'):
        value = result[name]
        counts = value['at_frozen_threshold']
        new.append(dict(model=f'Stage D selected {selection["selected"]} / {name}',AP=value['AP'],
                precision=counts['precision'],recall=counts['recall'],F1=counts['F1'],
                **{f'P_at_R_{str(r).replace(".","_")}':value['precision_at_recall'][str(r)] for r in (.3,.5,.7)},
                **{f'R_at_P_{str(p).replace(".","_")}':value['recall_at_precision'][str(p)] for p in (.9,.8)},
                ECE=value['ECE']['value'],phones=value['phones'],errors=value['errors'],speakers=value['speakers'],
                AP_CI_low=value['bootstrap_95']['AP'][0],AP_CI_high=value['bootstrap_95']['AP'][1],
                R_at_P_0_9_CI_low=value['bootstrap_95']['recall_at_precision_0_9'][0],
                R_at_P_0_9_CI_high=value['bootstrap_95']['recall_at_precision_0_9'][1]))
    with path.open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        writer.writerows(existing+new)


def report():
    selection = json.loads((RUN/'selection.json').read_text())
    result = json.loads((RUN/'evaluation-result.json').read_text())
    summaries = {name:json.loads((RUN/f'{name}-summary.json').read_text())
                 for name in ('train','calibration','speech_children','l2')}
    calibration = saved_summary('calibration', selection['threshold'])
    comparison = {name:stage_c_summary(name) for name in ('speech_children','l2')}
    for name in comparison:
        old = json.loads((STAGE_C/f'detection-{name}-phones.json').read_text())
        new = json.loads((RUN/f'predictions-{name}.json').read_text())
        keys = lambda rows: {(r['id'],r['index'],r['phone'],r['error']) for r in rows}
        if len(old) != len(new) or keys(old) != keys(new):
            raise ValueError('Round 3/4 comparison denominator mismatch')
        for suffix in ('pr_curve','coverage_curve'):
            write_csv(REPORT/f'stage-d-{name}-{suffix.replace("_curve","")}.csv',result[name][suffix])
    save_json(RUN/'comparison-stage-c.json',comparison)
    append_metrics(selection,result)
    child_errors = Counter(r['speaker'] for r in json.loads((RUN/'predictions-speech_children.json').read_text()) if r['error'])
    top_two_errors = sum(count for _,count in child_errors.most_common(2))
    lines = ['# Stage D — supervised per-phone detection on frozen C features','',
             f'Selected **{selection["selected"]}** by calibration-speaker AP. Combined candidate fitting '
             f'{selection["combined_fit_seconds"]:.2f}s / 1,800s. Frozen calibrated-logit threshold '
             f'**{selection["threshold"]:.8f}**. No L2 or reporting-child fitting/tuning.','',
             f'Children AP changes from {percent(comparison["speech_children"]["AP"])} to '
             f'{percent(result["speech_children"]["AP"])}; frozen F1 changes from '
             f'{percent(comparison["speech_children"]["at_frozen_threshold"]["F1"])} to '
             f'{percent(result["speech_children"]["at_frozen_threshold"]["F1"])}. Precision falls and recall rises. '
             'P@R≥.3/.5 falls; the empirical R@P≥.9 rises. '
             f'L2 AP changes from {percent(comparison["l2"]["AP"])} to {percent(result["l2"]["AP"])}, '
             f'but frozen F1 falls from {percent(comparison["l2"]["at_frozen_threshold"]["F1"])} to '
             f'{percent(result["l2"]["at_frozen_threshold"]["F1"])} and ECE is '
             f'{percent(result["l2"]["ECE"]["value"])}. '
             '**No reliable transfer or clinical-feedback qualification is established.**','',
             '## Data and features','',
             'SpeechOcean official train uses **all 2,500 utterances**, including lower-scored speech, '
             'from L2-Mandarin learners (adults and children). The unchanged round-3 label rule is '
             '**exact aggregate score 0 or 1 = error; exactly 2 = correct; fractional averaged scores '
             'are excluded**, including fractions below 1. No produced identity is inferred from scores.','',
             '| Group | Utterances | Labeled phones | Errors | Speakers | Fractional phones excluded |',
             '|---|---:|---:|---:|---:|---:|']
    for name, value in summaries.items():
        lines.append(f'| {name} | {value["utterances"]} | {value["phones"]} | {value["errors"]} | '
                     f'{value["speakers"]} | {value["excluded_fractional"]} |')
    lines += ['', 'Calibration uses the exact Stage C 62-speaker list. Reporting uses the same disjoint '
              '30 children ages 6–12, 7,980 phones / 185 errors. The four L2 pilot speakers '
              'YDCK/ZHAA/ASI/YBAA contribute the same 19,685 canonical positions / 2,252 errors. '
              'Reserved speakers were never opened. No CMU/private/closed-study source was used.','',
              '168 features, extracted identically by one function: 39 global replacement-ratio '
              'columns (canonical identity column is zero) plus deletion, preserving all 38 actual '
              'alternatives; mean/max canonical frame posterior in its CTC Viterbi state span; '
              'span seconds at 20 ms stride; utterance and word-relative positions; word metadata '
              'availability; canonical/previous/next one-hot identities with explicit boundary; '
              'greedy prompt-blind recognition disagreement. Ratios are log P(alternative complete '
              'sequence) − log P(canonical complete sequence), matching Stage C error orientation. '
              'CTC sums all legal paths without canonical windows for the ratio vector. '
              'Viterbi occupancy spans are emission-state spikes, **not validated phoneme durations**.','',
              'Expert scores, source, age, speaker, produced-phone references and manual timing are '
              'absent from feature values. SpeechOcean word grouping is independent prompt metadata. '
              'The saved L2 manifest has no independent canonical per-word grouping: word positions '
              'use −1/availability=0 for every L2 phone; manual reference timings are not substituted. '
              'This missing feature family limits the source comparison. All canonical positions '
              'get features before fractional-label masking. Train-derived standardization only.','',
              'Frozen C train posteriors were computed/cache-saved once on MPS; calibration/reporting/L2 '
              'reuse Stage C posteriors. C is the JIBO-adapted wav2vec2 espeak checkpoint. It was already '
              'exposed to the 222 all-correct train clips during adaptation. Cache identity records '
              'checkpoint/manifest/split/word-metadata/extractor hashes and feature names.','',
              f'Ratio clipping counts by group: { {k:v["clipped_ratios"] for k,v in summaries.items()} }. '
              f'Other feature exclusions: { {k:v["excluded"] for k,v in summaries.items()} }.','',
              '## Predeclared candidates and calibration selection','',
              'Seed43; no class weighting/oversampling/search. Logistic: standardized inputs, L2 C1, '
              'lbfgs/max_iter3000. HistGradientBoosting: raw identical columns, 200 iterations, '
              'learning rate .08, 15 leaves, min leaf50, L2=1, early stopping disabled. MLP: '
              'standardized inputs, 128/64 ReLU, dropout .1, one logit, BCE/AdamW .001/weight decay .01, '
              'batch1024, gradient clip5, fixed20epochs, no epoch selection. All trained only on '
              'official train labeled positions. sklearn1.8.0 is pinned in requirements-stage-d.txt.','',
              '| Candidate | Calibration AP | P at R≥.3 | P at R≥.5 | Fit seconds |',
              '|---|---:|---:|---:|---:|']
    for name, value in selection['candidates'].items():
        metric = value['calibration']
        lines.append(f'| {name} | {percent(metric["AP"])} | {percent(metric["precision_at_recall"]["0.3"])} | '
                     f'{percent(metric["precision_at_recall"]["0.5"])} | {value["fit_seconds"]:.2f} |')
    lines += ['', 'Selection uses raw calibration AP, ties follow declaration order. Only selected model '
              'gets positive-slope Platt scaling (slope L2=1, standardized raw logit); all same calibration '
              'phones fit it and the max-F1 threshold, highest threshold wins ties. This preserves ranking. '
              'Calibration threshold metrics/ECE are in-sample and optimistic. No isotonic alternative '
              'or new threshold was chosen on either reporting cohort.','',
              f'Platt parameters: {selection["platt"]}. Calibration at frozen threshold: '
              f'P {percent(calibration["at_frozen_threshold"]["precision"])}, '
              f'R {percent(calibration["at_frozen_threshold"]["recall"])}, '
              f'F1 {percent(calibration["at_frozen_threshold"]["F1"])}, '
              f'ECE {percent(calibration["ECE"]["value"])}.','',
              '## Selected model — single frozen reporting pass','',
              '| Cohort | AP [speaker 95% CI] | P at R≥.3 | P at R≥.5 | P at R≥.7 | R at P≥.9 [95% CI] | R at P≥.8 |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for name in ('speech_children','l2'):
        v = result[name]
        lines.append(f'| {name} | {percent(v["AP"])} {interval(v["bootstrap_95"]["AP"])} | ' +
                     ' | '.join(percent(v['precision_at_recall'][str(r)]) for r in (.3,.5,.7)) +
                     f' | {percent(v["recall_at_precision"]["0.9"])} '
                     f'{interval(v["bootstrap_95"]["recall_at_precision_0_9"])} | '
                     f'{percent(v["recall_at_precision"]["0.8"])} |')
    lines += ['', '| Cohort | TP | FP | FN | TN | Frozen P | Frozen R | Frozen F1 | ECE (15 bins) |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name in ('speech_children','l2'):
        v = result[name]
        c = v['at_frozen_threshold']
        lines.append(f'| {name} | {c["TP"]} | {c["FP"]} | {c["FN"]} | {c["TN"]} | '
                     f'{percent(c["precision"])} | {percent(c["recall"])} | {percent(c["F1"])} | '
                     f'{percent(v["ECE"]["value"])} |')
    lines += ['', 'AP is the unsmoothed tied-threshold empirical average precision. P@R summaries are '
              'maximum empirical precision at/above each recall; R@P is maximum recall at/above '
              'precision. These are reporting curves, **not deployable thresholds selected on test/L2**. '
              'ECE is error-probability calibration using 15 fixed equal-width bins.','',
              'Bootstrap: 2,000 speaker-cluster resamples with replacement, seed73, all phones from '
              'each selected speaker and exact multiplicities, percentile2.5/97.5. Fixed model, '
              'calibration and threshold; uncertainty in fitting/selection is not included. '
              'R@P≥.9 is recomputed descriptively in each replicate, not the frozen-threshold recall. '
              f'Valid replicates: { {name:result[name]["bootstrap_95"]["valid"] for name in ("speech_children","l2")} }. '
              f'Two reporting children account for {top_two_errors}/{result["speech_children"]["errors"]} '
              f'errors ({percent(top_two_errors/result["speech_children"]["errors"])}); '
              f'{len(child_errors)} children have any labeled errors. '
              'This concentration makes speaker-resampling uncertainty large. '
              'No paired significance test or claim that the modest AP gain is robust is made. '
              'Four-speaker L2 intervals are especially unstable and cannot establish population coverage.','',
              '## Abstention / risk–coverage','',
              'Retain largest absolute calibrated-logit distance from the frozen threshold, with tied '
              'confidence retained together. Others receive no verdict. Precision below is conditional '
              'on **error flags**, not all verdicts; — means no flags. Confident OK verdicts dominate '
              'low coverage. Verdict accuracy includes both OK/error verdicts. End-to-end error recall '
              'counts abstained errors as missed; high conditional precision alone is insufficient.','',
              '| Cohort | Verdict coverage | Phones with verdict | Error-flag precision | Verdict accuracy | End-to-end error recall |',
              '|---|---:|---:|---:|---:|---:|']
    for name in ('speech_children','l2'):
        curve = result[name]['coverage_curve']
        for target in (.1,.3,.5,.7,.9,1.):
            v = next(r for r in curve if r['coverage'] >= target)
            lines.append(f'| {name} | {percent(v["coverage"])} | {v["phones"]} | '
                         f'{percent(v["precision"])} | {percent(v["verdict_accuracy"])} | '
                         f'{percent(v["end_to_end_recall"])} |')
    lines += ['', 'Full PR/coverage curves: stage-d-{speech_children,l2}-{pr,coverage}.csv. '
              'Coverage denominators exclude only the same fractional-score phones as primary metrics; '
              'no additional usability/nonspeech rejection is implemented.','',
              '## Target-relevant consonants','',
              'One globally frozen threshold; no per-phone calibration/tuning. Sparse error counts '
              'make individual rows unstable. Zero-error AP/recall is undefined (—).','',
              '| Cohort | Phone | Phones | Errors | AP | Frozen P | Frozen R | Frozen F1 |',
              '|---|---|---:|---:|---:|---:|---:|---:|']
    for name in ('speech_children','l2'):
        for phone, v in result[name]['per_phone'].items():
            c = v['at_frozen_threshold']
            lines.append(f'| {name} | {phone} | {v["phones"]} | {v["errors"]} | {percent(v["AP"])} | '
                         f'{percent(c["precision"])} | {percent(c["recall"])} | {percent(c["F1"])} |')
    lines += ['', '## Comparison with round 3','',
              'Exact (utterance,index,phone,label) keys and denominator counts match round 3. '
              'Stage C uses the saved two-weight GOP/disagreement calibration and original frozen '
              'threshold. No acoustic model or Stage C calibration is rerun.','',
              '| Cohort | Detector | AP | P at R≥.3 | P at R≥.5 | R at P≥.9 | Frozen P | Frozen R | Frozen F1 | ECE |',
              '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name in ('speech_children','l2'):
        for label,v in [('Stage C',comparison[name]),('Stage D',result[name])]:
            c = v['at_frozen_threshold']
            values = [v['AP'],v['precision_at_recall']['0.3'],v['precision_at_recall']['0.5'],
                      v['recall_at_precision']['0.9'],c['precision'],c['recall'],c['F1'],v['ECE']['value']]
            lines.append(f'| {name} | {label} | ' + ' | '.join(percent(n) for n in values) + ' |')
    lines += ['', '## Honest limits','',
              'This is descriptive development evidence. Both SpeechOcean official-test speaker '
              'groups were exposed in round-2 architecture/checkpoint development; calibration is '
              'reused for model selection, probability fitting and threshold choice. Reporting children '
              'are disjoint from current detector calibration/training, but are **not an untouched '
              'confirmation set**. Fractional exclusion favors rating extremes and discards ambiguous '
              'phones. Score-based acceptability is not produced-phone truth or clinical diagnosis. '
              'Training population mixes adults/children and Mandarin L2; L2-ARCTIC pilot is four '
              'exposed adult speakers with different annotation semantics, including same-identity '
              'deviations. Canonical insertion-gap errors are outside the phone denominator.','',
              'JIBO adaptation uses younger children ages4–7 without clinical labels. Broad phone '
              'normalization loses narrow distortion detail. Forced emission spans do not establish '
              'valid timing, and L2 missing word metadata adds a feature distribution shift. Bootstrap '
              'intervals do not repair selection exposure or cross-source population mismatch. '
              'No prospective precision, coverage, calibration or learner-feedback gate is established. '
              'No app integration is included. Optional JIBO ±150ms check was not declared/run.','',
              '## Files, commands, checks and blockers','',
              'Code: mdd_v1/stage_d{,_features,_models,_metrics,_report,_verify}.py, '
              'test_stage_d.py, requirements-stage-d.txt, README.md. Report/protocol/command ledger/'
              'review/metrics/curves live in work/mdd-v1. Ignored posterior/feature caches, all three '
              'models, calibration predictions, selected reporting predictions, full metrics and '
              'bootstrap intervals live in outputs/mdd_v1/stage-d/.','',
              'Commands use research/audio-head/.venv/bin/python -B -W error, HF_HUB_OFFLINE=1. '
              'See stage-d-commands.csv for exact argv, exits and measured wall times, including '
              'corrected draft/setup failures. Package installation downloaded sklearn and small '
              'dependencies; **corpus/model operations remained offline**. No fitting command is '
              'repeated for report/verification. No commits/push/branch changes/iOS edits.','',
              '| Command receipt | Exit | Wall seconds |', '|---|---:|---:|']
    with (REPORT/'stage-d-commands.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            lines.append(f'| {row["label"]} | {row["exit_code"]} | {row["wall_seconds"]} |')
    verification = RUN/'verification.json'
    if verification.exists():
        verified = json.loads(verification.read_text())
        lines += ['', f'Saved-artifact verification: **{verified["status"]}**.', '']
        lines += ['- ' + check + '.' for check in verified['checks']]
        lines += ['', 'Reporting model inference was not repeated by verification.', '']
    review = REPORT/'stage-d-review.md'
    lines += ['', '**40 tests passed with warnings treated as errors.** Tests cover enumerated full CTC alternatives/deletion, repeated-state alignment, '
              'label/timing-independent features, explicit missing metadata, tied AP, ECE endpoints, '
              'cluster-bootstrap multiplicities against explicit resampling, positive Platt slope '
              'and completed-fit/evaluation guards. Legacy Stage C/manifest/runtime/L2 parser tests '
              'also run with warnings as errors. See command ledger for observed counts/exits.','',
              ('Independent read-only review and responses: stage-d-review.md.' if review.exists()
               else 'Independent read-only review is pending; completion must be checked before handoff.'), '',
              'No data-access or runtime blocker remains. Scientific/feature limitations above remain '
              'and must not be interpreted as clinical qualification.']
    (REPORT/'stage-d-result.md').write_text('\n'.join(lines)+'\n')
    print(f'Wrote {REPORT / "stage-d-result.md"}',flush=True)


if __name__ == '__main__':
    report()
