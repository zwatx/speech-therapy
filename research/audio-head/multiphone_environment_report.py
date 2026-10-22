"""Verify saved environmental results and write the descriptive report; no inference."""
import json
from pathlib import Path
import numpy as np
import multiphone_environment_challenge as challenge
import multiphone_research_audio as raw

PLAN_SHA = '1016d94bb15fab78929319da24f3706980c742505d50e805ea8bbbe60f45d9e9'


def main():
    base = challenge.OUTPUT
    plan, plan_pin = raw.read_bound_json(base/'plan.json', PLAN_SHA)
    report, report_pin = raw.read_bound_json(base/'results/report.json')
    raw.require(report['complete'] is True and report['plan'] == plan_pin, 'Unexpected challenge report')
    raw.guard(plan['inputBindings'])
    vocab_pin = raw.binding(Path(plan['snapshot'])/'vocab.json',
        'd732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0')
    vocab = {v:k for k,v in json.loads(Path(vocab_pin['path']).read_text()).items()}
    lines, sums = [], {c:{'total':0,'accepted':0,'abstained':0,'pipelineFailures':0} for c in challenge.CATEGORIES}
    for outcome, clip in zip(report['outcomes'], plan['clips'], strict=True):
        raw.require(outcome['filename'] == clip['metadata']['filename'] and outcome['category'] == clip['metadata']['category'],
                    'Outcome order or identity differs')
        group = sums[outcome['category']]; group['total'] += 1
        if not outcome['pipelineComplete']:
            group['pipelineFailures'] += 1
            lines.append(f"| {outcome['filename']} | {outcome['category']} | pipeline failure | — | {outcome['error']} |")
            continue
        gated, _ = raw.read_bound_json(outcome['gatedReport']['path'],outcome['gatedReport']['sha256'])
        adapter, _ = raw.read_bound_json(outcome['rawReport']['path'],outcome['rawReport']['sha256'])
        raw.require(gated['decision'] == outcome['decision'] and gated['sourceReport'] == outcome['rawReport'], 'Decision provenance differs')
        directory = Path(outcome['rawReport']['path']).parent
        for name, sha in adapter['filesSha256'].items(): raw.binding(directory/name,sha)
        raw.require(adapter['runtime']['device'] == 'cpu' and adapter['runtime']['threads'] == 2
                    and adapter['ctcRuntime']['fetchAttempts'] == 0 and adapter['canonicalPrompt']['canonicalPhones'] == ['B','AO1','L']
                    and adapter['headVariant'] == 'unweighted-all-age', 'Runtime differs')
        logp = np.fromfile(directory/'ctc.f32',dtype='<f4').reshape(-1,392)
        tokens = [t for t in raw.local.greedy_tokens(logp) if t>3]
        decision = outcome['decision']
        raw.require(len(tokens) == decision['recognizedPhoneTokens'], 'Token count differs')
        accepted = decision['ratingAvailable']; group['accepted' if accepted else 'abstained'] += 1
        text = ' '.join(vocab[t] for t in tokens) or 'none'
        lines.append(f"| {outcome['filename']} | {outcome['category']} | {'accepted' if accepted else 'abstained'} | {len(tokens)} | {text} |")
    raw.require(sums == report['summary'] and sum(g['total'] for g in sums.values()) == 12,'Summary differs')
    totals = {k:sum(g[k] for g in sums.values()) for k in ('total','accepted','abstained','pipelineFailures')}
    category_lines = [f"| {c} | {g['total']} | {g['accepted']} | {g['abstained']} | {g['pipelineFailures']} |" for c,g in sums.items()]
    text = f"""# ESC-10 environmental challenge results

Completed September 27, 2026. **{totals['abstained']}/12 abstained,
{totals['accepted']}/12 accepted, {totals['pipelineFailures']} pipeline failures.**
Acceptance means recognized-phone evidence under the fixed gate, not verified
speech, prompt match, or correct pronunciation. The environmental labels are
not VAD ground truth and do not establish absence of incidental speech.

The [predeclared protocol](multiphone-environment-protocol.md) selected two
lexicographically first distinct source recordings from each of six categories,
ESC-10 only, fold 1. No selection changed after inference. All clips retained
their complete five seconds; conversion used mono 16-kHz PCM16 without trimming
or amplitude normalization. The unchanged raw adapter ran once per clip on CPU
with two threads, BALL /B AO1 L/, target B, and `unweighted-all-age`.
The pinned hardened evidence gate filtered each completed report. No training,
threshold adjustment, feedback, cloud use, or promotion occurred.

| Category | Clips | Accepted | Abstained | Pipeline failures |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(category_lines)}

Recognized tokens below are greedy CTC outputs excluding special token IDs
0–3. They are model outputs, not manual transcripts. Every abstention had
`no-recognized-phone-evidence`; no category received a correctness label.

| Filename | Category | Gate outcome | Token count | Recognized tokens |
| --- | --- | --- | ---: | --- |
{chr(10).join(lines)}

## Interpretation

The gate withholds some environmental inputs but also admits other environmental
recordings. It must remain a necessary input check, with no claim of validated
speech detection or clinical safety. These 12 deliberately small fixed examples
do not estimate population false-acceptance rates, microphone robustness,
child-speech retention, or child SSD performance. Do not tune a threshold on
these observed outcomes and then present them as independent validation.

## Reproducibility and attribution

- Source: [Karol J. Piczak's ESC-50 repository](https://github.com/karolpiczak/ESC-50/tree/{challenge.COMMIT}), commit `{challenge.COMMIT}`.
- ESC-10 is [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/); the complete source LICENSE, README and each original Freesound contributor attribution are retained in the ignored output plan. Credit Karol J. Piczak, *ESC: Dataset for Environmental Sound Classification*, ACM Multimedia 2015, and those contributors. The only audio modification is the documented resampling/PCM conversion.
- Output directory: `research/audio-head/outputs/multiphone-20260927/environment-v1/`.
- Plan SHA-256: `{PLAN_SHA}`.
- Result SHA-256: `{report_pin['sha256']}`.
- Gate source SHA-256: `{plan['inputBindings']['gateSource']['sha256']}`.
- Converter: `{plan['ffmpegVersion'].splitlines()[0]}`; exact per-file commands and original/converted hashes are in `plan.json`.
- `multiphone_environment_challenge.py` implements selection, acquisition, declaration and inference; `multiphone_environment_report.py` verifies bound outputs and renders this report.

Verified: four focused selection/conversion/error tests; all 12 original and
converted WAV headers/durations; pinned input hashes; all saved raw artifact
hashes; zero model fetch attempts; exact selected clip order; category totals;
CTC token counts; CPU/head/prompt identity. The report check performs no new
inference. The broader app test suite was not run because only isolated research
scripts and documentation were added.
"""
    path = raw.HERE/'../../docs/model/multiphone-environment-report.md'
    raw.require(not path.exists(),'Report already exists')
    path.write_text(text)
    print(json.dumps({'report':str(path.resolve()),'totals':totals,'resultSha256':report_pin['sha256']},indent=2))


if __name__ == '__main__': main()
