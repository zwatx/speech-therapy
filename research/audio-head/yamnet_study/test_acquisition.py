import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yamnet_study import acquisition as a


class SelectionTest(unittest.TestCase):
    def rows(self):
        return [dict(filename=f'{category}-{i}.wav',category=category,fold='5',esc10='True',src_file=f'{category}-{i}')
                for category in a.CATEGORIES for i in range(6)]

    def test_fixed_order_exclusions_and_distinct_sources(self):
        rows=self.rows(); rows[1]['src_file']=rows[0]['src_file']
        chosen=a.select(list(reversed(rows)), {'dog-2'})
        self.assertEqual(len(chosen),24)
        self.assertEqual([r['filename'] for r in chosen[:4]], ['dog-0.wav','dog-3.wav','dog-4.wav','dog-5.wav'])
        self.assertEqual(len({r['src_file'] for r in chosen}),24)
        self.assertEqual([chosen[i*4]['category'] for i in range(6)], list(a.CATEGORIES))

    def test_reject_duplicate_or_inadequate_sources(self):
        rows=self.rows()
        with self.assertRaises(ValueError): a.select(rows+[copy.deepcopy(rows[0])],set())
        for r in rows[:3]:r['fold']='4'
        with self.assertRaises(ValueError): a.select(rows,set())


if __name__=='__main__':unittest.main()
