"""A0 greedy phoneme CTC, without prompt or dictionary input."""
import json
import time
from collections import Counter
import torch
from transformers import Wav2Vec2ForCTC
from .runtime import ESPEAK_MODEL, snapshot, extractor, waveform, device_setup, collapse
from .manifest import OUTPUT, load_manifest
from .inventory import map_espeak
from .evaluate import evaluate


def main():
    start = time.monotonic()
    device = device_setup()
    path = snapshot(ESPEAK_MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(str(path), local_files_only=True).eval().to(device)
    processor = extractor(ESPEAK_MODEL)
    vocab = json.loads((path/'vocab.json').read_text())
    inverse = {i: token for token, i in vocab.items()}
    rows = [r for r in load_manifest() if r['source'] == 'l2-arctic' or
            (r['split'] == 'test' and r.get('all_correct'))]
    predictions, details, unmapped = {}, [], Counter()
    with torch.inference_mode():
        for index, row in enumerate(rows):
            ids = model(**waveform(row, processor, device)).logits[0].argmax(-1).cpu().tolist()
            tokens = collapse(ids, inverse)
            phones, unknown = map_espeak(tokens)
            unmapped.update(unknown)
            predictions[row['id']] = phones
            details.append(dict(id=row['id'], raw_tokens=tokens, phones=phones, unmapped=unknown))
            if (index+1) % 25 == 0:
                print(f'A0 {index+1}/{len(rows)} elapsed={time.monotonic()-start:.1f}s', flush=True)
    result = dict(model=ESPEAK_MODEL, revision=path.name, wall_seconds=time.monotonic()-start,
                  device=str(device), unmapped=dict(unmapped))
    for name, selected in [('l2', [r for r in rows if r['source'] == 'l2-arctic']),
                           ('speech_dev', [r for r in rows if r['source'] == 'speechocean762'])]:
        result[name] = evaluate(selected, predictions)
    (OUTPUT/'a0-predictions.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in details))
    (OUTPUT/'a0-result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
