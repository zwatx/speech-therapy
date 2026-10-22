import unittest
from unittest.mock import patch
import multiphone_environment_extension as subject


class ExtensionTests(unittest.TestCase):
    def rows(self):
        return [dict(filename=f'2-{i:02d}{j}-{letter}-0.wav', src_file=f'{i}-{j}',
                     category=category, fold='4', esc10='True')
                for i, category in enumerate(subject.CATEGORIES)
                for j in range(6) for letter in ('A', 'B')]

    def test_sorted_selection_excludes_prior_and_duplicate_sources(self):
        rows = self.rows()
        excluded = {'0-0', '3-0'}
        extra = [dict(rows[0], filename='000.wav', esc10='False'),
                 dict(rows[0], filename='001.wav', fold='1')]
        selected = subject.select_rows(list(reversed(rows))+extra, excluded)
        self.assertEqual(len(selected), 24)
        self.assertEqual(len({r['src_file'] for r in selected}), 24)
        self.assertFalse(excluded & {r['src_file'] for r in selected})
        self.assertEqual([r['src_file'] for r in selected[:4]], ['0-1','0-2','0-3','0-4'])
        self.assertTrue(all('-A-' in r['filename'] for r in selected))

    def test_sources_are_distinct_across_categories(self):
        rows = self.rows()
        for row in rows:
            if row['category'] == subject.CATEGORIES[1] and row['src_file'] == '1-0':
                row['src_file'] = '0-0'
        selected = subject.select_rows(rows, set())
        self.assertEqual([r['src_file'] for r in selected[4:8]], ['1-1','1-2','1-3','1-4'])

    def test_insufficient_sources_duplicate_filenames_and_unsafe_name_fail(self):
        for rows, excluded in [(self.rows(), {f'0-{j}' for j in range(3)}),
                               (self.rows()+[self.rows()[0]], set()), ([], set())]:
            with self.assertRaises(ValueError): subject.select_rows(rows, excluded)
        rows = self.rows(); rows[0]['filename'] = '../000.wav'
        with self.assertRaises(ValueError): subject.select_rows(rows, set())

    def test_attribution_requires_exactly_one_source(self):
        row = {'filename': '2-123-A-0.wav'}
        line = '- [2-123-A.ogg]: contributor and license'
        self.assertEqual(subject.attribution(row, line), line)
        for text in ('', line+'\n'+line):
            with self.assertRaises(ValueError): subject.attribution(row, text)

    def test_changed_selection_fails_before_download(self):
        with patch.object(subject.raw, 'read_bound_json', side_effect=ValueError('SHA differs')):
            with patch.object(subject.original, 'download') as download:
                with self.assertRaises(ValueError): subject.acquire('bad-sha')
                download.assert_not_called()


if __name__ == '__main__': unittest.main()
