"""Synthetic-only blind component selection and closure tests."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from nisqa_ingest import source_code_selection as old
from nisqa_quality import selection as s


def raw(book, reader, capture='phone', index=1):
    ref=f'book_{book:05d}_chp_0001_reader_{reader:05d}_1_seg.wav'
    filename=ref[:-4]+f'_live_{capture.lower()}_{index}.wav'
    return dict(path='NISQA_TRAIN_LIVE/deg/'+filename, metadata=dict(
        con=str(index),file=str(index),con_description='Skype' if capture=='Skype' else 'VoIP-landline to mobile',
        filename_deg=filename,filename_ref=ref,source='DNS',lang='en',
        filepath_ref='NISQA_TRAIN_LIVE/ref/'+ref))


def prepare(values):
    return old.prepare_inventory(dict(training=values,columns=list(old.FIELDS),**old.INVENTORY_FLAGS))['eligible']


def pilot(rows):
    return [dict(row,identitySha256=s.identity_hash(row)) for row in rows if int(row['bookCode'])<20][:20]


def fixture():
    values=[raw(i,i) for i in range(20)]
    for i in range(20,240):
        conditions=('phone',) if i<30 else ('Skype',) if i<40 else ('phone','Skype')
        for condition in conditions:
            values.append(raw(i,i,condition))
            values.append(raw(i,i,condition,2))
        if i>=220:
            values.extend(raw(i,i+1000,c) for c in conditions)
    rows=prepare(values)
    return rows,pilot(rows)


class SelectionTests(unittest.TestCase):
    def test_full_graph_transitive_pilot_closure_before_exclusion(self):
        # Pilot reader0 connects book500; book500 connects reader501;
        # reader501 connects book502. The final row has no direct pilot code.
        values=[raw(i,i) for i in range(20)]
        values.extend([raw(500,0),raw(500,501),raw(502,501),raw(700,700)])
        rows=prepare(values); graph=s.build_components(rows,pilot(rows))
        self.assertEqual(graph['support']['excludedRows'],23)
        self.assertEqual(graph['support']['remainingRows'],1)
        excluded={r['path'] for r in graph['eligibilityExclusions']}
        self.assertIn(raw(502,501)['path'],excluded)
        connected=next(c for c in graph['components'] if raw(502,501)['path'] in c['paths'])
        self.assertEqual(connected['membership']['bookCode'],['00000','00500','00502'])
        self.assertEqual(connected['membership']['readerGroup'],['DNS-reader_00000','DNS-reader_00501'])

    def test_exact_reference_edge_and_component_id_canonical(self):
        rows,p=fixture(); rows=copy.deepcopy(rows)
        # Isolate reference-edge behavior with synthetic metadata-only graph
        # rows; real-parser validation is exercised in the other tests.
        a=next(r for r in rows if r['bookCode']=='00020')
        b=next(r for r in rows if r['bookCode']=='00021')
        a['sourceReferenceID']=b['sourceReferenceID']='opaque shared reference'
        with patch.object(s,'_validated_rows',return_value=rows):
            graph=s.build_components(rows,p)
        connected=next(c for c in graph['components'] if a['path'] in c['paths'])
        self.assertIn(b['path'],connected['paths'])
        expected=hashlib.sha256(json.dumps(connected['membership'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(connected['componentID'],expected)

    def test_quotas_hashes_full_partition_reservations_and_flags(self):
        rows,p=fixture(); graph=s.build_components(rows,p); result=s.select_study(graph)
        self.assertEqual(graph['support']['remainingComponents'],220)
        self.assertEqual(result['conditionCounts'],{'phone':100,'Skype':100})
        self.assertEqual(result['partitionCounts'],{'fit':120,'selection':40,'confirmation':40})
        self.assertEqual(len({r['componentID'] for r in result['selected']}),200)
        self.assertEqual(len({r['readerGroup'] for r in result['selected']}),200)
        selected_paths={r['path'] for r in result['selected']}
        self.assertEqual(selected_paths | {r['path'] for r in result['exclusions']},{r['path'] for r in rows})
        self.assertFalse(selected_paths & {r['path'] for r in result['exclusions']})
        for row in result['selected']:
            value=dict(row); saved=value.pop('identitySha256')
            self.assertEqual(saved,hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest())
            self.assertTrue(set(s.POLICY['edges']) <= set(row))
            self.assertFalse({'mos','noi','dis','col','loud','quality'} & set(row))
        for part in s.PARTITIONS:
            selected=[r for r in result['selected'] if r['partition']==part]
            self.assertEqual({c:sum(r['captureCondition']==c for r in selected) for c in s.CONDITIONS},s.POLICY['partitionQuotas'][part])
            reserved=result['partitions'][part]
            for row in selected:
                component=next(c for c in graph['components'] if c['componentID']==row['componentID'])
                self.assertTrue(set(component['paths']) <= set(reserved['reservedPaths']))
            for other in s.PARTITIONS:
                if other==part: continue
                theirs=result['partitions'][other]
                for field in s.POLICY['edges']:
                    self.assertFalse(set(reserved['membership'][field]) & set(theirs['membership'][field]))
        for flag,value in s.FLAGS.items(): self.assertIs(result[flag],value)
        self.assertEqual(json.loads(json.dumps(s.POLICY)),s.POLICY)

    def test_permutations_deterministic_and_exclusive_groups_used_first(self):
        rows,p=fixture(); graph=s.build_components(rows,p)
        shuffled=s.build_components(list(reversed(rows)),list(reversed(p)))
        self.assertEqual(graph,shuffled)
        first=s.select_study(graph); self.assertEqual(first,s.select_study(shuffled))
        books={r['bookCode'] for r in first['selected']}
        self.assertTrue({f'{i:05d}' for i in range(20,40)} <= books)
        for condition in s.CONDITIONS:
            selected=[r for r in first['selected'] if r['captureCondition']==condition]
            self.assertEqual([r['componentID'] for r in selected],sorted(
                [r['componentID'] for r in selected],key=lambda cid:(s.digest('partition',cid),cid)))

    def test_feasibility_insufficient_union_or_capture_support(self):
        for count,condition in [(199,None),(200,'phone')]:
            values=[raw(i,i) for i in range(20)]
            values.extend(raw(i,i,c) for i in range(20,20+count)
                          for c in ((condition,) if condition else ('phone','Skype')))
            rows=prepare(values); graph=s.build_components(rows,pilot(rows))
            with self.assertRaisesRegex(ValueError,'Insufficient'): s.select_study(graph)

    def test_undeclared_targets_paths_transforms_and_graph_tamper_rejected(self):
        rows,p=fixture()
        for kind in ('target','metadata','path','derived'):
            changed=copy.deepcopy(rows)
            if kind=='target': changed[0]['mos']='SECRET'
            elif kind=='metadata': changed[0]['publisherMetadata']['mos']='SECRET'
            elif kind=='path': changed[0]['path']='NISQA_TRAIN_LIVE/deg/../escape.wav'
            else: changed[0]['bookCode']='99999'
            with self.subTest(kind=kind),self.assertRaises(ValueError): s.build_components(changed,p)
        graph=s.build_components(rows,p); changed=copy.deepcopy(graph)
        changed['components'][0]['conditionSupport']['phone']+=1
        with self.assertRaises(ValueError): s.select_study(changed)
        changed=copy.deepcopy(p); changed[0]['identitySha256']='0'*64
        with self.assertRaises(ValueError): s.build_components(rows,changed)


if __name__=='__main__': unittest.main()
