"""Synthetic metadata tests; never reads corpus, ratings, audio or models."""
import unittest
from r_confirmatory.select import prepare_selection


def row(child='1', record='token', phones=None, start=0, end=1):
    folder = 'Synthetic_' + child
    return {'childId': child, 'tokenId': f'{folder}/PRE/{record}', 'folder': folder,
            'session': 'PRE', 'recordId': record, 'ageYears': 6,
            'phones': phones or ['R', 'AE1', 'T'], 'startSeconds': start, 'endSeconds': end}


class SelectionTests(unittest.TestCase):
    def test_full_child_roster_keeps_zero_selection_and_pre_audio_exclusions(self):
        payload = {'children': [{'childId': '2'}, {'childId': '1'}],
                   'tokens': [row(record='short', end=.099999), row(record='unsupported', phones=['R', 'AX0']),
                              row(record='not-r', phones=['B', 'AE1', 'T'])]}
        report = prepare_selection(payload)
        self.assertEqual(report['counts'], {'fullChildDenominator': 2, 'suppliedTokens': 3,
                         'eligibleTokens': 2, 'selectedTokens': 2, 'unselectedEligibleTokens': 0,
                         'preAudioUnmappableTokens': 1, 'belowReaderMinimumTokens': 1})
        self.assertEqual([c['childId'] for c in report['children']], ['1', '2'])
        self.assertEqual(report['children'][1]['reason'], 'no_eligible_tokens')
        self.assertEqual(report['children'][1]['selectedTokenIds'], [])
        dispositions = {r['tokenId'].split('/')[-1]: r for r in report['tokens']}
        self.assertEqual(dispositions['unsupported']['unmappablePhones'], ['AX0'])
        self.assertTrue(dispositions['short']['belowReaderMinimum'])
        self.assertEqual(dispositions['not-r']['disposition'], 'ineligible_single_consonantal_r')
        self.assertTrue(report['researchOnly'])
        self.assertFalse(report['learnerFeedbackEligible'])

    def test_cap_precedes_unsupported_exclusion_and_does_not_replace_tokens(self):
        payload = {'children': [{'childId': '1'}],
                   'tokens': [row(record=f't{index}', phones=['R', 'AX0']) for index in range(43)]}
        report = prepare_selection(payload)
        self.assertEqual(report['counts']['selectedTokens'], 40)
        self.assertEqual(report['counts']['preAudioUnmappableTokens'], 40)
        self.assertEqual(report['counts']['unselectedEligibleTokens'], 3)
        self.assertEqual(len(report['tokens']), 43)
        self.assertEqual(len(set(report['children'][0]['selectedTokenIds'])), 40)
        reversed_payload = {'children': payload['children'], 'tokens': list(reversed(payload['tokens']))}
        self.assertEqual(report, prepare_selection(reversed_payload))

    def test_reader_limit_uses_declared_six_decimal_rounding_and_r_context_scope(self):
        payload = {'children': [{'childId': '1'}], 'tokens': [
            row(record='at-limit', end=.0999996), row(record='below-limit', end=.0999994),
            row(record='syllabic', phones=['R', 'ER0']), row(record='repeated', phones=['R', 'AE1', 'R']),
            row(record='no-r', phones=['B', 'AE1'])]}
        report = prepare_selection(payload)
        self.assertEqual(report['counts']['eligibleTokens'], 2)
        self.assertEqual(report['counts']['selectedTokens'], 2)
        self.assertEqual(report['counts']['belowReaderMinimumTokens'], 1)
        indexed = {r['recordId']: r for r in report['tokens']}
        self.assertEqual(indexed['at-limit']['durationSeconds'], .1)
        self.assertFalse(indexed['at-limit']['belowReaderMinimum'])
        self.assertTrue(indexed['below-limit']['belowReaderMinimum'])

    def test_duplicate_unknown_rating_fields_and_invalid_metadata_fail_closed(self):
        import copy
        good = {'children': [{'childId': '1'}], 'tokens': [row()]}
        mutations = [
            lambda p: p['children'].append({'childId': '1'}),
            lambda p: p['tokens'].append(copy.deepcopy(p['tokens'][0])),
            lambda p: p['tokens'][0].update(positiveVotes=1),
            lambda p: p['tokens'][0].update(probability=.5),
            lambda p: p['tokens'][0].update(childId='2'),
            lambda p: p['tokens'][0].update(tokenId='different'),
            lambda p: p['tokens'][0].update(folder='Wrong_2'),
            lambda p: p['tokens'][0].update(ageYears=True),
            lambda p: p['tokens'][0].update(ageYears=13),
            lambda p: p['tokens'][0].update(endSeconds=float('inf')),
            lambda p: p['tokens'][0].update(endSeconds=10**400),
            lambda p: p['tokens'][0].update(startSeconds=-1),
            lambda p: p['tokens'][0].update(endSeconds=0),
            lambda p: p['tokens'][0].update(phones=[]),
            lambda p: p['tokens'][0].update(recordId='bad|delimiter'),
            lambda p: p['children'][0].update(childId='01'),
        ]
        for change in mutations:
            with self.subTest(change=mutations.index(change)):
                payload = copy.deepcopy(good)
                change(payload)
                with self.assertRaises(ValueError): prepare_selection(payload)

    def test_lexical_child_order_and_input_immutability(self):
        import copy
        payload = {'children': [{'childId': '2'}, {'childId': '10'}],
                   'tokens': [row(child='2'), row(child='10')]}
        original = copy.deepcopy(payload)
        report = prepare_selection(payload)
        self.assertEqual(payload, original)
        self.assertEqual([r['childId'] for r in report['children']], ['10', '2'])
        self.assertEqual(report['counts']['fullChildDenominator'], 2)
        # Independent shasum oracle for the fixed synthetic identity, not derived by the test.
        self.assertEqual(prepare_selection({'children': [{'childId': '1'}], 'tokens': [row()]})['tokens'][0]['selectionRankSha256'],
                         '57cb2a0997c5dc88e782d71dc62d13663ba1b873a8549866e088bc169d50c14f')
        self.assertEqual(len(report['selectedMembershipSha256']), 64)
        self.assertFalse(report['clinicalUseEligible'])
        self.assertFalse(report['productionUseEligible'])


if __name__ == '__main__': unittest.main()
