"""Seed identity, phase barriers and actual checkpoint validation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

from lexical_seed_replication import study as s
from lexical_unit_weights.test_core import bundle


def base_jobs():
    return [dict(id=f'{regime}-{family}-s{fold}-w{word}', family=family,
                 regime=regime, speakerFold=fold, wordGroup=word,
                 fitRows=list(range(65)), refitRows=list(range(65)),
                 selectionRows=[], addedValidationRows=[], outerRows=list(range(65, 76)))
            for regime in s.parent.REGIMES for family in s.parent.FAMILIES
            for fold in range(5) for word in range(5)]


class StudyTests(unittest.TestCase):
    def test_complete_fixed_matrix_preserves_base_jobs(self):
        original = base_jobs()
        jobs = s.make_jobs(original)
        self.assertEqual(len(jobs), 600)
        self.assertEqual(len({j['id'] for j in jobs}), 600)
        for seed in s.SEEDS:
            for objective in s.OBJECTIVES:
                subset = [j for j in jobs if j['seed'] == seed and j['objective'] == objective]
                self.assertEqual([j['baseJobId'] for j in subset], [j['id'] for j in original])
                for job, old in zip(subset, original, strict=True):
                    self.assertEqual({k: job[k] for k in old if k != 'id'},
                                     {k: v for k, v in old.items() if k != 'id'})
        for bad in (original[:-1], original[:-1] + [original[0]]):
            with self.assertRaises(ValueError):
                s.make_jobs(bad)

    def test_phase_barriers_precede_preparation_training_and_inference(self):
        with patch.object(s, 'load_plan', return_value=({}, {}, dict(cohort=dict(rows=[])))), \
             patch.object(s, 'check_freeze', side_effect=ValueError('missing freeze')), \
             patch.object(s.core, 'prepare') as prepare, patch.object(s.core, 'train') as train, \
             patch.object(s.core, 'replay') as replay:
            with self.assertRaisesRegex(ValueError, 'missing freeze'):
                s.fit('plan', 'sha', 'outer-refit', 'freeze', 'sha')
            with self.assertRaisesRegex(ValueError, 'missing freeze'):
                s.outer('plan', 'sha', 'freeze', 'sha')
            prepare.assert_not_called()
            train.assert_not_called()
            replay.assert_not_called()

    def test_declaration_is_exclusive_and_does_not_fit(self):
        original = base_jobs()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.object(s, 'BASE', root), \
                 patch.object(s, 'inputs', return_value=({}, original, s.make_jobs(original), {})), \
                 patch.object(s.core, 'prepare', side_effect=AssertionError('No transforms')), \
                 patch.object(s.core, 'train', side_effect=AssertionError('No training')), \
                 patch.object(s.core, 'replay', side_effect=AssertionError('No inference')):
                pin = s.declare(root / 'fresh')
                plan = s.read(pin)
                self.assertEqual(plan['seeds'], [17, 29, 43])
                self.assertEqual(plan['innerFits'], len(plan['jobs']))
                self.assertFalse(plan['trainingPerformed'])
                self.assertFalse(plan['outerInferencePerformed'])
                self.assertFalse(plan['seed7IncludedInNewResults'])
                for output in (root / 'fresh', root.parent / 'outside'):
                    with self.assertRaises(ValueError):
                        s.declare(output)

    def test_incomplete_or_misordered_freeze_fails_before_state_reads(self):
        jobs = s.make_jobs(base_jobs())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            pin = dict(path=str(root / 'plan.json'), sha256='plan')
            frozen = dict(complete=True, plan=pin, phase='inner', trainingPerformed=True,
                          outerInferencePerformed=False, runs=[dict(jobId=j['id']) for j in jobs], **s.FLAGS)
            with patch.object(s.validation, 'run', side_effect=AssertionError('State reads forbidden')):
                for change in ('missing', 'reordered', 'wrong-seed', 'incomplete'):
                    bad = copy.deepcopy(frozen)
                    if change == 'missing': bad['runs'].pop()
                    if change == 'reordered': bad['runs'].reverse()
                    if change == 'wrong-seed': bad['runs'][0]['jobId'] = 'seed7-unweighted-old'
                    if change == 'incomplete': bad['complete'] = False
                    path = root / 'inner-freeze.json'
                    path.write_text(json.dumps(bad))
                    with self.assertRaisesRegex(ValueError, 'Incomplete 600-job'):
                        s.check_freeze(dict(jobs=jobs), pin, path, s.files.binding(path)['sha256'], 'inner', {})
                with self.assertRaisesRegex(ValueError, 'outside its declared phase path'):
                    s.check_freeze(dict(jobs=jobs), pin, root / 'other.json', 'sha', 'inner', {})

    def test_actual_refit_states_validate_and_seed_epoch_rng_tampers_fail(self):
        source = bundle(True)
        with tempfile.TemporaryDirectory() as tmp:
            for family in s.parent.FAMILIES:
                for objective in s.OBJECTIVES:
                    job = next(j for j in s.make_jobs(base_jobs())
                               if j['seed'] == 17 and j['objective'] == objective and j['family'] == family)
                    output = Path(tmp).resolve() / objective / family
                    data = s.core.prepare(source, family, job['refitRows'], objective)
                    s.core.train(data, [], output, s.config_value(job, {}, 'outer-refit', {'epoch': 2}), seed=17, epochs=2)
                    record = dict(jobId=job['id'], selectedEpoch=2, artifacts=s.parent.scalar.manifest(output))
                    s.validation.run(job, record, {}, 'outer-refit', source['cohort'])
                    bad_job = dict(job, seed=29)
                    with self.assertRaisesRegex(ValueError, 'configuration differs'):
                        s.validation.run(bad_job, record, {}, 'outer-refit', source['cohort'])
                    with self.assertRaisesRegex(ValueError, 'Final selection differs'):
                        s.validation.run(job, dict(record, selectedEpoch=3), {}, 'outer-refit', source['cohort'])
                    # Rebind the modified checkpoint through report and manifest, so byte hashing alone cannot reject it.
                    checkpoint = output / 'last.pt'
                    state = torch.load(checkpoint, map_location='cpu', weights_only=True)
                    state['rng']['torch'][0] ^= 1
                    torch.save(state, checkpoint)
                    report_path = output / 'report.json'
                    report = json.loads(report_path.read_text())
                    report['artifacts']['last.pt'] = s.files.binding(checkpoint)
                    report_path.write_text(json.dumps(report))
                    record['artifacts'] = s.parent.scalar.manifest(output)
                    with self.assertRaisesRegex(ValueError, 'Checkpoint RNG differs'):
                        s.validation.run(job, record, {}, 'outer-refit', source['cohort'])

    def test_outer_seed_and_objective_identity_checked_before_translation(self):
        source = bundle(True)
        jobs = s.make_jobs(base_jobs())
        priors = {r['targetPhone']: dict(probabilities=[.2, .2, .6]) for r in source['cohort']['rows']}
        refits = dict(runs=[dict(artifacts={'best.pt': {'path': j['id']}, 'config.json': {'path': 'config'}}) for j in jobs])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            pin = dict(path=str(root / 'plan.json'), sha256='plan')
            frozen = dict(complete=True, plan=pin, refitFreeze=dict(path='refit', sha256='sha'),
                          predictions=[dict(jobId=j['id'], artifact=dict(path=j['id'])) for j in jobs],
                          outerInferencePerformed=True, trainingPerformed=False, **s.FLAGS)
            outer_path = root / 'outer-freeze.json'
            outer_path.write_text(json.dumps(frozen))
            outer_pin = s.files.binding(outer_path)
            values = {}
            for job, refit in zip(jobs, refits['runs'], strict=True):
                values[job['id']] = dict(job={k: job[k] for k in s.validation.JOB_FIELDS},
                    refitCheckpoint=refit['artifacts']['best.pt'], prediction=dict(marker=job['id']),
                    prior=dict(rowIndices=job['outerRows'], probabilities=[[.2, .2, .6]] * 11,
                               logProbabilities=np.log(np.tile([.2, .2, .6], (11, 1))).tolist()),
                    headInferencePerformed=True, **s.FLAGS)
            def read(binding):
                if binding == outer_pin: return frozen
                if binding['path'] == 'config': return dict(priorState=priors)
                return values[binding['path']]
            with patch.object(s, 'check_freeze', return_value=(refits, {})), patch.object(s, 'read', side_effect=read):
                result, _ = s.checked_outer(dict(jobs=jobs), pin, source, outer_path, outer_pin['sha256'])
                self.assertEqual(len(result), 600)
                for field, wrong in (('seed', 7), ('objective', 'unit-weighted')):
                    first = values[jobs[0]['id']]['job']
                    previous = first[field]
                    first[field] = wrong
                    with self.assertRaisesRegex(ValueError, 'Outer seed/objective lineage differs'):
                        s.checked_outer(dict(jobs=jobs), pin, source, outer_path, outer_pin['sha256'])
                    first[field] = previous


if __name__ == '__main__':
    unittest.main()
