"""Offline engineering parity for the already-run permitted fitting fixture.

Reads only saved fitting references; never runs an encoder or scientific study.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from ages_6_12_bundle.inference import load_bundle
from consumer_assessment.bridge import HERE, ROOT, MANIFEST_SHA, sha, canonical_bytes
from consumer_assessment.worker import BUNDLE, validate_sources


def verify(directory):
    validate_sources()
    base=HERE/'outputs/multiphone-20260927'
    plan=json.loads((base/'position-audio-v2/plan.json').read_text())
    case=next(c for c in plan['cases'] if c['clipId']=='000010011')
    response=json.loads((directory/'response.json').read_text())
    request=json.loads((directory/'request.json').read_text())
    engineering=json.loads((directory/'engineering.json').read_text())
    assert request['prompt']==case['prompt'] and request['ageYears']==6
    assert response['outcome']=='processed' and response['binding']['audioSha256']==case['audio']['sha256']
    assert response['binding']['requestSha256']==sha((directory/'request.json').read_bytes())
    for key in ('matrix','posterior/000010011'):
        pin=plan['inputs'][key]
        assert sha(Path(pin['path']).read_bytes())==pin['sha256']
    values=np.load(directory/'features.npy',allow_pickle=False)
    original=np.load(plan['inputs']['matrix']['path'],allow_pickle=False,mmap_mode='r')[case['rowIndices']]
    np.testing.assert_array_equal(values,original)
    ids=np.asarray([r['modelTargetId'] for r in engineering['rows']],dtype=np.int64)
    direct=load_bundle(BUNDLE,MANIFEST_SHA).predict(values,ids,age_years=6)
    actual=np.asarray([r['subjectiveCorpusRatingProbabilities'] for r in response['targets']])
    np.testing.assert_array_equal(actual,direct['probabilities'])
    ages=base/'ages-6-12-mixture-v1'
    export=json.loads((ages/'export-report.json').read_text())
    parity=ages/'parity.npz'
    assert sha(parity.read_bytes())==export['parityArtifact']['sha256']
    with np.load(parity,allow_pickle=False) as saved:
        positions=[int(np.flatnonzero(saved['rowIndices']==row)[0]) for row in case['rowIndices']]
        expected=np.exp(saved['expectedLogProbabilities'][positions])
        np.testing.assert_allclose(np.log(actual),saved['expectedLogProbabilities'][positions],atol=1e-6,rtol=0)
        saved_probability_delta=float(np.max(np.abs(actual-expected)))
        saved_log_delta=float(np.max(np.abs(np.log(actual)-saved['expectedLogProbabilities'][positions])))
        np.testing.assert_array_equal(ids,saved['targetIds'][positions])
    assert engineering['ctc']['posteriorsSha256']==plan['inputs']['posterior/000010011']['sha256']
    assert engineering['ctc']['fetchAttempts']==0
    validate_sources()
    result={'researchOnly':True,'verificationKind':'fresh engineering smoke parity; saved fitting references only',
        'clipId':'000010011','ageYears':6,'rows':6,'featureValuesCompared':int(values.size),
        'featureReferenceExact':True,'ctcPosteriorReferenceExact':True,'directRetainedLoaderExact':True,
        'savedFittingPredictionsWithinEstablishedTolerance':True,'savedFittingLogProbabilityTolerance':1e-6,
        'savedFittingMaxProbabilityDifference':saved_probability_delta,'savedFittingMaxLogProbabilityDifference':saved_log_delta,'sourceBindingsUnchanged':True,'fetchAttempts':0,
        'inferenceMilliseconds':response['timingMilliseconds']['inference'],
        'totalMilliseconds':response['timingMilliseconds']['total'],'noClinicalAccuracyEvaluated':True,
        'sealedTestAccessed':False,'scientificStudyRerun':False}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--smoke',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True); a=p.parse_args()
    report=verify(a.smoke)
    with a.report.open('xb') as f: f.write(canonical_bytes(report))
    print(json.dumps(report,indent=2))
