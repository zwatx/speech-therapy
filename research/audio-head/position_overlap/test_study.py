"""Exact half-sample timing and disjoint support accounting regressions."""
import json
import unittest
from position_overlap import study as s


class OverlapTests(unittest.TestCase):
    def setUp(self):
        self.recipe=json.loads(s.a.local.RECIPE.read_text())

    def measure(self,segments,interval=None,pooling=None):
        return s.measure(interval or [0,1],pooling or [0,3],1600,self.recipe,segments)

    def test_frontend_geometry_is_derived(self):
        self.assertEqual(s.frontend_geometry(self.recipe),(320,400))
        with self.assertRaisesRegex(ValueError,'Unsupported'):
            s.frontend_geometry({'convKernel':[3],'convStride':[2]})
        with self.assertRaisesRegex(ValueError,'Invalid'):
            s.frontend_geometry({'convKernel':[True],'convStride':[2]})

    def test_half_sample_center_is_not_rounded_to_segment_boundary(self):
        inside=self.measure([{'start':199,'end':200}])
        after=self.measure([{'start':200,'end':400}])
        self.assertEqual(inside['centersInside'],1)
        self.assertEqual(after['centersInside'],0)
        self.assertEqual(inside['occupancyOverlapSamples'],1)
        self.assertEqual(after['occupancyOverlapSamples'],200)

    def test_touching_boundary_has_no_occupancy_overlap_but_pool_context_can(self):
        value=self.measure([{'start':400,'end':500}])
        self.assertEqual(value['occupancyFootprintSamples'],[0,400])
        self.assertEqual(value['poolingFootprintSamples'],[0,1040])
        self.assertTrue(value['occupancyFootprintDisjoint'])
        self.assertFalse(value['poolingFootprintDisjoint'])
        self.assertEqual(value['poolingOverlapFraction'],100/1040)

    def test_disjoint_segments_intersect_union_without_double_counting(self):
        value=self.measure([{'start':0,'end':200},{'start':320,'end':400}])
        self.assertEqual(value['occupancyOverlapSamples'],280)
        self.assertEqual(value['occupancyOverlapFraction'],.7)
        self.assertEqual(value['centerFraction'],1.)
        with self.assertRaisesRegex(ValueError,'overlapping'):
            self.measure([{'start':0,'end':200},{'start':199,'end':400}])

    def test_no_segments_and_multiple_occupied_frames(self):
        empty=self.measure([])
        self.assertTrue(empty['zeroCentersInside']);self.assertTrue(empty['poolingFootprintDisjoint'])
        value=self.measure([{'start':500,'end':900}],[1,3],[0,4])
        self.assertEqual(value['occupiedFrames'],2)
        self.assertEqual(value['centersInside'],2)
        self.assertEqual(value['occupancyFootprintSamples'],[320,1040])
        self.assertEqual(value['occupancyOverlapSamples'],400)

    def test_invalid_frame_window_and_boolean_index_rejected(self):
        for interval,pool in [([True,1],[0,3]),([0,0],[0,2]),([0,5],[0,4]),([0,1],[0,2])]:
            with self.subTest(interval=interval,pooling=pool),self.assertRaises(ValueError):
                s.measure(interval,pool,1600,self.recipe,[])

    def test_vote_support_is_not_a_majority_label_and_shared_speakers_are_unioned(self):
        rows=[]
        for i,(legacy,counts,segments) in enumerate([(1,[0,0,5],[]),(None,[1,0,4],[{'start':0,'end':400}]),
                                                  (None,[0,1,4],[])]):
            rows.append(dict(id=str(i),clipId='same',speakerId='same',age=8,targetPhone='B',legacyRowIndex=legacy,
                             raterCounts=counts,policies={p:self.measure(segments) for p in s.POLICIES}))
        result=s.tables(rows)['short100']['all']['ages6to12']['B']
        self.assertEqual(result['all'],dict(positions=3,clips=1,speakers=1,raterVotes=[1,1,13],
                                          rating0Positions=1,below2Positions=2,allTopPositions=1))
        self.assertEqual(result['zeroCentersInside']['positions'],2)
        self.assertEqual(result['zeroCentersInside']['raterVotes'],[0,1,9])
        empty=s.tables(rows)['short100']['all']['ages13plus']['B']
        self.assertEqual(empty['all']['positions'],0)
        self.assertIsNone(empty['meanFractions']['centerFraction'])


if __name__=='__main__':unittest.main()
