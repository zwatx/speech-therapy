import io
import json
import unittest

from nisqa_ingest.lineage_inventory import FIELDS, extract


class LineageTests(unittest.TestCase):
    def fixture(self, rows):
        header = ['db', 'filepath_deg', *FIELDS, 'mos', 'noi', 'col', 'dis', 'loud', 'votes']
        import csv
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(header)
        for db, path in rows:
            writer.writerow([db, path, *(['opaque, metadata\nstring'] * len(FIELDS)),
                *(['HELDOUT_TARGET_SENTINEL'] * 6)])
        stream.seek(0)
        return stream

    def test_training_only_opaque_join_never_emits_or_decodes_targets(self):
        result = extract(self.fixture([('NISQA_VAL_LIVE', 'eval'),
            ('NISQA_TRAIN_LIVE', 'train')]), {'train'})
        self.assertEqual(len(result['training']), 1)
        self.assertNotIn('SENTINEL', json.dumps(result))
        self.assertFalse(result['numericTargetsAccessed'])
        self.assertFalse(result['readerSemanticsVerified'])

    def test_duplicate_missing_or_unexpected_training_identity_fails(self):
        for rows in ([('NISQA_TRAIN_LIVE', 'train')] * 2, [],
                     [('NISQA_TRAIN_LIVE', 'other')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                extract(self.fixture(rows), {'train'})


if __name__ == '__main__':
    unittest.main()
