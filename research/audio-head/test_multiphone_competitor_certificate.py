"""Fail-closed certificate tests with complete synthetic artifact graphs."""
import json
from pathlib import Path
import tempfile
import unittest
from multiphone_competitor_replay import evidence_binding, validate_certificate, HERE
from multiphone_local_train import digest

class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        def write(path, value):
            path.write_text(json.dumps(value))
        self.write = write
        splits = {'folds': [{'innerFitRows':[i], 'innerValidationRows':[i+5]} for i in range(5)]}
        write(self.path/'splits.json', splits)
        write(self.path/'cohort.json', {'rows': []})
        write(self.path/'config.json', {'binding': {'cohortPath':str(self.path/'cohort.json'), 'cohortSha256':digest(self.path/'cohort.json'), 'splitsPath':str(self.path/'splits.json'), 'splitsSha256':digest(self.path/'splits.json')}})
        (self.path/'competitor.npy').write_bytes(b'fixture')
        self.results=[]
        for fold in range(5):
            for arm in ['control','competitor']:
                path=self.path/f'fold-{fold}-{arm}';path.mkdir()
                write(path/'config.json', {'studyConfigSha256':digest(self.path/'config.json'), 'fitRows':[fold], 'validationRows':[fold+5]})
                write(path/'predictions.json', {'rowIndices':[fold+5]})
                for name in ['best.pt','last.pt','history.json']:
                    (path/name).write_bytes(b'fixture')
                r={'fold':fold,'arm':arm,'hashes':{p.name:digest(p) for p in path.iterdir()}}
                write(path/'report.json',r);self.results.append(r)
        write(self.path/'report.json',{'complete':True,'configSha256':digest(self.path/'config.json'), 'competitorSha256':digest(self.path/'competitor.npy'),'results':self.results})
        self.certificate={'exact':True,'binding':evidence_binding(self.path),'sourceSha256':digest(HERE/'multiphone_competitor_replay.py'), 'checks':[dict(fold=r['fold'],arm=r['arm'],rows=1,maximumAbsoluteDifference=0.) for r in self.results]}
        write(self.path/'independent-replay.json',self.certificate)

    def test_valid_certificate_and_missing_certificate(self):
        validate_certificate(self.path)
        (self.path/'independent-replay.json').unlink()
        with self.assertRaises(FileNotFoundError):validate_certificate(self.path)

    def test_modified_report_invalidates_certificate(self):
        report=json.loads((self.path/'report.json').read_text());report['extra']='changed'
        self.write(self.path/'report.json',report)
        with self.assertRaisesRegex(ValueError,'stale'):validate_certificate(self.path)

    def test_changed_cohort_rejected(self):
        self.write(self.path/'cohort.json', {'rows': ['changed']})
        with self.assertRaisesRegex(ValueError,'Cohort digest'):validate_certificate(self.path)

    def test_changed_checkpoint_rejected(self):
        (self.path/'fold-0-control/best.pt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'artifact'):validate_certificate(self.path)

    def test_wrong_or_missing_arm_and_replay_checks_rejected(self):
        self.certificate['checks'][0]['fold']=4
        self.write(self.path/'independent-replay.json',self.certificate)
        with self.assertRaisesRegex(ValueError,'checks'):validate_certificate(self.path)
        report=json.loads((self.path/'report.json').read_text());report['results'].pop()
        self.write(self.path/'report.json',report)
        with self.assertRaisesRegex(ValueError,'five folds'):evidence_binding(self.path)

if __name__=='__main__':unittest.main()
