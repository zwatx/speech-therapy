import copy
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from yamnet_padding import study as s


class PaddingTests(unittest.TestCase):
    def test_exact_source_and_zeros_without_aliasing(self):
        wave=np.array([-1.,.3,0.,.999],dtype=np.float32);before=wave.copy()
        for left,right in s.VARIANTS.values():
            out=s.pad(wave,left,right)
            self.assertEqual(len(out),len(wave)+left+right)
            np.testing.assert_array_equal(out[left:left+len(wave)],before)
            self.assertFalse(out[:left].any());self.assertFalse(out[left+len(wave):].any())
            out[left]=0;np.testing.assert_array_equal(wave,before)

    def test_bad_inputs(self):
        for wave in (np.zeros(0,np.float32),np.array([np.nan],np.float32),np.zeros(2,np.float64),np.array([2.],np.float32)):
            with self.assertRaises(ValueError):s.pad(wave,0,1)
        for left,right in ((True,1),(-1,0),(0,1.2)):
            with self.assertRaises(ValueError):s.pad(np.zeros(1,np.float32),left,right)

    def test_summary_tracks_padding_failure_and_support(self):
        clips=[dict(id='a',population='corpus',corpusId='a',category=None),
               dict(id='word',population='crop',corpusId=None,category=None)]
        rows=[dict(clipId='a',speakerId='s',age=6,targetPhone='B',raterCounts=[2,1,2])]
        records={x['id']:dict(originalSummary=dict(accepted=True),variants={name:dict(accepted=False,
                 sampleCount=16000,speechScore=.2) for name in s.VARIANTS}) for x in clips}
        result=s.summarize(dict(clips=clips,rows=rows),records)
        self.assertEqual(len(result['recordingLengthFallbackCounterexamples']),6)
        for r in result['variants'].values():
            self.assertEqual(r['panels']['crop']['acceptedToRejected'],['word'])
            self.assertEqual(r['child']['withheld']['a']['votes'],[2,1,2])
            self.assertEqual(r['child']['overall']['retained']['positions'],0)
        incomplete=copy.deepcopy(records);del incomplete['word']
        with self.assertRaises(ValueError):s.summarize(dict(clips=clips,rows=rows),incomplete)


if __name__=='__main__':unittest.main()
