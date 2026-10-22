from copy import deepcopy
import json
from pathlib import Path
import unittest

from content_review.packet import (PacketError, compile_packet, load_pack, load_pack_bytes,
                                   source_manifest, strict_json, validate_packet)
from workbench.domain import semantic_digest


PUBLIC_PACK = Path(__file__).resolve().parents[3] / 'docs/consumer-assessment/proposed-engineering-pack.json'


class PacketTests(unittest.TestCase):
    def test_pinned_pack_retains_every_variant_and_target_without_professional_approval(self):
        packet = compile_packet(PUBLIC_PACK.read_bytes())
        self.assertEqual(packet['counts'], {'prompts': 15, 'distinctSourceWords': 13,
                                          'variants': 17, 'allTargetOccurrences': 23,
                                          'selectedPositionOccurrences': 18})
        self.assertEqual(packet['status'], 'all_professional_review_pending')
        self.assertEqual(len(packet['prompts']), 15)
        self.assertTrue(all(prompt['status'] == 'pending' for prompt in packet['prompts']))
        self.assertEqual(packet['claimLimits'], {'qualifiedApprovalEstablished': False, 'referenceAudioVerified': False,
                                                'rightsVerified': False, 'learnerFeedbackEligible': False,
                                                'clinicalUseEligible': False, 'productionUseEligible': False})
        self.assertTrue(all(flag is False for flag in packet['claimLimits'].values()))
        banana = next(prompt for prompt in packet['prompts'] if prompt['id'] == 'n-middle-banana')
        self.assertEqual(banana['variants'], [{'id': 'variant-1', 'phones': ['B', 'AH', 'N', 'AE', 'N', 'AH'],
                                               'allTargetIndexes': [2, 4], 'selectedPositionIndexes': [2, 4]}])
        self.assertIn('selected_occurrence_ambiguous', banana['issues'])

    def test_occurrence_selection_remains_a_subset_without_silently_choosing_banana(self):
        by_id = {prompt['id']: prompt for prompt in compile_packet(load_pack_bytes())['prompts']}
        expected = {
            'b-beginning-baby': ([0, 2], [0]), 'b-middle-baby': ([0, 2], [2]),
            'k-middle-backpack': ([2, 5], [2]), 'k-end-backpack': ([2, 5], [5]),
            'y-beginning-yo-yo': ([0, 2], [0]), 'n-middle-banana': ([2, 4], [2, 4]),
        }
        for prompt_id, (all_indexes, selected_indexes) in expected.items():
            with self.subTest(prompt=prompt_id):
                variant = by_id[prompt_id]['variants'][0]
                self.assertEqual(variant['allTargetIndexes'], all_indexes)
                self.assertEqual(variant['selectedPositionIndexes'], selected_indexes)
        ambiguous = [prompt['id'] for prompt in by_id.values() if 'selected_occurrence_ambiguous' in prompt['issues']]
        self.assertEqual(ambiguous, ['n-middle-banana'])

    def test_metadata_issues_preserve_alias_variants_clusters_and_unsupported_target(self):
        by_id = {prompt['id']: prompt for prompt in compile_packet(load_pack_bytes())['prompts']}
        self.assertEqual(by_id['r-beginning-rabbit']['variants'][0]['phones'], ['R', 'AE', 'B', 'AH', 'T'])
        self.assertEqual(by_id['r-beginning-rabbit']['variants'][1]['phones'], ['R', 'AE', 'B', 'IH', 'T'])
        self.assertEqual(by_id['v-beginning-vase']['variants'][0]['phones'], ['V', 'EY', 'S'])
        self.assertEqual(by_id['v-beginning-vase']['variants'][1]['phones'], ['V', 'AA', 'Z'])
        self.assertEqual([p['id'] for p in by_id.values() if 'variant_choice' in p['issues']],
                         ['r-beginning-rabbit', 'v-beginning-vase'])
        self.assertEqual([p['id'] for p in by_id.values() if 'cluster_context' in p['issues']],
                         ['r-middle-bread', 's-beginning-sky'])
        self.assertEqual([p['id'] for p in by_id.values() if 'unsupported_target' in p['issues']], ['zh-middle-treasure'])
        self.assertIs(by_id['zh-middle-treasure']['modelInventorySupported'], False)
        self.assertIsNone(by_id['zh-middle-treasure']['modelTargetId'])
        alias = by_id['y-beginning-yo-yo']
        self.assertEqual((alias['word'], alias['sourceWord'], alias['lexicalGroup']), ('yo-yo', 'yoyo', 'yoyo'))
        self.assertIn('source_spelling_alias', alias['issues'])
        self.assertEqual(by_id['b-beginning-baby']['lexicalGroup'], by_id['b-middle-baby']['lexicalGroup'])
        self.assertTrue(all('professional_review_pending' in p['issues'] and 'reference_variety_pending' in p['issues']
                            for p in by_id.values()))

    def test_exact_packet_schema_links_and_pending_requirements_are_deterministic(self):
        raw = load_pack_bytes()
        packet = compile_packet(raw)
        self.assertEqual(set(packet), {'schemaVersion', 'kind', 'sourcePackSha256', 'sourceManifestSha256', 'projectId',
                                       'status', 'scope', 'counts', 'controlledWorkflow', 'prompts', 'claimLimits'})
        self.assertEqual(packet['sourcePackSha256'], 'a957a9e3291f0d90b275d40cd914890836ee7e6fc4fd361f7589cd1444587ef3')
        self.assertEqual(packet['projectId'], 'content-preparation-a957a9e3291f0d90')
        self.assertEqual(packet['sourceManifestSha256'], '95234c571679ec632935d94819bfd19b0b80e8560a996e65406b51f7a1a714a3')
        self.assertEqual(packet['sourceManifestSha256'], semantic_digest(source_manifest()))
        self.assertEqual(packet['scope'], {'minAge': 6, 'maxAge': 12, 'intendedLanguage': 'en',
                                           'referenceVariety': 'pending', 'use': 'engineering_preparation_only'})
        self.assertEqual(packet['controlledWorkflow'], {
            'handoff': 'docs/model/slp-handoff.md',
            'worksheet': 'docs/consumer-assessment/proposed-engineering-pack.md',
            'annotationPreparation': 'docs/consumer-assessment/annotation-data-preparation.md',
            'meaning': 'Links to existing controlled records; no new approval authority',
        })
        prompt_fields = {'id', 'word', 'sourceWord', 'lexicalGroup', 'targetPhone', 'position',
                         'modelInventorySupported', 'modelTargetId', 'status', 'issues', 'variants', 'requirements'}
        variant_fields = {'id', 'phones', 'allTargetIndexes', 'selectedPositionIndexes'}
        self.assertTrue(all(set(prompt) == prompt_fields for prompt in packet['prompts']))
        self.assertTrue(all(set(variant) == variant_fields for prompt in packet['prompts'] for variant in prompt['variants']))
        required = ['reference_variety', 'acceptable_variants', 'occurrence_rule', 'age_readiness', 'adult_support',
                    'reference_provenance', 'reference_rights', 'reference_scope', 'illustration_meaning_rights',
                    'cue_instruction_safety', 'controlled_professional_record']
        self.assertTrue(all(prompt['requirements'] == required for prompt in packet['prompts']))
        self.assertIsNone(validate_packet(packet))
        self.assertEqual(semantic_digest(compile_packet(raw)), semantic_digest(packet))
        self.assertIsNone(validate_packet(strict_json(json.dumps(packet))))
        packet['prompts'][0]['variants'][0]['phones'][0] = 'invented-edit'
        self.assertEqual(compile_packet(raw)['prompts'][0]['variants'][0]['phones'][0], 'R')
        metadata = load_pack()
        metadata['prompts'].clear()
        self.assertEqual(len(load_pack()['prompts']), 15)

    def test_frozen_source_manifest_stays_pending_with_no_enrollment_or_reference_verification(self):
        manifest = source_manifest()
        self.assertEqual(manifest['mode'], 'preparation')
        self.assertEqual(manifest['participants'], [])
        self.assertEqual(manifest['attempts'], [])
        self.assertEqual(manifest['policy']['allowedAges'], [6, 12])
        self.assertTrue(all(prompt['engineeringStatus'] == 'pending' for prompt in manifest['prompts']))
        controlled = manifest['task']['controlledReviewRecord']
        self.assertIs(controlled['currentSourceVerificationEstablished'], False)
        self.assertIs(controlled['qualifiedReviewEstablished'], False)
        self.assertEqual(len(controlled['catalogSourceHashes']), 3)
        manifest['task']['controlledReviewRecord']['qualifiedReviewEstablished'] = True
        self.assertIs(source_manifest()['task']['controlledReviewRecord']['qualifiedReviewEstablished'], False)

    def test_byte_pin_drift_is_rejected_before_interpreting_any_supplied_pack(self):
        raw = load_pack_bytes()
        changed = json.loads(raw)
        changed['prompts'][0]['learnerFindingEligible'] = True
        cases = (raw + b' ', raw[:-1], raw.replace(b'rabbit', b'RABBIT'), json.dumps(changed).encode(),
                 b'{invalid JSON', raw.decode(), bytearray(raw), None)
        for case_number, drift in enumerate(cases):
            with self.subTest(case=case_number):
                with self.assertRaises(PacketError) as error:
                    compile_packet(drift)
                self.assertEqual(error.exception.code, 'source_pack_drift')
                self.assertEqual(str(error.exception), 'source_pack_drift')

    def test_packet_validation_rejects_boolean_integer_and_approval_spoofs(self):
        original = compile_packet(load_pack_bytes())
        changes = [
            lambda p: p.update(schemaVersion=True),
            lambda p: p['scope'].update(minAge=6.0),
            lambda p: p['counts'].update(prompts=15.0),
            lambda p: p['claimLimits'].update(qualifiedApprovalEstablished=0),
            lambda p: p['claimLimits'].update(qualifiedApprovalEstablished=True),
            lambda p: p['prompts'][0].update(modelInventorySupported=1),
            lambda p: p['prompts'][3].update(modelTargetId=False),
            lambda p: p['prompts'][1]['variants'][0].update(allTargetIndexes=[True]),
            lambda p: p['prompts'][1]['variants'][0].update(selectedPositionIndexes=[True]),
            lambda p: p['prompts'][5]['variants'][0].update(selectedPositionIndexes=[2]),
            lambda p: p['prompts'][0].update(status='approved'),
            lambda p: p['prompts'][0].update(requirements=[]),
            lambda p: p.update(extra='invented'),
            lambda p: p.update(sourcePackSha256='0' * 64),
            lambda p: p.update(sourceManifestSha256='0' * 64),
        ]
        for case_number, change in enumerate(changes):
            candidate = deepcopy(original)
            change(candidate)
            with self.subTest(case=case_number):
                with self.assertRaises(PacketError) as error:
                    validate_packet(candidate)
                self.assertEqual(error.exception.code, 'invalid_packet')
        for case_number, bad in enumerate((None, [], {1: 'bad'}, {'bad': float('nan')}, {'bad': '\ud800'})):
            with self.subTest(non_json=case_number):
                with self.assertRaises(PacketError) as error:
                    validate_packet(bad)
                self.assertEqual(error.exception.code, 'invalid_packet')


class StrictJsonTests(unittest.TestCase):
    def test_valid_utf8_json_and_surrogate_pairs_preserve_finite_typed_values(self):
        expected = {'text': 'café😀', 'values': [0, -1, 0.5, True, False, None]}
        self.assertEqual(strict_json(json.dumps(expected, ensure_ascii=False).encode()), expected)
        self.assertEqual(strict_json(json.dumps(expected, ensure_ascii=True)), expected)
        self.assertIs(strict_json('true'), True)
        self.assertEqual(type(strict_json('1')), int)

    def test_duplicate_nonfinite_huge_numeric_and_malformed_values_have_only_safe_code(self):
        cases = ('{"field":1,"field":2}', '{"outer":{"x":1,"x":1}}', 'NaN', 'Infinity', '-Infinity',
                 '1e9999', '9' * 5000, '1.' + '0' * 5000, '{"x":}', '{}{}', '', '"\\ud800"',
                 '"\\udfff"', '{"\\ud800":1}', '\ud800', b'\xff', '{"x":1}'.encode('utf-16'),
                 True, {}, bytearray(b'{}'))
        for case_number, raw in enumerate(cases):
            with self.subTest(case=case_number):
                with self.assertRaises(PacketError) as error:
                    strict_json(raw)
                self.assertEqual(error.exception.code, 'invalid_json')
                self.assertEqual(error.exception.args, ('invalid_json',))

    def test_oversized_bytes_unicode_and_deep_recursion_are_rejected(self):
        cases = (b' ' * (8 * 1024 * 1024 + 1), 'é' * (4 * 1024 * 1024 + 1),
                 '[' * 5000 + '0' + ']' * 5000)
        for case_number, raw in enumerate(cases):
            with self.subTest(case=case_number):
                with self.assertRaises(PacketError) as error:
                    strict_json(raw)
                self.assertEqual(error.exception.code, 'invalid_json')


if __name__ == '__main__':
    unittest.main()
