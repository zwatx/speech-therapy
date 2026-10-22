"""Two-pass NISQA CSV boundary; CSV tokenization does not authorize target use."""
import csv
import hashlib
import math
from pathlib import PurePosixPath

TRAIN = 'NISQA_TRAIN_LIVE'
PREFIX = TRAIN + '/deg/'
TARGETS = ('mos', 'noi', 'dis', 'col', 'loud')
SALT = 'cadence-nisqa-train-live-ingest-v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _reader(stream, required):
    reader = csv.reader(stream, strict=True)
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError('CSV header missing') from None
    require(len(header) == len(set(header)) and all(header), 'CSV header invalid')
    require(set(required) <= set(header), 'CSV required columns missing')
    return reader, header, {name: i for i, name in enumerate(header)}


def _identity(row, index):
    """Read only split and relative path fields, never target columns."""
    require(len(row) > max(index['db'], index['filepath_deg']), 'CSV identity columns missing')
    db, path = row[index['db']], row[index['filepath_deg']]
    require(type(db) is str and type(path) is str and bool(db) and bool(path), 'CSV identity missing')
    parts = path.split('/')
    require(not any(c in path for c in ('\\', '\x00')) and not path.startswith('/')
            and not any(part in ('', '.', '..') for part in parts)
            and ':' not in parts[0] and str(PurePosixPath(path)) == path,
            'Unsafe CSV path')
    training = db == TRAIN
    require(training == path.startswith(PREFIX), 'Training split/path identity inconsistent')
    return db, path, training


def inventory(stream, *, metadata_fields=(), verified_metadata_fields=()):
    """Expose only identities and explicitly verified opaque metadata.

    Standard-library CSV tokenization necessarily reads combined-row strings,
    including held-out target tokens. This pass never indexes target fields,
    converts numeric fields, previews rows, or computes target statistics.
    Caller-owned streams must be opened with newline='' for quoted newlines.
    """
    fields = tuple(metadata_fields)
    verified = set(verified_metadata_fields)
    require(len(fields) == len(set(fields)) and not set(fields) & set(TARGETS)
            and not verified & set(TARGETS), 'Quality targets prohibited as metadata')
    require(set(fields) <= verified and not set(fields) & {'db', 'filepath_deg'},
            'Metadata fields must be explicitly verified')
    reader, header, index = _reader(stream, ('db', 'filepath_deg') + fields)
    seen, training, splits = set(), [], []
    for row in reader:
        require(len(row) == len(header), 'CSV row width invalid')
        db, path, is_train = _identity(row, index)
        require(path not in seen, 'Duplicate CSV identity')
        seen.add(path)
        identity = dict(db=db, path=path, metadata={name: row[index[name]] for name in fields})
        splits.append(identity)
        if is_train:
            training.append(identity)
    return dict(training=training, splitIdentities=splits,
                targetFieldsAccessed=False, csvTokenizationIncludesCombinedFields=True)


def selected_values(stream, selected_paths, *, scales, missing_values=None):
    """Parse quality targets only after discarding every unselected CSV row."""
    selected = tuple(selected_paths)
    require(len(selected) == len(set(selected)) == 20, 'Exactly 20 distinct selected paths required')
    for path in selected:
        _identity([TRAIN, path], {'db': 0, 'filepath_deg': 1})
    require(set(scales) == set(TARGETS), 'All five explicit quality scales required')
    checked_scales = {}
    for name in TARGETS:
        bounds = scales[name]
        require(isinstance(bounds, (tuple, list)) and len(bounds) == 2
                and all(type(v) in (int, float) and math.isfinite(v) for v in bounds)
                and bounds[0] < bounds[1], 'Invalid declared quality scale')
        checked_scales[name] = bounds
    missing_values = {} if missing_values is None else missing_values
    require(set(missing_values) <= set(TARGETS), 'Unknown missingness field')
    missing = {}
    for name in TARGETS:
        symbols = missing_values.get(name, ())
        require(isinstance(symbols, (tuple, list, set, frozenset))
                and all(type(s) is str for s in symbols), 'Invalid declared missingness symbols')
        missing[name] = set(symbols)
    reader, header, index = _reader(stream, ('db', 'filepath_deg') + TARGETS)
    wanted, found = set(selected), {}
    for row in reader:
        # Identity lookup alone precedes discarding held-out/unselected rows.
        db, path, is_train = _identity(row, index)
        if path not in wanted:
            continue
        require(is_train and db == TRAIN, 'Selected identity is not training-only')
        require(path not in found, 'Duplicate selected CSV identity')
        require(len(row) == len(header), 'Selected CSV row width invalid')
        quality, missing_tokens = {}, {}
        for name in TARGETS:
            token = row[index[name]]
            if token in missing[name]:
                quality[name] = None
                missing_tokens[name] = token
                continue
            try:
                value = float(token)
            except (TypeError, ValueError, OverflowError):
                raise ValueError('Selected quality value invalid') from None
            lo, hi = checked_scales[name]
            require(math.isfinite(value) and lo <= value <= hi, 'Selected quality value outside declared scale')
            quality[name] = value
        found[path] = dict(db=TRAIN, path=path, quality=quality, declaredMissing=missing_tokens)
    require(set(found) == wanted, 'Selected CSV identities missing; no replacement permitted')
    rows = [found[path] for path in selected]
    return dict(rows=rows, completeTargets=all(not row['declaredMissing'] for row in rows),
                trainingOnly=True, selectedPaths=list(selected))


def select(metadata):
    """Select verified phone/Skype metadata: 10 each, 20 distinct reader groups."""
    rows = list(metadata)
    require(all(isinstance(r, dict) and set(r) == {'path', 'captureCondition', 'readerGroup'} for r in rows),
            'Selection requires only verified identity/capture/reader metadata')
    require(len({r['path'] for r in rows}) == len(rows), 'Duplicate selection identity')
    for row in rows:
        _identity([TRAIN, row['path']], {'db': 0, 'filepath_deg': 1})
        require(row['captureCondition'] in ('phone', 'Skype')
                and type(row['readerGroup']) is str and bool(row['readerGroup']),
                'Verified capture condition and reader group required')
    def digest(kind, value):
        return hashlib.sha256((SALT+'\x00'+kind+'\x00'+value).encode()).hexdigest()
    groups = {}
    for row in rows:
        groups.setdefault(row['readerGroup'], []).append(row)
    # A feasibility-aware deterministic choice avoids consuming a scarce
    # condition's groups for the other condition. Mixed groups are shared.
    candidates = {condition: {g for g, rs in groups.items()
                    if any(r['captureCondition'] == condition for r in rs)} for condition in ('phone', 'Skype')}
    require(all(len(v) >= 10 for v in candidates.values())
            and len(candidates['phone'] | candidates['Skype']) >= 20,
            'Insufficient distinct reader groups for fixed quotas')
    used, chosen = set(), []
    for condition, other in (('phone', 'Skype'), ('Skype', 'phone')):
        ordered = sorted(candidates[condition], key=lambda g: (g in candidates[other], digest('group', g), g))
        available = [g for g in ordered if g not in used]
        require(len(available) >= 10, 'Insufficient distinct reader groups for fixed quotas')
        for group in available[:10]:
            options = [r for r in groups[group] if r['captureCondition'] == condition]
            selected = min(options, key=lambda r: (digest('file', r['path']), r['path']))
            used.add(group); chosen.append(dict(selected))
    return chosen
