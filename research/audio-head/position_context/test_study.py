"""Boundary, warning and support-accounting regressions for the diagnostic."""
import copy
import unittest

from position_context import study as s


class ContextTests(unittest.TestCase):
    def locate(self, interval, segments):
        return s.locate(interval, 2000, [dict(start=x, end=y) for x, y in segments])

    def test_half_sample_membership_and_end_distance_infimum(self):
        inside = self.locate([0, 1], [(199, 200)])
        before = self.locate([0, 1], [(200, 400)])
        after = self.locate([0, 1], [(0, 199)])
        self.assertEqual(inside['category'], 'centerInside')
        self.assertIsNone(inside['gapSamples'])
        self.assertEqual(inside['nearestDistanceDoubledSamples'], 0)
        self.assertEqual(before, dict(category='beforeFirst', gapSamples=[0, 200],
            nearestDistanceDoubledSamples=1, nearestDistanceMs=1 / 32))
        self.assertEqual(after, dict(category='afterLast', gapSamples=[199, 2000],
            nearestDistanceDoubledSamples=1, nearestDistanceMs=1 / 32))

    def test_internal_gap_is_not_recording_edge(self):
        value = self.locate([1, 3], [(0, 400), (900, 1600)])
        self.assertEqual(value, dict(category='internalGap', gapSamples=[400, 900],
            nearestDistanceDoubledSamples=121, nearestDistanceMs=121 / 32))

    def test_no_segments_retains_missing_distance(self):
        self.assertEqual(self.locate([1, 3], []), dict(category='noSegments',
            gapSamples=[0, 2000], nearestDistanceDoubledSamples=None, nearestDistanceMs=None))

    def test_between_center_fallback_uses_interior_centers_for_distance(self):
        # Centers 199.5, 519.5, 839.5, 1159.5: the nearest is not a span endpoint.
        value = self.locate([0, 4], [(600, 700)])
        self.assertEqual(value, dict(category='segmentBetweenCenters', gapSamples=None,
            nearestDistanceDoubledSamples=161, nearestDistanceMs=161 / 32))

    def test_membership_wins_for_multiframe_span_crossing_segments(self):
        value = self.locate([0, 4], [(500, 550), (1100, 1200)])
        self.assertEqual(value['category'], 'centerInside')
        self.assertEqual(value['nearestDistanceMs'], 0)
        self.assertIsNone(value['gapSamples'])

    def test_invalid_geometry_and_segments_are_rejected(self):
        for interval in ([True, 1], [0, 0], [-1, 1], [0, 7], [0., 1]):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                self.locate(interval, [])
        for segments in ([(0, 500), (499, 600)], [(400, 399)], [(-1, 1)], [(0, 2001)]):
            with self.subTest(segments=segments), self.assertRaises(ValueError):
                self.locate([0, 1], segments)

    def fixture(self, *, phone_index=0, canonical_index=1, fraction=.49, frames=1):
        clip = dict(words=[{'phones': ['AH0']}, {'phones': ['B', 'IY0']}, {'phones': ['S']}],
                    canonicalPhones=['AH0', 'B', 'IY0', 'S'])
        row = dict(wordIndex=1, phoneIndex=phone_index, canonicalIndex=canonical_index, targetPhone='B')
        flags = [s.BASE_FLAG] + ([s.SINGLE_FLAG] if frames == 1 else []) + ([s.ARGMAX_FLAG] if fraction < .5 else [])
        geometry = dict(intervalFrames=[1, 1 + frames], diagnosticFlags=flags,
                        scalarFeatures=[-1, .2, .3, -1, -1, fraction, .8, 0, 1, frames * .02, frames, -1, .5])
        return row, geometry, clip

    def test_prompt_positions_do_not_confuse_word_start_with_prompt_start(self):
        row, geometry, clip = self.fixture()
        c = s.context(row, geometry, clip)
        self.assertEqual(c, dict(singleFrame=True, targetNotArgmax=True, bothWarnings=True,
            wordFirst=True, wordLast=False, promptFirst=False, promptLast=False))
        row.update(wordIndex=2, phoneIndex=0, canonicalIndex=3, targetPhone='S')
        c = s.context(row, geometry, clip)
        self.assertTrue(c['wordFirst'] and c['wordLast'] and c['promptLast'])
        self.assertFalse(c['promptFirst'])
        row['canonicalIndex'] = 0
        with self.assertRaisesRegex(ValueError, 'prompt position'):
            s.context(row, geometry, clip)

    def test_exact_existing_warning_boundary_and_corrupt_flags(self):
        row, geometry, clip = self.fixture(fraction=.5, frames=2)
        c = s.context(row, geometry, clip)
        self.assertFalse(c['singleFrame'] or c['targetNotArgmax'] or c['bothWarnings'])
        geometry['diagnosticFlags'].append(s.ARGMAX_FLAG)
        with self.assertRaisesRegex(ValueError, 'warning or duration'):
            s.context(row, geometry, clip)
        row, geometry, clip = self.fixture()
        geometry['scalarFeatures'][10] = 3
        with self.assertRaisesRegex(ValueError, 'warning or duration'):
            s.context(row, geometry, clip)

    def test_empty_and_finite_numeric_support(self):
        self.assertEqual(s.numeric([None]), dict(count=0, minimum=None, median=None, p90=None, maximum=None))
        self.assertEqual(s.numeric([None, 0, 10]), dict(count=2, minimum=0., median=5., p90=9., maximum=10.))
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            s.numeric([float('nan')])

    def test_category_partition_votes_flags_and_shared_speaker_counts(self):
        rows = []
        _, geometry, _ = self.fixture()
        for i, (category, votes, legacy) in enumerate([
            ('centerInside', [0, 0, 5], 0), ('beforeFirst', [1, 0, 4], None),
            ('internalGap', [0, 1, 4], None), ('noSegments', [0, 0, 5], 1)]):
            policies = {p: dict(category=category, occupancyFootprintDisjoint=category == 'noSegments',
                poolingFootprintDisjoint=category == 'noSegments',
                nearestDistanceMs=None if category == 'noSegments' else (0 if i == 0 else 10)) for p in s.overlap.POLICIES}
            rows.append(dict(id=str(i), clipId='shared', speakerId='shared', age=8, targetPhone='B',
                legacyRowIndex=legacy, raterCounts=votes, policies=policies,
                intervalFrames=[0, 1], scalarFeatures=copy.deepcopy(geometry['scalarFeatures']),
                context={k: k in ('singleFrame', 'wordFirst', 'wordLast') for k in s.CONTEXT}))
        result = s.tables(rows)['short100']
        cell = result['all']['ages6to12']['B']
        self.assertEqual(cell['all']['positions'], 4)
        self.assertEqual(cell['all']['raterVotes'], [1, 1, 18])
        self.assertEqual(cell['all']['rating0Positions'], 1)
        self.assertEqual(cell['all']['below2Positions'], 2)
        self.assertEqual(cell['all']['allTopPositions'], 2)
        self.assertEqual(cell['all']['speakers'], 1)
        self.assertEqual(cell['all']['clips'], 1)
        self.assertEqual(cell['all']['wordFirst'], 4)
        self.assertEqual(cell['all']['wordLast'], 4)
        self.assertEqual(cell['zeroCenters']['positions'], 3)
        self.assertEqual(cell['zeroCenters']['nearestDistanceMissing'], 1)
        self.assertEqual(cell['zeroCenters']['numeric']['nearestDistanceMs']['count'], 2)
        self.assertEqual(result['original']['allAges']['B']['all']['speakers'], 1)
        self.assertEqual(result['added']['allAges']['B']['all']['speakers'], 1)
        empty = result['all']['ages13plus']['B']['all']
        self.assertEqual(empty['positions'], 0)
        self.assertEqual(empty['numeric']['occupiedFrames']['count'], 0)
        self.assertIsNone(empty['numeric']['occupiedFrames']['median'])


if __name__ == '__main__':
    unittest.main()
