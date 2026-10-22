import hashlib
import json
from pathlib import Path
import unittest

from workbench.content import prepare_content_manifest
from workbench.domain import ValidationError, validate_manifest


PUBLIC_PACK = Path(__file__).resolve().parents[3] / 'docs/consumer-assessment/proposed-engineering-pack.json'


class ContentPreparationTests(unittest.TestCase):
    def test_public_fifteen_prompt_snapshot_preserves_every_variant_and_target_occurrence(self):
        pack_bytes = PUBLIC_PACK.read_bytes()
        source = json.loads(pack_bytes)
        manifest = prepare_content_manifest(pack_bytes)
        self.assertEqual(validate_manifest(manifest), manifest)
        self.assertEqual(manifest['mode'], 'preparation')
        self.assertEqual(manifest['participants'], [])
        self.assertEqual(manifest['attempts'], [])
        self.assertEqual(manifest['policy']['allowedAges'], [6, 12])
        self.assertEqual(manifest['task']['definitionSource'], 'pending')
        self.assertEqual(len(manifest['prompts']), 15)
        self.assertEqual(sum(len(prompt['variants']) for prompt in manifest['prompts']), 17)
        self.assertEqual(sum(len(variant['occurrenceIndexes']) for prompt in manifest['prompts']
                             for variant in prompt['variants']), 23)
        output = {prompt['id']: prompt for prompt in manifest['prompts']}
        for prompt in source['prompts']:
            prepared = output[prompt['id']]
            self.assertEqual([variant['phones'] for variant in prepared['variants']], prompt['pronunciationVariants'])
            self.assertEqual([variant['occurrenceIndexes'] for variant in prepared['variants']], prompt['targetIndexesByVariant'])
            self.assertEqual(prepared['engineeringStatus'], 'pending')
            self.assertEqual(prepared['source'], {'kind': 'dictionary_snapshot', 'sha256': hashlib.sha256(pack_bytes).hexdigest()})
            self.assertIn(hashlib.sha256(pack_bytes).hexdigest(), prepared['version'])
        self.assertEqual(output['b-beginning-baby']['lexicalGroup'], output['b-middle-baby']['lexicalGroup'])
        self.assertEqual(output['y-beginning-yo-yo']['lexicalGroup'], 'yoyo')
        record = manifest['task']['controlledReviewRecord']
        self.assertEqual(record['catalogSourceHashes'], source['catalogSourceHashes'])
        self.assertFalse(record['currentSourceVerificationEstablished'])
        self.assertFalse(record['qualifiedReviewEstablished'])

    def test_header_and_pending_review_constraints_reject_approval_or_ratings_claims(self):
        changes = {
            'schema_boolean': lambda pack: pack.update({'schemaVersion': True}),
            'schema_unknown': lambda pack: pack.update({'schemaVersion': 2}),
            'approved_header': lambda pack: pack.update({'status': 'APPROVED'}),
            'extra_rating': lambda pack: pack['prompts'][0].update({'rating': 'expected'}),
            'approved_prompt': lambda pack: pack['prompts'][0].update({'reviewStatus': 'accepted'}),
            'learner_eligible': lambda pack: pack['prompts'][0].update({'learnerFindingEligible': True}),
            'integer_ineligible': lambda pack: pack['prompts'][0].update({'learnerFindingEligible': 0}),
            'missing_header': lambda pack: pack.pop('catalogSourceHashes'),
        }
        for name, change in changes.items():
            pack = json.loads(PUBLIC_PACK.read_bytes())
            change(pack)
            with self.subTest(name=name), self.assertRaises(ValidationError):
                prepare_content_manifest(json.dumps(pack).encode('utf-8'))

    def test_parser_rejects_duplicate_keys_nonfinite_numbers_non_utf8_and_non_bytes(self):
        source = json.loads(PUBLIC_PACK.read_bytes())
        source['prompts'][0]['modelTargetID'] = float('nan')
        duplicate = PUBLIC_PACK.read_bytes().replace(b'"schemaVersion" : 1', b'"schemaVersion": 0, "schemaVersion": 1')
        overflow = PUBLIC_PACK.read_bytes().replace(b'"modelTargetID" : 16', b'"modelTargetID" : 1e9999', 1)
        cases = (duplicate, json.dumps(source).encode('utf-8'), overflow,
                 b'\xff', b'{', PUBLIC_PACK.read_text())
        for value in cases:
            with self.subTest(kind=type(value).__name__, prefix=str(value)[:30]), self.assertRaises(ValidationError):
                prepare_content_manifest(value)

    def test_variant_counts_target_indexes_and_selected_position_metadata_must_reconcile(self):
        changes = {
            'variant_count': lambda pack: pack['prompts'][0].update({'variantCount': 1}),
            'boolean_count': lambda pack: pack['prompts'][1].update({'variantCount': True}),
            'missing_index_variant': lambda pack: pack['prompts'][0]['targetIndexesByVariant'].pop(),
            'extra_index_variant': lambda pack: pack['prompts'][0]['targetIndexesByVariant'].append([0]),
            'dropped_repeated_target': lambda pack: pack['prompts'][3]['targetIndexesByVariant'][0].pop(),
            'wrong_selected_position': lambda pack: pack['prompts'][3]['selectedPositionIndexesByVariant'][0].append(2),
            'boolean_selected_index': lambda pack: pack['prompts'][3]['selectedPositionIndexesByVariant'][0].__setitem__(0, False),
            'wrong_repeated_flag': lambda pack: pack['prompts'][3].update({'repeatedTargetInAnyVariant': False}),
            'wrong_multiple_flag': lambda pack: pack['prompts'][5].update({'multipleOccurrencesAtSelectedPosition': False}),
            'wrong_differ_flag': lambda pack: pack['prompts'][0].update({'selectedIndexesDifferAcrossVariants': True}),
            'boolean_model_id': lambda pack: pack['prompts'][3].update({'modelTargetID': False}),
            'unsupported_with_model_id': lambda pack: pack['prompts'][14].update({'modelTargetID': 3}),
            'invalid_upstream_hash': lambda pack: pack['catalogSourceHashes'][0].update({'sha256': 'not-a-hash'}),
        }
        for name, change in changes.items():
            pack = json.loads(PUBLIC_PACK.read_bytes())
            change(pack)
            with self.subTest(name=name), self.assertRaises(ValidationError):
                prepare_content_manifest(json.dumps(pack).encode('utf-8'))

    def test_source_pin_tracks_exact_pack_bytes_and_lexical_normalization_is_explicit(self):
        raw = PUBLIC_PACK.read_bytes()
        compact = json.dumps(json.loads(raw), separators=(',', ':')).encode('utf-8')
        original = prepare_content_manifest(raw)
        reformatted = prepare_content_manifest(compact)
        self.assertNotEqual(original['prompts'][0]['source']['sha256'], reformatted['prompts'][0]['source']['sha256'])
        self.assertNotEqual(original['task']['version'], reformatted['task']['version'])
        self.assertEqual(original['prompts'][0]['variants'], reformatted['prompts'][0]['variants'])
        pack = json.loads(raw)
        pack['prompts'][3]['sourceWord'] = '  BaBy  '
        normalized = prepare_content_manifest(json.dumps(pack).encode('utf-8'))
        prompts = {prompt['id']: prompt for prompt in normalized['prompts']}
        self.assertEqual(prompts['b-beginning-baby']['lexicalGroup'], 'baby')
        self.assertEqual(prompts['b-beginning-baby']['lexicalGroup'], prompts['b-middle-baby']['lexicalGroup'])
        self.assertEqual(prompts['b-beginning-baby']['word'], 'baby')
        self.assertEqual(normalized['task']['controlledReviewRecord']['lexicalGroupNormalization'], 'sourceWord.strip().casefold()')


if __name__ == '__main__':
    unittest.main()
