import unittest
from unittest.mock import patch
import multiphone_short_vad_followup as subject


class FollowupTests(unittest.TestCase):
    def records(self):
        return {'both':dict(clip={'id':'both'},vad=dict(default250=True,short100=True)),
                'short':dict(clip={'id':'short'},vad=dict(default250=False,short100=True)),
                'neither':dict(clip={'id':'neither'},vad=dict(default250=False,short100=False))}

    def measured(self):
        return {'both':dict(ratingAvailable=True,recognizedPhoneTokens=2),
                'short':dict(ratingAvailable=False,recognizedPhoneTokens=0)}

    def test_shortcircuit_retains_null_for_unmeasured(self):
        result = subject.combine(self.records(),self.measured())
        self.assertEqual(len(result),3)
        self.assertIsNone(result['neither']['phoneEvidence'])
        self.assertIsNone(result['neither']['recognizedPhoneTokens'])
        self.assertFalse(result['neither']['phoneEvidenceMeasured'])
        self.assertEqual(result['neither']['combined'],dict(default250=False,short100=False))
        self.assertEqual(result['both']['combined'],dict(default250=True,short100=True))
        self.assertEqual(result['short']['combined'],dict(default250=False,short100=False))

    def test_short_only_positive_applies_to_short_policy(self):
        measured=self.measured(); measured['short']=dict(ratingAvailable=True,recognizedPhoneTokens=1)
        self.assertEqual(subject.combine(self.records(),measured)['short']['combined'],
                         dict(default250=False,short100=True))

    def test_missing_positive_evidence_fails(self):
        measured=self.measured(); del measured['short']
        with self.assertRaises(ValueError): subject.combine(self.records(),measured)
        measured['short']=None
        with self.assertRaises(ValueError): subject.combine(self.records(),measured)

    def test_unexpected_extra_evidence_fails(self):
        measured=self.measured(); measured['neither']=dict(ratingAvailable=False,recognizedPhoneTokens=0)
        with self.assertRaises(ValueError): subject.combine(self.records(),measured)

    def test_bad_or_nonnested_vad_fails(self):
        for value in (dict(default250=True,short100=False),dict(default250=False,short100=1)):
            records=self.records(); records['neither']['vad']=value
            with self.assertRaises(ValueError): subject.selected_ids(records)

    def test_wrong_canonical_prompt_or_execution_runtime_fails(self):
        canonical = dict(transcript='BALL',canonicalPhones=['B','AO1','L'],
                         targets=[dict(targetPhone='B',wordIndex=0,phoneIndex=0)])
        runtime = dict(device='cpu',threads=2,torch=str(subject.raw.torch.__version__),
                       numpy=subject.np.__version__)
        contract = dict(device='cpu',threads=2)
        valid = dict(canonicalPrompt=canonical,runtime=runtime)
        subject.verify_report_metadata(valid,canonical,contract)
        for field,value in [('device','cuda'),('threads',1),('torch','other'),('numpy','other')]:
            with self.assertRaises(ValueError):
                subject.verify_report_metadata(dict(valid,runtime={**runtime,field:value}),canonical,contract)
        for value in (dict(canonical,transcript='CAT'),dict(canonical,canonicalPhones=['B']),
                      dict(canonical,targets=[dict(targetPhone='D',wordIndex=0,phoneIndex=0)])):
            with self.assertRaises(ValueError):
                subject.verify_report_metadata(dict(valid,canonicalPrompt=value),canonical,contract)

    def test_plan_pin_failure_prevents_inference(self):
        with patch.object(subject.raw,'read_bound_json',side_effect=ValueError('SHA differs')):
            with patch.object(subject.raw,'run') as inference:
                with self.assertRaises(ValueError): subject.run('invalid')
                inference.assert_not_called()


if __name__ == '__main__': unittest.main()
