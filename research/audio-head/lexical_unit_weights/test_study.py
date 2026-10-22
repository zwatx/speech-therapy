"""Phase barriers, paired control evaluation and weighted checkpoint integration."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from lexical_unit_weights import study as s
from lexical_unit_weights.test_core import bundle


class StudyTests(unittest.TestCase):
    def test_phase_barriers_precede_training_and_inference(self):
        with patch.object(s,'load_plan',return_value=({}, {}, dict(cohort=dict(rows=[])))),patch.object(s,'check_freeze',side_effect=ValueError('missing freeze')),patch.object(s.core,'prepare') as prep,patch.object(s.core,'train') as train,patch.object(s.core,'replay') as replay:
            with self.assertRaisesRegex(ValueError,'missing freeze'):s.fit(Path('plan'),'sha','outer-refit',Path('freeze'),'sha')
            with self.assertRaisesRegex(ValueError,'missing freeze'):s.outer(Path('plan'),'sha',Path('freeze'),'sha')
            prep.assert_not_called();train.assert_not_called();replay.assert_not_called()

    def test_fresh_declaration_without_training_or_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp).resolve()
            with patch.object(s,'BASE',base),patch.object(s,'inputs',return_value=({},[],{})),patch.object(s.core,'prepare',side_effect=AssertionError('No transforms')),patch.object(s.core,'train',side_effect=AssertionError('No training')),patch.object(s.core,'replay',side_effect=AssertionError('No inference')):
                pin=s.declare(base/'fresh');plan=s.read(pin)
                self.assertEqual(plan['weightRecipe'],s.weights.RECIPE)
                self.assertFalse(plan['trainingPerformed'])
                self.assertEqual(plan['primaryReferences'],'Corresponding unweighted expanded scalar, PCA and mixture')
                with self.assertRaises(ValueError):s.declare(base/'fresh')
                with self.assertRaises(ValueError):s.declare(base.parent/'outside')

    def test_actual_nonuniform_states_validate_and_rebound_weights_fail(self):
        b=bundle(True)
        with tempfile.TemporaryDirectory() as tmp:
            for family in s.FAMILIES:
                job=dict(id=f'all-age-{family}-s0-w0',family=family,regime='all-age',speakerFold=0,wordGroup=0,
                         fitRows=list(range(65)),selectionRows=[],refitRows=list(range(65)),addedValidationRows=[],outerRows=list(range(65,76)))
                data=s.core.prepare(b,family,job['refitRows']);out=Path(tmp).resolve()/family
                s.core.train(data,[],out,s.config_value(job,{},'outer-refit',{'epoch':2}),epochs=2)
                run=dict(jobId=job['id'],selectedEpoch=2,artifacts=s.scalar.manifest(out))
                s.validate_run(job,run,{},'outer-refit',b['cohort'])
                bad=copy.deepcopy(run);bad['selectedEpoch']=3
                with self.assertRaises(ValueError):s.validate_run(job,bad,{},'outer-refit',b['cohort'])
                # Rehash the complete JSON chain; semantic weight reconstruction must still reject it.
                changed=json.loads((out/'weights.json').read_text());changed['weights'][0]+=1
                (out/'weights.json').write_text(json.dumps(changed));weight_pin=s.files.binding(out/'weights.json')
                cfg=json.loads((out/'config.json').read_text());cfg['weights']=weight_pin
                (out/'config.json').write_text(json.dumps(cfg));config_pin=s.files.binding(out/'config.json')
                report=json.loads((out/'report.json').read_text());report['configSha256']=config_pin['sha256']
                report['artifacts']['config.json']=config_pin;report['artifacts']['weights.json']=weight_pin
                (out/'report.json').write_text(json.dumps(report));run['artifacts']=s.scalar.manifest(out)
                # Compact's existing validator checks checkpoint config before weight semantics;
                # scalar reaches the direct reconstructed-weight guard.
                with self.assertRaises(ValueError):s.validate_run(job,run,{},'outer-refit',b['cohort'])

    def test_all_eight_loss_responses_and_pairing_guard(self):
        rows=[];folds=[];groups=[]
        for f in range(5):
            for k,phone in enumerate(s.response.PHONES):
                rows.append(dict(id=f'{f}-{phone}',clipId=f'{f}-{phone}',speakerId=str(f),age=8,targetPhone=phone,raterCounts=[1,1,3]))
                folds.append(f);groups.append(k%5)
        view=dict(rowIndices=list(range(len(rows))),rowFolds=folds,rowWordGroups=groups,logProbabilities=np.log(np.tile([.2,.2,.6],(len(rows),1))).tolist())
        refs={regime:{family:copy.deepcopy(view) for family in (*s.FAMILIES,'equal-mixture','corrected-mixture')} for regime in s.REGIMES}
        result=dict(models={regime:{family:dict(original=copy.deepcopy(view)) for family in (*s.FAMILIES,'equal-mixture')} for regime in s.REGIMES},
                    comparisons={regime:dict(primary={family:dict(childDelta=dict(NLL=0.)) for family in (*s.FAMILIES,'equal-mixture')},secondary=dict(mixtureVsCorrectedMixture=dict(childDelta=dict(NLL=0.)))) for regime in s.REGIMES})
        out=s.loss_responses(result,refs,rows)
        self.assertEqual(len(out),8)
        self.assertTrue(all(len(v['perPhone'])==23 and v['pooled']['meanNLLDelta']==0 for v in out.values()))
        refs['child-only']['scalars']['rowIndices'].reverse()
        with self.assertRaisesRegex(ValueError,'pairing'):s.loss_responses(result,refs,rows)


if __name__=='__main__':unittest.main()
