"""Fitting-only equal recording/sound-unit contributions, without rating access."""
from collections import Counter
import math
import re
from lexical_phone_response.analysis import PHONES

RECIPE = dict(raw='inverse complete canonical same-phone count per recording',
              normalization='fit positions / fit recording-phone units',
              scope='complete supported canonical positions in selected recordings',
              batchReduction='mean of fixed fit-normalized weight times five-vote NLL',
              selection='unweighted original selection rows', classWeighting=False)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fit_weights(cohort, fitRows):
    rows = cohort['rows']
    require(isinstance(fitRows, list) and bool(fitRows)
            and all(type(i) is int and 0 <= i < len(rows) for i in fitRows)
            and len(set(fitRows)) == len(fitRows), 'Expected nonempty unique integer fitting rows')
    clips = {c['id']: c for c in cohort['clips']}
    require(len(clips) == len(cohort['clips']), 'Duplicate recording identity')
    selected_clips = {rows[i]['clipId'] for i in fitRows}
    expected, counts = set(), {}
    for clip_id in selected_clips:
        require(clip_id in clips, 'Missing fitting recording')
        clip = clips[clip_id]
        canonical = [p for word in clip['words'] for p in word['phones']]
        require(canonical == clip['canonicalPhones'] and len(canonical) == clip['canonicalPhoneCount'],
                'Incomplete fitting canonical sequence')
        normalized = [re.sub(r'[012]$', '', p) for p in canonical]
        counts[clip_id] = Counter(normalized)
        expected.update((clip_id, index) for index, phone in enumerate(normalized) if phone in PHONES)
    observed, units, multiples = set(), Counter(), []
    for i in fitRows:
        row = rows[i]; clip = clips[row['clipId']]
        index, wi, pi = row['canonicalIndex'], row['wordIndex'], row['phoneIndex']
        require(type(index) is int and 0 <= index < len(clip['canonicalPhones'])
                and type(wi) is int and 0 <= wi < len(clip['words'])
                and type(pi) is int and 0 <= pi < len(clip['words'][wi]['phones']), 'Invalid fitting geometry')
        key = row['clipId'], index
        require(key not in observed, 'Duplicate fitting canonical position')
        observed.add(key)
        phone = row['targetPhone']
        require(phone in PHONES and index == sum(len(w['phones']) for w in clip['words'][:wi])+pi
                and row['canonicalRaw'] == clip['canonicalPhones'][index] == clip['words'][wi]['phones'][pi]
                and re.sub(r'[012]$', '', row['canonicalRaw']) == phone
                and row['speakerId'] == clip['speakerId'] and row['age'] == clip['age'], 'Fitting canonical identity differs')
        multiples.append(counts[row['clipId']][phone]); units[row['clipId'],phone] += 1
    require(observed == expected, 'Fitting recordings must contain every supported canonical position')
    require(all(n == counts[clip][phone] for (clip,phone),n in units.items()), 'Incomplete recording/sound group')
    normalization = len(fitRows) / len(units)
    values = [normalization / count for count in multiples]
    require(math.isclose(math.fsum(values),len(fitRows),rel_tol=1e-14,abs_tol=1e-14), 'Weight mean differs')
    return dict(recipe=dict(RECIPE), fitRows=list(fitRows), canonicalCounts=multiples,
                unitCount=len(units), normalization=normalization, weights=values)
