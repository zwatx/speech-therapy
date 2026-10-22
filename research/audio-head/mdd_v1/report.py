"""Assemble the human-readable handoff from saved measurements, no inference."""
from collections import Counter
import csv
import json
import torch

from .manifest import OUTPUT, ROOT, load_manifest
from .evaluate import evaluate
from .inventory import PHONES

REPORT = ROOT.parents[1]/'work/mdd-v1'


def percent(value):
    return '—' if value is None else f'{100*value:.2f}%'


def describe(rows):
    return (f"{len(rows)} utterances / {len({r['speaker'] for r in rows})} speakers; "
            f"{sum(r['population']=='child' for r in rows)} child clips / "
            f"{sum(r['population']=='adult' for r in rows)} adult clips")


def main():
    rows = load_manifest()
    summary = json.loads((OUTPUT/'manifest-summary.json').read_text())
    a0 = json.loads((OUTPUT/'a0-result.json').read_text())
    selected = json.loads((OUTPUT/'selected-result.json').read_text())
    fits = {c: json.loads((OUTPUT/f'candidate-{c}/result.json').read_text()) for c in ['A', 'B']}
    a0_predictions = {r['id']: r['phones'] for r in
                      map(json.loads, (OUTPUT/'a0-predictions.jsonl').read_text().splitlines())}
    pilot = [r for r in rows if r['source'] == 'l2-arctic']
    # Review-added descriptive slices reuse saved hypotheses; no new inference.
    recomputed = evaluate(pilot, a0_predictions)
    for key in ('per', 'PER', 'precision', 'recall', 'F1', 'diagnosis_accuracy'):
        if recomputed[key] != a0['l2'][key]:
            raise ValueError(f'A0 primary metric changed during report replay: {key}')
    for key, value in a0['l2']['mdd'].items():
        if recomputed['mdd'][key] != value:
            raise ValueError(f'A0 primary MDD count changed: {key}')
    a0['l2'] = recomputed
    (OUTPUT/'a0-descriptive-metrics.json').write_text(json.dumps(recomputed, indent=2, ensure_ascii=False))
    a0_speakers = {speaker: evaluate([r for r in pilot if r['speaker'] == speaker], a0_predictions)
                   for speaker in sorted({r['speaker'] for r in pilot})}
    lines = ['# MDD v1 — stage A result', '',
             'Completed offline on the M3 Max/MPS, 2026-10-22. Development evidence only.', '',
             f"Selected **candidate {selected['selected']}**, epoch {selected['selected_epoch']}, "
             'solely by lowest SpeechOcean official test-speaker development PER. '
             'Both trained candidates are compared below; only the selected checkpoint '
             'was evaluated on L2. A0 used its original pretrained phoneme head.', '',
             'The trained model improves SpeechOcean dev PER and L2 error-detection F1, '
             'but L2 phone PER is slightly worse than A0. This is an engineering baseline, '
             'not a qualified feedback model.', '',
             '## Observed metrics', '',
             '| Model / evaluation | Utterances for PER | N | S | D | I | PER | MDD precision | Recall | F1 | Diagnosis |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    table = []
    evaluations = [('A0 / SpeechOcean dev', a0['speech_dev']),
                   ('A / SpeechOcean dev', torch.load(OUTPUT/'candidate-A/best.pt', weights_only=True)['metrics']),
                   ('B / SpeechOcean dev', torch.load(OUTPUT/'candidate-B/best.pt', weights_only=True)['metrics']),
                   ('A0 / L2 pilot', a0['l2']),
                   (f"Selected {selected['selected']} / L2 pilot", selected['l2'])]
    for name, result in evaluations:
        per = result['per']
        metric = dict(model=name, per_utterances=result['per_utterances'], **per, PER=result['PER'],
                      precision=result.get('precision'), recall=result.get('recall'),
                      F1=result.get('F1'), diagnosis_accuracy=result.get('diagnosis_accuracy'))
        table.append(metric)
        lines.append(f"| {name} | {result['per_utterances']} | {per['N']} | {per['S']} | {per['D']} | {per['I']} | "
                     f"{percent(result['PER'])} | {percent(result.get('precision'))} | {percent(result.get('recall'))} | "
                     f"{percent(result.get('F1'))} | {percent(result.get('diagnosis_accuracy'))} |")
    relative = (a0['l2']['PER']-selected['l2']['PER'])/a0['l2']['PER']
    lines += ['', f"Selected L2 PER relative improvement vs A0: {percent(relative)} (negative = worse).", '',
              'L2 PER excludes whole utterances with unknown perceived identities: '
              f"{a0['l2']['unknown_reference_utterances']} / {len(pilot)}. "
              'MDD detection includes all eligible pilot utterances. '
              'Primary MDD counts are canonical-position substitutions/deletions; '
              'insertion-gap counts are separate.', '',
              '| Model | TA | FR | FA | TR | Correct diagnosis / known TR | Reference insertions | Predicted insertions | Correct gap-phone matches |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name, result in [('A0', a0['l2']), (f"Selected {selected['selected']}", selected['l2'])]:
        m = result['mdd']
        lines.append(f"| {name} | {m['TA']} | {m['FR']} | {m['FA']} | {m['TR']} | {m['CD']} / {m['diagnosis_eligible_TR']} | "
                     f"{m['reference_insertions']} | {m['predicted_insertions']} | {m['correct_insertion_phones']} |")
    lines += ['', 'Review-added descriptive slice (primary metrics above stay frozen): '
              'same-broad-identity reference errors include starred deviations. '
              'A canonical broad-phone prediction false-accepts them; a different '
              'prediction may reject them but cannot name the correct broad identity.', '',
              '| Model | Same-broad reference errors | Same-broad TR / FA | Diagnosis excluding these TR | Recall excluding these reference errors |',
              '|---|---:|---:|---:|---:|']
    for name, result in [('A0', a0['l2']), (f"Selected {selected['selected']}", selected['l2'])]:
        m = result['mdd']
        lines.append(f"| {name} | {m['same_broad_identity_reference_errors']} | "
                     f"{m['same_broad_identity_TR']} / {m['same_broad_identity_FA']} | "
                     f"{percent(result['descriptive_diagnosis_excluding_same_broad'])} | "
                     f"{percent(result['descriptive_recall_excluding_same_broad'])} |")
    lines += ['', '## Data and exclusions', '',
              'Source labels and normalization remain in the JSONL manifest. '
              'Child means recorded age <18; SpeechOcean includes ages 6–15 and adults, '
              'so it is not exclusively the intended ages 6–12 population. L2 exact ages '
              'are unavailable here; speakers are adult per corpus context.', '']
    for split in ['train', 'test']:
        subset = [r for r in rows if r['split'] == split]
        eligible = [r for r in subset if r.get('all_correct')]
        speaker_pop = Counter({r['speaker']: r['population'] for r in eligible}.values())
        ages = sorted({r['age'] for r in subset if r['age'] is not None})
        target = [r for r in eligible if r['age'] is not None and 6 <= r['age'] <= 12]
        lines += [f"- SpeechOcean official {split}: {describe(subset)}. Recorded ages {', '.join(map(str, ages))}.",
                  f"- All-correct {split} subset: {describe(eligible)}; "
                  f"{speaker_pop['child']} child speakers / {speaker_pop['adult']} adult speakers. "
                  f"Ages 6–12: {len(target)} clips / {len({r['speaker'] for r in target})} speakers. "
                  f"Dropped {len(subset)-len(eligible)} utterances containing masked phones."]
    lines += [f'- L2 manual pilot: {describe(pilot)}; all evaluation only. '
              f"Reference events: {dict(Counter(e['event'] for r in pilot for e in r['events']))}.",
              '- Speaker IDs, utterance IDs, repeated audio paths and identical audio across splits were checked; no leakage found.',
              '- The 20 L2 reserved nested archives were never opened/listed/decoded. No CMU, private child or closed-study data was used.']
    for item in summary['excluded']:
        lines.append(f"- Excluded `{item['member']}`: {item['reason']}.")
    training = [r for r in rows if r['split'] == 'train' and r.get('all_correct')]
    dev = [r for r in rows if r['split'] == 'test' and r.get('all_correct')]
    scores = json.loads((ROOT/'outputs/speechocean762-metadata-v1/resource/scores.json').read_text())
    def prompt(row):
        return ' '.join(scores[row['id'].removeprefix('so:')]['text'].split()).upper()
    train_prompts = {prompt(r) for r in training}
    shared = sum(prompt(r) in train_prompts for r in dev)
    train_sequences = {tuple(r['canonical']) for r in training}
    shared_sequences = sum(tuple(r['canonical']) in train_sequences for r in dev)
    lines += ['', f"Prompt overlap audit: {shared}/{len(dev)} ({percent(shared/len(dev))}) "
              'all-correct dev utterances share an exact normalized transcript '
              '(uppercase, whitespace collapsed) with eligible training utterances. '
              f"Exact canonical-phone sequence overlap: {shared_sequences}/{len(dev)}. "
              'Speaker disjointness does not imply unfamiliar-word or prompt independence.']
    phone_support = Counter(p for r in training for p in r['perceived'])
    lines += ['', f"Eligible training has only {sum(phone_support.values())} phone positions. "
              f"Phones with zero positive targets: {', '.join(p for p in PHONES if not phone_support[p])}. "
              f"Phones with <10 targets: {dict((p, phone_support[p]) for p in PHONES if phone_support[p] < 10)}."]
    lines += ['', '## Settings and actual wall time', '',
              'Seed 17; 39 phones + CTC blank; greedy prompt-blind decoding. '
              'Single-clip encoder passes; PCM16 to 16 kHz polyphase resampling; '
              'each cached feature extractor supplies its own normalization. '
              'CTC loss is float32 on CPU with gradients copied to MPS. '
              'Gradient accumulation 16, AdamW decay .01, clipping 1.0. '
              'Drop every masked utterance; never train incorrect phones as canonical. '
              'Each candidate has the same 900-second training/dev budget and 30-epoch cap; '
              'actual compute/epochs may differ. Feature preparation is separate.', '',
              '| Run | Trainable parameters | Epochs / optimizer steps | Best epoch | Prep seconds | Training/dev seconds |',
              '|---|---:|---:|---:|---:|---:|']
    for c, fit in fits.items():
        checkpoint = torch.load(OUTPUT/f'candidate-{c}/best.pt', weights_only=True)
        lines.append(f"| {c} | {fit['trainable_parameters']:,} | {fit['epochs']} / {fit['steps']} | "
                     f"{checkpoint['epoch']} | {fit['preparation_seconds']:.2f} | {fit['training_wall_seconds']:.2f} |")
    lines += ['', 'A: pretrained espeak wav2vec2 final 4 transformer blocks and final layer norm '
              'fine-tuned at 1e-5, new linear head at 1e-3; lower 20 blocks frozen and cached. '
              f"Real-clip cached/full encoder maximum difference: {fits['A']['cache_parity_max_abs']:.3g}.", '',
              'B: pinned WavLM Base+ fully frozen final features, bidirectional LSTM '
              '(128 units/direction, one layer) plus linear head at 1e-3.', '',
              f"A0 inference/metrics wall time: {a0['wall_seconds']:.2f}s. "
              f"Selected L2 head inference/metrics: {selected['l2_head_inference_seconds']:.2f}s "
              '(frozen feature extraction logged separately).', '',
              f"Checkpoint reload verification: {selected['checkpoint_replay']}.", '',
              '## Per-speaker L2 development support', '',
              '| Speaker | Utterances | PER reference phones | A0 PER | Selected PER | Selected MDD F1 |',
              '|---|---:|---:|---:|---:|---:|']
    for speaker, result in selected['per_speaker'].items():
        lines.append(f"| {speaker} | {result['utterances']} | {result['per']['N']} | "
                     f"{percent(a0_speakers[speaker]['PER'])} | {percent(result['PER'])} | {percent(result['F1'])} |")
    lines += ['', '## Failure analysis', '',
              '| Reference → recognized | A0 count | Selected count |', '|---|---:|---:|']
    conf_a0 = dict(a0['l2']['top_confusions'])
    conf_selected = dict(selected['l2']['top_confusions'])
    for name in list(dict.fromkeys([k for k, _ in selected['l2']['top_confusions'][:12]]+
                                   [k for k, _ in a0['l2']['top_confusions'][:8]])):
        lines.append(f"| {name} | {conf_a0.get(name, 'outside top 20')} | {conf_selected.get(name, 'outside top 20')} |")
    lines += ['', f"A0 unmapped emission counts across all 800 L2+dev clips: `{json.dumps(a0['unmapped'], ensure_ascii=False)}`. "
              'These emissions become `<unk>` and count as errors; the mapping was frozen before A0.', '',
              f"L2 deletions rose from {a0['l2']['per']['D']} to {selected['l2']['per']['D']}, "
              f"while insertions fell from {a0['l2']['per']['I']} to {selected['l2']['per']['I']}. "
              'The deletion increase, including missed R and AH, outweighs fewer insertions. '
              'Error detection rejects more annotated errors but also more correct positions. '
              'Broad-phone accuracy does not guarantee useful error detection. Canonical-biased '
              'recognition can false-accept annotated errors, while recognition mistakes can '
              'false-reject acceptable productions. Tiny score-filtered training data and '
              'domain shift limit both fits. Source-starred distortions remain error events '
              'even when broad identities agree, which broad CTC cannot resolve.', '',
              '## Verification, commands, and limitations', '',
              'Main commands are run from `research/audio-head` using `.venv/bin/python -B`; '
              'all model commands set `HF_HUB_OFFLINE=1` and use local cached snapshots.', '',
              '- `python -B -m mdd_v1.manifest`: exit 0.',
              '- `python -B -m mdd_v1.baseline`: exit 0 on corrected offline-cache retry; '
              'initial attempt exited 1 because refs/main was absent. Snapshot IDs were '
              'made explicit before successful inference; no outcome-based model change.',
              '- `python -B -m mdd_v1.train_ctc A`, `B`, `select`: each exit 0 (candidate-exit-codes.txt).',
              '- `python -B -W error -m unittest mdd_v1.test_manifest mdd_v1.test_runtime test_l2_arctic_annotations`: '
              '21 tests, exit 0 after review fixes (20 passed before fitting). Final checks/review recorded in WORKLOG.md and commands.csv.',
              '- `python -B -m mdd_v1.report`: produces this report and metrics.csv from saved outputs.', '',
              'Raw manifests, predictions, feature caches, per-epoch histories, settings and '
              'best checkpoints: `research/audio-head/outputs/mdd_v1/` (ignored). '
              'Protocol, exact phone mapping, source ledger and logs: `work/mdd-v1/`. '
              'No branch switch, commit, push, download or upload occurred.', '',
              '**Limits:** adult L2 evaluation on only four already-exposed speakers; '
              'SpeechOcean labels are expert scores, not produced-phone transcriptions; '
              'all-correct utterance selection favors easy/acceptable examples and can miss '
              'unrated insertions; official test speakers are reused development, not confirmation. '
              'No child produced-phone truth, child MDD validation, SLP adjudication, '
              'calibration/nonspeech/coverage qualification, clinical diagnosis, or proposed-gate '
              'pass is established. All gates in protocol.md remain prospective. '
              'No task blocker remains; data/supervision limitations remain substantial.']
    (REPORT/'stage-a-result.md').write_text('\n'.join(lines)+'\n')
    with (REPORT/'metrics.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]))
        writer.writeheader(); writer.writerows(table)
    print(REPORT/'stage-a-result.md')


if __name__ == '__main__':
    main()
