"""Reviewed, fresh staged ridge fitting; confirmation labels open last.

No stage downloads data or performs encoder inference. Array states use explicit
JSON dtype/shape tags, never pickle. Callers launch with one-thread BLAS settings.
"""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import sys

import numpy as np

from nisqa_ingest import discovery, routing
from nisqa_ingest.discovery import binding, read, write, require, guard, checked_review, fresh
from nisqa_quality import ingestion, regression, targets

HERE = ingestion.HERE
PROTOCOL = ingestion.PROTOCOL
SOURCE_NAMES = ('training.py', 'test_training.py', 'regression.py', 'test_regression.py',
                'targets.py', 'test_targets.py')
THREAD_VARS = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')
POLICY = dict(version='nisqa-quality-training-v1', phases=['choose', 'refit-predict', 'confirm'],
              featureRows=200, fitRows=120, selectionRows=40, refitRows=160, confirmationRows=40,
              targetOrder=list(routing.TARGETS), serializer='typed JSON arrays; NPZ allow_pickle=False',
              predictionControls=['candidate', 'acoustic', 'mean', 'conditionMean'],
              confirmationBarrier='all models and predictions frozen before confirmation numeric parsing',
              confirmationReview='independent clear receipt names the exact predictionFreezeSha256',
              missingTargets='inconclusive; no dropping or replacement', implicitRestart=False,
              clippingPredictions=False, clinicalUseEligible=False, learnerJudgmentsEnabled=False)


def runtime():
    require(all(os.environ.get(key) == '1' for key in THREAD_VARS), 'Launch with one-thread BLAS/OpenMP environment')
    require(np.__version__ == '2.2.6', 'Pinned NumPy runtime required')
    return dict(python=sys.version, platform=platform.platform(), numpy=np.__version__,
                threadEnvironment={key: os.environ[key] for key in THREAD_VARS},
                linearAlgebra=np.show_config(mode='dicts'))


def _feature_plan(path, sha):
    from nisqa_quality import feature_study
    return feature_study.load(path, sha)


def _array_sha(value, dtype):
    return hashlib.sha256(np.ascontiguousarray(value, dtype=dtype).tobytes()).hexdigest()


def _npz(pin, specs):
    binding(pin['path'], pin['sha256'])
    with np.load(pin['path'], allow_pickle=False) as source:
        require(set(source.files) == set(specs), 'Unexpected array archive keys')
        result = {key: source[key] for key in specs}
    for key, (shape, dtype) in specs.items():
        value = result[key]
        require(value.shape == shape and value.dtype == np.dtype(dtype) and np.isfinite(value).all(),
                'Array shape, dtype or finiteness differs')
    return result


def encode(value):
    """Lossless typed JSON encoding for the bounded numerical model states."""
    if isinstance(value, np.ndarray):
        require(value.dtype.kind in 'fiub' and (value.dtype.kind not in 'f' or np.isfinite(value).all()),
                'Unsupported or nonfinite state array')
        return dict(__array__=True, dtype=value.dtype.str, shape=list(value.shape), data=value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict): return {key: encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [encode(item) for item in value]
    return value


def decode(value):
    if isinstance(value, dict) and '__array__' in value:
        require(set(value) == {'__array__', 'dtype', 'shape', 'data'} and value['__array__'] is True
                and value['dtype'] in ('<f8', '<f4', '<i8', '<i4', '|b1'), 'Invalid typed array state')
        result = np.array(value['data'], dtype=value['dtype'])
        require(list(result.shape) == value['shape'] and (result.dtype.kind != 'f' or np.isfinite(result).all()),
                'Typed state shape or finiteness differs')
        return result
    if isinstance(value, dict): return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list): return [decode(item) for item in value]
    return value


def _selected(selection_pin, ingestion_pin):
    frozen = read(selection_pin)
    require(frozen['complete'] is True and frozen['plan'] == ingestion_pin and frozen['selectedCount'] == 200,
            'Matching complete selection freeze required')
    value = read(frozen['selected'])
    selected = targets.validate_selected(value['selected'])
    return selected


def _joined_inputs(ingestion_plan, ingestion_sha, feature_freeze, feature_sha):
    old, old_pin = ingestion.load(ingestion_plan, ingestion_sha)
    root = Path(old_pin['path']).parent
    feature_pin = binding(feature_freeze, feature_sha); features = read(feature_pin)
    require(features['complete'] is True and features['ingestionPlan'] == old_pin
            and features['modelInferencePerformed'] is True and features['qualityTargetsInterpreted'] is False,
            'Completed target-free feature freeze required')
    feature_plan, feature_plan_pin = _feature_plan(features['plan']['path'], features['plan']['sha256'])
    require(feature_plan_pin == features['plan'], 'Feature plan binding differs')
    binding(features['review']['path'], features['review']['sha256'])
    checked_review(features['review']['path'], feature_plan_pin['sha256'])
    encoder, encoder_policy = features['encoder'], feature_plan['policies']['extraction']
    require(encoder['policy'] == encoder_policy and encoder['runtime'] == feature_plan['runtime']
            and encoder['parameterDtypes'] == ['torch.float32']
            and all(encoder[key] == encoder_policy[key] for key in ('modelId', 'revision', 'artifactSha256', 'artifactBytes')),
            'Frozen feature encoder identity differs')
    selection_pin = binding(root/'selection-freeze.json')
    audio_pin = binding(root/'audio-freeze.json'); waveforms_pin = binding(root/'waveforms-freeze.json')
    target_pin = binding(root/'fit-selection-targets-freeze.json')
    require(features['selectionFreeze'] == selection_pin and features['audioFreeze'] == audio_pin
            and features['waveformsFreeze'] == waveforms_pin, 'Feature ingestion phase joins differ')
    selected = _selected(selection_pin, old_pin)
    acquired, audited, target_freeze = read(audio_pin), read(waveforms_pin), read(target_pin)
    require(acquired['complete'] is True and acquired['plan'] == old_pin and acquired['selectionFreeze'] == selection_pin
            and acquired['selectedCount'] == 200, 'Complete 200-row acquisition required')
    require(audited['complete'] is True and audited['plan'] == old_pin and audited['selectionFreeze'] == selection_pin
            and audited['audioFreeze'] == audio_pin and audited['selectedCount'] == audited['decodedCount'] == 200
            and audited['allSelectedDecoded'] is True, 'All 200 waveforms must decode')
    require(target_freeze['complete'] is True and target_freeze['plan'] == old_pin
            and target_freeze['selectionFreeze'] == selection_pin and target_freeze['selectedCount'] == 160
            and target_freeze['completeTargets'] is True and target_freeze['confirmationTargetsAccessed'] is False,
            'Complete fitting/selection targets with closed confirmation required')
    # This phase binds the numeric file, but deliberately does not read it.
    fit_targets_pin = binding(target_freeze['targets']['path'], target_freeze['targets']['sha256'])
    arrays = _npz(features['features'], {'ssl': ((200, 1536), '<f4'), 'scalars': ((200, 6), '<f8')})
    records = read(features['records'])
    require(isinstance(records, list) and len(records) == 200, 'Exactly 200 ordered feature records required')
    for index, (record, row) in enumerate(zip(records, selected)):
        require(all(record[key] == row[key] for key in ('path', 'identitySha256', 'componentID', 'partition'))
                and type(record['validFrames']) is int and record['validFrames'] > 0,
                'Feature row identity or valid frame count differs')
        require(record['featureFloat32Sha256'] == _array_sha(arrays['ssl'][index], '<f4')
                and record['rawScalarsFloat64Sha256'] == _array_sha(arrays['scalars'][index], '<f8'),
                'Feature per-row hash differs')
    inputs = dict(ingestionPlan=old_pin, featureFreeze=feature_pin, featurePlan=feature_plan_pin,
                  selectionFreeze=selection_pin, selected=read(selection_pin)['selected'], audioFreeze=audio_pin,
                  waveformsFreeze=waveforms_pin, fitSelectionTargetsFreeze=target_pin, fitSelectionTargets=fit_targets_pin,
                  features=features['features'], featureRecords=features['records'], combinedCSV=old['inputs']['combinedCSV'])
    guard(inputs)
    return inputs, selected, arrays, features['encoder']


def declaration(ingestion_plan, ingestion_sha, feature_freeze, feature_sha):
    inputs, _, _, encoder = _joined_inputs(ingestion_plan, ingestion_sha, feature_freeze, feature_sha)
    return dict(study=POLICY['version'], protocol=binding(PROTOCOL), inputs=inputs,
                sources={name: binding(Path(__file__).parent/name) for name in SOURCE_NAMES},
                externalSources={name: binding(Path(module.__file__).resolve()) for name, module in
                                 (('discovery.py', discovery), ('routing.py', routing))},
                requirements={name: binding(HERE/name) for name in
                              ('requirements.txt', 'requirements.lock.txt', 'requirements.quality.txt')},
                runtime=runtime(), policies=dict(training=POLICY, regression=regression.POLICY, targets=targets.POLICY),
                encoder=encoder, trainingPerformed=False, confirmationTargetsAccessed=False,
                clinicalUseEligible=False, learnerJudgmentsEnabled=False)


def declare(output, ingestion_plan, ingestion_sha, feature_freeze, feature_sha):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(), 'Fresh training output required')
    plan = declaration(ingestion_plan, ingestion_sha, feature_freeze, feature_sha)
    output.mkdir(parents=True, mode=0o700); write(output/'plan.json', plan)
    return binding(output/'plan.json')


def load(path, sha):
    require(Path(path).resolve().is_relative_to(HERE/'outputs') and Path(path).name == 'plan.json', 'Canonical training plan required')
    pin = binding(path, sha); plan = read(pin); inputs = plan['inputs']
    current = declaration(inputs['ingestionPlan']['path'], inputs['ingestionPlan']['sha256'],
                          inputs['featureFreeze']['path'], inputs['featureFreeze']['sha256'])
    require(plan == current, 'Training source, protocol, inputs or runtime changed')
    return plan, pin


def _start(path, sha, review, phase, *, expected_review=None):
    plan, pin = load(path, sha); reviewed = checked_review(review, sha); root = Path(pin['path']).parent
    require(expected_review is None or reviewed == expected_review, 'Phase review changed before execution')
    fresh(root, phase); write(root/(phase+'-started.json'), dict(plan=pin, review=reviewed))
    return plan, pin, reviewed, root


def _data(plan):
    inputs = plan['inputs']; selected = _selected(inputs['selectionFreeze'], inputs['ingestionPlan'])
    arrays = _npz(inputs['features'], {'ssl': ((200, 1536), '<f4'), 'scalars': ((200, 6), '<f8')})
    authorized = [row for row in selected if row['partition'] != 'confirmation']
    result = read(inputs['fitSelectionTargets'])
    require(result['phase'] == 'fit-selection' and result['completeTargets'] is True
            and result['confirmationTargetsAccessed'] is False and result['trainingOnly'] is True
            and result['selectedPaths'] == [row['path'] for row in authorized]
            and len(result['rows']) == 160, 'Authorized numeric target phase differs')
    values = []
    for numeric, row in zip(result['rows'], authorized):
        require(all(numeric[key] == row[key] for key in ('path', 'identitySha256', 'componentID', 'partition'))
                and not numeric['errors'] and not numeric['declaredMissing'], 'Fitting numeric target join or coverage differs')
        values.append([numeric['quality'][key] for key in routing.TARGETS])
    y = regression._targets(values, rows=160)
    masks = {part: np.array([row['partition'] == part for row in selected]) for part in ('fit', 'selection', 'confirmation')}
    require([int(masks[p].sum()) for p in ('fit', 'selection', 'confirmation')] == [120, 40, 40], 'Partition counts differ')
    target_by_path = {row['path']: value for row, value in zip(authorized, y)}
    return selected, arrays, masks, target_by_path


def _choices(plan):
    selected, arrays, masks, values = _data(plan)
    fit_rows = [r for r in selected if r['partition'] == 'fit']; sel_rows = [r for r in selected if r['partition'] == 'selection']
    args = (arrays['ssl'][masks['fit']], arrays['scalars'][masks['fit']], np.array([values[r['path']] for r in fit_rows]),
            arrays['ssl'][masks['selection']], arrays['scalars'][masks['selection']], np.array([values[r['path']] for r in sel_rows]))
    captures = dict(fit_capture_conditions=[r['captureCondition'] for r in fit_rows],
                    selection_capture_conditions=[r['captureCondition'] for r in sel_rows])
    return {kind: regression.select_model(*args, kind=kind, **captures) for kind in ('candidate', 'acoustic')}


def choose(path, sha, review):
    plan, pin, reviewed, root = _start(path, sha, review, 'choose')
    try:
        choices = _choices(plan)
        for kind, state in choices.items(): write(root/'choose'/f'{kind}.json', encode(state))
        recipes = {kind: state['selectedLambda'] for kind, state in choices.items()}
        write(root/'choose/recipes.json', recipes); load(path, sha)
        artifacts = {kind: binding(root/'choose'/f'{kind}.json') for kind in choices}
        artifacts['recipes'] = binding(root/'choose/recipes.json')
        write(root/'choose-freeze.json', dict(complete=True, plan=pin, review=reviewed, artifacts=artifacts,
              fitSelectionTargets=plan['inputs']['fitSelectionTargets'], confirmationTargetsAccessed=False,
              selectedLambdas=recipes, trainingPerformed=True, clinicalUseEligible=False, learnerJudgmentsEnabled=False))
        return binding(root/'choose-freeze.json')
    except Exception as error:
        write(root/'choose-failure.json', dict(plan=pin, errorType=type(error).__name__, outputsPreserved=True)); raise


def _phase(path, sha, plan_pin, name):
    pin = binding(path, sha); frozen = read(pin)
    require(frozen['complete'] is True and frozen['plan'] == plan_pin and frozen['confirmationTargetsAccessed'] is False,
            'Matching immutable pre-confirmation freeze required')
    binding(frozen['review']['path'], frozen['review']['sha256']); checked_review(frozen['review']['path'], plan_pin['sha256'])
    guard(frozen['artifacts'])
    require(Path(pin['path']).name == name+'-freeze.json', 'Wrong phase freeze')
    return pin, frozen


def refit_predict(path, sha, review, choose_sha):
    plan, pin, reviewed, root = _start(path, sha, review, 'refit-predict')
    try:
        choose_pin, chosen = _phase(root/'choose-freeze.json', choose_sha, pin, 'choose')
        replay = _choices(plan)
        require(all(read(chosen['artifacts'][kind]) == encode(replay[kind]) for kind in replay)
                and read(chosen['artifacts']['recipes']) == chosen['selectedLambdas']
                == {kind: replay[kind]['selectedLambda'] for kind in replay}, 'Exact fitting/selection choice replay differs')
        selected, arrays, masks, values = _data(plan); train_mask = ~masks['confirmation']
        train = [r for r in selected if r['partition'] != 'confirmation']; heldout = [r for r in selected if r['partition'] == 'confirmation']
        y = np.array([values[r['path']] for r in train])
        models, predictions, clamps = {}, {}, {}
        for kind in ('candidate', 'acoustic'):
            model = regression.refit_model(arrays['ssl'][train_mask], arrays['scalars'][train_mask], y, chosen['selectedLambdas'][kind], kind=kind)
            x, diagnostics = regression.transform_features(arrays['ssl'][masks['confirmation']], arrays['scalars'][masks['confirmation']],
                                                          model['transform'], return_diagnostics=True)
            models[kind] = model; predictions[kind] = regression.predict(x, model['model']); clamps[kind] = diagnostics
        models['mean'] = y.mean(axis=0)
        models['conditionMean'] = regression.condition_mean(y, [r['captureCondition'] for r in train])
        predictions['mean'] = regression.fitted_mean(y, 40)
        predictions['conditionMean'] = regression.predict_condition_mean(models['conditionMean'], [r['captureCondition'] for r in heldout])
        write(root/'refit-predict/models.json', encode(models)); write(root/'refit-predict/clamps.json', clamps)
        write(root/'refit-predict/records.json', [{key: row[key] for key in ('path', 'identitySha256', 'componentID', 'partition', 'captureCondition')} for row in heldout])
        with (root/'refit-predict/predictions.npz').open('xb') as stream: np.savez(stream, allow_pickle=False, **predictions)
        load(path, sha)
        artifacts = {name: binding(root/'refit-predict'/file) for name, file in
                     (('models','models.json'), ('clamps','clamps.json'), ('records','records.json'), ('predictions','predictions.npz'))}
        write(root/'refit-predict-freeze.json', dict(complete=True, plan=pin, review=reviewed, chooseFreeze=choose_pin,
              artifacts=artifacts, confirmationTargetsAccessed=False, modelRows=160, predictionRows=40,
              predictionsFrozenBeforeConfirmationTargets=True, clinicalUseEligible=False, learnerJudgmentsEnabled=False))
        return binding(root/'refit-predict-freeze.json')
    except Exception as error:
        write(root/'refit-predict-failure.json', dict(plan=pin, errorType=type(error).__name__, outputsPreserved=True)); raise


def confirm(path, sha, review, prediction_sha):
    # A generic source-clear receipt can authorize choose/refit, but it cannot
    # authorize numerical confirmation labels. Check this separate receipt and
    # its exact immutable prediction binding before creating phase artifacts.
    plan_path = Path(path).resolve(); root = plan_path.parent
    require(plan_path.name == 'plan.json' and plan_path.is_relative_to(HERE/'outputs'), 'Canonical training plan required')
    reviewed = checked_review(review, sha); receipt = read(reviewed)
    require(receipt.get('predictionFreezeSha256') == prediction_sha
            and isinstance(prediction_sha, str) and len(prediction_sha) == 64,
            'Independent review of the exact prediction freeze required for confirmation')
    require(not Path(reviewed['path']).resolve().is_relative_to(root/'confirm'),
            'Confirmation receipt must be outside the confirmation output phase')
    binding(root/'refit-predict-freeze.json', prediction_sha)
    plan, pin, reviewed, root = _start(path, sha, review, 'confirm', expected_review=reviewed)
    try:
        prediction_pin, frozen = _phase(root/'refit-predict-freeze.json', prediction_sha, pin, 'refit-predict')
        _, chosen = _phase(frozen['chooseFreeze']['path'], frozen['chooseFreeze']['sha256'], pin, 'choose')
        require(frozen['modelRows'] == 160 and frozen['predictionRows'] == 40
                and frozen['predictionsFrozenBeforeConfirmationTargets'] is True, 'Prediction barrier differs')
        models = decode(read(frozen['artifacts']['models']))
        require(all(models[k]['model']['fitRows'] == 160 and models[k]['model']['lambda'] == chosen['selectedLambdas'][k]
                    for k in ('candidate', 'acoustic')), 'Refitted model recipe differs')
        predictions = _npz(frozen['artifacts']['predictions'], {name: ((40, 5), '<f8') for name in POLICY['predictionControls']})
        selected = _selected(plan['inputs']['selectionFreeze'], plan['inputs']['ingestionPlan'])
        expected = [{key: row[key] for key in ('path', 'identitySha256', 'componentID', 'partition', 'captureCondition')}
                    for row in selected if row['partition'] == 'confirmation']
        require(read(frozen['artifacts']['records']) == expected, 'Confirmation prediction identity joins differ')
        # All model and prediction bindings have been checked above. No model
        # fitting or prediction occurs after this numerical-target barrier.
        csv_pin = plan['inputs']['combinedCSV']; binding(csv_pin['path'], csv_pin['sha256'])
        try:
            with Path(csv_pin['path']).open(newline='', encoding='utf-8') as stream:
                result = targets.parse_partition_targets(stream, selected, 'confirmation')
            require(result['phase'] == 'confirmation' and result['confirmationTargetsAccessed'] is True
                    and result['trainingOnly'] is True and len(result['rows']) == 40
                    and result['selectedPaths'] == [r['path'] for r in expected]
                    and all(all(numeric[key] == row[key] for key in ('path', 'identitySha256', 'componentID', 'partition'))
                            for numeric, row in zip(result['rows'], expected)), 'Confirmation target joins differ')
        except ValueError:
            result = dict(phase='confirmation', confirmationTargetsAccessed=True, completeTargets=False,
                          rows=[], selectedPaths=[r['path'] for r in expected], missingCounts=None, invalidCounts=None,
                          reason='Fixed confirmation target parse or coverage failed; no replacement', errorType='ValueError')
        write(root/'confirm/targets.json', result)
        if result['completeTargets']:
            y = np.array([[row['quality'][name] for name in routing.TARGETS] for row in result['rows']])
            report = regression.confirmation_report(y, predictions['candidate'], predictions['acoustic'], predictions['mean'],
                predictions['conditionMean'], [r['componentID'] for r in expected], [r['captureCondition'] for r in expected])
            report.update(status='complete', completeTargets=True)
        else:
            report = dict(status='inconclusive', completeTargets=False, reason='Incomplete or invalid fixed confirmation targets; no dropping or replacement',
                          missingCounts=result['missingCounts'], invalidCounts=result['invalidCounts'], passesContinuationScreen=False)
        report.update(clinicalUseEligible=False, learnerJudgmentsEnabled=False)
        write(root/'confirm/results.json', report); load(path, sha)
        write(root/'confirm-freeze.json', dict(complete=True, plan=pin, review=reviewed, predictionFreeze=prediction_pin,
              artifacts={name: binding(root/'confirm'/file) for name, file in (('targets','targets.json'), ('results','results.json'))},
              confirmationTargetsAccessed=True, completeTargets=result['completeTargets'], clinicalUseEligible=False, learnerJudgmentsEnabled=False))
        return binding(root/'confirm-freeze.json')
    except Exception as error:
        write(root/'confirm-failure.json', dict(plan=pin, errorType=type(error).__name__, outputsPreserved=True)); raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'choose', 'refit-predict', 'confirm'))
    parser.add_argument('--output'); parser.add_argument('--ingestion-plan'); parser.add_argument('--ingestion-sha256')
    parser.add_argument('--feature-freeze'); parser.add_argument('--feature-sha256')
    parser.add_argument('--plan'); parser.add_argument('--plan-sha256'); parser.add_argument('--review')
    parser.add_argument('--choose-sha256'); parser.add_argument('--prediction-sha256')
    args = parser.parse_args()
    if args.command == 'declare': result = declare(args.output, args.ingestion_plan, args.ingestion_sha256, args.feature_freeze, args.feature_sha256)
    elif args.command == 'choose': result = choose(args.plan, args.plan_sha256, args.review)
    elif args.command == 'refit-predict': result = refit_predict(args.plan, args.plan_sha256, args.review, args.choose_sha256)
    else: result = confirm(args.plan, args.plan_sha256, args.review, args.prediction_sha256)
    print(result['sha256'])


if __name__ == '__main__': main()
