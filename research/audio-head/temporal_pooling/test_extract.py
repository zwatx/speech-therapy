"""Synthetic acceptance tests; no corpus audio, model inference or labels."""
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile

import numpy as np

from temporal_pooling.extract import pool, windows, exact_parity, checked_plan, RECIPE, base
from multiphone_phonetic_features import atomic_json, file_binding


class PoolTests(unittest.TestCase):
    def setUp(self):
        self.frames = np.random.default_rng(17).normal(size=(9,1024)).astype(np.float32)

    def row(self, s, e, t=9):
        return {'intervalFrames': [s,e], 'estimatedPoolingWindowFrames': [max(0,s-2),min(t,e+2)]}

    def test_half_open_bins_and_direct_means(self):
        rows = [self.row(3,6), self.row(1,2), self.row(7,8)]
        values, residual = pool(self.frames, rows, 9)
        np.testing.assert_array_equal(values['counts'], [[2,3,2],[1,1,2],[2,1,1]])
        for i,row in enumerate(rows):
            bins = windows(row,9)
            for j,(a,b) in enumerate(bins):
                np.testing.assert_array_equal(values['temporal'][i,j*1024:(j+1)*1024], self.frames[a:b].mean(0,dtype=np.float64).astype(np.float32))
            a,b = row['estimatedPoolingWindowFrames']
            np.testing.assert_array_equal(values['final'][i], self.frames[a:b].mean(0,dtype=np.float64).astype(np.float32))
        self.assertLessEqual(residual['float64MaxAbs'],1e-10)
        self.assertGreater(residual['persistedFloat32MaxAbs'],0)

    def test_empty_bins_and_full_interval(self):
        rows = [self.row(0,1),self.row(8,9),self.row(0,9)]
        values,_ = pool(self.frames,rows,9)
        np.testing.assert_array_equal(values['counts'], [[0,1,2],[2,1,0],[0,9,0]])
        bins = values['temporal'].reshape(-1,3,1024)
        np.testing.assert_array_equal(bins[0,0],bins[0,1])
        np.testing.assert_array_equal(bins[1,2],bins[1,1])
        np.testing.assert_array_equal(bins[2,0],bins[2,2])
        one,_ = pool(self.frames[:1], [self.row(0,1,1)], 1)
        np.testing.assert_array_equal(one['counts'], [[0,1,0]])
        np.testing.assert_array_equal(one['final'][0], self.frames[0])

    def test_bad_intervals_grids_and_nonfinite(self):
        for s,e in [(-1,2),(2,2),(3,2),(1,10),(True,3),(1.,3)]:
            with self.assertRaises(ValueError): pool(self.frames,[self.row(s,e)],9)
        with self.assertRaises(ValueError): pool(self.frames,[{'intervalFrames':[2,4],'estimatedPoolingWindowFrames':[1,6]}],9)
        for frames,t in [(self.frames.astype(np.float64),9),(self.frames,8),(self.frames[:,:100],9),(self.frames*np.nan,9)]:
            with self.assertRaises(ValueError): pool(frames,[self.row(2,4)],t)
        with self.assertRaises(ValueError): pool(self.frames,[],9)

    def test_exact_cache_gate_one_ulp_fails(self):
        x = self.frames[:1].copy()
        exact_parity(x,x.copy())
        y = x.copy(); y[0,0] = np.nextafter(y[0,0],np.float32(np.inf))
        with self.assertRaisesRegex(ValueError,'fresh-control'): exact_parity(x,y)
        with self.assertRaises(ValueError): exact_parity(x.astype(np.float64),x)

    def test_source_drift_fails_before_inference(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'plan.json'
            plan = {'recipe':RECIPE,'runtime':base.RUNTIME,'support':{'positions':9891,'clips':1040,'children':52},
                    'sources':{'source':'old'},'inputs':{},'model':{},'artifacts':{}}
            atomic_json(path,plan)
            with patch('temporal_pooling.extract.sources',return_value={'source':'new'}):
                with self.assertRaisesRegex(ValueError,'sources differ'): checked_plan(path,file_binding(path)['sha256'])


if __name__ == '__main__': unittest.main()
