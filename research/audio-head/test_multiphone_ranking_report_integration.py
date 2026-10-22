"""Temporary synthetic artifacts through all three real queue verifiers.

Only source/recipe declarations and the training-plan producer are substituted;
the fitted-file, history, checkpoint, replay, probability and report readers run
unchanged. These fixtures are not claimed to be actual trained study outcomes.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_consistency_queue as first
import multiphone_consistency_replication_queue as extra
import multiphone_ranking_queue as ranking
import multiphone_ranking_report as report


class RankingReportIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); (self.root / 'outputs').mkdir()
        self.rows = [dict(age=8 if i < 27 else 20, speakerId=f's{i}', clipId=f'c{i}',
            targetPhone='B' if i % 2 else 'P', raterCounts=[1, 1, 3] if i % 3 else [0, 0, 5]) for i in range(28)]
        members = [list(range(9)), list(range(6, 15)), list(range(12, 21)), list(range(21, 27)), list(range(6))]
        self.splits = dict(authorPartition='train', folds=[dict(innerValidationRows=x + [27]) for x in members])
        self.cohort = dict(authorPartition='train', rows=self.rows)
        self.inputs = {}
        for name, value in [('clean/cohort', self.cohort), ('clean/splits', self.splits),
                            ('warm/checkpoint', {'synthetic': 'shared-original'})]:
            path = self.root / (name.replace('/', '-') + '.json'); ranking.atomic_json(path, value)
            self.inputs[name] = {'path': str(path), 'sha256': ranking.digest(path)}
        self.features = self.root / 'features.json'; ranking.atomic_json(self.features, {'synthetic': True})
        self.preflight = self.root / 'preflight.json'
        self.contract = {'sourceSha256': {'synthetic': 'fixed'}, 'recipeSha256': 'synthetic-recipe', 'device': 'cpu', 'threads': 2}
        ranking.atomic_json(self.preflight, dict(complete=True, exact=True, fitOnly=True,
            validationInferencePerformed=False, fold=0, regime='child-only', coefficient=0, comparedUpdates=2,
            exactChecks={k: True for k in ranking.CHECKS}, **self.contract, inputFiles=self.inputs))
        support = self.root / 'support.json'; ranking.atomic_json(support, {'synthetic': True})
        self.enterContext(patch.object(report, 'HERE', self.root))
        self.enterContext(patch.object(report, 'SUPPORT', support))
        self.enterContext(patch.object(report, 'SUPPORT_SHA', ranking.digest(support)))
        for module in (first, extra, ranking):
            self.enterContext(patch.object(module, 'HERE', self.root))
            self.enterContext(patch.object(module, 'contract', return_value=self.contract))
            self.enterContext(patch.object(module.trainer, 'plan_guard', side_effect=self.training_guard))
        self.enterContext(patch.object(ranking.trainer, 'validate_preflight', side_effect=lambda p, _: ranking.read_json(p)))
        self.studies = {}
        for module, name in ((first, 'first'), (extra, 'extra'), (ranking, 'ranking')):
            with patch.object(module.trainer, 'declare', side_effect=lambda a, b, c, m=module: self.training_declare(m, a, b, c)):
                source = self.preflight if module is ranking else self.features
                plan = module.declare(source, ranking.digest(source), self.root / 'outputs' / name)
            base = Path(plan['base']); path = base / 'queue-plan.json'
            training = ranking.read_json(Path(plan['trainingPlan']['path']))
            ledger = dict(complete=True, planPath=str(path), planSha256=ranking.digest(path), contract=self.contract,
                          jobs=deepcopy(plan['jobs']))
            for job in ledger['jobs']:
                self.fit_files(module, job, plan, training)
                self.finish_job(module, job, plan, training)
            ledger_path = base / 'queue-ledger.json'; ranking.atomic_json(ledger_path, ledger)
            self.studies[name] = dict(module=module, plan=plan, training=training, ledger=ledger, path=ledger_path)
        self.enterContext(patch.object(report.controls, 'FIRST_LEDGER_SHA', ranking.digest(self.studies['first']['path'])))

    def population(self, fold, regime):
        validation = self.splits['folds'][fold]['innerValidationRows']
        fit = [i for i in range(27) if i not in validation]
        return dict(fitRows=fit, validationRows=validation,
            selectionRows=[i for i in validation if i < 27] if regime == 'child-only' else validation,
            inputFiles=self.inputs, support={'synthetic': True},
            meanDigest=ranking.trainer.tensor_digest(torch.zeros(2)), stdDigest=ranking.trainer.tensor_digest(torch.ones(2)))

    def training_declare(self, module, source, sha, path):
        value = dict(complete=True, **{k: self.contract[k] for k in ('sourceSha256', 'recipeSha256')}, inputFiles=self.inputs)
        if module is ranking:
            value.update(preflight=dict(path=str(source), sha256=sha),
                arms=[dict(fold=f, regime='child-only', coefficient=.1) for f in range(5)],
                populations={str(f): self.population(f, 'child-only') for f in range(5)})
        else:
            folds = [0] if module is first else [1, 2, 3, 4]
            value.update(noisyFeatures=str(source), noisyFeaturesSha256=sha,
                populations={(r if module is first else module.trainer.population_key(f, r)): self.population(f, r)
                             for f in folds for r in ('all-age', 'child-only')})
        ranking.atomic_json(path, value); return value

    def training_guard(self, plan, path, sha):
        ranking.require(ranking.digest(path) == sha and ranking.read_json(path) == plan, 'Synthetic training declaration differs')
        for item in plan['inputFiles'].values():
            ranking.require(ranking.digest(Path(item['path'])) == item['sha256'], 'Synthetic declared input changed')

    def fit_files(self, module, job, plan, training):
        out = Path(job['output']); out.mkdir(); fold = job.get('fold', 0)
        population = self.population(fold, job['regime']); indices = population['validationRows']
        rows = [self.rows[i] for i in indices]
        p = np.asarray([[.1, .1, .8] if i % 2 else [.2, .1, .7] for i in indices])
        evaluation = report.controls.first_report.score_predictions(p, rows)
        loss = evaluation['ages6to12' if job['regime'] == 'child-only' else 'allAges']['macroTargetLogLoss']
        config = dict(planPath=plan['trainingPlan']['path'], planSha256=plan['trainingPlan']['sha256'],
            **{k: job[k] for k in ('regime', 'coefficient')}, **deepcopy(population),
            **{k: self.contract[k] for k in ('sourceSha256', 'recipeSha256')},
            studentTrainingMode='eval-with-gradients', **{k: False for k in module.trainer.FALSE_FLAGS})
        if module is not first: config['fold'] = fold
        if module is ranking:
            config.update(nllSeed=7, pairSeed=20260926, pairsPerUpdate=64)
            ranking.atomic_json(out / 'support.json', population['support'])
            predictions = dict(rowIndices=indices, probabilities=p.tolist(), warmProbabilities=p.tolist())
        else:
            np.save(out / 'teacher-fit.npy', np.ones((len(population['fitRows']), 3)) / 3)
            config['teacherFitSha256'] = ranking.digest(out / 'teacher-fit.npy')
            predictions = dict(rowIndices=indices, noisyHumanLabelsAvailable=False,
                **{k: p.tolist() for k in report.controls.first_report.PROBABILITIES})
        if module is extra: config['sharedFeaturesIncludeOtherFoldsOuterWaveforms'] = True
        ranking.atomic_json(out / 'config.json', config)
        ranking.atomic_json(out / 'predictions.json', predictions)
        history = [dict(epoch=e, selectionMacroNLL=loss, **({'evaluation': evaluation} if module is ranking else {})) for e in range(3)]
        ranking.atomic_json(out / 'history.json', history)
        status = dict(complete=False, fitComplete=True, state='fitted-awaiting-independent-replay', bestEpoch=0, epochsRun=2)
        ranking.atomic_json(out / 'status.json', status)
        for name, epoch in (('best.pt', 0), ('last.pt', 2)):
            torch.save(dict(configSha256=ranking.digest(out / 'config.json'), epoch=epoch, bestEpoch=0,
                bestLoss=loss, mean=torch.zeros(2), std=torch.ones(2), model={'synthetic': torch.ones(1)}), out / name)
        value = dict(**status, bestCleanSelectionNLL=loss, **{k: False for k in module.trainer.FALSE_FLAGS})
        if module is ranking:
            value.update(fold=fold, regime=job['regime'], coefficient=.1, evaluation=evaluation, warmEvaluation=evaluation,
                         confidence=report.confidence(p, rows), warmConfidence=report.confidence(p, rows))
        else:
            sensitivity = first.trainer.sensitivity(p, p, p, rows)
            value.update(cleanEvaluation=evaluation, warmCleanEvaluation=evaluation, sensitivity=sensitivity, warmSensitivity=sensitivity)
        if module is extra:
            value.update(fold=fold, regime=job['regime'], coefficient=job['coefficient'], sharedFeaturesIncludeOtherFoldsOuterWaveforms=True)
        value['filesSha256'] = {name: ranking.digest(out / name) for name in module.FIT_FILES}
        ranking.atomic_json(out / 'report.json', value)

    def finish_job(self, module, job, plan, training):
        out = Path(job['output']); job['verified'] = module.verify_fitted(job, plan, training)
        replay = dict(complete=True, exact=True, state='verified', noisyAccuracyMeasured=False,
            rows=job['verified']['validationRows'], checkpointSha256=ranking.digest(out / 'best.pt'),
            reportSha256=ranking.digest(out / 'report.json'), **{k: job[k] for k in ('regime', 'coefficient')})
        if module is not first: replay['fold'] = job['fold']
        ranking.atomic_json(out / 'replay.json', replay)
        job.update(replaySha256=module.verify_replay(job), replayVerifiedExact=True, state='complete')
        for key in ('fitProcess', 'replayProcess'):
            log = out / (key + '.log'); log.write_text('Synthetic process fixture, no real execution.\n')
            job[key] = dict(state='complete', exitCode=0, logPath=str(log), logSha256=ranking.digest(log))
        module.guard_outputs(job)

    def build(self, name='comparison'):
        a, b, c = (self.studies[k]['path'] for k in ('first', 'extra', 'ranking'))
        return report.build(a, b, ranking.digest(b), c, ranking.digest(c), self.root / 'outputs' / name)

    def rehash_job(self, study, job):
        module = study['module']; out = Path(job['output'])
        value = ranking.read_json(out / 'report.json')
        value['filesSha256'] = {name: ranking.digest(out / name) for name in module.FIT_FILES}
        ranking.atomic_json(out / 'report.json', value)
        self.finish_job(module, job, study['plan'], study['training'])
        ranking.atomic_json(study['path'], study['ledger'])

    def test_three_real_queue_apis_accept_complete_fixed_inventory(self):
        with patch.object(first, 'verify_fitted', wraps=first.verify_fitted) as a, \
             patch.object(extra, 'verify_fitted', wraps=extra.verify_fitted) as b, \
             patch.object(ranking, 'verify_fitted', wraps=ranking.verify_fitted) as c:
            result = self.build()
        self.assertEqual((a.call_count, b.call_count, c.call_count), (6, 24, 5))
        self.assertEqual([arm['fold'] for arm in result['arms']], list(range(5)))
        self.assertEqual(result['support']['ages6to12']['deduplicated']['speakers'], 27)
        self.assertEqual(result['support']['ages6to12']['foldMembershipSums']['speakers'], 39)
        self.assertFalse(result['inferencePerformed']); self.assertFalse(result['coefficientSelected'])
        for age in report.AGES:
            self.assertEqual(result['descriptiveSummaries'][age]['macroNLL']['differenceVsControl']['perFold'], [0.] * 5)
        self.assertTrue((self.root / 'outputs/comparison/report.md').exists())

    def test_self_consistently_rehashed_control_moments_are_not_matched(self):
        study = self.studies['extra']; job = next(j for j in study['ledger']['jobs'] if j['fold'] == 1 and j['regime'] == 'child-only' and j['coefficient'] == 0)
        path = Path(job['output']) / 'best.pt'; checkpoint = torch.load(path, weights_only=True); checkpoint['mean'] += 1
        torch.save(checkpoint, path); self.rehash_job(study, job)
        with self.assertRaisesRegex(ValueError, 'normalization differs'): self.build()

    def test_self_consistently_rehashed_warm_predictions_are_not_matched(self):
        study = self.studies['extra']; job = next(j for j in study['ledger']['jobs'] if j['fold'] == 1 and j['regime'] == 'child-only' and j['coefficient'] == 0)
        out = Path(job['output']); predictions = ranking.read_json(out / 'predictions.json')
        # Update selected and original together so this remains an internally valid
        # epoch-zero control; the cross-study original identity must reject it.
        p = np.asarray(predictions['cleanProbabilities']); p[:, 0] += .01; p[:, 2] -= .01
        for key in report.controls.first_report.PROBABILITIES: predictions[key] = p.tolist()
        ranking.atomic_json(out / 'predictions.json', predictions)
        rows = [self.rows[i] for i in predictions['rowIndices']]
        evaluation = report.controls.first_report.score_predictions(p, rows); loss = evaluation['ages6to12']['macroTargetLogLoss']
        value = ranking.read_json(out / 'report.json'); value.update(cleanEvaluation=evaluation, warmCleanEvaluation=evaluation,
            bestCleanSelectionNLL=loss, sensitivity=first.trainer.sensitivity(p, p, p, rows), warmSensitivity=first.trainer.sensitivity(p, p, p, rows))
        ranking.atomic_json(out / 'report.json', value)
        ranking.atomic_json(out / 'history.json', [dict(epoch=e, selectionMacroNLL=loss) for e in range(3)])
        for name in ('best.pt', 'last.pt'):
            state = torch.load(out / name, weights_only=True); state['bestLoss'] = loss; torch.save(state, out / name)
        self.rehash_job(study, job)
        with self.assertRaisesRegex(ValueError, 'Original warm probabilities'): self.build()

    def test_missing_control_replay_and_partial_ranking_ledger_fail(self):
        path = Path(self.studies['extra']['ledger']['jobs'][0]['output']) / 'replay.json'; saved = path.read_bytes(); path.unlink()
        with self.assertRaises(FileNotFoundError): self.build()
        path.write_bytes(saved)
        study = self.studies['ranking']; study['ledger']['complete'] = False; ranking.atomic_json(study['path'], study['ledger'])
        with self.assertRaisesRegex(ValueError, 'incomplete'): self.build()

    def test_cross_study_comparison_requires_full_warm_and_clean_binding_identity(self):
        original = report.control_record
        for key in ('warm/alternate-checkpoint', 'clean/alternate-features'):
            def different_context(record, pins):
                config, value, predictions = original(record, pins)
                config = deepcopy(config)
                config['inputFiles'][key] = self.inputs['clean/cohort']
                return config, value, predictions
            # The actual control loader and all queue verifiers still execute;
            # inject an extra returned binding to isolate cross-study matching.
            with self.subTest(key=key), patch.object(report, 'control_record', side_effect=different_context), \
                 self.assertRaisesRegex(ValueError, 'warm-head or clean feature bindings differ'):
                self.build()

    def test_final_read_rechecks_prior_control_artifacts_and_ledger(self):
        original = report.markdown
        def mutate(value):
            result = original(value)
            path = Path(self.studies['first']['ledger']['jobs'][0]['output']) / 'predictions.json'
            with path.open('ab') as stream: stream.write(b' ')
            return result
        with patch.object(report, 'markdown', side_effect=mutate), self.assertRaisesRegex(ValueError, 'artifact changed'):
            self.build()
        self.assertFalse((self.root / 'outputs/comparison').exists())


if __name__ == '__main__': unittest.main()
