import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lexical_noise import study as s


class StudyTests(unittest.TestCase):
    def test_noise_requires_complete_anchor_before_predictions(self):
        with patch.object(s,'load_plan',return_value=({}, {}, {})),patch.object(s,'checked_freeze',side_effect=ValueError('incomplete anchors')),patch.object(s,'predictions') as predict:
            with self.assertRaisesRegex(ValueError,'incomplete anchors'):s.execute(Path('plan'),'sha','noise',Path('freeze'),'sha')
            predict.assert_not_called()

    def test_invalid_declaration_prevents_any_forward(self):
        with patch.object(s,'load_plan',side_effect=ValueError('changed declaration')),patch.object(s,'predictions') as predict:
            with self.assertRaisesRegex(ValueError,'changed declaration'):s.execute(Path('plan'),'sha','anchors')
            predict.assert_not_called()

    def test_fresh_declaration_without_head_inference(self):
        with tempfile.TemporaryDirectory(dir=s.BASE) as tmp:
            dest=Path(tmp)/'fresh'
            with patch.object(s,'inputs',return_value=({},[],{})),patch.object(s.core,'predict',side_effect=AssertionError('head inference')):
                pin=s.declare(dest);self.assertFalse(s.read(pin)['headInferencePerformed'])
                with self.assertRaisesRegex(ValueError,'Fresh ignored'):s.declare(dest)

    def test_feature_compatibility_accepts_changed_windows_but_not_identity(self):
        pin=dict(path='clean',sha256='abc')
        pins={'featureBinding':pin,'feature/original/recipe':'local','feature/recipe':'phonetic','feature/headInput/report':'report'}
        row=dict(rowIndex=3,rowId='clip:B',clipId='clip',targetId=0,targetPhone='B',canonicalIndex=1,wordIndex=0,phoneIndex=1)
        noisy=dict(inputFiles={'cleanFeatureBinding':pin,'original/localRecipe':'local','original/phoneticRecipe':'phonetic'},
                   cleanFeatureBindingSha256='abc',featureSourceBindingSha256='abc',scalarFeatureNames=s.cache.original.local.SCALAR_NAMES,
                   rowIndices=[3],rows=[dict(row,estimatedPoolingWindowFrames=[9,10])])
        with patch.object(s,'read',return_value=dict(rows=[dict(row,estimatedPoolingWindowFrames=[1,3])])):
            s.compatible(noisy,pins,{'positions':{3:0}})
            bad=copy.deepcopy(noisy);bad['rows'][0]['phoneIndex']=2
            with self.assertRaisesRegex(ValueError,'identity'):s.compatible(bad,pins,{'positions':{3:0}})
            bad=copy.deepcopy(noisy);bad['featureSourceBindingSha256']='wrong'
            with self.assertRaisesRegex(ValueError,'binding'):s.compatible(bad,pins,{'positions':{3:0}})

    def test_incomplete_phase_job_inventory_rejected(self):
        frozen=dict(complete=True,plan={'p':1},phase='anchors',runs=[],**s.FLAGS)
        with patch.object(s,'binding',return_value={}),patch.object(s,'read',return_value=frozen):
            with self.assertRaisesRegex(ValueError,'Incomplete'):s.checked_freeze({'jobs':[{'id':'a'}]}, {'p':1},Path('freeze'),'sha','anchors')

    def test_population_keeps_absent_phones_and_age_groups(self):
        row=dict(clipId='c',speakerId='s',targetPhone='B',age=8)
        moves={f:dict(TV=[.1],expectedShift=[.1],absoluteExpectedShift=[.1],rating0Shift=[0.],below2Shift=[0.],argmaxChanged=[False]) for f in s.FAMILIES}
        out=s.population(moves,[row])
        self.assertEqual(len(out['ages6to12']['perPhone']),23)
        self.assertEqual(out['ages6to12']['overall']['models']['existingMixture']['positions'],1)
        self.assertIsNone(out['ages13plus']['overall']['paired'])
        self.assertIsNone(out['ages6to12']['perPhone']['G']['models']['existingMixture']['measures'])


if __name__=='__main__':unittest.main()
