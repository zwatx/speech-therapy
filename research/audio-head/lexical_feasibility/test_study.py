"""Whole-utterance lexical exclusion, empty support and full-crossing guards."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lexical_feasibility import study as s


class LexicalTests(unittest.TestCase):
    def fixture(self):
        rows, clips = [], []
        for speaker, age in enumerate([8, 9, 30, 10, 31]):
            for variant, text in [('short', 'FROBNICATE'), ('long', 'FROBNICATE NONTARGET FROBNICATE')]:
                clip = f'{speaker}-{variant}'
                clips.append(dict(id=clip, speakerId=str(speaker), age=age, text=text))
                for wi in ([0] if variant == 'short' else [0, 2]):
                    rows.append(dict(clipId=clip, speakerId=str(speaker), age=age, wordIndex=wi,
                                     targetWord='FROBNICATE', targetPhone='B', trainingEligible=True, raterCounts=[0, 0, 5]))
        folds = []
        for fold in range(5):
            ids = lambda speakers: [i for i, r in enumerate(rows) if int(r['speakerId']) in speakers]
            valid = {(fold+1)%5}
            fit = set(range(5)) - {fold} - valid
            folds.append(dict(fold=fold, innerFitRows=ids(fit), innerValidationRows=ids(valid),
                              outerFitRows=ids(fit|valid), outerHoldoutRows=ids({fold})))
        return dict(authorPartition='train', rows=rows, clips=clips), dict(authorPartition='train', folds=folds)

    def test_hash_contract_golden_groups_and_strict_canonical_tokens(self):
        self.assertEqual([s.word_group(w) for w in ['FROBNICATE', 'QUUX', 'ZYZZYVA', 'NONTARGET']], [2, 1, 4, 0])
        for value in ['', 'word', 'TWO WORDS', ' WORD', 3]:
            with self.subTest(value=value), self.assertRaises(ValueError): s.word_group(value)

    def test_non_target_token_excludes_entire_clip_and_every_occurrence(self):
        cohort, splits = self.fixture()
        result = s.calculate(cohort, splits)
        cell = next(c for c in result['models']['all-age']['cells'] if c['speakerFold']==0 and c['wordGroup']==0)
        rows = cohort['rows']
        for key in ['innerFit', 'innerValidation', 'selection', 'outerFit']:
            part = cell['partitions'][key]
            self.assertTrue(part['retainedRows'])
            self.assertTrue(all(rows[i]['clipId'].endswith('short') for i in part['retainedRows']))
            self.assertTrue(all(rows[i]['clipId'].endswith('long') for i in part['excludedRows']))
        self.assertEqual(result['blockedClips']['0']['0-long'], ['NONTARGET'])
        self.assertEqual(cell['partitions']['outer']['retainedRows'], [])

    def test_full_crossing_covers_each_outer_row_once_and_deduplicates_fit_unions(self):
        cohort, splits = self.fixture(); result=s.calculate(cohort,splits)
        for regime, model in result['models'].items():
            self.assertEqual(len(model['cells']),25)
            ids=[i for c in model['cells'] for i in c['partitions']['outer']['retainedRows']]
            self.assertEqual(sorted(ids),list(range(15)))
            union=model['retainedUnions']['innerFit']
            expected=[i for i,r in enumerate(cohort['rows']) if regime=='all-age' or r['age']<=12]
            self.assertEqual(union['rowIndices'],expected)
            self.assertEqual(union['support']['allAges']['speakers'],5 if regime=='all-age' else 3)

    def test_empty_and_absent_rare_classes_remain_explicit(self):
        cohort,splits=self.fixture(); result=s.calculate(cohort,splits)
        empty=next(c for c in result['models']['all-age']['cells'] if c['speakerFold']==0 and c['wordGroup']==2)
        for key in ['innerFit','innerValidation','selection','outerFit']:
            support=empty['partitions'][key]['retained']['allAges']
            self.assertEqual(support['positions'],0)
            self.assertEqual(len(support['perPhone']),23)
            self.assertEqual(support['missingPhones'],list(s.metrics.PHONES))
        outer=empty['partitions']['outer']['retained']['allAges']
        self.assertNotIn('B',outer['missingPhones'])
        self.assertIn('B',outer['missingEventVoteClasses']['rating0'])

    def test_child_only_fit_and_selection_remain_age_restricted(self):
        cohort,splits=self.fixture(); result=s.calculate(cohort,splits)
        for cell in result['models']['child-only']['cells']:
            for key in ['innerFit','selection','outerFit']:
                self.assertTrue(all(6<=cohort['rows'][i]['age']<=12 for i in cell['partitions'][key]['retainedRows']))
        adult_validation=next(c for c in result['models']['child-only']['cells'] if c['speakerFold']==1 and c['wordGroup']==1)
        self.assertTrue(adult_validation['partitions']['innerValidation']['retainedRows'])
        self.assertFalse(adult_validation['partitions']['selection']['retainedRows'])

    def test_bad_word_index_and_transcript_mismatch_fail(self):
        for key,value in [('wordIndex',True),('wordIndex',99),('targetWord','DIFFERENT')]:
            cohort,splits=self.fixture();cohort['rows'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'word identity'):
                s.checked_metadata(cohort,splits)

    def test_overlapping_speakers_missing_outer_rows_and_bad_votes_fail(self):
        cohort,splits=self.fixture();splits['folds'][0]['innerFitRows'].append(splits['folds'][0]['outerHoldoutRows'][0])
        with self.assertRaisesRegex(ValueError,'speakers overlap'):s.checked_metadata(cohort,splits)
        cohort,splits=self.fixture();splits['folds'][0]['outerHoldoutRows'].pop()
        with self.assertRaisesRegex(ValueError,'cover eligible rows once'):s.checked_metadata(cohort,splits)
        cohort,splits=self.fixture();cohort['rows'][0]['raterCounts']=[0,0,4]
        with self.assertRaisesRegex(ValueError,'five-vote'):s.checked_metadata(cohort,splits)

    def test_declaration_does_not_open_metadata_or_calculate_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'outputs').mkdir()
            with patch.object(s,'HERE',root),patch.object(s,'plan_value',return_value={'pins':'test'}), \
                 patch.object(s,'calculate',side_effect=AssertionError('premature calculation')), \
                 patch.object(s,'checked_metadata',side_effect=AssertionError('premature read')):
                pin=s.declare(root/'outputs/new')
            self.assertTrue(Path(pin['path']).exists())


if __name__=='__main__':unittest.main()
