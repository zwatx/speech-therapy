"""Generated v2 context-binding examples; no historical reviews are migrated."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from intended_validation import (ProtocolError, blank_bundle, build_report, make_protocol,
                                 make_protocol_v2, review_context_digest, validate_protocol)
from workbench.domain import semantic_digest
from test_report import S, sample, rehash


def generated_v2():
    _, bundle = sample()
    bundle['allocation'][0]['positivePromptId'] = 'n-middle-banana'
    bundle['attempts'][0].update(promptId='n-middle-banana', word='banana', occurrenceIndex=2)
    protocol = make_protocol_v2(S, S, semantic_digest(bundle['allocation']),
                                semantic_digest(bundle['participants']))
    bundle.update(schemaVersion=2, protocolSha256=semantic_digest(protocol))
    attempts = {row['id']: row for row in bundle['attempts']}
    for row in bundle['originalReviews']:
        row['protocolSha256'] = bundle['protocolSha256']
        row['reviewContextSha256'] = review_context_digest(protocol, attempts[row['attemptId']])
        rehash(row)
    return protocol, bundle


class ContextV2Tests(unittest.TestCase):
    def test_valid_v2_and_judgments_unchanged(self):
        _, old = sample()
        protocol, bundle = generated_v2()
        before = copy.deepcopy(bundle['originalReviews'])
        report = build_report(protocol, bundle)
        self.assertEqual(report['schemaVersion'], 2)
        self.assertEqual(bundle['originalReviews'], before)
        self.assertEqual([r['observations'] for r in before], [r['observations'] for r in old['originalReviews']])
        self.assertFalse(report['engineeringCriteriaMet'])
        self.assertTrue(all(value is False for value in report['claimLimits'].values()))

    def test_other_valid_banana_occurrence_cannot_reuse_originals(self):
        protocol, bundle = generated_v2()
        bundle['attempts'][0]['occurrenceIndex'] = 4
        with self.assertRaisesRegex(ProtocolError, 'review_context_binding_mismatch'):
            build_report(protocol, bundle)

    def test_missing_stale_or_unhashed_context_fails(self):
        for change in ('missing', 'stale', 'unhashed'):
            protocol, bundle = generated_v2()
            review = bundle['originalReviews'][0]
            if change == 'missing':
                del review['reviewContextSha256']
            else:
                review['reviewContextSha256'] = S
            if change != 'unhashed':
                rehash(review)
            with self.subTest(change=change), self.assertRaises(ProtocolError):
                build_report(protocol, bundle)

    def test_context_change_and_rehashed_originals_invalidates_adjudication(self):
        protocol, bundle = generated_v2()
        originals = bundle['originalReviews'][:2]
        decision = dict(id='decision', attemptId='positive', adjudicatorId='adjudicator',
                        originalASha256=originals[0]['originalSha256'],
                        originalBSha256=originals[1]['originalSha256'],
                        observations=copy.deepcopy(originals[0]['observations']), reason='generated-example')
        decision['decisionSha256'] = semantic_digest(decision)
        bundle['adjudications'] = [decision]
        build_report(protocol, bundle)
        bundle['attempts'][0]['occurrenceIndex'] = 4
        for row in originals:
            row['reviewContextSha256'] = review_context_digest(protocol, bundle['attempts'][0])
            rehash(row)
        with self.assertRaisesRegex(ProtocolError, 'adjudication_binding_mismatch'):
            build_report(protocol, bundle)

    def test_digest_has_exact_blinded_context_and_no_prediction_or_identity(self):
        protocol, bundle = generated_v2()
        attempt = bundle['attempts'][0]
        expected = dict(protocolSha256=semantic_digest(protocol), attemptId=attempt['id'],
                        **{key: attempt[key] for key in ('recordingSha256', 'promptId', 'word',
                                                        'variantId', 'occurrenceIndex')})
        self.assertEqual(review_context_digest(protocol, attempt), semantic_digest(expected))
        changed = dict(attempt, participantId='another-person', admission='rejected',
                       prediction='different', primaryRole='challenge')
        self.assertEqual(review_context_digest(protocol, changed), semantic_digest(expected))
        for key, value in (('id', 'different'), ('recordingSha256', 'f' * 64),
                           ('promptId', 'other-prompt'), ('word', 'rabbit'),
                           ('variantId', 'variant-2'), ('occurrenceIndex', 4)):
            with self.subTest(key=key):
                self.assertNotEqual(review_context_digest(protocol, dict(attempt, **{key: value})), semantic_digest(expected))
        with self.assertRaises(ProtocolError):
            review_context_digest(make_protocol(S, S, S, S), attempt)
        with self.assertRaises(ProtocolError):
            review_context_digest(protocol, {'id': 'incomplete'})

    def test_strict_protocol_and_bundle_versions(self):
        for version in (True, False, 0, 3, 1.0, '2', None):
            protocol, bundle = generated_v2()
            protocol['schemaVersion'] = version
            with self.subTest(protocolVersion=version), self.assertRaises(ProtocolError):
                validate_protocol(protocol)
            protocol, bundle = generated_v2()
            bundle['schemaVersion'] = version
            with self.subTest(bundleVersion=version), self.assertRaises(ProtocolError):
                build_report(protocol, bundle)
        for builder, wrong in ((make_protocol, 2), (make_protocol_v2, 1)):
            protocol = builder(S, S, semantic_digest([]), semantic_digest([]))
            bundle = blank_bundle(protocol)
            bundle['schemaVersion'] = wrong
            with self.assertRaises(ProtocolError):
                build_report(protocol, bundle)
        protocol, bundle = generated_v2()
        protocol['reviewContextBinding']['fields'].append('prediction')
        with self.assertRaises(ProtocolError):
            validate_protocol(protocol)

    def test_legacy_generated_fixture_digests_remain_frozen(self):
        # Captured from the existing generated sample before v2 implementation.
        protocol, bundle = sample()
        self.assertEqual(semantic_digest(protocol), '97c86c71dc11f648cf770f57b2a5260f5f299e6d10fa23d9c2812c27ac98d3e2')
        self.assertEqual(semantic_digest(bundle), '8fcf4299124c438f5b066cbf09a04928d69e1e8d872d751ba65528059b56f6e0')
        self.assertEqual(semantic_digest(build_report(protocol, bundle)), 'acd7a2d1314e3c7b587c4e0f042a714ad7bda828fa52ea01306ce15c71f14ffb')

    def test_cli_prepares_v2_privately_and_exclusively(self):
        with tempfile.TemporaryDirectory() as temporary:
            os.chmod(temporary, 0o700)
            root = Path(temporary).resolve() / 'prepared'
            command = [sys.executable, '-B', '-W', 'error', '-m', 'intended_validation',
                       'prepare', str(root), S, S]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            for name in ('protocol.json', 'observations.json', 'preparation-report.json'):
                path = root / name
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(path.read_text())['schemaVersion'], 2)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)


if __name__ == '__main__':
    unittest.main()
