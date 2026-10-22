"""Apply frozen research gates to an externally verified saved evaluation.

This is a decision layer, not a numerical auditor or clinical approval. The
caller must run and externally anchor the frozen auditor before calling it.
"""
from __future__ import annotations
import hashlib
import json
import math

# Canonical semantic digest of the unchanged frozen policy, distinct from file SHA.
POLICY_DIGEST = '64d021e7e2d331bb4ee694ceb0ea5bfbbf56e4904acad82f3a07196309588d80'
AUDITOR_SHA = '006a4d98852859e0e6a2a6103a733fb7b301d75bf1a4b89641418d2a6118fb72'
FLAGS = {'researchOnly': True, 'clinicalUseEligible': False,
         'learnerFeedbackEligible': False, 'productionUseEligible': False}


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                         ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def decide_outcome(report, audit, policy, expected_children=80):
    """Use only saved primary values; return an explicit invalid decision on errors.

    expected_children may be reduced by the explicitly synthetic execution
    profile. The production profile must bind the complete original 80 roster.
    Receipts are caller attestations, not signatures or global chronology proof.
    """
    invalid={'schemaVersion':1,**FLAGS,'verdict':'invalid','reasons':['integrity_failure'],'coverage':None}
    try:
        if type(expected_children) is not int or not 1<=expected_children<=80:
            return invalid
        if _digest(policy)!=POLICY_DIGEST:
            return invalid
        if (audit['outcome']!='verified' or audit['reportSha256']!=_digest(report)
                or audit['auditorSourceSha256']!=AUDITOR_SHA):
            return invalid
        if any(type(obj[key]) is not bool or obj[key]!=value for obj in (report,audit) for key,value in FLAGS.items()):
            return invalid
        children=report['children']
        if (len(children)!=expected_children or type(report['fullChildDenominator']) is not int or report['fullChildDenominator']!=expected_children
                or type(audit['fullChildDenominator']) is not int or audit['fullChildDenominator']!=expected_children):
            return invalid
        rows=[]
        for child in children:
            pair=child['paired']['candidateVsRetained']
            rows.append({'childId':child['childId'],'selectedTokens':pair['selectedTokens'],
                         'sharedProcessedRatedTokens':pair['sharedProcessedRatedTokens'],
                         'definedAUROC':pair['aurocGain'] is not None})
        if (len({r['childId'] for r in rows})!=expected_children
                or any(type(r['childId']) is not str or not r['childId'].strip() for r in rows)
                or any(type(r['selectedTokens']) is not int or not 0<=r['selectedTokens']<=40
                       or type(r['sharedProcessedRatedTokens']) is not int
                       or not 0<=r['sharedProcessedRatedTokens']<=r['selectedTokens'] for r in rows)):
            return invalid
        selected=sum(r['selectedTokens'] for r in rows)
        shared=sum(r['sharedProcessedRatedTokens'] for r in rows)
        if report['selectedTokenDenominator']!=selected or audit['selectedTokenDenominator']!=selected:
            return invalid
        primary=report['pairedSummary']['candidateVsRetained']['auroc']
        defined=[r['childId'] for r in rows if r['definedAUROC']]
        if (type(primary['fullChildDenominator']) is not int or primary['fullChildDenominator']!=expected_children
                or type(primary['definedChildIds']) is not list or len(primary['definedChildIds'])!=len(defined)
                or set(primary['definedChildIds'])!=set(defined)
                or any(pair['aurocGain'] is not None and (not _finite(pair['aurocGain']) or not -1<=pair['aurocGain']<=1)
                       for pair in [c['paired']['candidateVsRetained'] for c in children])):
            return invalid
        bootstrap=primary['bootstrap']
        required={'seed':20261002,'generator':'numpy.default_rng/PCG64','requestedReplicates':2000,
                  'quantileMethod':'linear','confidenceLevel':.95,'generatedReplicates':2000 if defined else 0}
        if any(type(bootstrap[key]) is not type(value) or bootstrap[key]!=value for key,value in required.items()):
            return invalid
        mean=primary['meanGain'];interval=bootstrap['interval95']
        if defined:
            if type(interval) is not list or len(interval)!=2:return invalid
            lower,upper=interval
            if not all(_finite(x) for x in (mean,lower,upper)) or not -1<=lower<=upper<=1 or not -1<=mean<=1:
                return invalid
        elif mean is not None or interval is not None:return invalid
        coverage={'fullChildDenominator':expected_children,'definedPairedChildren':sum(r['definedAUROC'] for r in rows),
                  'selectedTokens':selected,'sharedProcessedRatedTokens':shared,'children':rows}
        reasons=[]
        if coverage['definedPairedChildren']!=expected_children:reasons.append('undefined_paired_children')
        if selected==0 or 100*shared<95*selected:reasons.append('overall_shared_coverage_below_95_percent')
        if any(r['selectedTokens']==0 or 100*r['sharedProcessedRatedTokens']<90*r['selectedTokens'] for r in rows):
            reasons.append('per_child_shared_coverage_below_90_percent')
        if reasons:verdict='inconclusive_coverage'
        else:
            if mean>=.02 and lower>0:verdict='pass_ranking'
            elif upper<.02:verdict='fail_below_target'
            else:verdict='inconclusive_precision'
        return {'schemaVersion':1,**FLAGS,'verdict':verdict,'reasons':reasons,'coverage':coverage,
                'reportSha256':audit['reportSha256'],'thresholdComparison':'exact_unrounded_saved_values',
                'secondaryRole':'descriptive_only_no_rescue'}
    except (KeyError,TypeError,ValueError,OverflowError,RecursionError):
        return invalid
