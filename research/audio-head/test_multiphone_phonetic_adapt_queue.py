"""Preflight/queue contracts without launching real audio or MPS work."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import torch

import multiphone_phonetic_adapt_queue as queue
import multiphone_phonetic_preflight as preflight


class PhoneticOrchestrationTests(unittest.TestCase):
    def test_exact_six_fixed_arms_and_commands_never_resume_implicitly(self):
        jobs = queue.jobs(Path('/tmp/test-plan'))
        self.assertEqual([(j['regime'], j['arm']) for j in jobs], [
            ('all-age', 'head-only'), ('all-age', 'upper1-lr1e-6'),
            ('child-only', 'head-only'), ('child-only', 'upper1-lr1e-6'),
            ('all-age', 'upper1-lr3e-6'), ('child-only', 'upper1-lr3e-6')])
        self.assertEqual(len({j['output'] for j in jobs}), 6)
        for job in jobs:
            cmd = queue.command(job)
            self.assertNotIn('--resume', cmd)
            self.assertEqual(cmd[-2:], ['--device', 'mps'])
            self.assertEqual(cmd[cmd.index('--regime') + 1], job['regime'])
            self.assertEqual(cmd[cmd.index('--arm') + 1], job['arm'])

    def test_plan_is_fresh_and_declares_no_parent_device_lock(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(queue, 'contract', return_value={'fixture': True}):
            root = Path(temp)
            base = root / 'outputs'
            base.mkdir()
            with patch.object(queue, 'HERE', root):
                plan = queue.make_plan(base, base / 'plan.json')
                self.assertFalse(plan['parentHoldsSharedDeviceLock'])
                self.assertFalse(plan['outcomesCanChangeOrderOrCoverage'])
                self.assertTrue(plan['allSixArmsFixed'])
                self.assertEqual(len(plan['jobs']), 6)
                with self.assertRaisesRegex(ValueError, 'new plan'):
                    queue.make_plan(base, base / 'plan.json')

    def test_history_keeps_epoch_zero_and_uses_declared_age_slice(self):
        recipe = {'maximumEpochs': 6, 'patienceEpochs': 2, 'minimumImprovement': 1e-7}
        history = [{'epoch': i, 'updates': i, 'selectionMacroTargetLogLoss': value,
                    'evaluation': {'allAges': {'macroTargetLogLoss': 2-value}, 'ages6to12': {'macroTargetLogLoss': value}}}
                   for i, value in enumerate([.2, .3, .4])]
        report = {'epochsRun': 2, 'bestEpoch': 0, 'bestSelectionMacroLogLoss': .2}
        queue.verify_history(history, report, 'child-only', recipe)
        with self.assertRaisesRegex(ValueError, 'metric'):
            queue.verify_history(history, report, 'all-age', recipe)
        continued = history + [{**history[-1], 'epoch': 3}]
        with self.assertRaisesRegex(ValueError, 'patience'):
            queue.verify_history(continued, {**report, 'epochsRun': 3}, 'child-only', recipe)

    def evidence(self):
        contract = {'trainerSha256': 'trainer', 'recipeSha256': 'recipe', 'preflightSourceSha256': 'preflight', 'sources': {}}
        value = {'complete': True, 'trainerSha256': 'trainer', 'recipeSha256': 'recipe', 'sourceSha256': 'preflight',
                 'reusedSources': {}, 'device': 'mps', 'validationInferencePerformed': False, 'changedWeightsPersisted': False,
                 'cases': []}
        for regime in ('all-age', 'child-only'):
            for role in ('first-fit', 'longest-fit'):
                value['cases'].append({'regime': regime, 'role': role, 'frozenParametersUnchanged': True,
                    'trainableEncoderParameters': 12596224, 'changedUpperTensors': ['encoder.layers.23.attention.q_proj.weight'],
                    'changedHeadTensors': ['classifier.0.weight'], 'optimizerStepSeconds': [.1, .08],
                    'gradientNorms': [1., .9], 'parityBeforeUpdates': {'mpsRawVsFrozenCache': {'maximumAbsoluteProbabilityDifference': .00001}}})
        return contract, value

    def test_preflight_binding_coverage_frozen_parameters_and_gradients_must_all_pass(self):
        contract, value = self.evidence()
        queue.verify_preflight(value, contract)
        mutations = [lambda x: x.update(sourceSha256='changed'), lambda x: x['cases'].pop(),
                     lambda x: x['cases'][0].update(frozenParametersUnchanged=False),
                     lambda x: x['cases'][0].update(changedUpperTensors=['encoder.layers.0.weight']),
                     lambda x: x['cases'][0].update(gradientNorms=[float('nan'), 1.]),
                     lambda x: x['cases'][0]['parityBeforeUpdates']['mpsRawVsFrozenCache'].update(maximumAbsoluteProbabilityDifference=.1)]
        for mutate in mutations:
            changed = deepcopy(value)
            mutate(changed)
            with self.assertRaises(ValueError):
                queue.verify_preflight(changed, contract)

    def test_fit_clip_selection_cannot_choose_a_longer_validation_clip(self):
        data = {'fit': [0, 1, 2], 'cohort': {'rows': [{'clipIndex': i} for i in (0, 1, 1, 2)],
                 'clips': [{'sampleCount': n} for n in (100, 200, 10000)]}}
        self.assertEqual(preflight.cases(data), [('first-fit', 0), ('longest-fit', 1)])
        data['fit'] = []
        with self.assertRaisesRegex(ValueError, 'fit clips'):
            preflight.cases(data)

    def test_preflight_numeric_and_update_proofs_reject_nonfinite_or_wrong_allowlists(self):
        self.assertEqual(preflight.difference(torch.tensor([.2, .8]), torch.tensor([.2, .8]))['maximumAbsoluteProbabilityDifference'], 0.)
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            preflight.difference(torch.tensor([float('nan')]), torch.tensor([.2]))
        before = {'weight': torch.tensor([1.])}
        self.assertEqual(preflight.updated_names(before, {'weight': torch.tensor([2.])}), ['weight'])
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            preflight.updated_names(before, {'other': torch.tensor([2.])})
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            preflight.updated_names(before, {'weight': torch.tensor([float('inf')])})

    def test_failed_measurement_retains_failure_without_trained_weights(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'outputs' / 'measurement.json'
            with patch.object(preflight, 'HERE', root), patch.object(preflight, 'measure', side_effect=RuntimeError('lock occupied')):
                with self.assertRaisesRegex(RuntimeError, 'lock occupied'):
                    preflight.preflight(path)
            result = json.loads(path.read_text())
            self.assertFalse(result['complete'])
            self.assertFalse(result['changedWeightsPersisted'])
            self.assertFalse(result['validationInferencePerformed'])

    def test_last_replay_mutating_plan_or_measurement_cannot_publish_complete_queue(self):
        for changed_artifact in ('plan', 'preflight', 'earlier-output'):
            with self.subTest(artifact=changed_artifact), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                base = root / 'outputs'
                base.mkdir()
                paths = {name: base / (name + '.json') for name in ('plan', 'preflight')}
                declaration = {'base': str(base), 'contract': {}, 'jobs': queue.jobs(base), 'allSixArmsFixed': True}
                paths['plan'].write_text(json.dumps(declaration))
                paths['preflight'].write_text('{}')
                replays = 0
                def child(command, job, log, save):
                    nonlocal replays
                    output = Path(command[command.index('--output') + 1])
                    output.mkdir(exist_ok=True)
                    if 'train' in command:
                        for name in ('config.json', 'predictions.json', 'history.json', 'prior.json', 'epoch-zero-predictions.json'):
                            (output / name).write_text('{}')
                        (output / 'best.pt').write_bytes(b'synthetic-checkpoint')
                        (output / 'epoch-zero.json').write_text(json.dumps({'predictionsSha256': queue.digest(output / 'epoch-zero-predictions.json')}))
                        report = {'evaluation': {}, **{key + 'Sha256': queue.digest(output / name) for key, name in
                                  (('predictions', 'predictions.json'), ('history', 'history.json'), ('prior', 'prior.json'),
                                   ('epochZero', 'epoch-zero.json'))}}
                        (output / 'report.json').write_text(json.dumps(report))
                    else:
                        (output / 'replay.json').write_text(json.dumps({'exact': True, 'device': 'mps',
                            'checkpointSha256': queue.digest(output / 'best.pt'), 'evaluation': {}}))
                        replays += 1
                        if replays == 6:
                            changed = (Path(declaration['jobs'][0]['output']) / 'predictions.json'
                                       if changed_artifact == 'earlier-output' else paths[changed_artifact])
                            with changed.open('ab') as stream:
                                stream.write(b' ')
                    job.update(state='complete', exitCode=0)
                    save()
                def verified(job, contract):
                    output = Path(job['output'])
                    return {key: queue.digest(output / name) for key, name in
                            (('configSha256', 'config.json'), ('reportSha256', 'report.json'), ('checkpointSha256', 'best.pt'))}
                with patch.object(queue, 'HERE', root), patch.object(queue, 'contract', return_value={}), \
                     patch.object(queue, 'verify_preflight'), patch.object(queue, 'run_child', side_effect=child), \
                     patch.object(queue, 'verify_completed', side_effect=verified), \
                     redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                    queue.run(paths['plan'], paths['preflight'])
                ledger = json.loads((base / 'phonetic-adaptation-queue-v1.json').read_text())
                self.assertEqual(replays, 6)
                self.assertFalse(ledger['complete'])
                self.assertIn('artifact changed' if changed_artifact == 'earlier-output' else 'plan/preflight changed', ledger['failure'])


if __name__ == '__main__':
    unittest.main()
