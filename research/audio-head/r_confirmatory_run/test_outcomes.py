"""Invented XML/archive checks; no reserved outcomes or corpus reads."""
import io
import unittest
import warnings
import zipfile

from r_confirmatory_run.outcomes import (
    project_selected_outcomes, project_archive_outcomes, project_reserved_outcomes, OutcomeError,
)


def selected(record='r1', session='s1', folder='Synthetic_7'):
    return {'childId': folder.rsplit('_', 1)[1], 'tokenId': f'{folder}/{session}/{record}',
            'folder': folder, 'session': session, 'recordId': record, 'ageYears': 9,
            'phones': ['R'], 'startSeconds': 0., 'endSeconds': 1.}


def tier(name, text):
    return f'<userTier name="{name}"><tierData><tw>{text}</tw></tierData></userTier>'


def record(identity='r1', ratings=''):
    return (f'<r id="{identity}"><segment start="0" end="1" unit="s"/>'
            + tier('ARPABET Target', 'R') + ratings + '</r>')


def xml(records, namespace=''):
    return (f'<session{namespace}><participants><participant id="CHI"><age>P9Y</age>'
            '</participant></participants><transcript>' + records
            + '</transcript></session>').encode()


class OutcomeProjectionTests(unittest.TestCase):
    def test_selected_votes_follow_frozen_correct_total_orientation(self):
        payload = xml(record(ratings=tier('responseCorrect', '2') + tier('responseTotal', '5')))
        self.assertEqual(project_selected_outcomes(io.BytesIO(payload), 'Synthetic_7', 's1', [selected()]),
            [{'childId': '7', 'tokenId': 'Synthetic_7/s1/r1', 'status': 'available',
              'positiveVotes': 3, 'negativeVotes': 2}])

    def test_missing_tiers_preserve_each_selected_token_as_unavailable(self):
        payload = xml(record('r1') + record('r2', tier('responseCorrect', '2'))
                      + record('r3', '<userTiers>' + tier('responseCorrect', '0')
                               + tier('responseTotal', '1') + '</userTiers>'),
                      namespace=' xmlns="urn:invented:session"')
        self.assertEqual(project_selected_outcomes(io.BytesIO(payload), 'Synthetic_7', 's1',
                                                  [selected('r3'), selected('r1'), selected('r2')]),
            [{'childId': '7', 'tokenId': 'Synthetic_7/s1/r3', 'status': 'available',
              'positiveVotes': 1, 'negativeVotes': 0},
             {'childId': '7', 'tokenId': 'Synthetic_7/s1/r1', 'status': 'unavailable',
              'reason': 'missing_outcome_tier'},
             {'childId': '7', 'tokenId': 'Synthetic_7/s1/r2', 'status': 'unavailable',
              'reason': 'missing_outcome_tier'}])

    def test_selected_structure_and_membership_must_match_before_votes_are_exposed(self):
        payload = xml(record(ratings=tier('responseCorrect', '2') + tier('responseTotal', '5')))
        variants = [[], [selected(), selected()]]
        for name, value in [('ageYears', 8), ('ageYears', 9.0), ('childId', '8'),
                            ('folder', 'Other_7'), ('session', 's2'), ('recordId', 'absent'),
                            ('tokenId', 'Synthetic_7/s1/other'), ('phones', ['B','R']),
                            ('startSeconds', .1), ('endSeconds', 2.),
                            ('startSeconds', False), ('endSeconds', True)]:
            variants.append([{**selected(), name: value}])
        variants.append([{'tokenId': 'Synthetic_7/s1/r1'}])
        for tokens in variants:
            with self.subTest(tokens=tokens):
                with self.assertRaises(OutcomeError) as caught:
                    project_selected_outcomes(io.BytesIO(payload), 'Synthetic_7', 's1', tokens)
                self.assertEqual(caught.exception.code, 'selected_structure_differs')
                self.assertEqual(str(caught.exception), 'selected_structure_differs')

    def test_duplicate_malformed_or_invalid_votes_are_integrity_failures(self):
        cases = [
            (tier('responseCorrect', '2') * 2 + tier('responseTotal', '5'), 'duplicate_outcome_tier'),
            ('<userTier name="responseCorrect"><tierData><tw>1</tw><tw>2</tw></tierData></userTier>', 'malformed_outcome_tier'),
            ('<userTier name="responseCorrect"/>', 'malformed_outcome_tier'),
            ('<userTier name="responseCorrect"><tierData/></userTier>', 'malformed_outcome_tier'),
            ('<userTier name="responseCorrect"><tierData>1<tw>2</tw></tierData></userTier>', 'malformed_outcome_tier'),
            ('<userTier name="responseCorrect">' + tier('responseTotal', '5') + '</userTier>', 'malformed_outcome_tier'),
            ('<userTier name="responseCorrect">' + tier('unrelated', 'PRIVATE_SENTINEL') + '</userTier>', 'malformed_outcome_tier'),
            (tier('responseCorrect', '<x>PRIVATE_SENTINEL</x>'), 'malformed_outcome_tier'),
            (tier('responseCorrect', 'PRIVATE_SENTINEL'), 'malformed_outcome_tier'),
            (tier('responseCorrect', ''), 'malformed_outcome_tier'),
            (tier('responseCorrect', '-1'), 'invalid_outcome_votes'),
            (tier('responseTotal', '0'), 'invalid_outcome_votes'),
            (tier('responseCorrect', '6') + tier('responseTotal', '5'), 'invalid_outcome_votes'),
            (tier('responseCorrect', '2') + tier('responseTotal', '1.5'), 'malformed_outcome_tier'),
        ]
        for rating, code in cases:
            with self.subTest(code=code, rating=rating):
                with self.assertRaises(OutcomeError) as caught:
                    project_selected_outcomes(io.BytesIO(xml(record(ratings=rating))),
                                              'Synthetic_7', 's1', [selected()])
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(str(caught.exception), code)

    def test_archive_projection_uses_only_selected_sessions_and_canonical_order(self):
        source = io.BytesIO()
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('0phon/Synthetic_7/s2.xml', xml(record(ratings=tier('responseCorrect', '1') + tier('responseTotal', '1'))))
            archive.writestr('0phon/Synthetic_7/s1.xml', xml(record()))
            archive.writestr('0phon/Unselected_99/else.xml', b'PRIVATE_SENTINEL malformed unselected XML')
        source.seek(0)
        self.assertEqual(project_archive_outcomes(source, [selected(session='s2'), selected()]),
            [{'childId': '7', 'tokenId': 'Synthetic_7/s1/r1', 'status': 'unavailable', 'reason': 'missing_outcome_tier'},
             {'childId': '7', 'tokenId': 'Synthetic_7/s2/r1', 'status': 'available', 'positiveVotes': 0, 'negativeVotes': 1}])

    def test_reserved_entry_point_rejects_other_modes_before_any_source_access(self):
        for profile in ({'mode': 'synthetic'}, {}, None, {'mode': 'engineering_fixture'}):
            with self.subTest(profile=profile):
                with self.assertRaises(OutcomeError) as caught:
                    project_reserved_outcomes(profile)
                self.assertEqual(caught.exception.code, 'reserved_profile_required')

    def test_unselected_and_unrelated_tier_mutations_cannot_change_selected_votes(self):
        good = tier('responseCorrect', '  +2 ') + tier('responseTotal', '5')
        rows = []
        for noise in ('PRIVATE_SENTINEL', '<r secret="PRIVATE_SENTINEL"><participant><age>junk</age></participant></r>',
                      'x' * 5000):
            payload = xml(record(ratings=good + tier('unrelated', noise))
                          + record('r2', tier('responseCorrect', noise) + tier('responseTotal', '-999')))
            rows.append(project_selected_outcomes(io.BytesIO(payload), 'Synthetic_7', 's1', [selected()]))
        self.assertEqual(rows, [[{'childId': '7', 'tokenId': 'Synthetic_7/s1/r1', 'status': 'available',
                                 'positiveVotes': 3, 'negativeVotes': 2}]] * 3)
        self.assertNotIn('PRIVATE_SENTINEL', repr(rows))
        payload = xml(record(ratings=tier('responseCorrect', '1_0') + tier('responseTotal', '12')))
        self.assertEqual(project_selected_outcomes(io.BytesIO(payload), 'Synthetic_7', 's1', [selected()])[0]['positiveVotes'], 2)

    def test_xml_and_stream_bounds_fail_with_fixed_diagnostics(self):
        good = xml(record(ratings=tier('responseCorrect', '2') + tier('responseTotal', '5')))
        class Chunked(io.BytesIO):
            def read(self, size):
                self.assert_size(size)
                return super().read(min(size, 7))
            def assert_size(self, size):
                if not 1 <= size <= 65536:
                    raise AssertionError('unbounded read')
        self.assertEqual(project_selected_outcomes(Chunked(good), 'Synthetic_7', 's1', [selected()])[0]['positiveVotes'], 3)
        cases = [
            (b'<!DOCTYPE session [<!ENTITY x "PRIVATE_SENTINEL">]>' + good, 'forbidden_xml_declaration'),
            (good[:-8], 'malformed_xml'),
            (good.replace(b'<session>', b'<wrongRoot>').replace(b'</session>', b'</wrongRoot>'), 'invalid_root'),
            (xml(record(ratings=tier('responseCorrect', 'x' * 4097))), 'allowed_text_limit'),
            (xml(record(ratings=tier('responseCorrect', '2').replace('<tierData>', '<tierData xmlns="foreign">'))), 'namespace_ambiguity'),
            (xml(record(ratings=tier('unrelated', '<x>' * 128 + '</x>' * 128))), 'nesting_limit'),
            (xml(record(ratings=tier('unrelated', 'x' * (16*1024*1024)))), 'entry_bytes_limit'),
            (xml(record() + record()), 'duplicate_record_id'),
        ]
        for payload, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(OutcomeError) as caught:
                    project_selected_outcomes(io.BytesIO(payload), 'Synthetic_7', 's1', [selected()])
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(str(caught.exception), code)
        class Changing(io.BytesIO):
            def seek(self, *args):
                super().seek(0)
                self.write(good.replace(b'<tw>2</tw>', b'<tw>1</tw>'))
                return super().seek(*args)
        with self.assertRaises(OutcomeError) as caught:
            project_selected_outcomes(Changing(good), 'Synthetic_7', 's1', [selected()])
        self.assertEqual(caught.exception.code, 'stream_bytes_changed')

    def test_archive_duplicates_missing_members_and_unsafe_selected_paths_fail(self):
        for duplicate in (False, True):
            source = io.BytesIO()
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('unselected.txt', 'invented')
                if duplicate:
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore', UserWarning)
                        archive.writestr('unselected.txt', 'invented duplicate')
            source.seek(0)
            with self.assertRaises(OutcomeError) as caught:
                project_archive_outcomes(source, [selected()])
            self.assertEqual(caught.exception.code, 'duplicate_archive_member' if duplicate else 'missing_archive_member')
        for token in (selected(session='../s1'), selected(folder='Synthetic_07'), selected(record='../r1')):
            with self.assertRaises(OutcomeError) as caught:
                project_archive_outcomes(io.BytesIO(b'not zip'), [token])
            self.assertEqual(caught.exception.code, 'selected_structure_differs')
        with self.assertRaises(OutcomeError) as caught:
            project_archive_outcomes(io.BytesIO(b'PRIVATE_SENTINEL not zip'), [selected()])
        self.assertEqual(str(caught.exception), 'outcome_archive_failed')


if __name__ == '__main__':
    unittest.main()
