"""Synthetic staged study fixtures; no corpus features, audio, or targets."""
import copy
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from nisqa_ingest import routing
from nisqa_ingest.discovery import binding, read, write
from nisqa_quality import extraction, selection, targets, training as d
from nisqa_quality.test_selection import fixture as lineage_fixture


class TrainingTests(unittest.TestCase):
    def fixture(self, parent, *, confirmation_token=None):
        parent = parent.resolve()
        here = parent/'workspace'; (here/'outputs').mkdir(parents=True)
        for name in ('requirements.txt', 'requirements.lock.txt', 'requirements.quality.txt'):
            (here/name).write_text('synthetic pinned requirements\n')
        protocol = parent/'protocol.md'; protocol.write_text('synthetic immutable phase protocol\n')
        old_root = here/'outputs/ingestion'; old_root.mkdir()
        feature_root = here/'outputs/features'; feature_root.mkdir()
        rows, pilot = lineage_fixture()
        selected = selection.select_study(selection.build_components(rows, pilot))['selected']
        rng = np.random.default_rng(471)
        ssl = np.zeros((200, 1536), dtype='<f4'); ssl[:, :32] = rng.normal(size=(200, 32))
        scalars = rng.uniform(.1, .3, size=(200, 6)).astype('<f8'); scalars[:, 4] = 0.; scalars[:, 5] = 6.
        csv_path = old_root/'combined.csv'
        with csv_path.open('w', newline='') as stream:
            writer = csv.writer(stream); writer.writerow(['db', 'filepath_deg', *routing.TARGETS])
            for index, row in enumerate(selected):
                value = float(3 + .3 * np.tanh(float(ssl[index, 0])))
                token = confirmation_token if row['partition'] == 'confirmation' and confirmation_token is not None else repr(value)
                writer.writerow([routing.TRAIN, row['path'], *[token] * 5])
            writer.writerow(['NISQA_VAL_LIVE', 'NISQA_VAL_LIVE/deg/never.wav', 'EVALUATION_SENTINEL'])
        old = dict(inputs=dict(combinedCSV=binding(csv_path)))
        write(old_root/'plan.json', old); old_pin = binding(old_root/'plan.json')
        write(old_root/'selected.json', dict(selected=selected))
        write(old_root/'selection-freeze.json', dict(complete=True, plan=old_pin, selectedCount=200,
                                                   selected=binding(old_root/'selected.json')))
        selection_pin = binding(old_root/'selection-freeze.json')
        write(old_root/'audio-freeze.json', dict(complete=True, plan=old_pin, selectionFreeze=selection_pin, selectedCount=200))
        audio_pin = binding(old_root/'audio-freeze.json')
        write(old_root/'waveforms-freeze.json', dict(complete=True, plan=old_pin, selectionFreeze=selection_pin,
                                                   audioFreeze=audio_pin, selectedCount=200, decodedCount=200, allSelectedDecoded=True))
        with csv_path.open(newline='') as stream:
            authorized = targets.parse_partition_targets(stream, selected, 'fit-selection')
        write(old_root/'fit-targets.json', authorized)
        write(old_root/'fit-selection-targets-freeze.json', dict(complete=True, plan=old_pin,
            selectionFreeze=selection_pin, targets=binding(old_root/'fit-targets.json'), selectedCount=160,
            completeTargets=True, confirmationTargetsAccessed=False))
        feature_plan = dict(study='synthetic feature plan', policies=dict(extraction=copy.deepcopy(extraction.POLICY)), runtime=dict(device='synthetic'))
        write(feature_root/'plan.json', feature_plan); feature_plan_pin = binding(feature_root/'plan.json')
        write(feature_root/'review.json', dict(planSha256=feature_plan_pin['sha256'], verdict='clear', blockingFindings=[], independent=True, reviewer='synthetic feature reviewer'))
        with (feature_root/'features.npz').open('xb') as stream:
            np.savez(stream, ssl=ssl, scalars=scalars)
        records = [dict(**{key: row[key] for key in ('path', 'identitySha256', 'componentID', 'partition')},
                        featureFloat32Sha256=d._array_sha(ssl[index], '<f4'),
                        rawScalarsFloat64Sha256=d._array_sha(scalars[index], '<f8'), validFrames=30)
                   for index, row in enumerate(selected)]
        write(feature_root/'records.json', records)
        encoder = dict(**{key: extraction.POLICY[key] for key in ('modelId', 'revision', 'artifactSha256', 'artifactBytes')},
                       policy=copy.deepcopy(extraction.POLICY), runtime=feature_plan['runtime'], parameterDtypes=['torch.float32'])
        write(feature_root/'feature-freeze.json', dict(complete=True, plan=feature_plan_pin, review=binding(feature_root/'review.json'),
            ingestionPlan=old_pin, selectionFreeze=selection_pin, audioFreeze=audio_pin,
            waveformsFreeze=binding(old_root/'waveforms-freeze.json'),
            features=binding(feature_root/'features.npz'), records=binding(feature_root/'records.json'),
            encoder=encoder,
            modelInferencePerformed=True, qualityTargetsInterpreted=False))
        feature_pin = binding(feature_root/'feature-freeze.json')
        return dict(here=here, protocol=protocol, old=old, oldPin=old_pin, featurePlan=feature_plan,
                    featurePlanPin=feature_plan_pin, featurePin=feature_pin, selected=selected,
                    ssl=ssl, scalars=scalars, oldRoot=old_root, featureRoot=feature_root)

    def patches(self, value):
        self.enterContext(patch.object(d, 'HERE', value['here']))
        self.enterContext(patch.object(d, 'PROTOCOL', value['protocol']))
        self.enterContext(patch.object(d.ingestion, 'load', return_value=(value['old'], value['oldPin'])))
        self.enterContext(patch.object(d, '_feature_plan', return_value=(value['featurePlan'], value['featurePlanPin'])))

    def declare(self, value):
        self.patches(value)
        pin = d.declare(value['here']/'outputs/training', value['oldPin']['path'], value['oldPin']['sha256'],
                        value['featurePin']['path'], value['featurePin']['sha256'])
        review = Path(pin['path']).parent/'review.json'
        write(review, dict(planSha256=pin['sha256'], verdict='clear', blockingFindings=[], independent=True, reviewer='synthetic independent reviewer'))
        return pin, review

    def confirmation_review(self, pin, predicted):
        path = Path(pin['path']).parent/'confirmation-review.json'
        write(path, dict(planSha256=pin['sha256'], predictionFreezeSha256=predicted['sha256'],
              verdict='clear', blockingFindings=[], independent=True, reviewer='synthetic prediction reviewer'))
        return path

    def phases(self, pin, review):
        chosen = d.choose(pin['path'], pin['sha256'], review)
        predicted = d.refit_predict(pin['path'], pin['sha256'], review, chosen['sha256'])
        return chosen, predicted

    def test_full_workflow_target_barrier_choices_models_controls_and_results(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.fixture(Path(directory))
            with patch.object(d, 'read', wraps=d.read) as reader:
                pin, review = self.declare(value)
                numeric_path = str(value['oldRoot']/'fit-targets.json')
                self.assertFalse(any(call.args[0].get('path') == numeric_path for call in reader.call_args_list))
            with (patch.object(d.targets, 'parse_partition_targets', side_effect=AssertionError('Confirmation closed')),
                  patch.object(d.np, 'savez', wraps=d.np.savez) as save_npz):
                chosen, predicted = self.phases(pin, review)
            self.assertEqual(save_npz.call_count, 1)
            self.assertIs(save_npz.call_args.kwargs['allow_pickle'], False)
            chosen_value = read(chosen)
            for kind in ('candidate', 'acoustic'):
                saved = d.decode(read(chosen_value['artifacts'][kind]))
                self.assertEqual(len(saved['grid']), 4)
                self.assertEqual(saved['transform']['joinedScaler']['constant'].dtype, np.dtype(bool))
                self.assertEqual(saved['selectedLambda'], chosen_value['selectedLambdas'][kind])
            prediction_value = read(predicted)
            self.assertFalse(prediction_value['confirmationTargetsAccessed'])
            self.assertTrue(prediction_value['predictionsFrozenBeforeConfirmationTargets'])
            models = d.decode(read(prediction_value['artifacts']['models']))
            self.assertEqual(models['candidate']['model']['fitRows'], 160)
            self.assertEqual(models['conditionMean']['fitCounts'], {'phone': 80, 'Skype': 80})
            parser = d.targets.parse_partition_targets
            with (patch.object(d.targets, 'parse_partition_targets', wraps=parser) as parsed,
                 patch.object(d.regression, 'fit_ridge', side_effect=AssertionError('No fitting after barrier')),
                 patch.object(d.regression, 'predict', side_effect=AssertionError('No prediction after barrier'))):
                final = d.confirm(pin['path'], pin['sha256'], self.confirmation_review(pin, predicted), predicted['sha256'])
            self.assertEqual(parsed.call_count, 1)
            self.assertEqual(parsed.call_args.args[2], 'confirmation')
            result = read(read(final)['artifacts']['results'])
            self.assertEqual(set(result['models']), {'candidate', 'acoustic', 'mean', 'conditionMean'})
            self.assertEqual(result['bootstrap']['draws'], 10000)
            self.assertFalse(result['clinicalUseEligible'] or result['learnerJudgmentsEnabled'])
            for artifact in Path(pin['path']).parent.rglob('*.json'):
                self.assertNotIn('EVALUATION_SENTINEL', artifact.read_text())

    def test_missing_and_invalid_confirmation_targets_inconclusive_without_dropping(self):
        for token in ('', 'NaN', 'SECRET_INVALID_TOKEN'):
            with self.subTest(token=token), tempfile.TemporaryDirectory() as directory:
                value = self.fixture(Path(directory), confirmation_token=token)
                pin, review = self.declare(value)
                with patch.object(d.targets, 'parse_partition_targets', side_effect=AssertionError('Confirmation closed')):
                    _, predicted = self.phases(pin, review)
                final = d.confirm(pin['path'], pin['sha256'], self.confirmation_review(pin, predicted), predicted['sha256'])
                frozen = read(final); numeric = read(frozen['artifacts']['targets']); result = read(frozen['artifacts']['results'])
                self.assertEqual(len(numeric['rows']), 40)
                self.assertFalse(frozen['completeTargets'])
                self.assertEqual(result['status'], 'inconclusive')
                self.assertFalse(result['passesContinuationScreen'])
                self.assertNotIn('SECRET_INVALID_TOKEN', repr(numeric))

    def test_model_and_prediction_tamper_block_before_confirmation_reader(self):
        for kind in ('models', 'predictions', 'records', 'clamps'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                value = self.fixture(Path(directory)); pin, review = self.declare(value)
                _, predicted = self.phases(pin, review)
                artifact = Path(read(predicted)['artifacts'][kind]['path'])
                artifact.write_bytes(artifact.read_bytes() + b'\nTAMPER')
                with patch.object(d.targets, 'parse_partition_targets', side_effect=AssertionError('Reader must stay closed')) as reader:
                    with self.assertRaisesRegex(ValueError, 'Pinned artifact'):
                        d.confirm(pin['path'], pin['sha256'], self.confirmation_review(pin, predicted), predicted['sha256'])
                self.assertEqual(reader.call_count, 0)

    def test_confirmation_requires_specific_prediction_review_before_phase_or_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.fixture(Path(directory)); pin, review = self.declare(value)
            _, predicted = self.phases(pin, review); root = Path(pin['path']).parent
            wrong = root/'wrong-prediction-review.json'
            write(wrong, dict(planSha256=pin['sha256'], predictionFreezeSha256='0'*64,
                  verdict='clear', blockingFindings=[], independent=True, reviewer='synthetic prediction reviewer'))
            wrong_plan = root/'wrong-plan-review.json'
            write(wrong_plan, dict(planSha256='0'*64, predictionFreezeSha256=predicted['sha256'],
                  verdict='clear', blockingFindings=[], independent=True, reviewer='synthetic prediction reviewer'))
            for receipt in (review, wrong, wrong_plan):
                with self.subTest(receipt=receipt.name), patch.object(d, '_start', wraps=d._start) as started, \
                     patch.object(d.targets, 'parse_partition_targets', side_effect=AssertionError('closed')) as reader:
                    with self.assertRaises(ValueError): d.confirm(pin['path'], pin['sha256'], receipt, predicted['sha256'])
                    started.assert_not_called(); reader.assert_not_called()
                self.assertFalse((root/'confirm-started.json').exists())
                self.assertFalse((root/'confirm').exists())
            specific = self.confirmation_review(pin, predicted)
            with patch.object(d.targets, 'parse_partition_targets', wraps=d.targets.parse_partition_targets) as reader:
                frozen = read(d.confirm(pin['path'], pin['sha256'], specific, predicted['sha256']))
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(frozen['review'], binding(specific))
            self.assertEqual(frozen['predictionFreeze'], predicted)

    def test_external_helpers_bind_resolved_import_paths_and_detect_changes(self):
        for name, module in (('discovery.py', d.discovery), ('routing.py', d.routing)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                value = self.fixture(Path(directory)); copy_path = Path(directory)/name
                copy_path.write_bytes(Path(module.__file__).read_bytes())
                with patch.object(module, '__file__', str(copy_path)):
                    pin, review = self.declare(value); plan = read(pin)
                    self.assertEqual(plan['externalSources'][name], binding(copy_path.resolve()))
                    self.assertFalse(copy_path.resolve().is_relative_to(value['here']))
                    copy_path.write_bytes(copy_path.read_bytes()+b'\n# changed helper\n')
                    with patch.object(d.targets, 'parse_partition_targets', side_effect=AssertionError('closed')) as reader:
                        with self.assertRaisesRegex(ValueError, 'Training source'): d.choose(pin['path'], pin['sha256'], review)
                        reader.assert_not_called()
                    self.assertFalse((Path(pin['path']).parent/'choose-started.json').exists())

    def test_source_runtime_protocol_input_review_and_fresh_guards(self):
        for kind in ('runtime', 'protocol', 'requirements', 'features', 'review', 'source'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                value = self.fixture(Path(directory)); pin, review = self.declare(value)
                context = patch.object(d, 'runtime', return_value={'changed': True}) if kind == 'runtime' else patch.object(d, 'SOURCE_NAMES', d.SOURCE_NAMES + ('missing-scope.py',)) if kind == 'source' else patch.object(d, 'POLICY', d.POLICY)
                if kind == 'protocol': value['protocol'].write_text('changed')
                if kind == 'requirements': (value['here']/'requirements.quality.txt').write_text('changed')
                if kind == 'features': (value['featureRoot']/'features.npz').write_bytes(b'changed')
                if kind == 'review': review.write_text('{}')
                with context, patch.object(d.targets, 'parse_partition_targets', side_effect=AssertionError('closed')):
                    with self.assertRaises(ValueError): d.choose(pin['path'], pin['sha256'], review)
        with tempfile.TemporaryDirectory() as directory:
            value = self.fixture(Path(directory)); pin, review = self.declare(value)
            chosen = d.choose(pin['path'], pin['sha256'], review)
            with self.assertRaisesRegex(ValueError, 'no implicit restart'):
                d.choose(pin['path'], pin['sha256'], review)
            with self.assertRaisesRegex(ValueError, 'Fresh training output'):
                d.declare(Path(pin['path']).parent, value['oldPin']['path'], value['oldPin']['sha256'], value['featurePin']['path'], value['featurePin']['sha256'])

    def test_exact_choice_replay_rejects_rebound_wrong_lambda(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.fixture(Path(directory)); pin, review = self.declare(value)
            chosen = d.choose(pin['path'], pin['sha256'], review)
            freeze = read(chosen); recipes = dict(freeze['selectedLambdas']); recipes['candidate'] = 10. if recipes['candidate'] != 10. else .01
            recipe_path = Path(freeze['artifacts']['recipes']['path']); recipe_path.unlink(); write(recipe_path, recipes)
            freeze['artifacts']['recipes'] = binding(recipe_path); freeze['selectedLambdas'] = recipes
            Path(chosen['path']).unlink(); write(chosen['path'], freeze); rebound = binding(chosen['path'])
            with self.assertRaisesRegex(ValueError, 'choice replay'):
                d.refit_predict(pin['path'], pin['sha256'], review, rebound['sha256'])
            self.assertFalse((Path(pin['path']).parent/'refit-predict-freeze.json').exists())

    def test_row_feature_hash_and_partition_identity_mismatches_before_declare(self):
        for kind in ('hash', 'identity', 'dtype'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                value = self.fixture(Path(directory)); self.patches(value)
                freeze = read(value['featurePin'])
                if kind == 'dtype':
                    with Path(freeze['features']['path']).open('wb') as stream:
                        np.savez(stream, ssl=value['ssl'].astype(np.float64), scalars=value['scalars'])
                    freeze['features'] = binding(freeze['features']['path'])
                else:
                    records = read(freeze['records'])
                    records[0]['featureFloat32Sha256' if kind == 'hash' else 'identitySha256'] = '0' * 64
                    Path(freeze['records']['path']).unlink(); write(freeze['records']['path'], records)
                    freeze['records'] = binding(freeze['records']['path'])
                Path(value['featurePin']['path']).unlink(); write(value['featurePin']['path'], freeze)
                feature_pin = binding(value['featurePin']['path'])
                with self.assertRaises(ValueError):
                    d.declare(value['here']/'outputs/training', value['oldPin']['path'], value['oldPin']['sha256'], feature_pin['path'], feature_pin['sha256'])
                self.assertFalse((value['here']/'outputs/training').exists())

    def test_typed_boolean_roundtrip_and_unbounded_arrays(self):
        state = {'constant': np.array([True, False]), 'predictions': np.array([[-2., 7.]], dtype='<f8')}
        restored = d.decode(d.encode(state))
        self.assertEqual(restored['constant'].dtype, np.dtype(bool))
        np.testing.assert_array_equal(restored['predictions'], state['predictions'])
        with self.assertRaises(ValueError): d.decode(dict(__array__=True, dtype='object', shape=[1], data=['x']))
        with self.assertRaises(ValueError): d.encode(np.array([np.nan]))

    def test_unbounded_prediction_arrays_survive_driver_and_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.fixture(Path(directory)); pin, review = self.declare(value)
            chosen = d.choose(pin['path'], pin['sha256'], review)
            original = d.regression.predict
            def unbounded(features, model):
                result = original(features, model)
                return result + 10 if model['fitRows'] == 160 else result
            with patch.object(d.regression, 'predict', side_effect=unbounded):
                predicted = d.refit_predict(pin['path'], pin['sha256'], review, chosen['sha256'])
            saved = d._npz(read(predicted)['artifacts']['predictions'], {name: ((40,5), '<f8') for name in d.POLICY['predictionControls']})
            self.assertTrue(np.all(saved['candidate'] > 5))
            final = d.confirm(pin['path'], pin['sha256'], self.confirmation_review(pin, predicted), predicted['sha256'])
            self.assertGreater(read(read(final)['artifacts']['results'])['models']['candidate']['macroMAE'], 7)

    def test_confirmation_parse_coverage_error_preserved_as_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.fixture(Path(directory)); pin, review = self.declare(value)
            _, predicted = self.phases(pin, review)
            with patch.object(d.targets, 'parse_partition_targets', side_effect=ValueError('Untrusted CSV token')):
                final = d.confirm(pin['path'], pin['sha256'], self.confirmation_review(pin, predicted), predicted['sha256'])
            result = read(read(final)['artifacts']['results'])
            self.assertEqual(result['status'], 'inconclusive')
            self.assertNotIn('Untrusted CSV token', repr(result))


if __name__ == '__main__': unittest.main()
