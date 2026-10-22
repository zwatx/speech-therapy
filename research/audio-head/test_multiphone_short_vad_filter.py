"""Mock baseline acoustic inference; exercise saved-probability short filtering."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import multiphone_short_vad_filter as subject

raw = subject.raw


class ShortFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=raw.HERE/'outputs')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        audio=self.root/'audio.wav'; audio.write_bytes(b'mocked audio')
        self.original=dict(inputBindings={'audio':raw.binding(audio)},ctcRuntime={'sampleCount':8192},
            targets=[dict(id='ball-b',targetPhone='B',wordIndex=0,phoneIndex=0,
                          subjectiveCorpusRatingProbabilities=[.1,.2,.7])])
        self.source=self.root/'raw.json'; raw.write_json(self.source,self.original)
        self.sha=raw.digest(self.source)
        artifact=self.root/'artifact'; artifact.write_bytes(b'mocked approved artifacts')
        self.pins={k:raw.binding(artifact) for k in
                   ('vendor/utils_vad.py','vendor/silero_vad.jit','studySource','gateSource','rawSource')}

    def exercise(self,phone=True,corrupt=None,nonfinite=False):
        output=self.root/'result'
        parameters_before=copy.deepcopy(subject.study.PARAMS)
        def baseline(report,sha,destination):
            raw.read_bound_json(report,sha)
            destination.mkdir()
            old=dict(complete=True,researchOnly=True,sourceReport=raw.binding(report,sha),
                inputBindings={**self.pins,**self.original['inputBindings']},runtime=subject.study.runtime(),
                phoneEvidenceDecision=dict(ratingAvailable=phone,reasons=[] if phone else ['no-recognized-phone-evidence']),
                vad=dict(parameters=copy.deepcopy(subject.study.PARAMS),sampleCount=8192,
                         probabilities=[float('nan') if nonfinite else .9]*16,timestamps=[],vad=False),
                targets=[dict(self.original['targets'][0],subjectiveCorpusRatingProbabilities=None)])
            if corrupt: corrupt(old)
            # Permit NaN in this intentionally corrupt fixture, never production output.
            path=destination/'finalreport.json'; path.write_text(json.dumps(old))
            return dict(report=str(path),sha256=raw.digest(path))
        class Helper:
            def get_speech_timestamps_from_probs(self,probabilities,**kwargs):
                return [] if kwargs['min_speech_duration_ms']==250 else [dict(start=0,end=8192)]
        with patch.object(subject,'approved_context',return_value=copy.deepcopy(self.pins)), \
             patch.object(subject.baseline,'filter_report',side_effect=baseline) as old_filter, \
             patch.object(subject.study,'load_helper',return_value=Helper()):
            if corrupt or nonfinite:
                with self.assertRaises(ValueError): subject.filter_report(self.source,self.sha,output)
                self.assertFalse((output/'finalreport.json').exists())
                return
            result=subject.filter_report(self.source,self.sha,output)
            old_filter.assert_called_once()
        self.assertEqual(subject.study.PARAMS,parameters_before)
        self.assertEqual(raw.digest(self.source),self.sha)
        return json.loads(Path(result['report']).read_text())

    def test_short_acceptance_restores_exact_original_vectors(self):
        result=self.exercise()
        self.assertEqual(result['targets'],self.original['targets'])
        self.assertTrue(result['decision']['ratingAvailable'])
        self.assertEqual(result['vad']['parameters']['min_speech_duration_ms'],100)
        self.assertFalse(result['clinicalUseEligible']); self.assertFalse(result['learnerFeedbackEligible'])

    def test_phone_failure_masks_even_with_short_segment(self):
        result=self.exercise(phone=False)
        self.assertTrue(result['vad']['vad'])
        self.assertFalse(result['decision']['ratingAvailable'])
        self.assertIsNone(result['targets'][0]['subjectiveCorpusRatingProbabilities'])

    def test_audio_hash_mismatch_has_no_final_report(self):
        self.exercise(corrupt=lambda old:old['inputBindings']['audio'].update(sha256='0'*64))

    def test_bad_parameters_have_no_final_report(self):
        self.exercise(corrupt=lambda old:old['vad']['parameters'].update(min_speech_duration_ms=100))

    def test_nonfinite_saved_probability_has_no_final_report(self):
        self.exercise(nonfinite=True)

    def test_baseline_source_mismatch_has_no_final_report(self):
        self.exercise(corrupt=lambda old:old['inputBindings'].__setitem__('studySource',dict(path='wrong',sha256='0'*64)))

    def test_comparison_source_and_parameters_mismatch(self):
        comparison,_=raw.read_bound_json(subject.COMPARISON,subject.COMPARISON_SHA)
        plan,_=raw.read_bound_json(comparison['plan']['path'],comparison['plan']['sha256'])
        read=raw.read_bound_json
        for field in ('source','parameters'):
            damaged=copy.deepcopy(plan)
            if field=='source': damaged['inputBindings']['comparisonSource']['sha256']='0'*64
            else: damaged['baseParameters']['min_speech_duration_ms']=100
            def reader(path,expected=None):
                if Path(path)==Path(comparison['plan']['path']): return damaged,raw.binding(path,expected)
                return read(path,expected)
            with self.subTest(field=field),patch.object(raw,'read_bound_json',side_effect=reader):
                with self.assertRaises(ValueError): subject.approved_context()


if __name__=='__main__': unittest.main()
