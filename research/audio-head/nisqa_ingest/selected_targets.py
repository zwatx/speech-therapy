"""Strict nominal target audit after the frozen training-path boundary."""
import math
import re

from . import routing

NUMBER = r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
POLICY = {
    'version': 'nisqa-selected-targets-nominal-strict-v1',
    'columns': list(routing.TARGETS),
    'rangeInclusive': [1, 5],
    'direction': 'higher is better; loudness means suitability',
    'missingTokens': ['', 'NaN'],
    'numericGrammar': NUMBER,
    'normalization': 'none; no trimming, case folding, clipping or rescaling',
    'missingVocabularyStatus': 'declared nominal strict audit; not publisher exhaustive vocabulary',
    'replacementPermitted': False,
    'trainingSplit': routing.TRAIN,
    'selectedCount': 20,
}
_NUMBER = re.compile(NUMBER, re.ASCII)


def parse_selected_targets(stream, selected_paths):
    """Return only selected training targets; preserve exact declared missing tokens.

    CSV tokenization reads combined strings, including discarded target tokens.
    Identity lookup precedes discarding rows; target indexing, row-width checks
    and numeric decoding occur only for selected identities. Open files with
    newline='' to preserve quoted CSV newlines.
    """
    selected = tuple(selected_paths)
    routing.require(all(type(path) is str for path in selected), 'Selected paths invalid')
    routing.require(len(selected) == len(set(selected)) == 20,
                    'Exactly 20 distinct selected paths required')
    for path in selected:
        routing._identity([routing.TRAIN, path], {'db': 0, 'filepath_deg': 1})
    reader, header, index = routing._reader(stream, ('db', 'filepath_deg') + routing.TARGETS)
    wanted, found = set(selected), {}
    for row in reader:
        db, path, training = routing._identity(row, index)
        if path not in wanted:
            continue
        routing.require(training and db == routing.TRAIN, 'Selected identity is not training-only')
        routing.require(path not in found, 'Duplicate selected CSV identity')
        routing.require(len(row) == len(header), 'Selected CSV row width invalid')
        quality, declared_missing = {}, {}
        for name in routing.TARGETS:
            token = row[index[name]]
            routing.require(type(token) is str, 'Selected quality value invalid')
            if token in ('', 'NaN'):
                quality[name] = None
                declared_missing[name] = token
                continue
            routing.require(_NUMBER.fullmatch(token) is not None, 'Selected quality value invalid')
            try:
                value = float(token)
            except (ValueError, OverflowError):
                raise ValueError('Selected quality value invalid') from None
            routing.require(math.isfinite(value) and 1 <= value <= 5,
                            'Selected quality value invalid')
            quality[name] = value
        found[path] = dict(db=db, path=path, quality=quality, declaredMissing=declared_missing)
    routing.require(set(found) == wanted, 'Selected CSV identities missing; no replacement permitted')
    rows = [found[path] for path in selected]
    missing_counts = {name: sum(name in row['declaredMissing'] for row in rows)
                      for name in routing.TARGETS}
    return dict(rows=rows, selectedPaths=list(selected), trainingOnly=True,
                missingCounts=missing_counts, completeTargets=not any(missing_counts.values()),
                csvTokenizationIncludesCombinedFields=True)
