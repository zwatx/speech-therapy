"""Canonical group weights and fitting-only scope on synthetic metadata."""
import copy
import unittest
from lexical_unit_weights import weights as w


def cohort():
    clips=[dict(id='repeat',speakerId='s',age=8,words=[dict(phones=['B','AH1']),dict(phones=['B','P','ZH'])],canonicalPhones=['B','AH1','B','P','ZH'],canonicalPhoneCount=5),
           dict(id='single',speakerId='t',age=9,words=[dict(phones=['P'])],canonicalPhones=['P'],canonicalPhoneCount=1),
           dict(id='excluded',speakerId='z',age=10,words=[dict(phones=['W'])],canonicalPhones=['W'],canonicalPhoneCount=1)]
    rows=[]
    for ci,index,wi,pi in [(0,0,0,0),(0,2,1,0),(0,3,1,1),(1,0,0,0),(2,0,0,0)]:
        c=clips[ci];p=c['canonicalPhones'][index]
        rows.append(dict(clipId=c['id'],speakerId=c['speakerId'],age=c['age'],canonicalIndex=index,canonicalRaw=p,
                         wordIndex=wi,phoneIndex=pi,targetPhone=p))
    return dict(rows=rows,clips=clips)


class WeightTests(unittest.TestCase):
    def test_exact_rational_and_group_mass_with_unsupported_gaps(self):
        result=w.fit_weights(cohort(),[0,1,2,3])
        self.assertEqual(result['canonicalCounts'],[2,2,1,1])
        self.assertEqual(result['unitCount'],3)
        self.assertEqual(result['normalization'],4/3)
        self.assertEqual(result['weights'],[2/3,2/3,4/3,4/3])
        self.assertEqual(sum(result['weights']),4)
        self.assertEqual(result['weights'][0]+result['weights'][1],result['weights'][2])
        reordered=w.fit_weights(cohort(),[3,1,0,2])
        self.assertEqual(reordered['fitRows'],[3,1,0,2])
        self.assertEqual(reordered['weights'],[4/3,2/3,2/3,4/3])

    def test_all_single_and_fresh_refit_normalization(self):
        c=cohort();single=w.fit_weights(c,[3,4]);inner=w.fit_weights(c,[0,1,2]);refit=w.fit_weights(c,[0,1,2,3])
        self.assertEqual(single['weights'],[1.,1.])
        self.assertEqual(inner['weights'],[.75,.75,1.5])
        self.assertNotEqual(inner['normalization'],refit['normalization'])

    def test_no_rating_or_excluded_metadata_access(self):
        c=cohort();before=w.fit_weights(c,[0,1,2,3]);other=copy.deepcopy(c)
        # No labels exist in the fixture. Changing them cannot influence metadata weights.
        for r in other['rows']:r['raterCounts']='not accessed'
        other['rows'][4]={'clipId':'excluded','raterCounts':object()}
        other['clips'][2]={'id':'excluded','words':None}
        self.assertEqual(before,w.fit_weights(other,[0,1,2,3]))

    def test_incomplete_groups_and_partial_recordings_rejected(self):
        for indices in ([0,2,3],[0,1,3],[],[0,0],[True],[5],[1.0]):
            with self.subTest(indices=indices),self.assertRaises(ValueError):w.fit_weights(cohort(),indices)

    def test_geometry_corruption_rejected(self):
        for kind in ('duplicate','word','indexbool','raw','phone','speaker','age','sequence','clipid'):
            c=cohort()
            if kind=='duplicate':c['rows'][1]=dict(c['rows'][0])
            elif kind=='word':c['rows'][1]['wordIndex']=0
            elif kind=='indexbool':c['rows'][0]['canonicalIndex']=False
            elif kind=='raw':c['rows'][0]['canonicalRaw']='W'
            elif kind=='phone':c['rows'][0]['targetPhone']='P'
            elif kind=='speaker':c['rows'][0]['speakerId']='z'
            elif kind=='age':c['rows'][0]['age']=11
            elif kind=='sequence':c['clips'][0]['canonicalPhoneCount']=4
            else:c['clips'].append(c['clips'][0])
            with self.subTest(kind=kind),self.assertRaises(ValueError):w.fit_weights(c,[0,1,2,3])


if __name__=='__main__':unittest.main()
