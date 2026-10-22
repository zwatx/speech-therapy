"""Synthetic noise-feature scope, numerical layout and publication checks."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import multiphone_consistency_features as features
from test_multiphone_controls import synthetic_study


def metadata():
    cohort, splits = synthetic_study()
    original, manifest = {'rows': []}, {'clips': []}
    for index, clip in enumerate(cohort['clips']):
        clip.update(sampleCount=1600 + 320*index, audioPath='/original/'+clip['id'])
        selected=[]
        for i, row in enumerate(cohort['rows']):
            if row['clipIndex'] != index: continue
            row.update(wordIndex=0, phoneIndex=row['targetId'])
            record={'rowIndex':i,'rowId':row['id'],'canonicalIndex':row['targetId'],
                    **{k:row[k] for k in ('clipId','targetId','targetPhone','wordIndex','phoneIndex')}}
            original['rows'].append(record); selected.append(record)
        manifest['clips'].append({**clip,'clipIndex':index,'canonicalPhones':['B','P'],
            'mappedTokenIds':[4,5],'mappingAmbiguities':[],'targetRows':selected})
    fold=splits['folds'][0]
    indices=sorted(fold['innerFitRows']+fold['innerValidationRows'])
    recipe=features.read_json(features.RECIPE)
    recipe.update(expectedRows=len(indices),expectedClips=len({cohort['rows'][i]['clipId'] for i in indices}))
    return cohort,splits,original,manifest,recipe


class ConsistencyFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.cohort,self.splits,self.original,self.manifest,self.recipe=metadata()
        indices,clips,parity=features.select_subset(self.cohort,self.splits,self.original,self.manifest,self.recipe)
        self.plan={'rowIndices':indices,'clips':clips,'parityClips':parity,'recipe':self.recipe,'inputFiles':{}}

    def units(self):
        entries,noisy,ctc={}, {}, {'entries':{}}
        for clip in self.plan['clips']:
            audio={'id':clip['id'],'clipId':clip['id'],'audioPath':'/noisy/'+clip['id'],
                   'audioSha256':'noise-'+clip['id'],'sampleCount':clip['sampleCount']}
            rows=[{**r,'intervalFrames':[1,2],'estimatedPoolingWindowFrames':[0,4]} for r in clip['targets']]
            target=np.asarray([np.full(1024,r['rowIndex']) for r in rows],dtype=np.float32)
            scalars=np.asarray([np.full(13,r['rowIndex']+1) for r in rows],dtype=np.float32)
            c={'frames':4,'sha256':'ctc-'+clip['id']}
            entries[clip['id']]=features.save_unit(self.root/'units'/clip['id'],clip,audio,{'requestedSNRdB':20},
                                                 rows,target,scalars,c,'plan')
            noisy[clip['id']],ctc['entries'][clip['id']]=audio,c
        return entries,noisy,ctc

    def test_scope_exact_union_no_outer_rows_and_parity_only_fit(self):
        fold=self.splits['folds'][0]
        self.assertEqual(self.plan['rowIndices'],sorted(fold['innerFitRows']+fold['innerValidationRows']))
        self.assertFalse(set(self.plan['rowIndices'])&set(fold['outerHoldoutRows']))
        fit={self.cohort['rows'][i]['clipId'] for i in fold['innerFitRows']}
        self.assertTrue({c['clipId'] for c in self.plan['parityClips']}<=fit)
        reasons=[r for p in self.plan['parityClips'] for r in p['reasons']]
        self.assertEqual(set(reasons),{'all-age/first','all-age/longest','child-only/first','child-only/longest'})
        for row in self.cohort['rows']: row['raterCounts']=[5,0,0]
        again=features.select_subset(self.cohort,self.splits,self.original,self.manifest,self.recipe)
        self.assertEqual(again,(self.plan['rowIndices'],self.plan['clips'],self.plan['parityClips']))

    def test_altered_canonical_or_source_target_rejected(self):
        changed=deepcopy(self.original)
        changed['rows'][self.plan['rowIndices'][0]]['targetPhone']='R'
        with self.assertRaisesRegex(ValueError,'Target identity'):
            features.select_subset(self.cohort,self.splits,changed,self.manifest,self.recipe)
        changed=deepcopy(self.manifest)
        c=next(c for c in changed['clips'] if c['id']==self.plan['clips'][0]['id'])
        c['canonicalPhones']=['P','B']
        with self.assertRaisesRegex(ValueError,'Target identity'):
            features.select_subset(self.cohort,self.splits,self.original,changed,self.recipe)

    def test_real_pcm_noise_exactly_reuses_reviewed_transform_preserves_original(self):
        x=.2*np.sin(np.arange(3200)*.02)
        source=self.root/'original.wav';source.write_bytes(features.capture.pcm16_bytes(x)[0])
        before=source.read_bytes();sha=features.digest(source)
        clip={'id':'000000001','audioPath':str(source),'audioSha256':sha,'sampleCount':3200}
        entry,measured=features.write_noisy(clip,self.root/'noise.wav',20260926)
        expected,_,_=features.capture.transform(features.read_rating_pcm(source,sha).numpy(),'noise20db',sha,20260926)
        self.assertEqual(source.read_bytes(),before)
        self.assertEqual(Path(entry['audioPath']).read_bytes(),expected)
        self.assertAlmostEqual(measured['measuredSNRdBAfterPCM16'],20,places=2)
        with self.assertRaises(FileExistsError): features.write_noisy(clip,self.root/'noise.wav',20260926)

    def test_perclip_binding_and_global_ascending_matrix_order(self):
        entries,noisy,ctc=self.units();out=self.root/'assembled';out.mkdir()
        rows,descriptors,pins=features.assemble(self.plan,'plan',entries,noisy,ctc,out)
        self.assertEqual([r['rowIndex'] for r in rows],self.plan['rowIndices'])
        target=np.load(out/'target.npy');scalars=np.load(out/'scalars.npy')
        np.testing.assert_array_equal(target[:,0],self.plan['rowIndices'])
        np.testing.assert_array_equal(scalars[:,0],np.asarray(self.plan['rowIndices'])+1)
        self.assertEqual(descriptors['target']['shape'],[len(rows),1024])
        self.assertEqual(descriptors['scalars']['shape'],[len(rows),13])
        features.guard(pins)
        self.assertTrue(all('raterCounts' not in r for r in rows))

    def test_rehashed_row_swap_and_wrong_noise_identity_rejected(self):
        entries,noisy,ctc=self.units();clip=self.plan['clips'][0];entry=entries[clip['id']]
        metadata=features.read_json(Path(entry['entryPath']));metadata['rows'].reverse()
        features.atomic_json(Path(entry['entryPath']),metadata);entry['entrySha256']=features.digest(Path(entry['entryPath']))
        with self.assertRaisesRegex(ValueError,'row or partition'):
            features.checked_unit(entry,clip,'plan',ctc['entries'][clip['id']],noisy[clip['id']])
        metadata['rows'].reverse();metadata['noisyAudio']['audioSha256']='changed'
        features.atomic_json(Path(entry['entryPath']),metadata);entry['entrySha256']=features.digest(Path(entry['entryPath']))
        with self.assertRaisesRegex(ValueError,'source, row'):
            features.checked_unit(entry,clip,'plan',ctc['entries'][clip['id']],noisy[clip['id']])

    def test_matrix_corruption_before_digest_still_fails_exact_unit_audit(self):
        entries,noisy,ctc=self.units();out=self.root/'tampered';out.mkdir()
        real_save=np.save
        def wrong(stream,value,**kwargs):
            corrupt=value.copy();corrupt[0,0]+=100
            real_save(stream,corrupt,**kwargs)
        with patch.object(features.np,'save',side_effect=wrong),self.assertRaisesRegex(ValueError,'Assembled target order'):
            features.assemble(self.plan,'plan',entries,noisy,ctc,out)

    def test_parity_failure_prevents_any_noisy_waveform_or_complete_report(self):
        plan_path=self.root/'plan.json'
        plan={**self.plan,'inputFiles':{},'recipe':self.recipe}
        features.atomic_json(plan_path,plan)
        with patch.object(features,'validate_plan',return_value=({},self.original,{})),\
             patch.object(features,'make_batch',return_value=({},{})),\
             patch.object(features.extraction,'PhoneticEncoder',return_value=object()),\
             patch.object(features,'parity_checks',side_effect=ValueError('parity failed')),\
             patch.object(features,'write_noisy') as write:
            with self.assertRaisesRegex(ValueError,'parity failed'):
                features.run(plan_path,features.digest(plan_path))
            write.assert_not_called()
        self.assertFalse((self.root/'features/features.json').exists())
        self.assertFalse(features.read_json(self.root/'features/failure.json')['complete'])

    def test_guard_retains_authoritative_source_pin(self):
        p=self.root/'protocol';p.write_text('fixed')
        pins={'protocol':features.pin(p)};features.guard(pins)
        p.write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed'):features.guard(pins)
        with self.assertRaisesRegex(ValueError,'Pinned consistency JSON'):
            features.read_bound(p,pins['protocol']['sha256'])

    def test_lexical_snapshot_pin_catches_symlink_retarget_that_blob_pin_misses(self):
        good,bad=self.root/'good.bin',self.root/'bad.bin'
        good.write_bytes(b'original');bad.write_bytes(b'changed')
        snapshot=self.root/'snapshot';snapshot.mkdir()
        link=snapshot/'model.bin';link.symlink_to(good)
        resolved={'oldBlob':features.pin(link.resolve())}
        with patch.object(features,'phonetic_snapshot',return_value=snapshot):
            lexical=features.lexical_checkpoint_pins({'artifactSha256':{'model.bin':features.digest(good)}})
        self.assertEqual(lexical['phoneticSnapshot/model.bin']['path'],str(link.absolute()))
        link.unlink();link.symlink_to(bad)
        features.guard(resolved)
        with self.assertRaisesRegex(ValueError,'artifact changed'):features.guard(lexical)


if __name__=='__main__':unittest.main()
