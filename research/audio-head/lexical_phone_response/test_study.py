"""Synthetic canonical geometry, cached support and declaration guards."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from lexical_phone_response import study as s


def fixture():
    clips = [dict(id='c',speakerId='child',age=8,canonicalPhoneCount=5,
                  canonicalPhones=['W','AH1','W','P','ZH'],words=[dict(phones=['W','AH1']),dict(phones=['W','P','ZH'])]),
             dict(id='a',speakerId='adult',age=20,canonicalPhoneCount=1,canonicalPhones=['W'],words=[dict(phones=['W'])])]
    rows=[]
    for clip,ci,wi,pi,votes,legacy in [('c',0,0,0,[1,0,4],0),('c',2,1,0,[0,2,3],None),('c',3,1,1,[0,0,5],2),('a',0,0,0,[2,1,2],3)]:
        parent=clips[0 if clip=='c' else 1]
        rows.append(dict(id=f'{clip}:{ci}',clipId=clip,speakerId=parent['speakerId'],age=parent['age'],canonicalIndex=ci,
                         canonicalRaw=parent['canonicalPhones'][ci],wordIndex=wi,phoneIndex=pi,
                         targetPhone=parent['canonicalPhones'][ci],raterCounts=votes,legacyRowIndex=legacy))
    return dict(clips=clips,rows=rows)


def saved(rows,indices):
    result={}
    for age in s.AGES:
        selected=[rows[i] for i in indices if age=='allAges' or (6 <= rows[i]['age'] <= 12 if age=='ages6to12' else rows[i]['age']>=13)]
        per={}
        for phone in s.analysis.PHONES:
            part=[r for r in selected if r['targetPhone']==phone]
            per[phone]=dict(positions=len(part),speakers=len({r['speakerId'] for r in part}),
                            raterVotes=[sum(r['raterCounts'][c] for r in part) for c in range(3)])
        result[age]=dict(positions=len(selected),speakers=len({r['speakerId'] for r in selected}),recordings=len({r['clipId'] for r in selected}),perPhone=per)
    return result


def lineage_fixture():
    cohort=fixture();data=dict(rowIndices=[0,2],folds=[0,1],groups=[1,2])
    corpus={o:dict(rowIndices=[i for i,r in enumerate(cohort['rows']) if o=='all' or (r['legacyRowIndex'] is not None)==(o=='original')]) for o in s.ORIGINS}
    jobs=[];models={}
    for regime in s.prior.REGIMES:
        cells=[]
        for fold in range(5):
            for word in range(5):
                for family in ('scalars','pca16-scalars'):
                    jobs.append(dict(regime=regime,speakerFold=fold,wordGroup=word,family=family,fitRows=[0,1],refitRows=[0,1,2,3]))
                parts={}
                for part,ids in [('innerFit',[0,1]),('outerFit',[0,1,2,3])]:
                    parts[part]=dict(retainedRows=ids,retainedByOrigin={o:dict(rowIndices=[i for i in ids if i in corpus[o]['rowIndices']]) for o in s.ORIGINS})
                cells.append(dict(speakerFold=fold,wordGroup=word,partitions=parts))
        models[regime]=dict(cells=cells)
    pins={k:k for k in ('cohort','inventoryReport','inventoryPlan','expandedHeadsPlan','responseParentReport','responseParentPlan')}
    files=dict(cohort=cohort,expandedHeadsPlan=dict(jobs=jobs),inventoryReport=dict(complete=True,plan='inventoryPlan',models=models,corpusByOrigin=corpus),
               responseParentReport=dict(complete=True,plan='responseParentPlan',sampling=dict(rowIndices=data['rowIndices'],rowFolds=data['folds'],rowWordGroups=data['groups'])))
    return dict(inputs=pins),files,data


class StudyTests(unittest.TestCase):
    def test_complete_canonical_repetition_across_words(self):
        cohort=fixture()
        self.assertEqual(s.multiplicities(cohort),[2,2,1,1])
        # Original W remains repeated because its added occurrence is in the complete recording.
        result=s.composition(cohort['rows'],[0,2,3],[2,2,1,1],saved(cohort['rows'],[0,2,3]))
        w=result['ages6to12']['perPhone']['W']
        self.assertEqual(w['occurrence']['single']['positions'],0)
        self.assertEqual(w['occurrence']['repeated']['positions'],1)
        self.assertEqual(w['ratingVoteFractions'],[.2,0.,.8])
        self.assertEqual(w['phoneMassFraction'],.5)
        self.assertEqual(result['ages13plus']['perPhone']['W']['occurrence']['single']['positions'],1)
        self.assertIsNone(result['allAges']['perPhone']['CH']['ratingVoteFractions'])

    def test_geometry_corruption_rejected(self):
        for kind in ('missing','duplicate','raw','index','word','speaker','age','sequence'):
            cohort=fixture()
            if kind=='missing':cohort['rows'].pop(1)
            elif kind=='duplicate':cohort['rows'].append(cohort['rows'][0])
            elif kind=='raw':cohort['rows'][0]['canonicalRaw']='P'
            elif kind=='index':cohort['rows'][0]['canonicalIndex']=True
            elif kind=='word':cohort['rows'][1]['wordIndex']=0
            elif kind=='speaker':cohort['rows'][0]['speakerId']='other'
            elif kind=='age':cohort['rows'][0]['age']=10
            else:cohort['clips'][0]['canonicalPhones'].pop()
            with self.subTest(kind=kind),self.assertRaises(ValueError):s.multiplicities(cohort)

    def test_cached_support_and_multiplicity_guards(self):
        rows=fixture()['rows'];ids=list(range(4));support=saved(rows,ids)
        for kind in ('positions','speakers','recordings','phone','votes'):
            bad=copy.deepcopy(support)
            if kind=='phone':bad['allAges']['perPhone'].pop('CH')
            elif kind=='votes':bad['allAges']['perPhone']['W']['raterVotes']=[0,0,15]
            else:bad['allAges'][kind]+=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):s.composition(rows,ids,[2,2,1,1],bad)
        for indices,multiple in [([0,0],[2,2,1,1]),([True],[2,2,1,1]),([4],[2,2,1,1]),(ids,[2,2,1]),(ids,[2,2,0,1]),(ids,[2,2,True,1])]:
            with self.assertRaises(ValueError):s.composition(rows,indices,multiple,support)
        empty=s.composition(rows,[],[2,2,1,1],saved(rows,[]))
        self.assertIsNone(empty['allAges']['perPhone']['W']['phoneMassFraction'])

    def test_metadata_lineage_before_analysis(self):
        plan,files,data=lineage_fixture()
        with patch.object(s.prior,'checked_inputs',return_value=data),patch.object(s,'read',side_effect=files.__getitem__),patch.object(s,'multiplicities',side_effect=AssertionError('No grouping')),patch.object(s.analysis,'analyze',side_effect=AssertionError('No analysis')):
            result=s.checked_inputs(plan)
            self.assertEqual(len(result[3]),50)
        for kind in ('parent','corpus','origin','family','missing','cell'):
            changed=copy.deepcopy(files)
            if kind=='parent':changed['responseParentReport']['sampling']['rowIndices']=[2,0]
            elif kind=='corpus':changed['inventoryReport']['corpusByOrigin']['added']['rowIndices']=[]
            elif kind=='origin':changed['inventoryReport']['models']['all-age']['cells'][0]['partitions']['innerFit']['retainedByOrigin']['original']['rowIndices']=[1]
            elif kind=='family':changed['expandedHeadsPlan']['jobs'][1]['fitRows']=[0]
            elif kind=='missing':changed['expandedHeadsPlan']['jobs'].pop()
            else:changed['inventoryReport']['models']['all-age']['cells'].reverse()
            with self.subTest(kind=kind),patch.object(s.prior,'checked_inputs',return_value=data),patch.object(s,'read',side_effect=changed.__getitem__),self.assertRaises(ValueError):s.checked_inputs(plan)

    def test_fresh_declaration_without_response_calculation(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder).resolve();out=base/'fresh'
            with patch.object(s,'BASE',base),patch.object(s,'inputs',return_value={}),patch.object(s,'checked_inputs') as checked,patch.object(s,'multiplicities',side_effect=AssertionError('No categories')),patch.object(s.analysis,'analyze',side_effect=AssertionError('No analysis')):
                pin=s.declare(out);self.assertEqual(checked.call_count,1)
                self.assertFalse(s.read(pin)['resamplingPerformed'])
                with self.assertRaises(ValueError):s.declare(out)
                with self.assertRaises(ValueError):s.declare(base.parent/'outside')
                with self.assertRaises(FileExistsError):s.write(out/'plan.json',{})
                (out/'plan.json').write_text('{}')
                with self.assertRaises(ValueError):s.read(pin)


if __name__=='__main__':unittest.main()
