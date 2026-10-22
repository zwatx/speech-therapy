import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from workbench.demo import make_manifest
from workbench.store import Store, verify_export
from workbench.domain import ValidationError
from workbench.demo import example_answer, make_predictions

class StoreLifecycleTests(unittest.TestCase):
    def test_created_project_reopens_without_losing_original_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'project'
            manifest = make_manifest()
            store = Store.create(path, manifest)
            manifest['title'] = 'caller mutation'
            self.assertEqual(store.manifest['title'], 'Assessment validation workbench')
            self.assertEqual(Store.open(path).manifest, store.manifest)

    def test_original_review_is_immutable_and_survives_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'project'
            store = Store.create(path, make_manifest())
            item = store.snapshot('reviewer-a')['items'][0]
            answer = example_answer('attempt-01', 'reviewer-a')
            store.submit_review('reviewer-a', item['itemId'], answer)
            answer['target'] = 'omitted'
            reopened = Store.open(path)
            self.assertEqual(reopened.snapshot('reviewer-a')['items'][0]['review']['target'], 'expected')
            with self.assertRaises(ValidationError):
                reopened.submit_review('reviewer-a', item['itemId'], answer)

    def test_seals_require_complete_originals_and_adjudication_preserves_them(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store.create(Path(directory) / 'project', make_manifest())
            with self.assertRaises(ValidationError):
                store.seal_reviews('reviewer-a')
            for role in ('reviewer-a', 'reviewer-b'):
                for attempt, item in zip(store.manifest['attempts'], store.snapshot(role)['items']):
                    store.submit_review(role, item['itemId'], example_answer(attempt['id'], role))
                store.seal_reviews(role)
            item = next(row for row in store.snapshot('adjudicator')['items'] if row['attemptId'] == 'attempt-10')
            pins = [item['reviewA']['sha256'], item['reviewB']['sha256']]
            store.adjudicate('attempt-10', {'target': 'altered', 'notes': 'Invented explicit resolution.', 'reviewedOriginals': pins})
            item = next(row for row in Store.open(store.path).snapshot('adjudicator')['items'] if row['attemptId'] == 'attempt-10')
            self.assertEqual([item['reviewA']['answer']['target'], item['reviewB']['answer']['target']], ['expected', 'altered'])
            self.assertEqual(item['adjudication']['answer']['target'], 'altered')
            with self.assertRaises(ValidationError):
                store.submit_review('reviewer-a', store.snapshot('reviewer-a')['items'][0]['itemId'], example_answer('attempt-01', 'reviewer-a'))

    def test_content_revisions_preserve_initial_prompt_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store.create(Path(directory) / 'project', make_manifest())
            before = store.manifest
            store.record_content_review('rabbit', {'decision': 'accepted', 'reviewerId': 'operator', 'notes': 'Invented content review.', 'reference': None})
            store.record_content_review('rabbit', {'decision': 'revise', 'reviewerId': 'operator', 'notes': 'Invented current restriction.', 'reference': None})
            self.assertEqual(Store.open(store.path).manifest, before)
            self.assertEqual([record['record']['decision'] for record in store.export_bundle()['aggregate']['contentReviews']], ['accepted', 'revise'])

    def test_prediction_lock_cannot_be_replaced_and_withdrawal_preserves_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store.create(Path(directory) / 'project', make_manifest())
            source = store.manifest
            package = make_predictions(source)
            store.save_prediction_lock(package['payload'], package['expectedSha256'])
            with self.assertRaises(ValidationError):
                store.save_prediction_lock(package['payload'], package['expectedSha256'])
            store.withdraw('person-a', 'Invented withdrawal.')
            self.assertFalse(store.snapshot('reviewer-a')['items'][0]['recordingAvailable'])
            self.assertEqual(Store.open(store.path).manifest, source)
            bundle = store.export_bundle()
            self.assertEqual(bundle['aggregate']['predictionLock']['sha256'], package['expectedSha256'])
            self.assertEqual(bundle['report']['denominators']['attempts'], 11)

    def test_truncated_or_modified_history_fails_closed(self):
        for corruption in ('truncated', 'modified'):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'project'
                Store.create(path, make_manifest())
                journal = path / 'events.jsonl'
                content = journal.read_bytes()
                journal.write_bytes(content[:-1] if corruption == 'truncated' else content.replace(b'Assessment validation', b'Assessment fraudulent'))
                with self.assertRaises(ValidationError):
                    Store.open(path)

    def test_concurrent_review_submissions_save_one_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'project'
            store = Store.create(path, make_manifest())
            item = store.snapshot('reviewer-a')['items'][0]['itemId']
            def submit(target):
                answer = example_answer('attempt-01', 'reviewer-a')
                answer['target'] = target
                try:
                    return Store.open(path).submit_review('reviewer-a', item, answer)
                except ValidationError:
                    return 'refused'
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(submit, ['expected', 'altered']))
            self.assertEqual(results.count('refused'), 1)
            self.assertEqual(Store.open(path).revision, 1)
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            self.assertEqual((path / 'events.jsonl').stat().st_mode & 0o777, 0o600)

    def test_export_replay_detects_a_forged_report_even_with_recomputed_outer_digest(self):
        from workbench.domain import semantic_digest
        with tempfile.TemporaryDirectory() as directory:
            store = Store.create(Path(directory) / 'project', make_manifest())
            bundle = store.export_bundle()
            self.assertTrue(verify_export(bundle)['verified'])
            bundle['report']['denominators']['attempts'] = 99
            bundle['sha256'] = semantic_digest({key: value for key, value in bundle.items() if key != 'sha256'})
            with self.assertRaises(ValidationError):
                verify_export(bundle)

    def test_reviewer_seal_state_is_own_and_denied_recording_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store.create(Path(directory) / 'project', make_manifest())
            self.assertFalse(store.snapshot('reviewer-a')['sealed'])
            for attempt, item in zip(store.manifest['attempts'], store.snapshot('reviewer-a')['items']):
                store.submit_review('reviewer-a', item['itemId'], example_answer(attempt['id'], 'reviewer-a'))
            store.seal_reviews('reviewer-a')
            self.assertTrue(Store.open(store.path).snapshot('reviewer-a')['sealed'])
            self.assertFalse(store.snapshot('reviewer-b')['sealed'])
            denied = next(a for a in store.snapshot()['attempts'] if a['id'] == 'attempt-04')
            self.assertFalse(denied['recordingAvailable'])

if __name__ == '__main__':
    unittest.main()
