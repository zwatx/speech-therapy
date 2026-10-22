"""Canonical annotation lineage and punctuation projection regression checks."""
import copy
import unittest
from unittest.mock import patch

from lexical_canonical import study as s
from lexical_feasibility import test_study as fixtures


class CanonicalTests(unittest.TestCase):
    def fixture(self):
        cohort, splits = fixtures.LexicalTests().fixture()
        annotation = dict(authorPartition='train', authorTestObjectsDecoded=False, clips=[], rows=[])
        for clip in cohort['clips']:
            words=[dict(text=w,phones=['AH0'] if w=='NONTARGET' else ['B']) for w in clip['text'].split()]
            phones=[p for w in words for p in w['phones']]
            clip.update(audioSha256='hash-'+clip['id'],canonicalPhoneCount=len(phones))
            clip['text']+='.'
            annotation['clips'].append(dict(clip,words=words,canonicalPhones=phones))
        for i,row in enumerate(cohort['rows']):
            row.update(id='original-'+str(i),phoneIndex=0)
            annotation['rows'].append(dict(row,id='occurrence-'+str(i),legacyRowId=row['id'],legacyRowIndex=i))
        return cohort,annotation,splits

    def test_annotation_words_replace_punctuation_without_changing_original(self):
        cohort,annotation,_=self.fixture();before=copy.deepcopy(cohort)
        with patch.object(s.prior,'word_group',side_effect=AssertionError('no grouping yet')):
            projected,receipt=s.canonical_view(cohort,annotation)
        self.assertEqual(cohort,before)
        self.assertEqual(receipt['legacyRowsChecked'],15)
        self.assertEqual(len(receipt['rawTranscriptDifferences']),10)
        self.assertEqual(receipt['canonicalTokens']['0-long'],['FROBNICATE','NONTARGET','FROBNICATE'])
        self.assertEqual(projected['clips'][0]['text'],'FROBNICATE')
        self.assertEqual(receipt['rawTranscriptDifferences'][0]['rawTokens'],['FROBNICATE.'])

    def test_projection_retains_full_exclusion_and_outer_coverage(self):
        cohort,annotation,splits=self.fixture();projected,_=s.canonical_view(cohort,annotation)
        result=s.prior.calculate(projected,splits)
        self.assertEqual(result['blockedClips']['0']['0-long'],['NONTARGET'])
        self.assertTrue(all(m['outerCoverageExactlyOnce'] for m in result['models'].values()))

    def test_unrelated_extra_annotation_clip_is_not_added(self):
        cohort,annotation,_=self.fixture()
        extra=copy.deepcopy(annotation['clips'][0]);extra['id']='extra';annotation['clips'].append(extra)
        projected,receipt=s.canonical_view(cohort,annotation)
        self.assertEqual(len(projected['clips']),10)
        self.assertEqual(receipt['ignoredAdditionalClips'],['extra'])

    def test_wrong_clip_identity_missing_clip_and_bad_word_structure_fail(self):
        for key,value in [('audioSha256','wrong'),('speakerId','wrong'),('age',99),('text','DIFFERENT')]:
            cohort,annotation,_=self.fixture();annotation['clips'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'clip identity'):
                s.canonical_view(cohort,annotation)
        cohort,annotation,_=self.fixture();annotation['clips'].pop(0)
        with self.assertRaisesRegex(ValueError,'Missing canonical clip'):s.canonical_view(cohort,annotation)
        cohort,annotation,_=self.fixture();annotation['clips'][0]['words'][0]['text']='TWO WORDS'
        with self.assertRaisesRegex(ValueError,'word token'):s.canonical_view(cohort,annotation)

    def test_canonical_phone_and_legacy_vote_or_identity_mismatch_fail(self):
        cohort,annotation,_=self.fixture();annotation['clips'][0]['canonicalPhones']=['P']
        with self.assertRaisesRegex(ValueError,'phone coverage'):s.canonical_view(cohort,annotation)
        for key,value in [('raterCounts',[0,1,4]),('wordIndex',1),('legacyRowId','wrong')]:
            cohort,annotation,_=self.fixture();annotation['rows'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'legacy row'):
                s.canonical_view(cohort,annotation)
        cohort,annotation,_=self.fixture();annotation['rows'].pop()
        with self.assertRaisesRegex(ValueError,'legacy coverage'):s.canonical_view(cohort,annotation)

    def test_duplicate_legacy_index_and_test_partition_rejected(self):
        cohort,annotation,_=self.fixture();annotation['rows'].append(copy.deepcopy(annotation['rows'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate or invalid legacy'):s.canonical_view(cohort,annotation)
        cohort,annotation,_=self.fixture();annotation['authorPartition']='test'
        with self.assertRaisesRegex(ValueError,'Train-only'):s.canonical_view(cohort,annotation)


if __name__=='__main__':unittest.main()
