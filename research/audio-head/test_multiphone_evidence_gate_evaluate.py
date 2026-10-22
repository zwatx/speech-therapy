import json
from pathlib import Path
import tempfile
import unittest
import wave
import numpy as np
import multiphone_evidence_gate_evaluate as evaluation

gate, raw = evaluation.gate, evaluation.raw

class GateEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=raw.HERE/'outputs')
        self.root = Path(self.temp.name)
        self.wav = self.root/'input.wav'
        with wave.open(str(self.wav), 'wb') as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
            stream.writeframes(np.zeros(1600, dtype='<i2').tobytes())
        self.posterior = self.root/'ctc.f32'
        p = np.full((4,392), .001/391); p[:,0] = .999
        np.log(p).astype('<f4').tofile(self.posterior)
        self.clip = {'id':'example','sampleCount':1600,'audioPath':str(self.wav),'audioSha256':raw.digest(self.wav)}
        self.entry = {'clipId':'example','sampleCount':1600,'audioSha256':self.clip['audioSha256'],
                      'configSha256':'config','vocabularySize':392,'frames':4,'path':'ctc.f32','sha256':raw.digest(self.posterior)}
    def tearDown(self): self.temp.cleanup()
    def test_changed_waveform_byte_rejected_before_abstention(self):
        data=bytearray(self.wav.read_bytes()); data[-1]^=1; self.wav.write_bytes(data)
        with self.assertRaises(ValueError): evaluation.bound_clip(self.clip,self.entry,self.root,'config')
    def test_changed_posterior_byte_rejected_before_abstention(self):
        data=bytearray(self.posterior.read_bytes()); data[0]^=1; self.posterior.write_bytes(data)
        with self.assertRaises(ValueError): evaluation.bound_clip(self.clip,self.entry,self.root,'config')
    def test_entry_hash_binding_and_path_escape_rejected(self):
        for entry in (dict(self.entry,audioSha256='wrong'),dict(self.entry,configSha256='wrong'),
                      dict(self.entry,path='../ctc.f32'),dict(self.entry,sha256='wrong')):
            with self.assertRaises(ValueError): evaluation.bound_clip(self.clip,entry,self.root,'config')
    def report_fixture(self):
        bindings={'audio':raw.binding(self.wav)}
        job={'audioPath':str(self.wav),'audioSha256':raw.digest(self.wav),'bindings':bindings,
             'sampleCount':1600,'expectedFrames':4,'researchOnly':True,'ctcCheckpoint':{},'sessionOptions':{}}
        raw.write_json(self.root/'ctc-job.json',job)
        ctc={'complete':True,'jobSha256':raw.digest(self.root/'ctc-job.json'),
             'audioSha256':raw.digest(self.wav),'sampleCount':1600,'frames':4,
             'posteriorsPath':'ctc.f32','posteriorsSha256':raw.digest(self.posterior),
             'checkpoint':{},'sessionOptions':{}}
        raw.write_json(self.root/'ctc.json',ctc)
        return {'complete':True,'researchOnly':True,'clinicalUseEligible':False,'learnerFeedbackEligible':False,
                'inputBindings':bindings,'ctcRuntime':ctc,
                'filesSha256':{n:raw.digest(self.root/n) for n in ('ctc.f32','ctc.json','ctc-job.json')},
                'targets':[{'id':'B','targetPhone':'B','wordIndex':0,'phoneIndex':0,
                            'subjectiveCorpusRatingProbabilities':[.01,.01,.98]}]}
    def test_filter_rejects_changed_report_and_has_no_abstained_scores(self):
        report=self.report_fixture()
        path=self.root/'raw.json'; raw.write_json(path,report); pin=raw.digest(path)
        result=gate.filter_report(path,pin,self.root/'gated.json')
        filtered=json.loads(Path(result['report']).read_text())
        self.assertFalse(filtered['decision']['ratingAvailable'])
        self.assertIsNone(filtered['targets'][0]['subjectiveCorpusRatingProbabilities'])
        path.write_text(path.read_text()+' ')
        with self.assertRaises(ValueError): gate.filter_report(path,pin,self.root/'must-not-exist.json')
        self.assertFalse((self.root/'must-not-exist.json').exists())
    def test_missing_ctc_bindings_rejected(self):
        original=self.report_fixture()
        for i,name in enumerate(('ctc.f32','ctc.json','ctc-job.json')):
            report=json.loads(json.dumps(original)); del report['filesSha256'][name]
            path=self.root/f'missing-{i}.json'; raw.write_json(path,report)
            with self.assertRaises(ValueError): gate.filter_report(path,raw.digest(path),self.root/f'result-{i}.json')
            self.assertFalse((self.root/f'result-{i}.json').exists())
    def test_same_frame_other_audio_ctc_and_job_mismatch_rejected(self):
        original=self.report_fixture()
        changes=[('audioSha256','other-audio'),('jobSha256','other-job'),('frames',5),('posteriorsSha256','other-posteriors')]
        for i,(key,value) in enumerate(changes):
            report=json.loads(json.dumps(original)); ctc=dict(original['ctcRuntime']); ctc[key]=value
            (self.root/'ctc.json').write_text(json.dumps(ctc)); report['ctcRuntime']=ctc
            report['filesSha256']['ctc.json']=raw.digest(self.root/'ctc.json')
            path=self.root/f'mismatch-{i}.json'; raw.write_json(path,report)
            with self.assertRaises(ValueError): gate.filter_report(path,raw.digest(path),self.root/f'result-{i}.json')
            self.assertFalse((self.root/f'result-{i}.json').exists())
    def test_job_binding_mismatch_rejected_even_with_updated_hashes(self):
        report=self.report_fixture(); job=json.loads((self.root/'ctc-job.json').read_text())
        job['bindings']['audio']['sha256']='other-audio'
        (self.root/'ctc-job.json').write_text(json.dumps(job))
        report['filesSha256']['ctc-job.json']=raw.digest(self.root/'ctc-job.json')
        report['ctcRuntime']['jobSha256']=report['filesSha256']['ctc-job.json']
        (self.root/'ctc.json').write_text(json.dumps(report['ctcRuntime']))
        report['filesSha256']['ctc.json']=raw.digest(self.root/'ctc.json')
        path=self.root/'mismatch.json'; raw.write_json(path,report)
        with self.assertRaises(ValueError): gate.filter_report(path,raw.digest(path),self.root/'result.json')
        self.assertFalse((self.root/'result.json').exists())
    def test_summary_keeps_vote_positions_and_speaker_overlap_distinct(self):
        rows=[{'clipId':'a','speakerId':'one','raterCounts':[2,1,2]},
              {'clipId':'b','speakerId':'one','raterCounts':[0,1,4]},
              {'clipId':'b','speakerId':'one','raterCounts':[0,0,5]}]
        tables=evaluation.summarize(rows,{'a':{'ratingAvailable':False},'b':{'ratingAvailable':True}})
        self.assertEqual(tables['total']['speakers'],1)
        self.assertEqual(tables['withheld']['rating0Votes'],2)
        self.assertEqual(tables['withheld']['rating0Positions'],1)
        self.assertEqual(tables['retained']['clips'],1)
        self.assertEqual(tables['retained']['below2Positions'],1)
if __name__ == '__main__': unittest.main()
