"""Fixed temporal comparisons, reusing frozen numeric evaluators with explicit label translation."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from middle_layer_replication import evaluation as frozen
from temporal_pooling import study as s

SEEDS, TARGETS, require = frozen.SEEDS, frozen.TARGETS, frozen.require
LABELS = {'middle': 'temporal', 'middleMixture': 'temporalMixture', 'replicationPass': 'developmentScreenPass'}


def rename(value, mapping):
    if isinstance(value, dict): return {mapping.get(k, k): rename(v, mapping) for k, v in value.items()}
    if isinstance(value, list): return [rename(v, mapping) for v in value]
    return value


def evaluate_seed(rows, indices, folds, logs):
    require(set(logs) == {'temporal', 'final', 'scalar'}, 'Expected three temporal matched predictions')
    return rename(frozen.evaluate_seed(rows, indices, folds, rename(logs, {'temporal':'middle'})), LABELS)


def summarize(seeds):
    return rename(frozen.summarize(rename(seeds, {v:k for k,v in LABELS.items()})), LABELS)


def evaluate(rows, jobs, candidates, controls):
    return rename(frozen.evaluate(rows, jobs, candidates, controls), LABELS)


def diagnostics(plan, pin, bundle):
    result = {}
    for phase in ('inner', 'refit'):
        frozen_phase = s.read(s.files.binding(Path(pin['path']).parent/(phase+'-freeze.json')))
        result[phase] = {}
        for record in frozen_phase['runs']:
            transform = torch.load(record['artifacts']['transform.pt']['path'], map_location='cpu', weights_only=True)
            result[phase][record['jobId']] = s.core.compact.diagnostics(transform, bundle['target'], bundle['positions'])
    feature = s.read(plan['inputs']['featureReport'])
    count = np.load(feature['matrices']['counts']['path'], allow_pickle=False)
    result['phaseElapsedSeconds'] = {phase: s.read(s.files.binding(Path(pin['path']).parent/(phase+'-freeze.json')))['elapsedSeconds']
                                      for phase in ('controls', 'inner', 'refit', 'outer')}
    result['emptyBins'] = dict(before=int((count[:,0] == 0).sum()), after=int((count[:,2] == 0).sum()),
                               both=int(((count[:,0] == 0) & (count[:,2] == 0)).sum()), positions=len(count))
    result['extraction'] = dict(report=plan['inputs']['featureReport'], cachedFinalExactAllRows=feature['cachedFinalExactAllRows'],
                               repeats=feature['repeats'], elapsedSeconds=feature['elapsedSeconds'])
    return result


def calculate(path, sha, outer_path, outer_sha):
    plan, pin, bundle = s.load_plan(path, sha)
    control_pin = s.checked_control_freeze(plan, pin)
    candidates, outer_pin = s.checked_outer(plan, pin, bundle, outer_path, outer_sha)
    controls = s.checked_controls(plan, bundle)
    require(controls == s.read(s.read(control_pin)['records']), 'Control replay differs from preflight')
    value = evaluate(bundle['cohort']['rows'], plan['jobs'], candidates, controls)
    diagnostic = diagnostics(plan, pin, bundle)
    s.files.guard(plan['inputs']); s.files.guard(plan['sources'])
    return dict(complete=True, study=s.STUDY, representation=s.REPRESENTATION, plan=pin, controls=control_pin,
                outerFreeze=outer_pin, diagnostics=diagnostic, **value, **s.FLAGS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('evaluate', 'verify'))
    parser.add_argument('--plan', type=Path, required=True); parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--outer-sha256', required=True)
    args = parser.parse_args(); root = args.plan.resolve().parent
    result = calculate(args.plan, args.plan_sha256, root/'outer-freeze.json', args.outer_sha256)
    if args.command == 'evaluate':
        require(not (root/'results.json').exists(), 'Preserve existing results')
        s.files.write_json(root/'results.json', result)
    else:
        require(s.read(s.files.binding(root/'results.json')) == result, 'Results do not reconstruct exactly')
    print(json.dumps(s.files.binding(root/'results.json')))


if __name__ == '__main__': main()
