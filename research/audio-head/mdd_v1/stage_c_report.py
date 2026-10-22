"""Saved-artifact Stage C report, metrics append and complete PR/coverage CSVs."""
import csv
import html
import json
from pathlib import Path

from .jibo import RUN
from .manifest import ROOT,OUTPUT,load_manifest
from .evaluate import evaluate

WORK = ROOT.parents[1]/'work/mdd-v1'


def percent(value):
    return '—' if value is None else f'{100*value:.2f}%'


def write_csv(path,rows):
    with path.open('w',newline='') as out:
        writer = csv.DictWriter(out,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def sample_curve(curve,n=400):
    count = min(n,len(curve))
    return [curve[i] for i in sorted({round(j*(len(curve)-1)/max(1,count-1)) for j in range(count)})]


def plot_svg(series,xkey,title):
    pieces = [f'<svg viewBox="0 0 680 330" role="img" aria-label="{html.escape(title)}"><title>{html.escape(title)}</title>']
    for i in range(6):
        x = i/5
        pieces.append(f'<path d="M {50+600*x:.1f} 20 V 280 M50 {280-260*x:.1f} H650" stroke="currentColor" opacity=".12"/>')
        pieces.append(f'<text x="{50+600*x:.1f}" y="300" text-anchor="middle">{x:.1f}</text><text x="42" y="{284-260*x:.1f}" text-anchor="end">{x:.1f}</text>')
    pieces.append('<path d="M50 20 V280 H650" stroke="currentColor" fill="none"/>')
    for name,curve,color in series:
        commands = []
        move = True
        for p in sample_curve(curve):
            if p['precision'] is None:
                move=True; continue
            commands.append(f'{"M" if move else "L"}{50+600*p[xkey]:.2f},{280-260*p["precision"]:.2f}')
            move=False
        pieces.append(f'<path d="{" ".join(commands)}" fill="none" stroke="{color}" stroke-width="2"/>')
    pieces.append(f'<text x="350" y="324" text-anchor="middle">{"Recall" if xkey=="recall" else "Fraction of eligible phones given a verdict"}</text>')
    pieces.append('<text transform="translate(13 155) rotate(-90)" text-anchor="middle">Error-flag precision</text></svg>')
    return ''.join(pieces)


def main():
    recognition = json.loads((RUN/'recognition-result.json').read_text())
    detection = json.loads((RUN/'detection-result.json').read_text())
    fit = json.loads((RUN/'result.json').read_text())
    data = json.loads((RUN/'data-summary.json').read_text())
    a0 = json.loads((OUTPUT/'a0-result.json').read_text())
    a = json.loads((OUTPUT/'selected-result.json').read_text())
    calibration = detection['calibration']
    ledger = json.loads((RUN/'budget-ledger.json').read_text())
    failed_settings = json.loads((RUN/'failed-variable-shapes/settings.json').read_text())
    probe = json.loads((RUN/'resource-probe-final.json').read_text())
    manifest = load_manifest(RUN/'manifest.jsonl')
    splits = json.loads((RUN/'child-split.json').read_text())['children']
    speech_split = json.loads((RUN/'speech-detection-split.json').read_text())
    metrics = []
    for name,results in [('A0',dict(recognition['A0'],speech_dev=a0['speech_dev'],l2=a0['l2'])),
                         ('A',dict(recognition['A'],speech_dev=a['speech_dev'],l2=a['l2'])),('C',recognition['C'])]:
        for source in ('jibo_test','speech_dev','l2'):
            metrics.append((name,source,results[source]))
    rows = []
    for name,source,m in metrics:
        rows.append(f'| {name} | {source} | {m["per_utterances"]} | {m["per"]["N"]} | {m["per"]["S"]} | {m["per"]["D"]} | {m["per"]["I"]} | {percent(m["PER"])} | {percent(m.get("precision"))} | {percent(m.get("recall"))} | {percent(m.get("F1"))} | {percent(m.get("diagnosis_accuracy"))} |')
    mdd_rows = '\n'.join(f'| {name} | {m["mdd"]["TA"]} | {m["mdd"]["FR"]} | {m["mdd"]["FA"]} | {m["mdd"]["TR"]} | {m["mdd"]["CD"]} / {m["mdd"]["diagnosis_eligible_TR"]} |' for name,source,m in metrics if source=='l2')
    detection_rows = []
    coverage_rows = []
    for source in ('l2','speech_children','speech_all_children'):
        d = detection[source]; op = d['at_frozen_threshold']
        detection_rows.append(f'| {source} | {d["phones"]} | {d["errors"]} | {d["speakers"]} | {percent(op["precision"])} | {percent(op["recall"])} | {percent(op["F1"])} | {percent(d["precision_at_recall"]["0.3"])} | {percent(d["precision_at_recall"]["0.5"])} | {percent(d["precision_at_recall"]["0.7"])} | {percent(d["recall_at_precision_0_9"])} |')
        write_csv(WORK/f'stage-c-{source}-pr.csv',d['pr_curve'])
        write_csv(WORK/f'stage-c-{source}-coverage.csv',d['coverage_curve'])
        for coverage in (.1,.3,.5,.7,.9,1.):
            p = next(p for p in d['coverage_curve'] if p['coverage']>=coverage)
            coverage_rows.append(f'| {source} | {percent(p["coverage"])} | {p["phones"]} | {percent(p["precision"])} | {percent(p["verdict_accuracy"])} | {percent(p["end_to_end_recall"])} |')
    summary = []
    for split,group in data['splits'].items():
        summary.append(f'| {split} | {group["children"]} | {group["utterances"]} | {group["hours"]:.4f} | {group["phones"]} | {group["genders"]} | {group["tasks"]} |')
    confusions = '\n'.join(f'| {phone} | {count} |' for phone,count in recognition['C']['jibo_test']['top_confusions'])
    train = [r for r in manifest if r['split']=='train']
    test = [r for r in manifest if r['split']=='test']
    prompts = {r['raw']['orthographic_text_normalized'] for r in train}
    phone_sequences = {tuple(r['perceived']) for r in train}
    prompt_overlap = sum(r['raw']['orthographic_text_normalized'] in prompts for r in test)
    phone_overlap = sum(tuple(r['perceived']) in phone_sequences for r in test)
    metadata = json.loads((RUN/'posterior-summary.json').read_text())
    history_rows = '\n'.join(f'| {e["epoch"]} | {e.get("seen",0)} | {e.get("steps",0)} | {percent(e["dev_PER"])} | {e["seconds"]:.2f} |' for e in fit['history'])
    report = f'''# MDD v1 — Stage C child adaptation and prompt-aware detection

Completed offline on M3 Max/MPS, 2026-10-22. One predeclared C variant initialized
from round-2 selected A, with the same final-four-block architecture. Selected
**epoch {fit['best_epoch']}** by **JIBO dev PER {percent(fit['best_dev_PER'])} only**.
No L2 labels were used for fitting, model choice, calibration or threshold choice.

The first child produced-phone result is **JIBO test PER {percent(recognition['C']['jibo_test']['PER'])}**,
versus A0 {percent(recognition['A0']['jibo_test']['PER'])} and round-2 A {percent(recognition['A']['jibo_test']['PER'])}.
This measures broad recognition of child productions, not clinical error detection.
Relative child PER reduction vs same 39-phone-head A:
{percent(1-recognition['C']['jibo_test']['PER']/recognition['A']['jibo_test']['PER'])}.
SpeechOcean dev PER rises from {percent(a['speech_dev']['PER'])} to
{percent(recognition['C']['speech_dev']['PER'])}; L2 PER rises from
{percent(a['l2']['PER'])} to {percent(recognition['C']['l2']['PER'])}, and recognition-
based MDD F1 falls from {percent(a['l2']['F1'])} to {percent(recognition['C']['l2']['F1'])}.
Child recognition gains accompany regression on the adult/proxy sources.
At the SpeechOcean-chosen threshold, prompt-aware L2 precision/recall/F1 are
{percent(detection['l2']['at_frozen_threshold']['precision'])} /
{percent(detection['l2']['at_frozen_threshold']['recall'])} /
{percent(detection['l2']['at_frozen_threshold']['F1'])}. Precision rises and recall
falls substantially relative to recognition disagreement; F1 is lower. Disjoint
SpeechOcean children reach F1 {percent(detection['speech_children']['at_frozen_threshold']['F1'])}
on the selected score labels. These results show limited source transfer.



## Recognition and prompt-blind MDD

| Model | Evaluation | PER utterances | N | S | D | I | PER | MDD precision | Recall | F1 | Diagnosis accuracy |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

JIBO test: 876 intervals from 11 children, ages 4–7 at corpus level (individual
ages unavailable). SpeechOcean dev is the same 203 all-correct official-test
utterances used in round 2, score-derived canonical proxies. L2 has 597 pilot
utterances/4 adult speakers; 11 whole utterances with unknown produced identities
are excluded from PER only. Canonical-position MDD includes all 19,685 positions.
A0/A SpeechOcean and L2 numbers reuse saved round-2 predictions, without rerunning
those models. A0/A JIBO are matched new evaluations of the same held-out intervals.
A0 emitted {sum(recognition['A0']['unmapped'].values())} unmapped original-vocabulary
tokens on JIBO, retained as `<unk>` PER errors; raw tokens remain in
A0-recognition-details.jsonl. The round-2 original-head mapping was unchanged.
Checkpoint reload verification: {recognition['checkpoint_replay']}.

L2 recognition-based MDD support (canonical-position substitutions/deletions):

| Model | TA | FR | FA | TR | Correct diagnosis / eligible TR |
|---|---:|---:|---:|---:|---:|
{mdd_rows}

## Prompt-aware error detection

For each canonical position: error-oriented GOP = max log P(complete canonical
sequence with that phone replaced by any of the other 38 phones, or deleted)
minus log P(complete canonical sequence). CPU float32 CTC sums every legal
alignment; no forced canonical phone window. A second feature is greedy
prompt-blind recognition disagreement at that position. Logistic calibration
standardizes these two features using SpeechOcean calibration data only.

Calibration: {calibration['phones']} phones, {calibration['errors']} exact-score
errors, {len(speech_split['calibration_speakers'])} official-test speakers. Scores
exactly 0 or 1 label errors, score 2 labels correct, fractional aggregate scores
are excluded: {detection['excluded_fractional_score_phones']}. L2 source error
annotations are used as-is, including same-broad-identity starred deviations.
These detection metrics cover canonical-position substitutions/deletions;
insertion-gap events remain outside this denominator.
Threshold: logit **{calibration['threshold']:.8f}**, maximum calibration F1
{percent(calibration['calibration_at_threshold']['F1'])}; ties take highest threshold.
Standardization mean {calibration['mean']}, scale {calibration['scale']}; weights
(intercept, GOP, disagreement) {calibration['weights']}. L2 fit count: **0**.

| Evaluation | Phones | Errors | Speakers | Precision at frozen threshold | Recall | F1 | P at R≥.3 | P at R≥.5 | P at R≥.7 | R at P≥.9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(detection_rows)}

PR summaries are maximum empirical precision at or above the stated recall,
and maximum recall at precision ≥ .9; these curve summaries are descriptive,
not new L2 operating thresholds. Complete tied-threshold curves are saved as
stage-c-l2-pr.csv, stage-c-speech_children-pr.csv and
stage-c-speech_all_children-pr.csv. No smoothing/interpolation.
Average precision: L2 {percent(detection['l2']['average_precision'])}; SpeechOcean
disjoint children {percent(detection['speech_children']['average_precision'])};
full official-test children {percent(detection['speech_all_children']['average_precision'])}.

Recognition-disagreement-only on the same detection denominators:
L2 {detection['l2']['disagreement_only']};
SpeechOcean disjoint children {detection['speech_children']['disagreement_only']};
full official-test children {detection['speech_all_children']['disagreement_only']}.

SpeechOcean has two child rows: **speech_all_children** is the complete released
official-test cohort ages 6–12, including calibration children; **speech_children**
is only the disjoint reporting-speaker subset ages 6–12. The full-cohort metric is
in part in-sample for calibration and must not be treated as held-out performance. Speaker partition is 62
calibration/63 reporting, frozen before scoring. Both groups were previously
consumed for round-2 architecture/checkpoint development, so this is neither
independent confirmation nor an untouched test. Score-based acceptability labels
are not transcriptions or clinical error diagnoses; fractional exclusion biases
the denominator toward rating extremes. Calibration ages include adults.

## Abstention / coverage

Confidence is absolute logit distance from the frozen threshold. Keep the most
confident phone verdicts, ties together; abstain on the rest. Error-flag precision
is conditional on flags among retained verdicts. Also show verdict accuracy and
end-to-end recall, counting abstained reference errors as misses. A confident
correct verdict can increase coverage without producing an error flag.

| Evaluation | Coverage | Phones with verdict | Error-flag precision | Verdict accuracy | End-to-end recall |
|---|---:|---:|---:|---:|---:|
{chr(10).join(coverage_rows)}

Complete empirical curves are stage-c-l2-coverage.csv and
stage-c-speech_children-coverage.csv plus stage-c-speech_all_children-coverage.csv.
All exclusions before scoring remain
outside these coverage denominators: fractional-score phones above and GOP
failures {detection['excluded']}. No usability/nonspeech rejection is implemented.

## Data, mapping and split

JIBO: 7,810 released utterances / 109 child IDs. Non-null/exact filter: 7,734.
Drop xxx in either normalized phone or text; none survives the prior filter.
Unknown-symbol exclusions: {data['exclusion_counts'].get('unmapped',0)} utterances;
null/inexact: {data['exclusion_counts'].get('null/inexact',0)}; material endpoint
overrun: {data['exclusion_counts'].get('endpoint_overrun',0)}. Retained 7,294 utterances.
Unknown symbol occurrences: {data['unknown_symbols']}.

| Split | Children | Utterances | Cropped hours | Broad phones | Child gender | Task counts |
|---|---:|---:|---:|---:|---|---|
{chr(10).join(summary)}

Seed 31, gender/task-set stratified proportional dealing, 87/11/11 children;
all session IDs for a child_id stay together. child-split.json is frozen before
model loading/fitting, with all child IDs and mapping exclusions retained locally.
No duplicate IDs/cross-split cropped-audio hashes. Prompt overlap:{prompt_overlap}/{len(test)}
test intervals have an exact normalized orthographic string in JIBO training;
phone-sequence overlap:{phone_overlap}/{len(test)}. Alphabet/digit tasks dominate;
speaker separation does not imply unfamiliar-word generalization.

Mapping arpabet39-jibo-ipa-v2 preserves the original 39 head IDs. Explicit longest
match handles ligature/tied affricates and diphthongs, rhotic vowels; known-phone
length/nasalization detail is stripped, raw text retained. Glottal stop and other
unsupported sounds drop the whole utterance, which biases the resulting subset.
The pre-fit mapping audit corrected e/o support and unknown Unicode grouping,
with the exact same frozen child split; no fit preceded this correction.
Session float32/PCM16 audio is read directly at 16 kHz and cropped at rounded sample
boundaries. The retained set contains 36 sub-millisecond end-rounding clamps; the material
.1823125s overrun is dropped. No clipping/PCM requantization of float recordings.

## Settings and measured wall times

Trainable parameters: {fit['trainable_parameters']:,}. Final 4 blocks, final norm and 40-output head;
lower 20 blocks frozen in eval mode and cached. Starting checkpoint SHA256
{fit['initialization_sha256']}. Seed 17, AdamW encoder LR 1e-5, head LR 1e-4, weight decay .01,
accumulation 16, gradient clip 1. CPU float32 CTC autograd copied to MPS.
Each epoch shuffles {fit['jibo_train']} JIBO train clips plus 222 all-correct
SpeechOcean train clips: ratio {fit['jibo_train']/222:.3f}:1, each clip once.
No oversampling, augmentation, language model, beam search or L2 training.

Initial frozen-feature preparation: {failed_settings['preparation_seconds']:.2f}s;
final retry preparation using that cache: {fit['preparation_seconds']:.2f}s.
Successful training/dev/checkpoint loop: {fit['training_wall_seconds']:.2f}s
/ {fit['budget_seconds']}s final retry allowance; {fit['steps']} optimizer steps.
Conservative cumulative fitting/probe charge:
**{fit['cumulative_budget_charge_seconds']:.2f}s / 2700s** = successful loop +{fit['prior_fitting_seconds']}s
for two failed attempts and one interrupted attempt +120s diagnostic probe reserve. The probe reserve includes
real-clip parity/gradient checks and an 800-utterance numerical replay, whose
weights were discarded and never evaluated. No L2/test metrics informed retries.
Up to 8 epochs; earliest lowest JIBO dev PER wins, with starting A as epoch 0.
Successful-run history (loop seconds cumulative):

| Epoch | Utterances seen in epoch | Cumulative updates | JIBO dev PER | Loop seconds |
|---|---:|---:|---:|---:|
{history_rows}

Resource corrections: initial variable-shape SDPA OOM occurred late epoch 1,
before any adapted dev checkpoint evaluation or test/L2 scoring. Last progress:
4,800 clips / 300 updates / 420.2s. Log/settings timestamps measured 453s; 455s charged.
Error: 15.09 GiB live MPS tensors plus 48.54 GiB other allocations. A masked-bucket
SDPA retry stopped at a nonfinite loss before completing epoch 1 (30s measured,
32s charged); an 800-utterance first-order replay did not reproduce that numerical
failure. Its trigger remains uncertain. Both failures remain archived. A later eager run was interrupted before epoch 1
evaluation, last observed 2,400 clips / 87.3s. Its exit time was unobserved; a 180s
conservative estimate is charged, with the uncertainty disclosed. Its raw log was
inadvertently replaced by a guarded recovery launch; observed progress remains
in the tool/worklog record, and the guarded launch performed no fitting.
The per-attempt charges are saved in budget-ledger.json. The interrupted time
is estimated, so exact cumulative compute cannot be independently reconstructed.

The final resource path uses eager attention, finite -10000 padding-key mask,
64-frame buckets, true-length logits and unused-cache release per update.
Nonfinite gradient norms stop before optimizer updates. Same top-four-block
architecture/loss/data/LRs; no extra scientific candidate. Real short/median/42.6s
clips matched original SDPA frame argmax exactly, with max logit difference ≤ 2.01e-5;
real MPS parameter gradients were finite. CPU tests check logits/input gradients
across bucket boundaries. No memory guard was disabled. Cache growth is a likely
OOM cause, without a separate long-run root-cause reproduction; the successful
full run is the practical resource check. Padding changes dropout RNG consumption,
so identical training trajectories are not claimed. All attempts share one budget.
Recognition comparison: {recognition['wall_seconds']:.2f}s;
detection feature/posterior preparation: {metadata['wall_seconds']:.2f}s;
CPU GOP/scoring/calibration: {detection['wall_seconds']:.2f}s.
Preparation and final evaluation are outside the 45-minute fitting-loop budget,
as declared before training. These are wall times, not total summed CPU time.

## JIBO test top confusions (selected C)

Deletions dominate many confusions: {recognition['C']['jibo_test']['per']['D']}
deletions, {recognition['C']['jibo_test']['per']['S']} substitutions and
{recognition['C']['jibo_test']['per']['I']} insertions over 9,113 reference phones.
The table describes recognition errors, without attributing a clinical cause.

| Reference → recognized | Count |
|---|---:|
{confusions}

## Verification, commands and limitations

Run from research/audio-head with HF_HUB_OFFLINE=1 and .venv/bin/python -B -W error.
Commands: unittest mdd_v1.test_manifest mdd_v1.test_runtime mdd_v1.test_stage_c
 test_l2_arctic_annotations; -m mdd_v1.jibo; -m mdd_v1.stage_c;
-m mdd_v1.stage_c_eval recognition/posteriors/detect; -m mdd_v1.stage_c_report.
Exact exits and corrected draft failures are recorded in stage-c-commands.csv.
Tests cover masked-bucket logits/gradient parity, Unicode/tied phones/unknowns,
float/PCM crops, child grouping,
exact CTC probabilities against enumerated paths, impossible repeated targets,
strict labels, tied PR/coverage, and calibration. Astra's independent read-only
reviews found one JSON tuple/list verification issue, which was corrected and
checked against all five saved recognition comparisons; no blockers remain; see stage-c-review.md and final verification evidence.
No branch switch, commit, push, data transfer/download, private data, CMU or
reserved L2 payload access. Unrelated iOS changes were preserved.

JIBO ages 4–7 with unknown individual ages and no clinical labels is not an
ages 6–12 clinical cohort. Released manual transcriptions are taken as reference; no independent audio-level
adjudication or inter-annotator reliability was measured. Produced-phone broad
PER does not validate child error
feedback or distortion diagnosis. Normalization removes narrow detail; task,
language and speaker demographics can shift results. Cross-corpus participant
overlap is unverified. Adult L2 uses only four
already-exposed development speakers. SpeechOcean scores are acceptability
proxies, not produced-phone truth; both its selection and calibration material
have been consumed. No prospective precision/coverage/calibration gate is passed
by these descriptive results, even when an empirical point looks favorable.

JIBO attribution: Shankar et al. (2024), JASA Express Letters 4(11), 115201,
DOI 10.1121/10.0034195; balaji1312 (2026), JIBO Kids Corpus v1.0.0,
DOI 10.5281/zenodo.19604408; DrivenData (2026), JIBO Kids Corpus Transcripts,
K-12 AI Infrastructure Program (dataset 13/version 12), CC BY 4.0. Modifications:
explicit broad-phone normalization, interval cropping, filtering and frozen split.
'''
    (WORK/'stage-c-result.md').write_text(report)
    metric_path = WORK/'metrics.csv'
    with metric_path.open(newline='') as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames
        existing = list(reader)
    additions = []
    for name,source,m in metrics:
        additions.append(dict(model=f'Stage C {name} / {source}',per_utterances=m['per_utterances'],
                              **m['per'],PER=m['PER'],precision=m.get('precision',''),recall=m.get('recall',''),F1=m.get('F1',''),diagnosis_accuracy=m.get('diagnosis_accuracy','')))
    for source in ('l2','speech_children','speech_all_children'):
        op = detection[source]['at_frozen_threshold']
        additions.append(dict(model=f'Stage C GOP / {source}',precision=op['precision'],recall=op['recall'],F1=op['F1']))
    existing_names = {r['model'] for r in existing}
    with metric_path.open('a',newline='') as dest:
        writer = csv.DictWriter(dest,fieldnames=fields)
        for row in additions:
            if row['model'] not in existing_names:
                writer.writerow(row)
    series_pr = [('L2 adult pilot',detection['l2']['pr_curve'],'#2563eb'),('SpeechOcean disjoint children',detection['speech_children']['pr_curve'],'#d97706'),('SpeechOcean full test children',detection['speech_all_children']['pr_curve'],'#059669')]
    series_coverage = [('L2 adult pilot',detection['l2']['coverage_curve'],'#2563eb'),('SpeechOcean disjoint children',detection['speech_children']['coverage_curve'],'#d97706'),('SpeechOcean full test children',detection['speech_all_children']['coverage_curve'],'#059669')]
    page = '''<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><style>
body{font:14px var(--font-sans,system-ui);color:var(--foreground,#111827);margin:0}h2{font-size:17px;margin:16px 0 8px}p{line-height:1.5}svg{width:100%;height:330px;font:12px system-ui}small{color:var(--muted-foreground,#475569)}.legend{display:flex;gap:20px;flex-wrap:wrap}.blue{color:#2563eb}.orange{color:#d97706}.green{color:#059669}
</style><body><h2>Stage C: empirical detection curves</h2><p class="legend"><span class="blue">━ L2 adult pilot</span><span class="orange">━ SpeechOcean disjoint children</span><span class="green">━ SpeechOcean full test children</span></p><small>Calibration and verdict threshold use SpeechOcean development speakers only. Both SpeechOcean curves use ages 6–12. The disjoint subset excludes calibration speakers; the full released-test cohort includes them. All SpeechOcean material was previously consumed development data.</small><h2>Precision–recall</h2>'''
    page += plot_svg(series_pr,'recall','Empirical precision recall curves')
    page += '<h2>Precision under abstention</h2>'+plot_svg(series_coverage,'coverage','Precision vs fraction of phones given a verdict')
    page += '<p><small>Coverage retains verdicts by distance from the frozen calibration threshold. Precision counts error flags only; gaps mean no error flags, so precision is undefined. Curves are sampled for display; full empirical points and denominators are in the CSVs. Broad-phone recognition and score proxies do not validate clinical feedback.</small></p></body></html>'
    page = page.replace('</body></html>', r"""<script>
function sizeCharts() {
  document.querySelectorAll('svg').forEach(svg => {
    const width = svg.clientWidth;
    if (!width) return;
    const scale = (width - 80) / 600;
    svg.setAttribute('viewBox', '0 0 ' + width + ' 330');
    svg.querySelectorAll('path').forEach(path => {
      path.setAttribute('transform', 'matrix(' + scale + ' 0 0 1 ' + (50 * (1 - scale)) + ' 0)');
      path.setAttribute('vector-effect', 'non-scaling-stroke');
    });
    svg.querySelectorAll('text[x]').forEach(label => {
      if (!label.dataset.baseX) label.dataset.baseX = label.getAttribute('x');
      const original = Number(label.dataset.baseX);
      label.setAttribute('x', original >= 50 ? 50 + (original - 50) * scale : original);
    });
  });
}
requestAnimationFrame(sizeCharts);
new ResizeObserver(sizeCharts).observe(document.body);
</script></body></html>""")
    (WORK/'stage-c-curves.html').write_text(page)
    print('Wrote stage-c-result.md, appended metrics.csv, complete curve CSVs and stage-c-curves.html')


if __name__ == '__main__':
    main()
