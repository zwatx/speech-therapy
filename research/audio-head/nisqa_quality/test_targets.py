"""Synthetic phased rating access; no corpus rows or quality previews."""
import csv
import io
import unittest
from unittest.mock import patch

from nisqa_ingest import routing
from nisqa_quality import targets as t, selection as s
from nisqa_quality.test_selection import fixture

HEADER=['db','filepath_deg',*routing.TARGETS,'extra']


def chosen():
    rows,pilot=fixture()
    return s.select_study(s.build_components(rows,pilot))['selected']


def stream(rows):
    result=io.StringIO(newline=''); writer=csv.writer(result)
    writer.writerow(HEADER); writer.writerows(rows); result.seek(0); return result


class TargetTests(unittest.TestCase):
    def test_fit_selection_skips_confirmation_eval_unselected_and_short_rows(self):
        selected=chosen()
        data=[]
        for row in selected:
            data.append([routing.TRAIN,row['path'],*(['SECRET,\nNaN']*5 if row['partition']=='confirmation' else ['3']*5),'unused'])
        data += [['NISQA_VAL_LIVE','NISQA_VAL_LIVE/deg/x.wav',object()],
                 [routing.TRAIN,routing.PREFIX+'other.wav']]
        result=t.parse_partition_targets(stream(list(reversed(data))),selected,'fit-selection')
        self.assertEqual(len(result['rows']),160); self.assertTrue(result['completeTargets'])
        self.assertFalse(result['confirmationTargetsAccessed']); self.assertNotIn('SECRET',repr(result))
        self.assertEqual(result['selectedPaths'],[r['path'] for r in selected if r['partition']!='confirmation'])

    def test_other_phase_targets_never_indexed_and_confirmation_helper_exact40(self):
        selected=chosen()
        class Guard(list):
            def __getitem__(self,key):
                if key not in (0,1): raise AssertionError('Forbidden target indexed')
                return super().__getitem__(key)
        data=[Guard([routing.TRAIN,r['path'],object()]) if r['partition']!='confirmation'
              else [routing.TRAIN,r['path'],*['3']*5,'x'] for r in selected]
        with patch.object(routing,'_reader',return_value=(iter(data),HEADER,{k:i for i,k in enumerate(HEADER)})):
            result=t.parse_partition_targets(None,selected,'confirmation')
        self.assertEqual(len(result['rows']),40); self.assertTrue(result['completeTargets'])

    def test_missing_and_invalid_preserved_with_generic_errors(self):
        selected=chosen(); data=[[routing.TRAIN,r['path'],*['3']*5,'x'] for r in selected]
        fit=next(i for i,r in enumerate(selected) if r['partition']=='fit')
        data[fit][2:7]=['','NaN','SECRET',' 3','5.00001']
        result=t.parse_partition_targets(stream(data),selected,'fit-selection')
        self.assertFalse(result['completeTargets']); self.assertNotIn('SECRET',repr(result))
        self.assertEqual(result['missingCounts']['mos'],1); self.assertEqual(result['missingCounts']['noi'],1)
        self.assertEqual(sum(result['invalidCounts'].values()),3)
        row=next(r for r in result['rows'] if r['path']==selected[fit]['path'])
        self.assertEqual(row['declaredMissing'],{'mos':'','noi':'NaN'})
        self.assertEqual(row['quality'],dict.fromkeys(routing.TARGETS))

    def test_strict_numeric_and_exact_missing_vocabulary(self):
        selected=chosen()
        for token in ['nan','NA','NaN ','+inf','1e999','٣','1_0','3\n','.','0.99','5.01']:
            data=[[routing.TRAIN,r['path'],*['3']*5,'x'] for r in selected]
            data[0][2]=token
            result=t.parse_partition_targets(stream(data),selected,'fit-selection')
            self.assertEqual(result['invalidCounts']['mos'],1)
        data=[[routing.TRAIN,r['path'],*['+1','5.','.3e1','30E-1','4.2'],'x'] for r in selected]
        result=t.parse_partition_targets(stream(data),selected,'fit-selection')
        self.assertTrue(result['completeTargets'])

    def test_missing_duplicate_width_and_quota_fail(self):
        selected=chosen(); data=[[routing.TRAIN,r['path'],*['3']*5,'x'] for r in selected]
        for bad in [data[1:],data+[data[0]], [data[0][:-1],*data[1:]]]:
            with self.assertRaises(ValueError): t.parse_partition_targets(stream(bad),selected,'fit-selection')
        bad=[dict(r) for r in selected]; bad[0]['partition']='confirmation'
        body=dict(bad[0]); body.pop('identitySha256'); bad[0]['identitySha256']=s.identity_hash(body)
        with self.assertRaises(ValueError): t.parse_partition_targets(stream(data),bad,'fit-selection')
        bad=[dict(r) for r in selected]; bad[0]['readerGroup']='DNS-reader_999999'
        body=dict(bad[0]); body.pop('identitySha256'); bad[0]['identitySha256']=s.identity_hash(body)
        with self.assertRaises(ValueError): t.validate_selected(bad)
        with self.assertRaises(ValueError): t.parse_partition_targets(stream(data),selected,'unknown')


if __name__=='__main__': unittest.main()
