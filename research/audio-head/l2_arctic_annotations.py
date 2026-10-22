"""Strict long-text IntervalTier reader and L2-ARCTIC manual-label interpretation.

This is a bounded schema reader, not a complete Praat implementation. It rejects
unsupported syntax instead of repairing times or silently dropping annotations.
Label semantics require separately established manual-annotation provenance.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import math
import re

ARPABET = frozenset('AA AE AH AO AW AY B CH D DH EH ER EY F G HH IH IY JH K L M N NG OW OY P R S SH T TH UH UW V W Y Z ZH'.split())
VOWELS = frozenset('AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW'.split())
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
STRING = r'"((?:[^"]|"")*)"'
MAX_BYTES = 200_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Reader:
    def __init__(self, text):
        self.text, self.position = text, 0

    def take(self, expression):
        found = re.match(r'\s*' + expression, self.text[self.position:])
        require(found is not None, f'Unsupported TextGrid syntax near character {self.position}')
        self.position += found.end()
        return found

    def string(self, field):
        return self.take(re.escape(field) + r'\s*=\s*' + STRING).group(1).replace('""', '"')

    def number(self, field):
        raw = self.take(re.escape(field) + r'\s*=\s*(' + NUMBER + r')(?=\s|$)').group(1)
        try:
            value = Decimal(raw)
        except InvalidOperation as error:
            raise ValueError('Invalid interval time') from error
        require(value.is_finite() and math.isfinite(float(value)), 'Nonfinite interval time')
        return raw, value

    def count(self, field, maximum):
        raw = self.take(re.escape(field) + r'\s*=\s*(\d+)(?=\s|$)').group(1)
        value = int(raw)
        require(1 <= value <= maximum, f'Unsupported {field} count')
        return value


def parse_textgrid(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES, 'Invalid TextGrid byte size')
    encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    try:
        text = raw.decode(encoding)
    except UnicodeError as error:
        raise ValueError('TextGrid must be UTF-8 or BOM-marked UTF-16') from error
    require('\x00' not in text, 'Unexpected NUL in TextGrid')
    reader = Reader(text)
    require(reader.string('File type') == 'ooTextFile' and reader.string('Object class') == 'TextGrid',
            'Only long-text TextGrid format is supported')
    start_raw, start = reader.number('xmin'); end_raw, end = reader.number('xmax')
    require(0 <= start < end <= 3600, 'Invalid TextGrid time domain')
    reader.take(r'tiers\?\s*<exists>')
    count = reader.count('size', 16)
    reader.take(r'item\s*\[\s*\]\s*:')
    tiers, names = [], set()
    for i in range(1, count+1):
        reader.take(r'item\s*\[\s*' + str(i) + r'\s*\]\s*:')
        require(reader.string('class') == 'IntervalTier', 'Only IntervalTier is supported')
        name = reader.string('name')
        require(name and name not in names, 'Missing or duplicate tier name')
        names.add(name)
        _, tier_start = reader.number('xmin'); _, tier_end = reader.number('xmax')
        require((tier_start, tier_end) == (start, end), 'Tier domain differs from TextGrid')
        size = reader.count('intervals: size', 20_000)
        previous, intervals = start, []
        for index in range(1, size+1):
            reader.take(r'intervals\s*\[\s*' + str(index) + r'\s*\]\s*:')
            left_raw, left = reader.number('xmin'); right_raw, right = reader.number('xmax')
            label = reader.string('text')
            require(left == previous and start <= left < right <= end
                    and float(left) < float(right), 'Intervals must be positive, adjacent and inside the tier')
            intervals.append(dict(index=index, start=float(left), end=float(right),
                                  startText=left_raw, endText=right_raw, rawLabel=label))
            previous = right
        require(previous == end, 'Intervals do not cover their tier')
        tiers.append(dict(index=i, name=name, type='IntervalTier', intervals=intervals))
    require(not text[reader.position:].strip(), 'Unexpected trailing TextGrid content')
    require({'words', 'phones'} <= names, 'Manual example requires words and phones tiers')
    return dict(format='Praat-long-text-IntervalTier', encoding=encoding, start=float(start), end=float(end),
                startText=start_raw, endText=end_raw, tiers=tiers)


def phone_token(raw, *, perceived=False):
    match = re.fullmatch(r'([A-Z]+|err)([012]?)(\*?)', raw)
    require(match is not None, 'Unsupported phone label: '+raw)
    phone, stress, deviation = match.groups()
    if phone == 'err':
        require(perceived and not stress, 'err is only a perceived identity without stress')
        return dict(raw=raw, phone=None, stress=None, uncertain=True, deviation=bool(deviation))
    require(phone in ARPABET and (not stress or phone in VOWELS)
            and (perceived or not deviation), 'Unsupported canonical/perceived phone: '+raw)
    return dict(raw=raw, phone=phone, stress=int(stress) if stress else None,
                uncertain=False, deviation=bool(deviation))


def interpret_label(raw):
    """Keep deletion, insertion, unknown identity and deviation distinct."""
    require(isinstance(raw, str), 'Label must be text')
    label = raw.strip()
    if label in ('', 'sil', 'sp'):
        return dict(rawLabel=raw, event='nonlexical', nonlexicalKind={'':'unlabeled', 'sil':'silence', 'sp':'sp-unresolved'}[label],
                    canonical=None, perceived=None, errorCode=None, plainPerceivedPhoneKnown=False)
    fields = [part.strip() for part in label.split(',')]
    if len(fields) == 1:
        canonical = phone_token(fields[0])
        return dict(rawLabel=raw, event='unchanged', nonlexicalKind=None, canonical=canonical,
                    perceived=dict(canonical), errorCode=None, plainPerceivedPhoneKnown=True)
    require(len(fields) == 3 and fields[2] in ('s', 'a', 'd'), 'Malformed or unsupported error label: '+raw)
    canonical_raw, perceived_raw, code = fields
    if code == 'a':
        require(canonical_raw == 'sil', 'Insertion must use canonical sil')
        canonical, perceived = None, phone_token(perceived_raw, perceived=True)
    elif code == 'd':
        require(perceived_raw == 'sil', 'Deletion must use perceived sil')
        canonical, perceived = phone_token(canonical_raw), None
    else:
        canonical, perceived = phone_token(canonical_raw), phone_token(perceived_raw, perceived=True)
    return dict(rawLabel=raw, event={'s':'substitution', 'a':'insertion', 'd':'deletion'}[code],
                nonlexicalKind=None, canonical=canonical, perceived=perceived, errorCode=code,
                plainPerceivedPhoneKnown=bool(perceived and not perceived['uncertain'] and not perceived['deviation']))


def parse_annotations(raw):
    grid = parse_textgrid(raw)
    by_name = {tier['name']: tier for tier in grid['tiers']}
    words = by_name['words']['intervals']
    records = []
    for interval in by_name['phones']['intervals']:
        interpretation = interpret_label(interval['rawLabel'])
        # Preserve every overlap. Never force a cross-word phone into one word.
        overlaps = [dict(wordIntervalIndex=w['index'], rawWord=w['rawLabel'],
                         overlapSeconds=min(w['end'], interval['end'])-max(w['start'], interval['start']))
                    for w in words if w['rawLabel'].strip() and w['start'] < interval['end'] and interval['start'] < w['end']]
        records.append(dict(**interval, **{k:v for k,v in interpretation.items() if k != 'rawLabel'},
            tierName='phones', tierIndex=by_name['phones']['index'], wordOverlaps=overlaps,
            trainingEligible=False, evaluationEligible=False, learnerFeedbackEligible=False))
    return dict(grid=grid, records=records, manualProvenanceRequired=True,
                timingMeaning='TextGrid intervals only; no waveform duration or perceptual accuracy checked',
                labelsMeaning='Source manual-annotation conventions, not child diagnoses or adjudicated truth')
