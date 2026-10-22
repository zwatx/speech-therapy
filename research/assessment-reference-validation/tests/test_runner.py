import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reference_validation import runner as r
from consumer_assessment.bridge import response_base, FLAGS
from content_review.private_io import write_private
from workbench.domain import semantic_digest

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        raw = r.generated_case('tone')
        self.assets = {}
        for word in ('rabbit','bread','door','baby','banana','backpack','sky','vase','yoyo','thumb','feather','ring','treasure'):
            path = self.root / (word + '.wav'); write_private(str(path), raw)
            self.assets[word] = {'sourceWord':word,'wavPath':str(path),'wavSha256':r.sha(raw)}
        self.registry = {'schemaVersion':1,'assets':list(self.assets.values())}
        self.asset_patch = patch.object(r, '_assets', return_value=self.assets)
        self.asset_patch.start()
        self.plan = r.prepare_plan(self.registry)
    def tearDown(self):
        self.asset_patch.stop(); self.temp.cleanup()
    def response(self, raw):
        response = response_base(raw)
        response.update(outcome='unavailable',reason='unit_test_only_no_inference')
        return response
    def test_predeclared_matrix_preserves_full_denominator(self):
        self.assertEqual(self.plan['expectedAttempts'],23)
        self.assertEqual(sum(c['kind']=='public_reference' for c in self.plan['cases']),17)
        self.assertEqual(sum(c['kind']=='deliberate_source_word_mismatch' for c in self.plan['cases']),2)
        banana = next(c for c in self.plan['cases'] if c['sourceWord']=='banana' and c['kind']=='public_reference')
        self.assertEqual([t['phoneIndex'] for t in banana['prompt']['targets']],[2,4])
        self.assertFalse(self.plan['claimLimits']['intendedChildAccuracyEstablished'])
    def test_changed_plan_rejected_before_model_or_output(self):
        plan=copy.deepcopy(self.plan); plan['harnessAgeYears']=True
        with patch.object(r,'assess') as model:
            with self.assertRaises(r.RunError): r.run_plan(plan,self.registry,semantic_digest(self.plan),str(self.root/'run'))
            model.assert_not_called()
        self.assertFalse((self.root/'run').exists())
    def test_changed_bytes_and_hardlink_rejected_before_any_model(self):
        path=Path(self.assets['rabbit']['wavPath']); path.write_bytes(b'changed')
        with patch.object(r,'assess') as model:
            with self.assertRaises(r.RunError): r.run_plan(self.plan,self.registry,semantic_digest(self.plan),str(self.root/'run'))
            model.assert_not_called()
        path.write_bytes(r.generated_case('tone'))
        import os
        os.link(path,self.root/'extra')
        with patch.object(r,'assess') as model:
            with self.assertRaises(ValueError): r.run_plan(self.plan,self.registry,semantic_digest(self.plan),str(self.root/'run2'))
            model.assert_not_called()
    def test_no_filtered_failures_and_no_retry(self):
        with patch.object(r,'assess',side_effect=self.response) as model:
            report=r.run_plan(self.plan,self.registry,semantic_digest(self.plan),str(self.root/'run'))
            self.assertEqual(model.call_count,23)
        self.assertEqual(report['allAttemptDenominator'],23)
        self.assertEqual(report['outcomes'],{'unavailable':23})
        self.assertEqual(len(list((self.root/'run').glob('*-started.json'))),23)
        self.assertEqual(len(list((self.root/'run').glob('*-terminal.json'))),23)
        self.assertTrue((self.root/'run/report.json').exists())
    def test_bad_binding_keeps_started_without_claiming_complete(self):
        def wrong(raw):
            response=self.response(raw); response['binding']['audioSha256']='0'*64
            return response
        with patch.object(r,'assess',side_effect=wrong) as model:
            with self.assertRaises(r.RunError):r.run_plan(self.plan,self.registry,semantic_digest(self.plan),str(self.root/'run'))
            self.assertEqual(model.call_count,1)
        self.assertEqual(len(list((self.root/'run').glob('*-started.json'))),1)
        self.assertFalse((self.root/'run/report.json').exists())
    def test_incomplete_summary_fails(self):
        with self.assertRaises(r.RunError):r.summarize(self.plan,[])
    def test_incomplete_licenses_rejected_without_model(self):
        self.asset_patch.stop()
        try:
            with patch.object(r, 'assess') as model:
                with self.assertRaises(r.RunError): r.prepare_plan({'schemaVersion': True, 'assets': []})
                model.assert_not_called()
        finally:
            self.asset_patch.start()
    def test_generated_negatives_have_real_format_and_distinct_bytes(self):
        self.assertEqual(len({r.sha(r.generated_case(k)) for k in ('silence','tone','clipping','malformed')}),4)
        self.assertTrue(r.generated_case('silence').startswith(b'RIFF'))
        self.assertEqual(r.generated_case('malformed'),b'not-a-WAV')

if __name__=='__main__': unittest.main()
