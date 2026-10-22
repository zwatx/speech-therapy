"""Synthetic audited-summary contract examples; integrated stages run the real auditor."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from r_confirmatory_run.verdict import decide_outcome

POLICY = json.loads((Path(__file__).resolve().parents[3]/'docs/consumer-assessment/r-confirmatory-decisions-20261003.json').read_text())
AUDITOR = hashlib.sha256((Path(__file__).resolve().parents[1]/'r_confirmatory/evaluation_audit.py').read_bytes()).hexdigest()


def example(mean=.02, lower=.001, upper=.04, selected=20, shared=20):
    children=[{'childId':str(i),'arms':{'candidate':{'coverage':{'selected':selected}}},'paired':{'candidateVsRetained':{'selectedTokens':selected,'sharedProcessedRatedTokens':shared,'tokenIds':[f'{i}/{j}' for j in range(shared)],'aurocGain':mean}}} for i in range(1,81)]
    report={'researchOnly':True,'clinicalUseEligible':False,'learnerFeedbackEligible':False,'productionUseEligible':False,'fullChildDenominator':80,'selectedTokenDenominator':80*selected,'children':children,'pairedSummary':{'candidateVsRetained':{'auroc':{'fullChildDenominator':80,'definedChildIds':[str(i) for i in range(1,81)],'excludedChildren':[],'meanGain':mean,'bootstrap':{'interval95':[lower,upper],'seed':20261002,'generator':'numpy.default_rng/PCG64','requestedReplicates':2000,'generatedReplicates':2000,'quantileMethod':'linear','confidenceLevel':.95}}}}}
    digest=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    audit={'outcome':'verified','reportSha256':digest,'auditorSourceSha256':AUDITOR,'fullChildDenominator':80,'selectedTokenDenominator':80*selected,'researchOnly':True,'learnerFeedbackEligible':False,'clinicalUseEligible':False,'productionUseEligible':False}
    return report,audit


class VerdictTests(unittest.TestCase):
    def test_exact_mean_target_and_positive_lower_bound_pass(self):
        report,audit=example()
        before=copy.deepcopy((report,audit,POLICY))
        decision=decide_outcome(report,audit,POLICY)
        self.assertEqual(decision['verdict'],'pass_ranking')
        self.assertEqual(decision['coverage']['selectedTokens'],1600)
        self.assertEqual(decision['coverage']['sharedProcessedRatedTokens'],1600)
        self.assertEqual((report,audit,POLICY),before)

    def test_changed_policy_and_audit_or_denominator_tampering_are_invalid(self):
        report,audit=example()
        policy=copy.deepcopy(POLICY);policy['primary']['meanGainTarget']=.01
        self.assertEqual(decide_outcome(report,audit,policy)['verdict'],'invalid')
        for mutate in (lambda r,a:a.update(outcome='failed'),lambda r,a:a.update(reportSha256='0'*64),lambda r,a:a.update(selectedTokenDenominator=999),lambda r,a:r['children'][0]['paired']['candidateVsRetained'].update(selectedTokens=-1)):
            r,a=example();mutate(r,a)
            self.assertEqual(decide_outcome(r,a,POLICY)['verdict'],'invalid')

    def test_integrity_precedes_coverage_for_malformed_saved_primary(self):
        report,audit=example(shared=1)
        report['pairedSummary']['candidateVsRetained']['auroc']['bootstrap']['interval95']=[.2,.1]
        audit['reportSha256']=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        self.assertEqual(decide_outcome(report,audit,POLICY)['verdict'],'invalid')

    def test_exact_threshold_boundaries_do_not_relax_with_audit_tolerance(self):
        for mean,lower,upper,expected in [(.02,0,.04,'inconclusive_precision'),(.019999999999999997,.001,.04,'inconclusive_precision'),(.019,-.01,.019999999999999997,'fail_below_target'),(.019,-.01,.02,'inconclusive_precision'),(.02,.02,.02,'pass_ranking')]:
            with self.subTest(mean=mean,lower=lower,upper=upper):
                r,a=example(mean,lower,upper)
                self.assertEqual(decide_outcome(r,a,POLICY)['verdict'],expected)

    def test_integer_coverage_gates_keep_every_capped_token(self):
        r,a=example(shared=19)
        self.assertEqual(decide_outcome(r,a,POLICY)['verdict'],'pass_ranking')
        # 18/20 for one child and 20/20 for another: exactly 90% each and95%overall.
        for index,shared in [(0,18),(1,20)]:
            pair=r['children'][index]['paired']['candidateVsRetained']
            pair['sharedProcessedRatedTokens']=shared
            pair['tokenIds']=[f'{index+1}/{j}' for j in range(shared)]
        a['reportSha256']=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        self.assertEqual(decide_outcome(r,a,POLICY)['verdict'],'pass_ranking')
        r['children'][0]['paired']['candidateVsRetained']['sharedProcessedRatedTokens']=17
        r['children'][0]['paired']['candidateVsRetained']['tokenIds'].pop()
        a['reportSha256']=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        d=decide_outcome(r,a,POLICY)
        self.assertEqual(d['verdict'],'inconclusive_coverage')
        self.assertIn('per_child_shared_coverage_below_90_percent',d['reasons'])

    def test_zero_selection_and_one_class_children_remain_in_full_denominator(self):
        for selected in [0,20]:
            r,a=example()
            pair=r['children'][0]['paired']['candidateVsRetained'];pair['aurocGain']=None
            pair['selectedTokens']=pair['sharedProcessedRatedTokens']=selected;pair['tokenIds']=[f'1/{j}' for j in range(selected)]
            primary=r['pairedSummary']['candidateVsRetained']['auroc'];primary['definedChildIds'].remove('1')
            r['selectedTokenDenominator']=a['selectedTokenDenominator']=1580+selected
            a['reportSha256']=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
            d=decide_outcome(r,a,POLICY)
            self.assertEqual(d['verdict'],'inconclusive_coverage')
            self.assertEqual(d['coverage']['fullChildDenominator'],80)
            self.assertEqual(d['coverage']['definedPairedChildren'],79)

    def test_negative_child_gain_is_not_an_extra_failure_gate(self):
        r,a=example()
        r['children'][0]['paired']['candidateVsRetained']['aurocGain']=-.1
        for c in r['children'][1:]:c['paired']['candidateVsRetained']['aurocGain']=1.7/79
        a['reportSha256']=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        self.assertEqual(decide_outcome(r,a,POLICY)['verdict'],'pass_ranking')
