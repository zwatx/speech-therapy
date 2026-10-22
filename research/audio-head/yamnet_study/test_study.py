import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yamnet_study import study


class TablesTest(unittest.TestCase):
    def fixture(self):
        clips=[dict(id='child/a',corpusId='a',population='corpus',baseline=True,category=None,sampleCount=16000),
               dict(id='crop/a',corpusId=None,population='crop',baseline=True,category=None,sampleCount=1600),
               dict(id='new/a',corpusId=None,population='new',baseline=None,category='dog',sampleCount=80000)]
        rows=[dict(clipId='a',speakerId='s',age=6,targetPhone='B',raterCounts=[1,1,3]),
              dict(clipId='a',speakerId='s',age=6,targetPhone='P',raterCounts=[0,0,5])]
        records={x['id']:dict(accepted=False,speechScore=.1) for x in clips}
        return dict(clips=clips,rows=rows),records

    def test_withheld_speech_preserves_support_and_unknown_baseline(self):
        plan,records=self.fixture();value=study.tables(plan,records)
        self.assertEqual(value['retention']['baseline']['overall']['retained']['positions'],2)
        self.assertEqual(value['retention']['yamnet']['withheld']['a']['votes'],[1,1,8])
        self.assertEqual(value['retention']['yamnet']['overall']['retained']['votes'],[0,0,0])
        self.assertEqual(value['lostPreviouslyRetainedSpeech'],['child/a','crop/a'])
        self.assertFalse(value['childAndCropRetentionPass'])
        fresh=value['panels']['new']['categories']['dog']
        self.assertEqual(fresh,dict(total=1,baseline=None,yamnet=0,combined=None))

    def test_crops_and_coverage_matter(self):
        plan,records=self.fixture();records['child/a']['accepted']=True
        self.assertFalse(study.tables(plan,records)['childAndCropRetentionPass'])
        records['crop/a']['accepted']=True
        self.assertTrue(study.tables(plan,records)['childAndCropRetentionPass'])
        del records['new/a']
        with self.assertRaises(ValueError):study.tables(plan,records)


if __name__=='__main__':unittest.main()
