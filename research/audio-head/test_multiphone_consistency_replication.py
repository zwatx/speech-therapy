"""Synthetic split boundaries and exact replay for the fixed four-fold extension."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_consistency_replication as trainer
from test_multiphone_controls import synthetic_study


def synthetic_data(fold, regime):
    cohort, splits = synthetic_study()
    fit, validation, selection = trainer.baseline.select_rows(cohort, splits, fold, regime)
    torch.manual_seed(29 + fold)
    network = trainer.model()
    generator = np.random.default_rng(91 + fold)
    indices = fit + validation
    clean = torch.tensor(generator.normal(size=(len(indices), 1037)), dtype=torch.float32)
    noisy = clean + torch.tensor(generator.normal(scale=.2, size=clean.shape), dtype=torch.float32)
    ids = torch.tensor([cohort['rows'][i]['targetId'] for i in indices], dtype=torch.long)
    return dict(cohort=cohort, splits=splits, fit=fit, validation=validation, selection=selection,
        clean=clean, noisy=noisy, ids=ids, fitCount=len(fit), mean=torch.zeros(1037), std=torch.ones(1037),
        teacherFit=trainer.predict(network, clean[:len(fit)], ids[:len(fit)]),
        warmPredictions=trainer.predict(network, clean[len(fit):], ids[len(fit):]),
        warmState=deepcopy(network.state_dict()), warmModel=network.requires_grad_(False), allBindings={},
        labels=torch.tensor([cohort['rows'][i]['raterCounts'] for i in fit], dtype=torch.float32) / 5)


class ReplicationTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / 'outputs').mkdir()
        self.plan_path = self.root / 'outputs/plan.json'
        self.data = {(f, r): synthetic_data(f, r) for f in trainer.FOLDS for r in trainer.REGIMES}
        self.plan = {'complete': True, 'recipeSha256': trainer.digest(trainer.RECIPE),
            'sourceSha256': {'synthetic': 'stable'}, 'inputFiles': {}, 'arms': trainer.arms(),
            'sharedFeaturesIncludeOtherFoldsOuterWaveforms': True,
            **{key: False for key in trainer.FALSE_FLAGS},
            'noisyFeatures': 'unused-synthetic', 'noisyFeaturesSha256': 'unused-synthetic',
            'populations': {trainer.population_key(f,r): {k + 'Rows': self.data[f,r][k]
                                for k in ('fit','validation','selection')}
                            for f in trainer.FOLDS for r in trainer.REGIMES}}
        trainer.atomic_json(self.plan_path, self.plan)
        self.plan_sha = trainer.digest(self.plan_path)
        self.enterContext(patch.object(trainer, 'HERE', self.root))
        self.enterContext(patch.object(trainer, 'source_hashes', return_value={'synthetic': 'stable'}))
        self.loader = self.enterContext(patch.object(trainer, 'load_data',
            side_effect=lambda fold, regime, *_: deepcopy(self.data[fold,regime])))
        self.enterContext(redirect_stdout(io.StringIO()))

    def args(self, fold=1, regime='all-age', coefficient=.1, name='trial'):
        return SimpleNamespace(plan=self.plan_path, plan_sha256=self.plan_sha, fold=fold, regime=regime,
            coefficient=coefficient, output=self.root / 'outputs' / name)

    def test_all_eight_populations_fit_and_exactly_replay_four_prediction_arrays(self):
        for fold in trainer.FOLDS:
            for regime in trainer.REGIMES:
                with self.subTest(fold=fold, regime=regime):
                    args = self.args(fold, regime, name=f'{fold}-{regime}')
                    report = trainer.fit(args)
                    self.assertEqual(report['fold'], fold)
                    self.assertFalse(report['complete'])
                    self.assertTrue(report['fitComplete'])
                    replay = trainer.replay(args.output)
                    self.assertTrue(replay['exact'])
                    self.assertEqual((replay['fold'], replay['regime']), (fold, regime))
                    saved = torch.load(args.output / 'best.pt', weights_only=True)
                    self.assertEqual(saved['configSha256'], trainer.digest(args.output / 'config.json'))
                    self.assertEqual(np.load(args.output / 'teacher-fit.npy').shape[0], self.data[fold,regime]['fitCount'])
                    self.assertNotIn('noisyEvaluation', report)

    def test_fold_zero_and_reordered_declaration_rejected(self):
        with self.assertRaisesRegex(ValueError, 'declared arm'):
            trainer.fit(self.args(fold=0))
        changed = deepcopy(self.plan); changed['arms'].reverse()
        trainer.atomic_json(self.plan_path, changed)
        args = self.args(); args.plan_sha256 = trainer.digest(self.plan_path)
        with self.assertRaisesRegex(ValueError, 'declaration changed'):
            trainer.fit(args)

    def test_epoch_zero_eligible_and_clean_only_noisy_validation_isolation(self):
        args = self.args(fold=3, name='zero')
        with patch.object(trainer, 'selection_value', return_value=.25):
            report = trainer.fit(args)
            self.assertEqual((report['bestEpoch'], report['epochsRun']), (0,2))
            self.assertTrue(trainer.replay(args.output)['exact'])
        first = self.args(fold=3, coefficient=1., name='first'); trainer.fit(first)
        self.data[3,'all-age']['noisy'][self.data[3,'all-age']['fitCount']:] *= -20
        second = self.args(fold=3, coefficient=1., name='second'); trainer.fit(second)
        self.assertEqual(trainer.read_json(first.output / 'history.json'), trainer.read_json(second.output / 'history.json'))
        a, b = [torch.load(args.output / 'best.pt', weights_only=True) for args in (first,second)]
        self.assertTrue(all(torch.equal(a['model'][key], b['model'][key]) for key in a['model']))
        self.assertNotEqual(trainer.read_json(first.output / 'predictions.json')['noisyProbabilities'],
                            trainer.read_json(second.output / 'predictions.json')['noisyProbabilities'])

    def test_zero_control_noisy_fit_values_cannot_change_updates(self):
        first = self.args(fold=2, coefficient=0., name='first'); trainer.fit(first)
        self.data[2,'all-age']['noisy'][:self.data[2,'all-age']['fitCount']] = float('nan')
        second = self.args(fold=2, coefficient=0., name='second'); trainer.fit(second)
        self.assertEqual(trainer.read_json(first.output / 'history.json'), trainer.read_json(second.output / 'history.json'))
        a, b = [torch.load(args.output / 'best.pt', weights_only=True) for args in (first,second)]
        self.assertTrue(all(torch.equal(a['model'][key], b['model'][key]) for key in a['model']))

    def test_late_output_mutation_blocks_publication(self):
        original = trainer.sensitivity
        for filename in ('config.json','teacher-fit.npy','best.pt','history.json'):
            args = self.args(name=filename.replace('.','-'))
            mutated = False
            def change(*values):
                nonlocal mutated
                if not mutated:
                    with (args.output / filename).open('ab') as stream: stream.write(b' ')
                    mutated = True
                return original(*values)
            with patch.object(trainer, 'sensitivity', side_effect=change):
                with self.assertRaisesRegex(ValueError, 'Owned training artifact'):
                    trainer.fit(args)
            self.assertFalse((args.output / 'report.json').exists())

    def test_declaration_retains_eight_populations_and_pilot_pins(self):
        recipe = trainer.read_json(trainer.RECIPE)
        protocol = Path(recipe['protocolPath'])
        alias = protocol.parent / '..' / protocol.parent.name / protocol.name
        for data in self.data.values():
            data['allBindings']['protocol'] = {'path': str(alias), 'sha256': recipe['protocolSha256']}
        result = trainer.declare(self.root / 'noisy.json', 'synthetic', self.root / 'outputs/declared.json')
        self.assertEqual(len(result['populations']), 8)
        self.assertEqual(result['arms'], trainer.arms())
        self.assertEqual(result['inputFiles']['protocol']['path'], str(alias))
        self.assertEqual(result['inputFiles']['declaredReplicationProtocol']['path'], str(protocol))
        for name, pin in recipe['retainedPilot'].items():
            self.assertEqual(result['inputFiles']['retainedPilot/' + name], pin)
        for (fold,regime), data in self.data.items():
            population = result['populations'][trainer.population_key(fold,regime)]
            self.assertEqual(population['fitRows'], data['fit'])
            self.assertEqual(population['selectionRows'], data['selection'])

    def test_rehashed_wrong_fold_and_prediction_tamper_rejected(self):
        args = self.args(); trainer.fit(args)
        report = trainer.read_json(args.output / 'report.json'); report['fold'] = 4
        trainer.atomic_json(args.output / 'report.json', report)
        with self.assertRaisesRegex(ValueError, 'membership differs'):
            trainer.replay(args.output)
        report['fold'] = 1; trainer.atomic_json(args.output / 'report.json', report)
        predictions = trainer.read_json(args.output / 'predictions.json'); predictions['noisyProbabilities'][0] = [.1,.2,.7]
        trainer.atomic_json(args.output / 'predictions.json', predictions)
        with self.assertRaisesRegex(ValueError, 'artifacts differ'):
            trainer.replay(args.output)

    def test_changed_recipe_and_missing_warm_population_rejected(self):
        recipe = trainer.read_json(trainer.RECIPE); trainer.validate_recipe(recipe)
        recipe['learningRate'] = .001
        with self.assertRaisesRegex(ValueError, 'fixed24-arm'):
            trainer.validate_recipe(recipe)
        recipe = trainer.read_json(trainer.RECIPE); recipe['warmHeads'].pop('fold-4/child-only')
        with self.assertRaisesRegex(ValueError, 'Warm population coverage'):
            trainer.validate_recipe(recipe)


class ReplicationInputTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_warm_loading_uses_fold_population_clean_moments_and_original_best_epoch(self):
        for fold, regime, epoch in ((1,'all-age',3),(2,'child-only',7),(4,'child-only',3)):
            with self.subTest(fold=fold, regime=regime):
                directory = self.root / f'{fold}-{regime}'; directory.mkdir()
                cohort, splits = synthetic_study()
                fit, validation, selection = trainer.baseline.select_rows(cohort,splits,fold,regime)
                raw = np.random.default_rng(fold).normal(size=(len(cohort['rows']),1037)).astype(np.float32)
                raw[validation] += 100  # This must not contaminate fitting moments.
                mean = torch.from_numpy(raw[fit].astype(np.float64).mean(0).astype(np.float32))
                std = torch.from_numpy(raw[fit].astype(np.float64).std(0).clip(1e-6).astype(np.float32))
                noisy = raw * 1.1 + 7
                data = dict(cohort=cohort,splits=splits,fit=fit,validation=validation,selection=selection,
                            bindings={}, values=raw,positions={i:i for i in range(len(raw))},mean=mean,std=std,priors={})
                config = dict(family='target-scalars',regime=regime,fold=fold,lr=.0003,seed=7,phase='inner',
                    binding=str(self.root/'synthetic-binding.json'),bindingSha256='synthetic-binding',
                    fitRows=fit,validationRows=validation,selectionRows=selection,inputFiles={},priorState={})
                trainer.atomic_json(directory/'config.json',config)
                network = trainer.model()
                ids = torch.tensor([cohort['rows'][i]['targetId'] for i in validation])
                probabilities = trainer.predict(network,(torch.from_numpy(raw[validation])-mean)/std,ids)
                trainer.atomic_json(directory/'predictions.json',dict(rowIndices=validation,probabilities=probabilities.tolist()))
                trainer.atomic_json(directory/'prior.json',{})
                trainer.atomic_json(directory/'history.json',[{'epoch':epoch}])
                saved = dict(configSha256=trainer.digest(directory/'config.json'),epoch=epoch,bestEpoch=epoch,bestLoss=.2,
                             mean=mean,std=std,model=network.state_dict())
                torch.save(saved,directory/'best.pt')
                trainer.atomic_json(directory/'report.json',dict(complete=True,phase='inner',bestEpoch=epoch,
                    bestSelectionMacroLogLoss=.2,configSha256=trainer.digest(directory/'config.json'),
                    **{key+'Sha256':trainer.digest(directory/name) for key,name in
                       [('checkpoint','best.pt'),('predictions','predictions.json'),('history','history.json'),('prior','prior.json')]}))
                trainer.atomic_json(directory/'replay.json',dict(exact=True,rows=len(validation),checkpointSha256=trainer.digest(directory/'best.pt')))
                warm = dict(directory=str(directory),selectedEpoch=epoch,
                    files={p.name:trainer.digest(p) for p in directory.iterdir()})
                recipe = dict(warmHeads={trainer.population_key(fold,regime):warm},cleanFeatureBindingSha256='synthetic-binding')
                with patch.object(trainer.baseline,'source_guard'), patch.object(trainer.baseline,'setup',return_value=data), \
                     patch.object(trainer,'feature_matrix',return_value=(noisy,data['positions'],{})):
                    result = trainer.load_data(fold,regime,self.root/'features.json','synthetic',recipe)
                    expected = fit + validation
                    self.assertTrue(torch.equal(result['clean'],(torch.from_numpy(raw[expected])-mean)/std))
                    self.assertTrue(torch.equal(result['noisy'],(torch.from_numpy(noisy[expected])-mean)/std))
                    self.assertEqual(result['teacherFit'].shape,(len(fit),3))
                    self.assertTrue(np.array_equal(result['warmPredictions'],probabilities))
                    self.assertTrue(torch.equal(result['labels'],torch.tensor([cohort['rows'][i]['raterCounts'] for i in fit])/5))
                    self.assertFalse(result['warmModel'].training)
                    self.assertTrue(all(not p.requires_grad for p in result['warmModel'].parameters()))
                    warm['selectedEpoch'] += 1
                    with self.assertRaisesRegex(ValueError,'checkpoint or clean fitting moments'):
                        trainer.load_data(fold,regime,self.root/'features.json','synthetic',recipe)
                    warm['selectedEpoch'] -= 1
                    altered = {**data,'mean':mean+1}
                    with patch.object(trainer.baseline,'setup',return_value=altered):
                        with self.assertRaisesRegex(ValueError,'checkpoint or clean fitting moments'):
                            trainer.load_data(fold,regime,self.root/'features.json','synthetic',recipe)

    def feature_fixture(self):
        recipe = trainer.read_json(trainer.RECIPE)
        rows = [dict(id=f'clip-{i}:B',clipId=f'clip-{i}',targetId=0,targetPhone='B',
                     wordIndex=0,phoneIndex=0,trainingEligible=i!=1) for i in range(4)]
        bound = dict(cohort={'rows':rows},bindings={})
        expected = [0,2,3]
        binding_path = self.root/'binding.json';trainer.atomic_json(binding_path,dict(files={}))
        binding = dict(path=str(binding_path),sha256=trainer.digest(binding_path))
        recipe['cleanFeatureBindingSha256'] = binding['sha256']
        report = dict(complete=True,completeCoverage=True,authorPartition='train',partition='all-eligible-author-training-rows',
            rowIndices=expected,expectedRows=3,expectedClips=3,failedRows=[],unmappableRows=[],condition='noise20db',snrDb=20,
            cleanFeatureBindingSha256=binding['sha256'],featureSourceBindingSha256=binding['sha256'],
            scalarFeatureNames=trainer.baseline.SCALAR_NAMES,originalParityComplete=True,**trainer.producer.FLAGS,
            inputFiles={'cleanFeatureBinding':binding,'protocol':dict(path=recipe['protocolPath'],sha256=trainer.PROTOCOL_SHA)},
            rows=[dict(rowIndex=i,rowId=rows[i]['id'],**{key:rows[i][key] for key in
                      ('clipId','targetId','targetPhone','wordIndex','phoneIndex')}) for i in expected])
        arrays=[np.arange(3*w,dtype=np.float32).reshape(3,w) for w in (1024,13)]
        pins={'binding':binding,'protocol':report['inputFiles']['protocol']}
        for key,name,array in zip(('targetFeatures','scalarFeatures'),('target','scalars'),arrays,strict=True):
            path=self.root/(name+'.npy');np.save(path,array,allow_pickle=False)
            report[key]=dict(path=path.name,sha256=trainer.digest(path),shape=list(array.shape),dtype='float32')
            pins['matrix/'+name]=dict(path=str(path),sha256=trainer.digest(path))
        path=self.root/'features.json';trainer.atomic_json(path,report)
        pins['features']=dict(path=str(path),sha256=trainer.digest(path))
        return path,recipe,bound,report,arrays,pins

    def test_full_feature_adapter_preserves_exact_row_and_column_order_and_authoritative_pins(self):
        path,recipe,bound,report,arrays,pins=self.feature_fixture()
        original=trainer.read_json
        with patch.object(trainer.producer,'validate_features',return_value=(report,*arrays,pins)), \
             patch.object(trainer,'read_json',side_effect=lambda p:recipe if p==trainer.RECIPE else original(p)):
            values,positions,retained=trainer.feature_matrix(path,trainer.digest(path),bound)
        self.assertTrue(np.array_equal(values,np.concatenate(arrays,axis=1)))
        self.assertEqual(positions,{0:0,2:1,3:2})
        self.assertEqual(retained,{'noisy/'+k:v for k,v in pins.items()})

    def test_full_feature_adapter_rejects_mismatched_scope_identity_shape_and_late_mutation(self):
        mutations=[lambda r,a,p:r.update(snrDb=10),lambda r,a,p:r.update(rowIndices=[0,3,2]),
            lambda r,a,p:r['rows'][0].update(targetId=2),lambda r,a,p:r.update(originalParityComplete=False),
            lambda r,a,p:r.update(partition='innerFitRows+innerValidationRows'),
            lambda r,a,p:a.__setitem__(0,a[0].astype(np.float64)),
            lambda r,a,p:p['matrix/target'].update(sha256='0'*64),
            lambda r,a,p:(self.root/'target.npy').write_bytes(b'changed')]
        for mutation in mutations:
            path,recipe,bound,report,arrays,pins=self.feature_fixture();sha=trainer.digest(path)
            mutation(report,arrays,pins)
            original=trainer.read_json
            with patch.object(trainer.producer,'validate_features',return_value=(report,*arrays,pins)), \
                 patch.object(trainer,'read_json',side_effect=lambda p:recipe if p==trainer.RECIPE else original(p)):
                with self.assertRaises((ValueError,KeyError)):
                    trainer.feature_matrix(path,sha,bound)


if __name__ == '__main__':
    unittest.main()
