"""Saved-artifact integration of both queue APIs; synthetic fixtures, no inference.

Only source-location contracts are substituted. Plan/output/replay validation,
clean metrics, paired movement and final publication guards execute normally.
Synthetic replay markers exercise the reader contract; actual checkpoint replay
is independently covered by the two trainers' tests.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_consistency_queue as pilot_queue
import multiphone_consistency_replication_queue as extension_queue
import multiphone_consistency_replication_report as report


class ReplicationReportIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / 'repo'
        self.here = self.root / 'research/audio-head'; self.here.mkdir(parents=True)
        self.outputs = self.here / 'outputs'; self.outputs.mkdir()
        protocol_source = report.trainer.HERE / '../../docs/model/multiphone-consistency-replication-protocol.md'
        self.protocol = self.root / 'docs/model/multiphone-consistency-replication-protocol.md'
        self.protocol.parent.mkdir(parents=True); self.protocol.write_bytes(protocol_source.read_bytes())
        children = [list(range(0,8)),list(range(6,14)),list(range(12,20)),list(range(18,26)),[0,4,8,12,16,20,26]]
        self.cohort = {'authorPartition':'train','rows':[dict(id=f'target-{i}',speakerId=f'speaker-{i}',
            clipId=f'clip-{i}',targetId=0,targetPhone='B',age=8 if i<27 else 20,
            raterCounts=[1,1,3] if i%3==0 else [0,0,5]) for i in range(32)]}
        self.splits = {'authorPartition':'train','folds':[dict(innerValidationRows=indices+[27+f])
                                                       for f,indices in enumerate(children)]}
        self.cohort_path,self.splits_path=self.outputs/'cohort.json',self.outputs/'splits.json'
        report.atomic_json(self.cohort_path,self.cohort);report.atomic_json(self.splits_path,self.splits)
        self.bindings={'clean/'+name:{'path':str(path),'sha256':report.digest(path)}
                       for name,path in [('cohort',self.cohort_path),('splits',self.splits_path)]}
        self.contracts={}
        for label,module in [('pilot',pilot_queue),('extension',extension_queue)]:
            contract=dict(sourceSha256={'synthetic':'fixed'},recipeSha256=report.digest(module.trainer.RECIPE),
                          trainerSha256='synthetic-'+label,device='cpu',threads=2)
            self.contracts[label]=contract
            self.enterContext(patch.object(module,'HERE',self.here))
            self.enterContext(patch.object(module.trainer,'HERE',self.here))
            self.enterContext(patch.object(module,'contract',return_value=contract))
            self.enterContext(patch.object(module.trainer,'source_hashes',return_value=contract['sourceSha256']))
        self.first,self.first_sha=self.make_queue(pilot_queue,'pilot')
        self.second,self.second_sha=self.make_queue(extension_queue,'extension')
        self.enterContext(patch.object(report,'FIRST_LEDGER_SHA',self.first_sha))

    def make_queue(self,module,label):
        base=self.outputs/label;base.mkdir()
        jobs=module.jobs(base)
        populations={}
        for job in jobs:
            fold=job.get('fold',0);regime=job['regime']
            validation=self.splits['folds'][fold]['innerValidationRows']
            fit=[i for i,r in enumerate(self.cohort['rows']) if i not in validation
                 and (regime=='all-age' or r['age']<=12)]
            selection=[i for i in validation if regime=='all-age' or self.cohort['rows'][i]['age']<=12]
            key=regime if module is pilot_queue else module.trainer.population_key(fold,regime)
            populations[key]=dict(fitRows=fit,validationRows=validation,selectionRows=selection)
        training=dict(complete=True,**{k:self.contracts[label][k] for k in ('sourceSha256','recipeSha256')},
            inputFiles=self.bindings,populations=populations,noisyFeatures=str(base/'features.json'),
            noisyFeaturesSha256='',**{key:False for key in module.trainer.FALSE_FLAGS})
        report.atomic_json(base/'features.json',dict(complete=True,synthetic=True))
        training['noisyFeaturesSha256']=report.digest(base/'features.json')
        if module is pilot_queue:
            training['arms']=[dict(regime=r,coefficient=c) for r in module.trainer.REGIMES for c in module.trainer.COEFFICIENTS]
        else:
            training.update(arms=module.trainer.arms(),sharedFeaturesIncludeOtherFoldsOuterWaveforms=True)
        training_path=base/'training-plan.json';report.atomic_json(training_path,training)
        plan=dict(complete=True,base=str(base),contract=self.contracts[label],
            trainingPlan=dict(path=str(training_path),sha256=report.digest(training_path)),
            noisyFeatures=dict(path=training['noisyFeatures'],sha256=training['noisyFeaturesSha256']),
            jobs=deepcopy(jobs),plannedTrials=len(jobs),implicitResumeAllowed=False,outcomesCanChangeOrderOrCoverage=False,
            **{key:False for key in module.trainer.FALSE_FLAGS})
        plan['allSixArmsFixed' if module is pilot_queue else 'allTwentyFourArmsFixed']=True
        plan_path=base/'queue-plan.json';report.atomic_json(plan_path,plan)
        for job in jobs:
            self.make_arm(module,job,plan,training)
        ledger=dict(complete=True,planPath=str(plan_path),planSha256=report.digest(plan_path),
                    contract=self.contracts[label],jobs=jobs,pid=1,parentPid=1,processSessionId=1)
        ledger_path=base/'queue-ledger.json';report.atomic_json(ledger_path,ledger)
        return ledger_path,report.digest(ledger_path)

    def make_arm(self,module,job,plan,training):
        output=Path(job['output']);output.mkdir()
        fold=job.get('fold',0);regime=job['regime'];coefficient=job['coefficient']
        key=regime if module is pilot_queue else module.trainer.population_key(fold,regime)
        population=training['populations'][key];indices=population['validationRows']
        rows=[self.cohort['rows'][i] for i in indices]
        warm=np.array([[.05+.002*i,.1, .85-.002*i] for i in indices],dtype=np.float64)
        # Clean stays at epoch zero. Synthetic saved noise probabilities differ
        # to exercise the reader's paired deltas and confidence reconstruction.
        clean=warm.copy();warm_noisy=.9*warm+.1/3
        noisy=(.9+.05*coefficient)*warm+(.1-.05*coefficient)/3
        evaluation=report.first_report.score_predictions(clean,rows)
        loss=module.trainer.baseline.selection_loss(evaluation,regime)
        np.save(output/'teacher-fit.npy',np.tile([.05,.1,.85],(len(population['fitRows']),1)))
        config=dict(planPath=plan['trainingPlan']['path'],planSha256=plan['trainingPlan']['sha256'],
            regime=regime,coefficient=coefficient,**population,sourceSha256=training['sourceSha256'],
            recipeSha256=training['recipeSha256'],inputFiles=self.bindings,studentTrainingMode='eval-with-gradients',
            teacherFitSha256=report.digest(output/'teacher-fit.npy'),**{k:False for k in module.trainer.FALSE_FLAGS})
        if module is extension_queue:config.update(fold=fold,sharedFeaturesIncludeOtherFoldsOuterWaveforms=True)
        report.atomic_json(output/'config.json',config)
        checkpoint=dict(configSha256=report.digest(output/'config.json'),epoch=0,bestEpoch=0,bestLoss=loss,
                        mean=torch.zeros(1),std=torch.ones(1),model={},optimizer={})
        torch.save(checkpoint,output/'best.pt');torch.save({**checkpoint,'epoch':2},output/'last.pt')
        report.atomic_json(output/'history.json',[dict(epoch=e,selectionMacroNLL=loss) for e in range(3)])
        report.atomic_json(output/'status.json',dict(complete=False,fitComplete=True,state='fitted-awaiting-independent-replay',bestEpoch=0,epochsRun=2))
        report.atomic_json(output/'predictions.json',dict(rowIndices=indices,noisyHumanLabelsAvailable=False,
            cleanProbabilities=clean.tolist(),noisyProbabilities=noisy.tolist(),warmCleanProbabilities=warm.tolist(),
            warmNoisyProbabilities=warm_noisy.tolist()))
        fitted=dict(complete=False,fitComplete=True,state='fitted-awaiting-independent-replay',bestEpoch=0,epochsRun=2,
            bestCleanSelectionNLL=loss,cleanEvaluation=evaluation,warmCleanEvaluation=evaluation,
            sensitivity=report.trainer.sensitivity(clean,noisy,warm,rows),
            warmSensitivity=report.trainer.sensitivity(warm,warm_noisy,warm,rows),
            filesSha256={name:report.digest(output/name) for name in module.FIT_FILES},
            **{key:False for key in module.trainer.FALSE_FLAGS})
        if module is extension_queue:fitted.update(fold=fold,regime=regime,coefficient=coefficient,sharedFeaturesIncludeOtherFoldsOuterWaveforms=True)
        report.atomic_json(output/'report.json',fitted)
        job['verified']=module.verify_fitted(job,plan,training)
        replay=dict(complete=True,exact=True,state='verified',noisyAccuracyMeasured=False,rows=len(indices),
                    checkpointSha256=report.digest(output/'best.pt'),reportSha256=report.digest(output/'report.json'))
        if module is extension_queue:replay.update(fold=fold,regime=regime,coefficient=coefficient)
        report.atomic_json(output/'replay.json',replay)
        job.update(replaySha256=module.verify_replay(job),replayVerifiedExact=True,state='complete')
        for key in ('fitProcess','replayProcess'):
            log=output/(key+'.log');log.write_text('Synthetic fixture, no process or inference executed.\n')
            job[key]=dict(state='complete',exitCode=0,logPath=str(log),logSha256=report.digest(log),pid=1)
        module.guard_outputs(job)

    def test_checked_queue_accepts_both_real_api_shapes_and_binds_folds(self):
        pins={}
        first,_,cohort,splits=report.checked_queue(pilot_queue,self.first,self.first_sha,[0],pins)
        extra,_,other_cohort,other_splits=report.checked_queue(extension_queue,self.second,self.second_sha,[1,2,3,4],pins)
        self.assertEqual(len(first),6);self.assertEqual(len(extra),24)
        self.assertEqual(cohort,other_cohort);self.assertEqual(splits,other_splits)
        self.assertEqual([r['fold'] for r in first],[0]*6)
        self.assertEqual([r['fold'] for r in extra],[f for f in range(1,5) for _ in range(6)])
        self.assertEqual(pins[str(self.first)],self.first_sha)
        self.assertEqual(pins[str(self.second)],self.second_sha)
        self.assertEqual(extra[0]['profiles']['ages6to12']['clean']['argmaxCounts'],[0,0,8])

    def test_build_recomputes_thirty_arms_profiles_support_and_signed_changes(self):
        output=self.outputs/'combined'
        value=report.build(self.first,self.second,self.second_sha,output)
        self.assertTrue(value['complete']);self.assertEqual(len(value['arms']),30)
        self.assertFalse(value['coefficientSelected']);self.assertFalse(value['noisyAccuracyMeasured'])
        child=value['support']['ages6to12']
        self.assertEqual(child['deduplicated']['speakers'],27)
        self.assertEqual(child['foldMembershipSums']['speakers'],39)
        for item in value['descriptiveSummaries']:
            movement=item['ages']['ages6to12']['meanNoiseTotalVariation']['differenceVsCoefficientZero']
            if item['coefficient']==0:self.assertEqual(movement['perFold'],[0.]*5)
            else:self.assertEqual(movement['directionCounts']['lower'],5)
        self.assertEqual(value['markdownSha256'],report.digest(output/'report.md'))
        saved=report.read_json(output/'report.json')
        self.assertEqual(saved['arms'],value['arms'])
        self.assertIn('27 distinct children',(output/'report.md').read_text())

    def test_rehashed_ledger_with_wrong_fold_or_mutated_prediction_is_rejected(self):
        ledger=report.read_json(self.second);ledger['jobs'][0]['fold']=0
        report.atomic_json(self.second,ledger)
        with self.assertRaisesRegex(ValueError,'inventory differs'):
            report.checked_queue(extension_queue,self.second,report.digest(self.second),[1,2,3,4],{})
        ledger['jobs'][0]['fold']=1;report.atomic_json(self.second,ledger)
        path=Path(ledger['jobs'][0]['output'])/'predictions.json'
        with path.open('ab') as stream:stream.write(b' ')
        with self.assertRaisesRegex(ValueError,'artifact changed'):
            report.checked_queue(extension_queue,self.second,report.digest(self.second),[1,2,3,4],{})

    def test_late_inputs_or_earlier_arm_changes_block_publication(self):
        original_markdown=report.markdown
        first_job=report.read_json(self.first)['jobs'][0]
        for label,path in [('ledger',self.second),('protocol',self.protocol),('cohort',self.cohort_path),
                           ('earlier-arm',Path(first_job['output'])/'predictions.json'),
                           ('earlier-log',Path(first_job['fitProcess']['logPath']))]:
            with self.subTest(label=label):
                before=path.read_bytes();output=self.outputs/('blocked-'+label)
                def mutate(value):
                    text=original_markdown(value)
                    with path.open('ab') as stream:stream.write(b' ')
                    return text
                try:
                    with patch.object(report,'markdown',side_effect=mutate):
                        with self.assertRaises(ValueError):
                            report.build(self.first,self.second,self.second_sha,output)
                    self.assertFalse(output.exists())
                finally:path.write_bytes(before)


if __name__=='__main__':
    unittest.main()
