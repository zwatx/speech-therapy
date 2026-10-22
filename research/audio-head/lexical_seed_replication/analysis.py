"""Paired seed-specific comparisons and descriptive across-seed ranges."""
import numpy as np

from lexical_expanded_heads import evaluation as e
from lexical_phone_response import analysis as response

SEEDS = (17, 29, 43)
OBJECTIVES = ('unweighted', 'unit-weighted')
NEURAL = (*e.FAMILIES, 'equal-mixture')
require = e.require


def models(rows, original_rows, jobs, records):
    """Use the unchanged evaluator's joins and complete summaries without historical comparisons."""
    cells, mapping = e.checked_inputs(rows, original_rows, jobs, records)
    result = {}
    for regime in e.REGIMES:
        selected = [cells[regime, 'scalars', s, w] for s, w in e.CELL_KEYS]
        sources = {family: [records[cells[regime, family, s, w]['id']]['prediction']
                            for s, w in e.CELL_KEYS] for family in e.FAMILIES}
        sources['prior'] = [records[j['id']]['prior'] for j in selected]
        sources['equal-mixture'] = [e.mixture.mixture(a, b, [rows[i] for i in j['outerRows']])
                                   for j, a, b in zip(selected, sources['scalars'], sources['pca16-scalars'], strict=True)]
        result[regime] = {family: e.model_views(rows, selected, predictions) for family, predictions in sources.items()}
        require(result[regime]['scalars']['original']['rowIndices'] == sorted(mapping), 'Original population differs')
    return result


def paired(models_by_objective, corrected_seed7, original_rows):
    require(set(models_by_objective) == set(OBJECTIVES) and set(corrected_seed7) == set(e.REGIMES),
            'Both objectives and age regimes required')
    comparisons, responses = {}, {}
    for regime in e.REGIMES:
        original = {objective: {family: models_by_objective[objective][regime][family]['original']
                                for family in (*NEURAL, 'prior')} for objective in OBJECTIVES}
        require(original['unweighted']['prior'] == original['unit-weighted']['prior'], 'Objective-specific fitting priors differ')
        contrasts = [('primary/' + family, original['unit-weighted'][family], original['unweighted'][family])
                     for family in NEURAL]
        contrasts += [('secondary/' + objective, original[objective]['equal-mixture'], corrected_seed7[regime])
                      for objective in OBJECTIVES]
        decision = {}
        for name, candidate, reference in contrasts:
            e.compact.check_reference_identity(candidate, reference)
            rr = [original_rows[i] for i in candidate['rowIndices']]
            for view in (candidate, reference):
                e.checked_prediction(view, candidate['rowIndices'], rr)
            screen = e.compact.consistency(candidate, reference)
            keep = [k for k, row in enumerate(rr) if 6 <= row['age'] <= 12]
            folds = [candidate['rowFolds'][k] for k in keep]
            groups = [candidate['rowWordGroups'][k] for k in keep]
            change = response.analyze([rr[k] for k in keep], folds, groups,
                                      np.asarray(candidate['logProbabilities'])[keep], np.asarray(reference['logProbabilities'])[keep])
            require(np.isclose(change['pooled']['meanNLLDelta'], screen['childDelta']['NLL'], rtol=2e-11, atol=2e-12),
                    'Paired child response differs from screen')
            change['consistencyDecision'] = screen
            responses[regime + '/' + name] = change
            decision[name] = screen
        comparisons[regime] = dict(primary={f: decision['primary/' + f] for f in NEURAL},
            secondaryVsCorrectedSeed7={o: decision['secondary/' + o] for o in OBJECTIVES},
            neuralMinusFitPrior={o: {f: e.compact.primary_delta(original[o][f]['pooled'], original[o]['prior']['pooled'])
                                     for f in NEURAL} for o in OBJECTIVES})
    return dict(comparisons=comparisons, childLossResponses=responses)


def describe(values):
    if all(v is None for v in values):
        return None
    require(all(v is not None and np.isfinite(v) for v in values), 'Mixed missing or invalid seed values')
    return dict(mean=float(np.mean(values)), minimum=float(min(values)), maximum=float(max(values)))


def across_seeds(results):
    require([r['seed'] for r in results] == list(SEEDS), 'All three ordered new seeds required')
    expected = {r + '/' + scope + '/' + name for r in e.REGIMES
                for scope, names in (('primary', NEURAL), ('secondary', OBJECTIVES)) for name in names}
    require(all(set(r['childLossResponses']) == expected for r in results), 'Missing or extra seed contrasts')
    summary = {}
    for name in sorted(expected):
        changes = [r['childLossResponses'][name] for r in results]
        decisions = [v['consistencyDecision'] for v in changes]
        require(all(v['pooled']['support'] == changes[0]['pooled']['support'] for v in changes), 'Across-seed child support differs')
        phones = {}
        for phone in response.PHONES:
            values = [v['perPhone'][phone] for v in changes]
            require(all(v['support'] == values[0]['support'] for v in values), 'Across-seed sound support differs')
            phones[phone] = dict(support=values[0]['support'], meanNLLDelta=describe([v['meanNLLDelta'] for v in values]),
                                 perSeed={str(seed): v['meanNLLDelta'] for seed, v in zip(SEEDS, values, strict=True)})
        summary[name] = dict(support=changes[0]['pooled']['support'],
            perSeedDecisions={str(seed): d for seed, d in zip(SEEDS, decisions, strict=True)},
            everySeedPasses=all(d['consistentDevelopmentGain'] for d in decisions),
            pooledDelta={key: describe([d['childDelta'][key] for d in decisions]) for key in decisions[0]['childDelta']},
            speakerFoldNLLDelta={str(f): describe([d['speakerFoldChildDeltas'][f]['NLL'] for d in decisions]) for f in range(5)},
            perPhone=phones, promotionEligible=False)
    return dict(seeds=list(SEEDS), contrasts=summary,
                interpretation='Descriptive training-randomness mean/range on the same reused development population; seeds are not independent participants.',
                seed7Included=False, uncertaintyIntervalComputed=False, seedSelectionPerformed=False, promotionEligible=False)
