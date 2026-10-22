"""Paired legacy-row evaluation and separate expanded-population descriptions.

The caller must validate frozen artifact/checkpoint lineage before calling evaluate.
This module only joins supplied predictions; it does not open artifacts or fit models.
"""
from __future__ import annotations

import numpy as np

from lexical_compact import study as compact
from lexical_expansion import study as expansion
from lexical_mixture import study as mixture
from rating_temperature import study as scoring

require = compact.require
REGIMES = ('all-age', 'child-only')
FAMILIES = ('scalars', 'pca16-scalars')
CELL_KEYS = tuple((s, w) for s in range(5) for w in range(5))
MEMBERSHIPS = ('fitRows', 'selectionRows', 'refitRows', 'outerRows')


def summarize(prediction, rows):
    """Keep the frozen summary schema, including explicit empty-cell support."""
    p, logs = (np.asarray(prediction[k], dtype=np.float64).reshape(len(rows), 3)
               for k in ('probabilities', 'logProbabilities'))
    if rows:
        return scoring.summarize(p, rows, np.zeros(len(rows), dtype=bool), logs)
    # The frozen stable-log wrapper infers a float mask for [], so use its
    # underlying support/metric helpers for this structurally empty case only.
    measures = scoring.metrics.summarize(p, [], np.zeros(0, dtype=bool))
    reliability = {
        age: {phone: {event: scoring.reliability.reliability(p, [], classes)
                      for event, classes in scoring.reliability.EVENTS.items()}
              for phone in ('aggregate', *scoring.metrics.PHONES)}
        for age in scoring.AGES}
    return dict(measures=measures, reliability=reliability,
                nllUsesUnclippedStableLogs=True)


def checked_prediction(value, indices, rows):
    require(value['rowIndices'] == indices, 'Outer row identity differs')
    p, logs = (np.asarray(value[k], dtype=np.float64)
               for k in ('probabilities', 'logProbabilities'))
    require(p.shape == logs.shape == (len(indices), 3)
            and np.isfinite(p).all() and np.isfinite(logs).all()
            and (p >= 0).all() and (p <= 1).all()
            and np.allclose(p.sum(1), 1, atol=1e-12, rtol=0)
            and np.allclose(np.exp(logs), p, rtol=3e-13, atol=0),
            'Invalid normalized stable probability/log pair')
    if 'rawProbabilities' in value:
        raw = np.asarray(value['rawProbabilities'], dtype=np.float64)
        require(raw.shape == p.shape and np.isfinite(raw).all()
                and (raw >= 0).all() and (raw <= 1).all()
                and np.allclose(raw.sum(1), 1, rtol=0, atol=2e-7)
                and np.allclose(raw, p, rtol=2e-6, atol=1e-7),
                'Invalid raw float32 probabilities')
    if 'NLL' in value:
        # Reuse the frozen stable-log implementation to verify the saved loss.
        expected = mixture.mixture(value, value, rows)['NLL']
        require(np.isfinite(value['NLL']) and np.isclose(value['NLL'], expected, rtol=0, atol=1e-12),
                'Saved NLL differs from stable logs and votes')


def checked_inputs(rows, original_rows, jobs, records):
    require(rows and all(r['trainingEligible'] is True for r in rows), 'Ineligible expanded rows')
    scoring.reliability.votes(rows)
    mapping = expansion.legacy_map(original_rows, rows)
    scoring.reliability.votes([original_rows[i] for i in mapping])
    require(all(r['targetPhone'] in scoring.metrics.PHONES for r in rows), 'Unknown target phone')
    expected = {(regime, family, s, w) for regime in REGIMES for family in FAMILIES for s, w in CELL_KEYS}
    require(len(jobs) == len(expected), 'Expected all 100 expanded jobs')
    by_cell, ids = {}, set()
    for job in jobs:
        regime, family, s, w = (job[k] for k in ('regime', 'family', 'speakerFold', 'wordGroup'))
        key = regime, family, s, w
        require(type(s) is int and type(w) is int and key in expected and key not in by_cell,
                'Invalid or duplicate expanded job cell')
        require(job['id'] == f'{regime}-{family}-s{s}-w{w}' and job['id'] not in ids,
                'Invalid or duplicate expanded job id')
        ids.add(job['id'])
        for name in MEMBERSHIPS:
            members = job[name]
            require(isinstance(members, list) and len(set(members)) == len(members)
                    and all(type(i) is int and 0 <= i < len(rows) for i in members),
                    'Invalid or duplicate job row membership')
        require(job['outerRows'], 'Empty outer job')
        # Expanded validation additions join the final refit but never the
        # original-only epoch-selection rows; the caller validates that lineage.
        require(not set(job['fitRows']) & set(job['selectionRows'])
                and set(job['fitRows'] + job['selectionRows']) <= set(job['refitRows'])
                and not set(job['refitRows']) & set(job['outerRows']), 'Overlapping or inconsistent job partitions')
        if regime == 'child-only':
            require(all(6 <= rows[i]['age'] <= 12 for i in job['refitRows']), 'Child-only fitting membership differs')
        by_cell[key] = job
    require(set(by_cell) == expected and set(records) == ids, 'Missing or extra job records')
    row_assignment = None
    for regime in REGIMES:
        assigned = {}
        for s, w in CELL_KEYS:
            a, b = (by_cell[regime, family, s, w] for family in FAMILIES)
            mixture.check_pair(a, b)
            ar, br = records[a['id']], records[b['id']]
            require(ar['prior'] == br['prior'], 'Family-specific fitting priors differ')
            for job, record in ((a, ar), (b, br)):
                if 'jobId' in record:
                    require(record['jobId'] == job['id'], 'Record job identity differs')
                rr = [rows[i] for i in job['outerRows']]
                for name in ('prediction', 'prior'):
                    checked_prediction(record[name], job['outerRows'], rr)
            for i in a['outerRows']:
                require(i not in assigned, 'Duplicate outer prediction')
                assigned[i] = s, w
        require(sorted(assigned) == list(range(len(rows))), 'Incomplete expanded outer coverage')
        require(row_assignment is None or assigned == row_assignment, 'Age-regime outer identities differ')
        row_assignment = assigned
    return by_cell, mapping


def model_views(rows, jobs, predictions):
    merged = {}
    for job, prediction in zip(jobs, predictions, strict=True):
        for i, p, logs in zip(prediction['rowIndices'], prediction['probabilities'],
                              prediction['logProbabilities'], strict=True):
            require(i not in merged, 'Duplicate outer prediction')
            merged[i] = p, logs, job['speakerFold'], job['wordGroup']
    result = {}
    for population in ('original', 'added', 'all'):
        selected = [i for i in merged if population == 'all'
                    or (rows[i]['legacyRowIndex'] is not None) == (population == 'original')]
        def identity(i):
            return rows[i]['legacyRowIndex'] if population == 'original' else i
        selected.sort(key=identity)
        def payload(indices):
            return dict(rowIndices=[identity(i) for i in indices],
                        probabilities=[merged[i][0] for i in indices],
                        logProbabilities=[merged[i][1] for i in indices])
        def summary(indices):
            return summarize(payload(indices), [rows[i] for i in indices])
        cells = []
        for s, w in CELL_KEYS:
            indices = [i for i in selected if merged[i][2:] == (s, w)]
            cells.append(dict(speakerFold=s, wordGroup=w,
                              rowIndices=[identity(i) for i in indices], summary=summary(indices)))
        folds = []
        for s in range(5):
            indices = [i for i in selected if merged[i][2] == s]
            folds.append(dict(speakerFold=s, rowIndices=[identity(i) for i in indices], summary=summary(indices)))
        result[population] = dict(**payload(selected), rowFolds=[merged[i][2] for i in selected],
            rowWordGroups=[merged[i][3] for i in selected], cells=cells, speakerFolds=folds, pooled=summary(selected))
    return result


def evaluate(rows, original_rows, jobs, records, references):
    """Evaluate frozen supplied predictions without training, inference, or I/O.

    Original views use original cohort indices (including gaps); added/all views
    use expanded indices. Only original views enter historical comparisons.
    Caller-supplied references must be the already lineage-checked frozen models.
    """
    by_cell, mapping = checked_inputs(rows, original_rows, jobs, records)
    models, comparisons = {}, {}
    for regime in REGIMES:
        selected_jobs = [by_cell[regime, 'scalars', s, w] for s, w in CELL_KEYS]
        sources = {family: [records[by_cell[regime, family, s, w]['id']]['prediction']
                            for s, w in CELL_KEYS] for family in FAMILIES}
        sources['prior'] = [records[j['id']]['prior'] for j in selected_jobs]
        sources['equal-mixture'] = [mixture.mixture(a, b, [rows[i] for i in j['outerRows']])
                                   for j, a, b in zip(selected_jobs, sources['scalars'], sources['pca16-scalars'], strict=True)]
        models[regime] = {family: model_views(rows, selected_jobs, predictions)
                          for family, predictions in sources.items()}
        original = {family: views['original'] for family, views in models[regime].items()}
        require(original['scalars']['rowIndices'] == sorted(mapping), 'Legacy evaluation coverage differs')
        # Validate every reference before calculating any historical contrast.
        for family in (*FAMILIES, 'equal-mixture', 'corrected-mixture'):
            candidate = original['equal-mixture' if family == 'corrected-mixture' else family]
            reference = references[regime][family]
            compact.check_reference_identity(candidate, reference)
            checked_prediction(reference, candidate['rowIndices'], [original_rows[i] for i in candidate['rowIndices']])
        comparisons[regime] = dict(
            primary={family: compact.consistency(original[family], references[regime][family])
                     for family in (*FAMILIES, 'equal-mixture')},
            secondary=dict(
                mixtureVsCorrectedMixture=compact.consistency(original['equal-mixture'], references[regime]['corrected-mixture']),
                neuralMinusExpandedFitPrior={family: compact.primary_delta(original[family]['pooled'], original['prior']['pooled'])
                                             for family in (*FAMILIES, 'equal-mixture')}))
    return dict(models=models, comparisons=comparisons)
