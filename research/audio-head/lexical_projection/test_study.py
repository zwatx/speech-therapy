"""Study phase/identity guards using actual synthetic adaptation artifacts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lexical_projection import study as s
from lexical_projection import test_core as fixtures

class RunnerTests(unittest.TestCase):
    def test_actual_synthetic_run_manifest_and_membership_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            d,_,_,sel,_,pins=fixtures.ProjectionTests().fixture(Path(tmp)/'source',flat=True)
            job=dict(id='synthetic-projection',regime='child-only',speakerFold=0,wordGroup=0,fitRows=d['fit'],selectionRows=sel,refitRows=d['fit']+sel,
                     sourceInner=dict(zip(['checkpoint','transform','config'],pins)))
            source=Path(tmp)/'source-selection.json';s.write(source,s.core.predict(d,sel));job['sourceSelection']=s.binding(source)
            plan=dict(path='synthetic-plan',sha256='synthetic')
            dest=Path(tmp)/'adapt';s.core.train(d,sel,dest,s.config_value(job,plan,'inner'))
            aa=s.artifacts(dest);run=dict(jobId=job['id'],selectedEpoch=0,artifacts=aa)
            s.check_run(job,run,plan,'inner',d['cohort']['rows'])
            cfg=s.read(aa['config.json']);history=s.read(aa['history.json'])
            for kind in ('nll','row','order','continued','raw'):
                altered=copy.deepcopy(history)
                if kind=='nll':altered[1]['selection']['NLL']+=.01
                elif kind=='row':altered[1]['selection']['rowIndices'].reverse()
                elif kind=='order':altered[1]['orderSha256']='wrong'
                elif kind=='continued':
                    altered.append(copy.deepcopy(altered[-1]));altered[-1]['epoch']=6
                else:altered[1]['selection']['rawProbabilities'][0][0]=float('nan')
                with self.subTest(kind=kind),self.assertRaises(ValueError):s.history_state(altered,cfg,d['cohort']['rows'])

            bad=copy.deepcopy(job);bad['selectionRows']=sel[:-1]
            with self.assertRaisesRegex(ValueError,'configuration'):s.check_run(bad,run,plan,'inner',d['cohort']['rows'])
            badrun=copy.deepcopy(run);badrun['selectedEpoch']=1
            with self.assertRaises(ValueError):s.check_run(job,badrun,plan,'inner',d['cohort']['rows'])

    def test_declaration_never_trains_or_predicts(self):
        with tempfile.TemporaryDirectory(dir=s.BASE) as tmp:
            with patch.object(s,'inputs',return_value=({},[])),patch.object(s.core,'train',side_effect=AssertionError('no fit')),patch.object(s.core,'predict',side_effect=AssertionError('no predict')):
                out=Path(tmp)/'new';self.assertTrue(Path(s.declare(out)['path']).exists())
                with self.assertRaises(ValueError):s.declare(out)

    def test_refit_requires_complete_inner_before_preparation(self):
        with patch.object(s,'load_plan',return_value=({}, {}, {})),patch.object(s,'check_freeze',side_effect=ValueError('incomplete')),patch.object(s,'prepared') as prepare:
            with self.assertRaisesRegex(ValueError,'incomplete'):s.fit(Path('fake'), 'sha','outer-refit',Path('freeze'),'sha')
            prepare.assert_not_called()

    def test_outer_requires_complete_refit_before_preparation(self):
        with patch.object(s,'load_plan',return_value=({}, {}, {})),patch.object(s,'check_freeze',side_effect=ValueError('incomplete')),patch.object(s,'prepared') as prepare:
            with self.assertRaisesRegex(ValueError,'incomplete'):s.outer(Path('fake'),'sha',Path('freeze'),'sha')
            prepare.assert_not_called()

    def test_freeze_rejects_missing_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'freeze.json';s.write(out,dict(complete=True,plan={},phase='inner',runs=[]));pin=s.binding(out)
            with self.assertRaisesRegex(ValueError,'Incomplete'):s.check_freeze(dict(jobs=[dict(id='required')]),{},out,pin['sha256'],'inner')

if __name__=='__main__':unittest.main()
