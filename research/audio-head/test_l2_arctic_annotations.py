"""Synthetic schema cases; these are not extra observed human annotations."""
import unittest
import l2_arctic_annotations as subject


def grid(tiers=None, end=1):
    tiers = tiers or [('words', [(0,end,'word')]), ('phones', [(0,end,'R')])]
    lines=['File type = "ooTextFile"', 'Object class = "TextGrid"', 'xmin = 0', f'xmax = {end}',
           'tiers? <exists>', f'size = {len(tiers)}', 'item []:']
    for i,(name,intervals) in enumerate(tiers,1):
        lines += [f'item [{i}]:', 'class = "IntervalTier"', f'name = "{name}"', 'xmin = 0', f'xmax = {end}',
                  f'intervals: size = {len(intervals)}']
        for j,(start,stop,text) in enumerate(intervals,1):
            escaped=text.replace('"','""')
            lines += [f'intervals [{j}]:', f'xmin = {start}', f'xmax = {stop}', f'text = "{escaped}"']
    return ('\n'.join(lines)+'\n').encode()


class AnnotationTests(unittest.TestCase):
    def test_substitution_preserves_raw_stress_unknown_and_deviation(self):
        row=subject.interpret_label(' R , AH0* , s ')
        self.assertEqual(row['rawLabel'],' R , AH0* , s ')
        self.assertEqual(row['canonical']['phone'],'R')
        self.assertEqual(row['perceived'],dict(raw='AH0*',phone='AH',stress=0,uncertain=False,deviation=True))
        self.assertFalse(row['plainPerceivedPhoneKnown'])
        for token in ('err','err*'):
            row=subject.interpret_label(f'R,{token},s')
            self.assertIsNone(row['perceived']['phone']);self.assertTrue(row['perceived']['uncertain'])
            self.assertFalse(row['plainPerceivedPhoneKnown'])
        self.assertEqual(subject.interpret_label('R,R*,s')['event'],'substitution')

    def test_insertion_deletion_and_nonlexical_have_distinct_absence(self):
        addition=subject.interpret_label('sil,AH1,a')
        self.assertIsNone(addition['canonical']);self.assertEqual(addition['perceived']['phone'],'AH')
        deletion=subject.interpret_label('R,sil,d')
        self.assertIsNone(deletion['perceived']);self.assertEqual(deletion['canonical']['phone'],'R')
        self.assertFalse(deletion['plainPerceivedPhoneKnown'])
        for raw in ('sil','sp',''):
            row=subject.interpret_label(raw)
            self.assertEqual(row['event'],'nonlexical');self.assertIsNone(row['canonical']);self.assertIsNone(row['errorCode'])
        self.assertEqual(subject.interpret_label('sp')['nonlexicalKind'],'sp-unresolved')
        accepted=subject.interpret_label('EH1')
        self.assertEqual(accepted['canonical']['stress'],1);self.assertEqual(accepted['event'],'unchanged')

    def test_invalid_phone_contracts_reject_instead_of_relabeling(self):
        for raw in ('R1','R*','err','XYZ','AA3','R,S','R,S,x','R,S,s,extra','R,S,a','sil,R,s',
                    'sil,sil,d','R,R,d','R,sil,s','R,err1,s','R,S**,s','R*,S,s'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):subject.interpret_label(raw)

    def test_unicode_quote_escaping_and_auxiliary_tiers_are_retained(self):
        raw=grid([('words',[(0,1,'a "word"\nnext')]),('phones',[(0,1,'R,AH0,s')]),('IPA',[(0,1,'ɹ,ə,s')])])
        for data in (raw,b'\xef\xbb\xbf'+raw,raw.decode().encode('utf-16')):
            result=subject.parse_annotations(data)
            self.assertEqual(len(result['records']),1)
            self.assertEqual(result['grid']['tiers'][2]['intervals'][0]['rawLabel'],'ɹ,ə,s')
            self.assertEqual(result['records'][0]['wordOverlaps'][0]['rawWord'],'a "word"\nnext')
            self.assertTrue(result['manualProvenanceRequired'])
            self.assertTrue(all(result['records'][0][k] is False for k in ('trainingEligible','evaluationEligible','learnerFeedbackEligible')))

    def test_cross_word_phone_retains_all_overlaps_and_real_deletion_duration(self):
        result=subject.parse_annotations(grid([('words',[(0,.4,'one'),(.4,1,'two')]),('phones',[(0,1,'R,sil,d')])]))
        row=result['records'][0]
        self.assertEqual([r['wordIntervalIndex'] for r in row['wordOverlaps']],[1,2])
        self.assertEqual(row['startText'],'0');self.assertEqual(row['endText'],'1')
        self.assertIsNone(row['perceived'])

    def test_interval_gaps_overlaps_zero_duration_and_bad_domains_fail(self):
        for intervals in ([(0,.5,'R'),(.6,1,'S')],[(0,.5,'R'),(.4,1,'S')],[(0,0,'R'),(0,1,'S')],
                          [(0,.5,'R')],[(0,2,'R')],[(.1,1,'R')],[(0,.5,'R'),(.50000000001,1,'S')]):
            with self.subTest(intervals=intervals),self.assertRaises(ValueError):
                subject.parse_annotations(grid([('words',[(0,1,'word')]),('phones',intervals)]))

    def test_duplicate_missing_unsupported_and_truncated_tiers_fail(self):
        raw=grid()
        variants=[raw+b'junk', raw.replace(b'name = "phones"',b'name = "words"'),
                  raw.replace(b'name = "phones"',b'name = "other"'),raw.replace(b'item [2]',b'item [3]'),
                  raw.replace(b'IntervalTier',b'TextTier'),raw.replace(b'size = 2',b'size = 3',1),
                  raw.replace(b'xmax = 1',b'xmax = nan',1),raw.replace(b'ooTextFile',b'ooTextFile short'),raw[:-12]]
        for data in variants:
            with self.subTest(data=data[:30]),self.assertRaises(ValueError):subject.parse_annotations(data)
        with self.assertRaises(ValueError):subject.parse_annotations(b'x'*(subject.MAX_BYTES+1))
        with self.assertRaises(ValueError):subject.parse_annotations(b'\xffinvalid')


if __name__=='__main__':unittest.main()
