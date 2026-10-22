import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import multiphone_practice_coverage as study


def cohort():
    targets=[c for _,_,c in study.MAPPING]
    rows=[]; clips=[]
    for i,(word,phone,age,speaker,votes) in enumerate([
        ('BALL','B',6,'s1',[1,1,3]),('ball','B',12,'s1',[0,0,5]),
        ('BALL','B',13,'s2',[0,1,4]),('BALLS','B',7,'s3',[1,0,4]),
        ('BALL','L',8,'s4',[2,0,3]),('TREASURE','ZH',8,'s5',[0,2,3]),
        ('YOYO','Y',8,'s6',[0,0,5]),('YO-YO','Y',8,'s7',[0,0,5])]):
        clip_id=f'c{i}';target_id=targets.index(phone)
        clips.append({'id':clip_id,'age':age,'speakerId':speaker})
        rows.append({'id':clip_id+':'+phone,'clipId':clip_id,'clipIndex':i,'age':age,
                     'speakerId':speaker,'wordIndex':0,'phoneIndex':0,'targetWord':word,
                     'targetPhone':phone,'targetId':target_id,'raterCounts':votes,
                     'trainingEligible':phone!='ZH'})
    return {'authorPartition':'train','authorTestObjectsDecoded':False,'authorTestInferencePerformed':False,
            'targetPhones':targets,'eligibleTargetIds':list(range(23)),'rows':rows,'clips':clips,
            'labelSummary':{'rawRows':len(rows)}}


def prompt(word='ball',phone='B'):
    return {'promptId':phone+'-beginning-'+word,'word':word,'normalizedWord':study.normalize_word(word),
            'targetPhone':phone,'position':'beginning'}


class CoverageTests(unittest.TestCase):
    def test_normalization_has_no_spelling_equivalences(self):
        self.assertEqual(study.normalize_word(' \tYO-YO\r\n'),'yo-yo')
        for other in ('yoyo','yo yo','yo–yo','yo-yo!','yo-yos','yó-yo'):
            self.assertNotEqual(study.normalize_word(other),'yo-yo')
        self.assertEqual(study.normalize_word('Ä'),'Ä')

    def test_exact_phone_and_word_distinct_counts_and_votes(self):
        row=study.coverage([prompt()],cohort())[0]
        self.assertEqual(row['allAges'],{'positions':3,'clips':3,'speakers':2,'raterCounts':[1,2,12]})
        self.assertEqual(row['ages6to12'],{'positions':2,'clips':2,'speakers':1,'raterCounts':[1,1,8]})
        self.assertEqual(row['matchedRowIndices'],[0,1,2])
        self.assertEqual(row['matchedChildRowIndices'],[0,1])

    def test_unmatched_and_unsupported_rows_preserved(self):
        missing,zh=study.coverage([prompt('boat'),prompt('treasure','ZH')],cohort())
        self.assertEqual(missing['allAges']['positions'],0)
        self.assertEqual(missing['allAges']['raterCounts'],[0,0,0])
        self.assertTrue(missing['modelTargetSupported'])
        self.assertEqual(zh['allAges']['positions'],1)
        self.assertFalse(zh['modelTargetSupported'])

    def test_duplicate_position_and_invalid_votes_rejected(self):
        for mutation in ('duplicate','fractional','binding'):
            data=cohort()
            if mutation=='duplicate':data['rows'].append(copy.deepcopy(data['rows'][0]))
            if mutation=='fractional':data['rows'][0]['raterCounts']=[.2,.8,4]
            if mutation=='binding':data['rows'][0]['age']=8
            with self.assertRaises(ValueError):study.coverage([prompt()],data)

    def test_child_boundary_and_hyphen_are_exact(self):
        data=cohort(); data['rows'][0]['age']=5;data['clips'][0]['age']=5
        result=study.coverage([prompt(),prompt('yo-yo','Y')],data)
        self.assertEqual(result[0]['ages6to12']['positions'],1)
        self.assertEqual(result[1]['matchedRowIndices'],[7])

    def test_actual_swift_and_worksheet_inventory_only(self):
        prompts=study.parse_swift(study.SWIFT.read_text())
        self.assertEqual(len(prompts),72)
        study.validate_worksheet(study.WORKSHEET.read_text(),prompts,study.digest(study.SWIFT))
        self.assertNotEqual([p['promptId'] for p in prompts if p['word']=='ring'][0],
                            [p['promptId'] for p in prompts if p['word']=='ring'][1])

    def test_parser_fails_closed_for_expressions_extra_content_and_id_change(self):
        original=study.SWIFT.read_text()
        for altered in (original.replace('("ball",','(variable,'),
                        original.replace('"b", "b", "B sound",','"b", "b", "B sound", OTHER,'),
                        original.replace('position.rawValue','position.label')):
            with self.assertRaises(ValueError):study.parse_swift(altered)

    def test_worksheet_mismatch_and_false_approval_rejected(self):
        prompts=study.parse_swift(study.SWIFT.read_text()); text=study.WORKSHEET.read_text()
        for bad in (text.replace('b-beginning-ball','b-beginning-balls'),
                    text.replace('| Pending |','| Accepted |',1),text.replace('Source SHA-256','Old source')):
            with self.assertRaises(ValueError):study.validate_worksheet(bad,prompts,study.digest(study.SWIFT))

    def temporary_plan(self, directory):
        cohort_path=Path(directory)/'cohort.json';cohort_path.write_text(json.dumps(cohort()))
        return cohort_path

    def test_plan_precedes_counts_pins_inputs_and_publication_is_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            cohort_path=self.temporary_plan(directory)
            with patch.object(study,'COHORT',cohort_path),patch.object(study,'COHORT_SHA',study.digest(cohort_path)):
                declaration=study.prepare(Path(directory)/'out')
                plan=Path(declaration['planPath'])
                self.assertFalse((plan.parent/'report.json').exists())
                result=study.run(plan,declaration['planSha256'])
                report=json.loads(Path(result['reportPath']).read_text())
                self.assertEqual(len(report['rows']),72)
                self.assertTrue(all(report[k] is False for k in study.FLAGS))
                self.assertEqual(report['coverageCsv']['sha256'],study.digest(report['coverageCsv']['path']))
                with self.assertRaises(ValueError):study.run(plan,declaration['planSha256'])

    def test_changed_cohort_and_late_input_mutation_cannot_publish(self):
        for late in (False,True):
            with self.subTest(late=late),tempfile.TemporaryDirectory() as directory:
                cohort_path=self.temporary_plan(directory)
                with patch.object(study,'COHORT',cohort_path),patch.object(study,'COHORT_SHA',study.digest(cohort_path)):
                    declaration=study.prepare(Path(directory)/'out');plan=Path(declaration['planPath'])
                    original=study.coverage
                    def mutated(*args):
                        answer=original(*args);cohort_path.write_text(cohort_path.read_text()+' ');return answer
                    if not late:cohort_path.write_text(cohort_path.read_text()+' ')
                    with patch.object(study,'coverage',mutated if late else original),self.assertRaises(ValueError):
                        study.run(plan,declaration['planSha256'])
                    self.assertFalse((plan.parent/'report.json').exists())

    def test_plan_mutation_after_captured_read_cannot_adopt_new_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            cohort_path=self.temporary_plan(directory)
            with patch.object(study,'COHORT',cohort_path),patch.object(study,'COHORT_SHA',study.digest(cohort_path)):
                declaration=study.prepare(Path(directory)/'out');plan=Path(declaration['planPath'])
                read_bytes=Path.read_bytes; changed=False
                def mutate_after_read(path):
                    nonlocal changed
                    value=read_bytes(path)
                    if path==plan and not changed:
                        changed=True;path.write_bytes(value+b' ')
                    return value
                with patch.object(Path,'read_bytes',mutate_after_read),self.assertRaisesRegex(ValueError,'Changed input: plan'):
                    study.run(plan,declaration['planSha256'])
                self.assertFalse((plan.parent/'report.json').exists())


if __name__=='__main__':
    unittest.main()
