"""Synthetic-only closure, salted selection and forty-row target boundaries."""
import copy
import csv
import hashlib
import io
import json
import unittest
from unittest.mock import patch

from nisqa_ingest import routing
from nisqa_quality import replication_support as r, selection as s
from nisqa_quality.test_selection import raw,prepare,pilot

HEADER=['db','filepath_deg',*routing.TARGETS,'extra']


def fixtures():
    values=[raw(i,i) for i in range(20)]
    values.extend([raw(500,0),raw(500,501),raw(502,501)])
    for i in range(20,320):
        for condition in s.CONDITIONS:
            for index in (1,2): values.append(raw(i,i,condition,index))
        if i>=300:
            values.extend([raw(i,i+1000),raw(i+1000,i+1000,'Skype')])
    rows=prepare(values); graph=s.build_components(rows,pilot(rows)); current=s.select_study(graph)['selected']
    return graph,current


def selected():
    graph,current=fixtures(); return r.select_replication(graph,current)['selected']


def stream(rows):
    value=io.StringIO(newline=''); writer=csv.writer(value)
    writer.writerow(HEADER); writer.writerows(rows); value.seek(0); return value


class ReplicationTests(unittest.TestCase):
    def test_full_closure_reservations_and_identity_only_selection(self):
        graph,current=fixtures(); value=r.select_replication(graph,current)
        self.assertEqual(value['selectedCount'],40); self.assertEqual(value['conditionCounts'],{'phone':20,'Skype':20})
        self.assertEqual(value['remainingSupport']['components'],100)
        self.assertEqual(value['remainingSupport']['bothConditionComponents'],100)
        self.assertEqual([row['captureCondition'] for row in value['selected']],['phone']*20+['Skype']*20)
        self.assertEqual(len({row['componentID'] for row in value['selected']}),40)
        reserved=value['reservations']
        for prior in ('pilot','currentStudy'):
            self.assertFalse(set(reserved[prior]['componentIDs'])&set(reserved['replication']['componentIDs']))
            for field in s.POLICY['edges']:
                self.assertFalse(set(reserved[prior]['membership'][field])&set(reserved['replication']['membership'][field]))
        self.assertIn(raw(502,501)['path'],reserved['pilot']['reservedPaths'])
        self.assertGreater(len(reserved['currentStudy']['reservedPaths']),200)
        chosen={row['path'] for row in value['selected']}
        excluded={row['path'] for row in value['exclusions']}
        self.assertFalse(chosen&excluded)
        self.assertEqual(chosen|excluded,{row['path'] for row in graph['eligibleRows']})
        for row in value['selected']:
            body=dict(row); sha=body.pop('identitySha256')
            self.assertEqual(sha,s.identity_hash(body))
            self.assertFalse({'mos','noi','dis','col','loud','duration','size','amplitude','quality'}&set(row))
            component=next(c for c in graph['components'] if c['componentID']==row['componentID'])
            self.assertTrue(set(component['paths'])<=set(reserved['replication']['reservedPaths']))
        for key,flag in r.FLAGS.items(): self.assertIs(value[key],flag)
        json.dumps(value,allow_nan=False)

    def test_hash_order_and_group_file_choices_are_stable_under_input_permutation(self):
        graph,current=fixtures(); actual=r.select_replication(graph,current)
        rebuilt=s.build_components(list(reversed(graph['eligibleRows'])),list(reversed(graph['pilotSelected'])))
        self.assertEqual(actual,r.select_replication(rebuilt,list(reversed(current))))
        blocked=set(graph['pilotClosure'])|{row['componentID'] for row in current}; used=set()
        for condition in s.CONDITIONS:
            expected=sorted((c for c in graph['components'] if c['componentID'] not in blocked|used and c['conditionSupport'][condition]),
                            key=lambda c:(r.digest('component',c['componentID']),c['componentID']))[:20]
            chosen=[row for row in actual['selected'] if row['captureCondition']==condition]
            self.assertEqual([c['componentID'] for c in expected],[row['componentID'] for row in chosen])
            for component,row in zip(expected,chosen):
                options=[v for v in component['rows'] if v['captureCondition']==condition]
                group=min({v['readerGroup'] for v in options},key=lambda g:(r.digest('group',g),g))
                file=min((v for v in options if v['readerGroup']==group),key=lambda v:(r.digest('file',v['path']),v['path']))
                self.assertEqual(row['path'],file['path'])
            used.update(c['componentID'] for c in expected)
        manual=hashlib.sha256((r.SALT+'\0component\0example').encode()).hexdigest()
        self.assertEqual(r.digest('component','example'),manual)

    def test_graph_current_identity_and_unsafe_fields_fail_closed(self):
        graph,current=fixtures()
        altered=copy.deepcopy(graph); altered['support']['remainingComponents']+=1
        with self.assertRaises(ValueError): r.select_replication(altered,current)
        altered=copy.deepcopy(graph); altered['eligibleRows'][0]['quality']=3
        with self.assertRaises(ValueError): r.select_replication(altered,current)
        altered=copy.deepcopy(current); altered[0]['componentID']='0'*64
        body=dict(altered[0]); body.pop('identitySha256'); altered[0]['identitySha256']=s.identity_hash(body)
        with self.assertRaises(ValueError): r.select_replication(graph,altered)
        values=selected()
        for field,value in [('readerGroup','DNS-reader_99999'),('path','NISQA_TRAIN_LIVE/deg/../evil.wav'),('partition','confirmation')]:
            altered=copy.deepcopy(values); altered[0][field]=value
            body=dict(altered[0]); body.pop('identitySha256'); altered[0]['identitySha256']=s.identity_hash(body)
            with self.assertRaises(ValueError): r.validate_selected40(altered)
        with self.assertRaises(ValueError): r.validate_selected40(list(reversed(values)))

    def test_insufficient_components_have_no_replacement(self):
        graph,current=fixtures()
        used={row['componentID'] for row in current}
        remaining=[c for c in graph['components'] if not c['excludedByPilot'] and c['componentID'] not in used]
        keep={c['componentID'] for c in remaining[:39]}|used|set(graph['pilotClosure'])
        rows=[row for c in graph['components'] if c['componentID'] in keep for row in c['rows']]
        smaller=s.build_components(rows,graph['pilotSelected'])
        with self.assertRaisesRegex(ValueError,'Insufficient'): r.select_replication(smaller,current)

    def test_other_targets_never_indexed_and_csv_quoted_values_skipped(self):
        values=selected()
        class Guard(list):
            def __getitem__(self,key):
                if key not in (0,1): raise AssertionError('Forbidden target indexed')
                return super().__getitem__(key)
        graph,current=fixtures()
        data=[Guard([routing.TRAIN,row['path'],object()]) for row in current]
        data.extend([Guard(['NISQA_VAL_LIVE','NISQA_VAL_LIVE/deg/eval.wav',object()]),
                     Guard([routing.TRAIN,routing.PREFIX+'unselected.wav'])])
        data.extend([routing.TRAIN,row['path'],*['3']*5,'unused'] for row in values)
        with patch.object(routing,'_reader',return_value=(iter(reversed(data)),HEADER,{k:i for i,k in enumerate(HEADER)})):
            result=r.parse_replication_targets(None,values)
        self.assertEqual(result['selectedPaths'],[row['path'] for row in values]); self.assertTrue(result['completeTargets'])
        csv_rows=[[routing.TRAIN,row['path'],*['3']*5,'unused'] for row in values]
        csv_rows.extend([[routing.TRAIN,current[0]['path'],*['SECRET,\nNaN']*5,'unused'],
                         ['NISQA_TEST_LIVE','NISQA_TEST_LIVE/deg/test.wav','SECRET']])
        result=r.parse_replication_targets(stream(csv_rows),values)
        self.assertNotIn('SECRET',repr(result)); self.assertEqual(len(result['rows']),40)

    def test_exact_missing_invalid_numeric_values_preserved_not_replaced(self):
        values=selected(); data=[[routing.TRAIN,row['path'],*['3']*5,'unused'] for row in values]
        data[0][2:7]=['','NaN','SECRET',' 3','1e999']
        result=r.parse_replication_targets(stream(data),values)
        self.assertFalse(result['completeTargets']); self.assertNotIn('SECRET',repr(result))
        self.assertEqual(sum(result['missingCounts'].values()),2); self.assertEqual(sum(result['invalidCounts'].values()),3)
        self.assertEqual(result['rows'][0]['quality'],dict.fromkeys(routing.TARGETS))
        self.assertEqual(result['rows'][0]['declaredMissing'],{'mos':'','noi':'NaN'})
        self.assertEqual(len(result['rows']),40)
        data[0][2:7]=['+1','5.','.3e1','30E-1','4.2']
        self.assertTrue(r.parse_replication_targets(stream(data),values)['completeTargets'])
        for token in ('nan','NA','NaN ','+inf','٣','1_0','3\n','0.9','5.1'):
            data[0][2]=token
            self.assertEqual(r.parse_replication_targets(stream(data),values)['invalidCounts']['mos'],1)

    def test_parse_coverage_and_join_failures_are_distinct_and_generic(self):
        values=selected(); data=[[routing.TRAIN,row['path'],*['3']*5,'unused'] for row in values]
        for rows,reason in ((data[:-1],'coverage'),(data+[data[0]],'coverage'),([data[0][:-1],*data[1:]],'parse'),
                            ([['NISQA_VAL_LIVE',data[0][1],'SECRET'],*data[1:]],'join')):
            with self.subTest(reason=reason),self.assertRaises(r.ReplicationTargetError) as caught:
                r.parse_replication_targets(stream(rows),values)
            self.assertEqual(caught.exception.reason,reason); self.assertNotIn('SECRET',str(caught.exception))
        bad=copy.deepcopy(values); bad[0]['identitySha256']='0'*64
        with self.assertRaises(r.ReplicationTargetError) as caught: r.parse_replication_targets(stream(data),bad)
        self.assertEqual(caught.exception.reason,'join')
        with self.assertRaises(r.ReplicationTargetError) as caught: r.parse_replication_targets(io.StringIO('broken'),values)
        self.assertEqual(caught.exception.reason,'parse')
        malformed=io.StringIO(','.join(HEADER)+'\n'+routing.TRAIN+','+values[0]['path']+',"SECRET_UNCLOSED\n')
        with self.assertRaises(r.ReplicationTargetError) as caught: r.parse_replication_targets(malformed,values)
        self.assertEqual(caught.exception.reason,'parse'); self.assertNotIn('SECRET',str(caught.exception))


if __name__=='__main__': unittest.main()
