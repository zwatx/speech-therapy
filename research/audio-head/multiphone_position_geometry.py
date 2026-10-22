"""Occurrence-aware geometry from fixed full-sequence CTC arrays; no rating use."""
from __future__ import annotations

from collections import defaultdict
import numpy as np

import multiphone_local_features as local

require = local.require
POSITION_FIELDS = ('id', 'clipId', 'wordIndex', 'phoneIndex', 'canonicalIndex',
                   'targetId', 'targetPhone', 'legacyRowIndex')
PARITY_FIELDS = ('canonicalIndex', 'tokenId', 'intervalFrames',
                 'estimatedFrameCenterSeconds', 'scalarFeatures', 'diagnosticFlags')


def clip_geometry(clip, positioned_rows, log_probabilities, recipe, vocabulary):
    """Only positional metadata enters this function; no ratings or notes leave it."""
    require(positioned_rows and len({r['id'] for r in positioned_rows}) == len(positioned_rows),
            'Missing or duplicate occurrence IDs')
    indices = [r['canonicalIndex'] for r in positioned_rows]
    require(indices == sorted(set(indices)), 'Canonical positions must be unique and ordered')
    phones = clip['canonicalPhones']
    mapped, tokens, flags = local.canonical_mapping(phones, vocabulary, recipe)
    require(len(log_probabilities) == local.convolution_frames(clip['sampleCount'], recipe),
            'Source waveform and CTC frame count differ')
    offsets, flattened = [], []
    for word in clip['words']:
        offsets.append(len(flattened))
        flattened.extend(word['phones'])
    require(flattened == phones, 'Word structure and flattened canonical sequence differ')
    for row in positioned_rows:
        wi, pi, ci = row['wordIndex'], row['phoneIndex'], row['canonicalIndex']
        require(type(wi) is int and 0 <= wi < len(clip['words']) and type(pi) is int and
                0 <= pi < len(clip['words'][wi]['phones']) and type(ci) is int and
                ci == offsets[wi]+pi and row['clipId'] == clip['id'] and
                row['id'] == f"{clip['id']}:{wi}:{pi}" and phones[ci] == row['targetPhone'],
                'Occurrence does not match its word/phone position')
    estimates, diagnostics = local.local_features(log_probabilities, tokens, indices, recipe)
    rows = []
    for source, estimate in zip(positioned_rows, estimates, strict=True):
        require(estimate['canonicalIndex'] == source['canonicalIndex'], 'Local target order changed')
        start, end = estimate['intervalFrames']
        context = recipe['poolingContextFrames']
        rows.append({**{key: source[key] for key in POSITION_FIELDS}, **estimate,
                     'mappingAmbiguities': flags,
                     'estimatedPoolingWindowFrames': [max(0, start-context), min(len(log_probabilities), end+context)]})
    groups = defaultdict(list)
    for row in rows:
        groups[row['targetPhone']].append(row)
    repeated = {p: items for p, items in groups.items() if len(items) > 1}
    for items in repeated.values():
        require(all(a['intervalFrames'][1] <= b['intervalFrames'][0] for a, b in zip(items, items[1:])),
                'Repeated canonical states overlap or reverse')
        for a, b in zip(items, items[1:]):
            if b['canonicalIndex'] == a['canonicalIndex']+1:
                require(a['intervalFrames'][1] < b['intervalFrames'][0],
                        'Adjacent equal CTC tokens require an intervening blank')
    values = np.asarray([r['scalarFeatures'] for r in rows], dtype=np.float32)
    require(values.shape == (len(rows), 13) and np.isfinite(values).all(), 'Invalid occurrence scalar matrix')
    return dict(clipId=clip['id'], mappedTokens=mapped, mappedTokenIds=tokens,
                mappingAmbiguities=flags, rows=rows, diagnostics=diagnostics,
                repeatedTargetGroups=len(repeated), repeatedPositions=sum(map(len, repeated.values())))


def legacy_parity(computed, legacy_rows, legacy_diagnostic):
    """Verify old scalar/window identities while allowing the new occurrence IDs."""
    linked = [r for r in computed['rows'] if r['legacyRowIndex'] is not None]
    expected = {r['rowIndex']: r for r in legacy_rows}
    require(len(expected) == len(legacy_rows) and {r['legacyRowIndex'] for r in linked} == set(expected),
            'Legacy row coverage differs')
    for row in linked:
        old = expected[row['legacyRowIndex']]
        require(all(row[k] == old[k] for k in PARITY_FIELDS+('wordIndex', 'phoneIndex', 'targetId', 'targetPhone')),
                'Original position feature differs')
        require(row['estimatedPoolingWindowFrames'] == old['estimatedPoolingWindowFrames'] and
                row['mappingAmbiguities'] == old['mappingAmbiguities'], 'Original window/mapping differs')
    if legacy_rows:
        require(legacy_diagnostic is not None and legacy_diagnostic['clipId'] == computed['clipId'] and
                all(legacy_diagnostic[k] == v for k, v in computed['diagnostics'].items()),
                'Original utterance diagnostic differs')
    else:
        require(legacy_diagnostic is None, 'Unexpected legacy diagnostic without original targets')
    return len(linked)
