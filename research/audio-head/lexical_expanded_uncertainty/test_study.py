"""Synthetic identity, declaration and stable-array guards; no corpus I/O."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from lexical_expanded_uncertainty import study as s


def fixture():
    original = [dict(trainingEligible=False)]
    rows = []
    for i in range(14837):
        child = i < 5654
        speaker = str(i % 52) if child else 'adult'+str(i % 73)
        r = dict(id=f'original-{i}', trainingEligible=True, clipId=f'clip-{i}', speakerId=speaker,
                 age=8 if child else 20, targetPhone=s.analysis.PHONES[i % 23], targetWord='WORD',
                 wordIndex=0, phoneIndex=0, raterCounts=[1,1,3])
        original.append(r)
        rows.append(dict(r, id=f'expanded-{i}', legacyRowId=r['id'], legacyRowIndex=i+1))
    eligible = list(range(1,14838))
    folds = [(i % 52 if i < 5654 else i % 73) % 5 for i in range(14837)]
    groups = [i % 5 for i in range(14837)]
    cells = [dict(speakerFold=f,wordGroup=w,rowIndices=[i for i,g,h in zip(eligible,folds,groups) if (g,h)==(f,w)])
             for f in range(5) for w in range(5)]
    view = dict(rowIndices=eligible,rowFolds=folds,rowWordGroups=groups,probabilities=[[.2,.2,.6]]*14837,
                logProbabilities=np.log(np.tile([.2,.2,.6],(14837,1))).tolist(),cells=cells,
                speakerFolds=[dict(speakerFold=f,rowIndices=[i for i,g in zip(eligible,folds) if g==f]) for f in range(5)])
    parent = dict(jobs=[dict(family='scalars',regime='all-age',speakerFold=c['speakerFold'],wordGroup=c['wordGroup'],
                            outerRows=[i-1 for i in c['rowIndices']]) for c in cells])
    pins = {k:k for k in ('expandedHeadsPlan','expandedHeadsReport','originalCohort','cohort')}
    data = dict(expandedHeadsPlan=parent,originalCohort=dict(rows=original),cohort=dict(rows=rows))
    comparisons = {r:dict(primary={f:dict(childDelta={k:0. for k in s.ENDPOINTS}) for f in s.CONTRASTS[:3]},
                         secondary=dict(mixtureVsCorrectedMixture=dict(childDelta={k:0. for k in s.ENDPOINTS}))) for r in s.REGIMES}
    data['expandedHeadsReport'] = dict(complete=True,plan='expandedHeadsPlan',models={r:{f:{'original':view} for f in s.CONTRASTS[:3]} for r in s.REGIMES},comparisons=comparisons,**s.FLAGS)
    for name in ('scalar','compact','mixture','corrected'):
        pins[name+'ReferencePlan']=name+'ReferencePlan';pins[name+'ReferenceReport']=name+'ReferenceReport'
        data[name+'ReferenceReport']=dict(complete=True,plan=name+'ReferencePlan',models={r:{'scalars':view} if name=='scalar' else view for r in s.REGIMES})
    return dict(inputs=pins),data,view


class StudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.fixture=fixture()

    def test_complete_original_child_pairing_and_index_gap(self):
        plan,data,_=self.fixture
        with patch.object(s,'read',side_effect=data.__getitem__),patch.object(s.analysis,'analyze',side_effect=AssertionError('No endpoints')),patch.object(s.core,'speaker_weights',side_effect=AssertionError('No resampling')):
            result=s.checked_inputs(plan)
        self.assertEqual(len(result['comparisons']),8)
        self.assertEqual(result['rowIndices'],list(range(1,5655)))
        self.assertEqual(len(set(r['speakerId'] for r in result['rows'])),52)
        self.assertEqual(len(set(r['targetPhone'] for r in result['rows'])),23)

    def test_bad_original_join_and_reference_lineage_rejected(self):
        plan,data,_=self.fixture
        for kind in ('label','duplicate','lineage'):
            changed=copy.deepcopy(data)
            if kind=='label':changed['cohort']['rows'][0]['raterCounts']=[0,0,5]
            elif kind=='duplicate':changed['cohort']['rows'][1]['legacyRowIndex']=1
            else:changed['correctedReferenceReport']['plan']='wrong'
            with patch.object(s,'read',side_effect=changed.__getitem__),self.assertRaises(ValueError):s.checked_inputs(plan)

    def test_full_view_identity_cells_and_stable_arrays(self):
        _,_,view=self.fixture
        s.checked_view(view,view['rowIndices'],view['rowFolds'],view['rowWordGroups'])
        for kind in ('order','fold','word','cell','missingfold','probability','log'):
            changed=copy.deepcopy(view)
            if kind=='order':changed['rowIndices'][0:2]=[2,1]
            elif kind=='fold':changed['rowFolds'][0]=4
            elif kind=='word':changed['rowWordGroups'][0]=4
            elif kind=='cell':changed['cells'][0]['rowIndices'].pop()
            elif kind=='missingfold':changed['speakerFolds'].pop()
            elif kind=='probability':changed['probabilities'][0]=[0.,0.,0.]
            else:changed['logProbabilities'][0]=[-1.,-1.,-1.]
            with self.assertRaises(ValueError):s.checked_view(changed,view['rowIndices'],view['rowFolds'],view['rowWordGroups'])

    def test_all_eight_comparisons_share_draws_and_observed_folds_checked(self):
        zero={k:0. for k in s.ENDPOINTS}
        source=dict(childDelta=zero,speakerFoldChildDeltas=[dict(NLL=0.) for _ in range(5)])
        pairs={r+'/'+c:dict(candidate={},reference={},sourceComparison=source) for r in s.REGIMES for c in s.CONTRASTS}
        data=dict(rows=[dict(speakerId='child')],folds=[0],groups=[0],rowIndices=[1],comparisons=pairs)
        draws=dict(speakerIds=['child'],speakerFolds=[0],weights=np.ones((2000,1),dtype=np.int64))
        result=dict(observed=dict(candidate=zero,reference=zero),influence=dict(speakerFolds={str(i):dict(NLLDelta=0.,additiveNLLContribution=0.) for i in range(5)}))
        with patch.object(s,'checked_inputs',return_value=data),patch.object(s.core,'speaker_weights',return_value=draws) as sampling,patch.object(s.analysis,'analyze',side_effect=lambda *args:copy.deepcopy(result)) as analyze,patch.object(s,'guard'):
            report=s.calculate(dict(inputs={}),{'path':'synthetic','sha256':'synthetic'})
            self.assertEqual(len(report['comparisons']),8)
            self.assertEqual(sampling.call_count,1)
            self.assertEqual(sampling.call_args.args[2:],(2000,20260927))
            self.assertTrue(all(call.args[-1] is draws for call in analyze.call_args_list))
            result['influence']['speakerFolds']['0']['NLLDelta']=.1
            with self.assertRaisesRegex(ValueError,'Observed fold NLL'):s.calculate(dict(inputs={}),{})

    def test_hash_changes_and_exclusive_write(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'input.json';s.write(p,{'ok':True});pin=s.binding(p)
            self.assertEqual(s.read(pin),{'ok':True})
            with self.assertRaises(FileExistsError):s.write(p,{})
            p.write_text('{}')
            with self.assertRaises(ValueError):s.read(pin)

    def test_declaration_checks_inputs_but_does_not_sample(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder).resolve();out=base/'fresh';observed=[]
            with patch.object(s,'BASE',base),patch.object(s,'inputs',return_value={}),patch.object(s,'checked_inputs',side_effect=lambda p:observed.append(p)),patch.object(s.analysis,'analyze',side_effect=AssertionError('No analysis')),patch.object(s.core,'speaker_weights',side_effect=AssertionError('No sampling')):
                pin=s.declare(out)
                self.assertEqual(len(observed),1)
                self.assertFalse(json.loads(Path(pin['path']).read_text())['resamplingPerformed'])
                with self.assertRaises(ValueError):s.declare(out)
                with self.assertRaises(ValueError):s.declare(base.parent/'outside-study')

    def test_changed_declaration_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'plan.json';s.write(path,{'wrong':True});pin=s.binding(path)
            with patch.object(s,'inputs',return_value={}),self.assertRaises(ValueError):s.load_plan(path,pin['sha256'])


if __name__=='__main__':unittest.main()
