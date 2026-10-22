"""Synthetic membership, scalar-decision and phase-barrier tests.

Never reads the cohort, ratings, feature arrays, audio, checkpoints or
historical predictions, and never fits or scores a head.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

from lexical_feasibility.study import word_group
from posterior_pooling import study as s

WORDS = {}
for number in range(500):
    WORDS.setdefault(word_group(f'WORD{number}'), f'WORD{number}')
    if len(WORDS) == 5:
        break


def fixture():
    """Three seeds x 25 cells with filtered outer rows, per-cell purged roles and a temporal copy."""
    rows, lexicon, cells = [], {}, []
    for number in range(25):
        wg = number % 5
        base = len(rows)
        for age, legacy, word in ((8, 0, WORDS[wg]), (8, None, WORDS[wg]), (30, 1, WORDS[wg])):
            rows.append(dict(age=age, legacyRowIndex=legacy, targetWord=word.lower()))
        for _ in range(3):
            rows.append(dict(age=8, legacyRowIndex=None, targetWord=WORDS[(wg+1) % 5]))
        lexicon[base] = [WORDS[wg]]
        for i in range(base+3, base+6):
            lexicon[i] = [WORDS[(wg+1) % 5]]
        cells.append(dict(outer=[base, base+1, base+2], fit=[base+3], selection=[base+4], added=[base+5]))
    historical, temporal = [], []
    for seed in s.SEEDS:
        for family in ('scalars', 'pca16-scalars'):
            for number, cell in enumerate(cells):
                sf, wg = divmod(number, 5)
                historical.append(dict(id=f'seed{seed}-unweighted-child-only-{family}-s{sf}-w{wg}',
                                       baseJobId=f'child-only-{family}-s{sf}-w{wg}', seed=seed, objective='unweighted',
                                       family=family, regime='child-only', speakerFold=sf, wordGroup=wg,
                                       fitRows=cell['fit'], selectionRows=cell['selection'], addedValidationRows=cell['added'],
                                       refitRows=cell['fit']+cell['selection']+cell['added'], outerRows=cell['outer']))
        originals = {j['id']: j for j in historical}
        for number, cell in enumerate(cells):
            sf, wg = divmod(number, 5)
            prefix = f'seed{seed}-unweighted-child-only-'
            refs = dict(scalar=prefix+f'scalars-s{sf}-w{wg}', final=prefix+f'pca16-scalars-s{sf}-w{wg}')
            final = originals[refs['final']]
            temporal.append(dict(final, id='temporal-'+final['id'], outerRows=cell['outer'][:1],
                                 representation=s.TEMPORAL_REPRESENTATION, references=refs))
    return historical, temporal, rows, lexicon


class MembershipTests(unittest.TestCase):
    def setUp(self):
        self.historical, self.temporal, self.rows, self.lexicon = fixture()

    def cells(self, temporal=None, historical=None):
        return s.make_cells(historical or self.historical, temporal or self.temporal, self.rows, positions=25)

    def test_cells_copy_temporal_order_roles_and_child_coverage(self):
        cells = self.cells()
        jobs = s.make_jobs(cells, self.historical)
        self.assertEqual((len(cells), len(jobs)), (75, 225))
        self.assertEqual([j['arm'] for j in jobs[:3]], ['candidate', 'freshHard', 'scalar'])
        originals = {j['id']: j for j in self.historical}
        for cell in cells:
            self.assertEqual(len(cell['outerRows']), 1)
            self.assertTrue(all(self.rows[i]['legacyRowIndex'] is not None and self.rows[i]['age'] <= 12 for i in cell['outerRows']))
        for job in jobs:
            old = originals[job['references']['scalar' if job['arm'] == 'scalar' else 'final']]
            self.assertTrue(job['id'].startswith('posterior-'+job['arm']+'-'))
            self.assertEqual({k: job[k] for k in s.validation.JOB_FIELDS if k != 'id'},
                             {k: old[k] for k in s.validation.JOB_FIELDS if k != 'id'})
            self.assertEqual([job[k] for k in s.ROLES], [old[k] for k in s.ROLES])
            self.assertEqual((job['study'], job['representation']), (s.STUDY, s.REPRESENTATIONS[job['arm']]))
        for seed in s.SEEDS:
            self.assertEqual(sorted(i for c in cells if c['seed'] == seed for i in c['outerRows']),
                             [i for i, r in enumerate(self.rows) if r['age'] <= 12 and r['legacyRowIndex'] is not None])

    def test_reordered_mismatched_or_incomplete_membership_rejected(self):
        changes = []
        temporal = copy.deepcopy(self.temporal); temporal[0]['fitRows'] = list(reversed(temporal[0]['fitRows'] + [999]))
        changes.append((temporal, None))
        temporal = copy.deepcopy(self.temporal); temporal[3]['outerRows'] = []
        changes.append((temporal, None))
        temporal = copy.deepcopy(self.temporal); temporal[4]['extra'] = True
        changes.append((temporal, None))
        temporal = copy.deepcopy(self.temporal); temporal[1], temporal[2] = temporal[2], temporal[1]
        changes.append((temporal, None))
        for field, value in (('seed', 7), ('objective', 'unit-weighted'), ('family', 'scalars')):
            historical = copy.deepcopy(self.historical)
            next(j for j in historical if j['id'] == 'seed29-unweighted-child-only-pca16-scalars-s1-w2')[field] = value
            changes.append((None, historical))
        for temporal, historical in changes:
            with self.assertRaises(ValueError):
                self.cells(temporal, historical)

    def test_role_disjointness_and_whole_utterance_purging(self):
        cells = self.cells()
        originals = {j['id']: j for j in self.historical}
        s.check_purging(cells, originals, self.rows, self.lexicon)
        cell = cells[7]; job = originals[cell['references']['final']]
        lexicon = dict(self.lexicon)
        lexicon[job['fitRows'][0]] = [WORDS[cell['wordGroup']]]
        with self.assertRaisesRegex(s.IntegrityFailure, 'Held-out word'):
            s.check_purging(cells, originals, self.rows, lexicon)
        broken = copy.deepcopy(originals); broken[cell['references']['final']]['selectionRows'] = job['fitRows']
        with self.assertRaisesRegex(s.IntegrityFailure, 'disjointness'):
            s.check_purging(cells, broken, self.rows, self.lexicon)
        rows = copy.deepcopy(self.rows); rows[cell['outerRows'][0]]['targetWord'] = WORDS[(cell['wordGroup']+2) % 5]
        with self.assertRaisesRegex(s.IntegrityFailure, 'Outer target'):
            s.check_purging(cells, originals, rows, self.lexicon)


def outcomes(count, failure=None, cell_failure=None):
    global_checks = dict.fromkeys(s.GLOBAL_CHECKS, s.PASS)
    cells = [dict(cell=f'c{i}', jobId=f'ref{i}', checks=dict.fromkeys(s.CELL_CHECKS, s.PASS)) for i in range(count)]
    if failure:
        global_checks['historicalRuntime'] = failure
        for cell in cells: cell['checks']['savedState'] = s.SKIP
    if cell_failure:
        cells[-1]['checks'].update(outerReplay=cell_failure, savedState=s.SKIP)
    return global_checks, cells


class ScalarDecisionTests(unittest.TestCase):
    def test_all_cell_reuse_or_all_cell_fallback_only(self):
        decision = s.decide(*outcomes(75))
        self.assertEqual((decision['scalarReuse'], decision['requiredJobs']['inner'], decision['failureCodes']), (True, 150, []))
        for arguments in (dict(cell_failure='outer-replay-differs'), dict(failure='historical-runtime-differs')):
            decision = s.decide(*outcomes(75, **arguments))
            self.assertFalse(decision['scalarReuse'])
            self.assertEqual(decision['mode'], 'fresh-scalar-fallback-all-cells')
            self.assertEqual(decision['requiredJobs'], dict(inner=225, refit=225, outer=225))
        self.assertEqual(decision['failedCells'], [])
        self.assertEqual(s.decide(*outcomes(75, cell_failure='outer-replay-differs'))['failedCells'], ['c74'])

    def test_unexplained_skip_unknown_or_incomplete_outcomes_stop(self):
        global_checks, cells = outcomes(3)
        cells[0]['checks']['savedState'] = s.SKIP
        with self.assertRaisesRegex(s.IntegrityFailure, 'Unevaluated'):
            s.decide(global_checks, cells, 3)
        global_checks, cells = outcomes(3)
        cells[1]['checks']['recipe'] = 'looks-worse'
        with self.assertRaisesRegex(s.IntegrityFailure, 'unknown'):
            s.decide(global_checks, cells, 3)
        global_checks, cells = outcomes(3)
        with self.assertRaises(s.IntegrityFailure):
            s.decide(global_checks, cells[:2], 3)
        del cells[0]['checks']['outerReplay']
        with self.assertRaises(s.IntegrityFailure):
            s.decide(global_checks, cells, 3)

    def test_only_explicit_compatibility_failures_are_recorded(self):
        self.assertEqual(s.outcome(lambda: s.compatible(True, 'recipe-differs')), s.PASS)
        self.assertEqual(s.outcome(lambda: s.compatible(False, 'recipe-differs')), 'recipe-differs')
        for error in (s.IntegrityFailure('corrupt'), ValueError('generic'), KeyError('missing'), RuntimeError('unpickle')):
            def check(error=error): raise error
            with self.assertRaises(type(error)):
                s.outcome(check)
        with self.assertRaises(s.IntegrityFailure):
            s.CompatibilityFailure('model-looked-worse')
        self.assertFalse(issubclass(s.CompatibilityFailure, ValueError))

    def test_hash_inventory_binding_and_identity_failures_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ref = 'seed17-unweighted-child-only-scalars-s0-w0'
            def run(names, label):
                artifacts = {}
                for name in names:
                    (root/(label+name)).write_text(label+name)
                    artifacts[name] = s.files.binding(root/(label+name))
                return dict(jobId=ref, artifacts=artifacts, selectedEpoch=1)
            first, fitted = run(s.RUN_FILES | s.SELECTION_FILES, 'inner-'), run(s.RUN_FILES, 'refit-')
            (root/'outer.json').write_text('{}')
            outer = dict(jobId=ref, artifact=s.files.binding(root/'outer.json'))
            pins = {f'control/{label}/{ref}/{n}': b for label, r in (('Inner', first), ('Refit', fitted)) for n, b in r['artifacts'].items()}
            pins[f'control/Outer/{ref}/prediction'] = outer['artifact']
            job = dict(id=ref, seed=17, objective='unweighted', regime='child-only', family='scalars')
            cases = [(dict(job, family='pca16-scalars'), first, pins, 'identity')]
            missing = copy.deepcopy(first); del missing['artifacts']['selection.json']
            cases.append((job, missing, pins, 'inventory'))
            cases.append((job, first, {k: v for k, v in pins.items() if not k.endswith('/best.pt')}, 'declaration-bound'))
            for changed, record, bound, message in cases:
                with self.assertRaisesRegex(s.IntegrityFailure, message):
                    s.structural(changed, record, fitted, outer, bound, [])
            (root/'inner-history.json').write_text('tampered')
            with self.assertRaisesRegex(s.IntegrityFailure, 'hash drift'):
                s.structural(job, first, fitted, outer, pins, [])

    def test_static_and_replay_mismatches_have_specific_codes(self):
        fresh = s.core.initialize(13, 17)[0].state_dict()
        mean, std = torch.zeros(13), torch.ones(13)
        state = lambda: dict(model={k: v.clone() for k, v in fresh.items()}, mean=mean.clone(), std=std.clone())
        states = {phase: dict(config=dict(recipe=s.core.recipe(17), weightRecipe=s.core.UNWEIGHTED_RECIPE, priorState={'B': 1}),
                              weights={'weights': [1.]}, checkpoints={name: state() for name in s.STATES},
                              artifacts={'best.pt': {'path': phase}}, selection={'NLL': 1.}) for phase in s.PHASES}
        data = {phase: dict(weightState={'weights': [1.]}, priors={'B': 1}, mean=mean, std=std) for phase in s.PHASES}
        job = dict(seed=17, selectionRows=[1], outerRows=[2])
        run = lambda: {k: s.outcome(v) for k, v in s.static_checks(job, states, data).items()}
        self.assertEqual(set(run().values()), {s.PASS})
        edits = [(lambda t: t['inner']['config']['recipe'].update(lr=.001), 'recipe'),
                 (lambda t: t['outer-refit']['weights'].update(weights=[2.]), 'fittingWeights'),
                 (lambda t: t['inner']['config'].update(priorState={'B': 2}), 'fitPriors'),
                 (lambda t: t['outer-refit']['checkpoints']['last.pt']['std'].add_(1e-6), 'normalization'),
                 (lambda t: next(iter(t['inner']['checkpoints']['initial.pt']['model'].values())).add_(1.), 'initialState')]
        codes = dict(recipe='recipe-differs', fittingWeights='fitting-weights-differ', fitPriors='fit-priors-differ',
                     normalization='normalization-differs', initialState='initial-state-differs')
        original = copy.deepcopy(states)
        for edit, name in edits:
            states = copy.deepcopy(original); edit(states)
            self.assertEqual(run()[name], codes[name])
        outer = dict(prediction={'NLL': 2.})
        saved = {'inner': {'NLL': 1.}, 'outer-refit': {'NLL': 2.}}
        exact = lambda binding, data, rows, seed: saved[binding['path']]
        drift = lambda binding, data, rows, seed: dict(saved[binding['path']], NLL=saved[binding['path']]['NLL']+1e-12)
        checks = s.replay_checks(job, original, outer, data, predict=exact)
        self.assertEqual({k: s.outcome(v) for k, v in checks.items()}, dict(selectionReplay=s.PASS, outerReplay=s.PASS))
        checks = s.replay_checks(job, original, outer, data, predict=drift)
        self.assertEqual({k: s.outcome(v) for k, v in checks.items()},
                         dict(selectionReplay='selection-replay-differs', outerReplay='outer-replay-differs'))

    def test_scalar_component_never_mixes_sources(self):
        plan = dict(cells=[dict(id=f'c{i}', jobs=dict(scalar=f'scalar{i}')) for i in range(2)])
        reuse, fallback = (dict(decision=dict(scalarReuse=value)) for value in (True, False))
        records = {f'c{i}': dict(prediction=f'old{i}') for i in range(2)}
        fresh = {f'scalar{i}': dict(prediction=f'new{i}') for i in range(2)}
        self.assertEqual(s.scalar_component(plan, reuse, records, {}), records)
        self.assertEqual(s.scalar_component(plan, fallback, {}, fresh), {'c0': fresh['scalar0'], 'c1': fresh['scalar1']})
        for controls, old, new in ((reuse, records, {'scalar0': fresh['scalar0']}), (reuse, {'c0': records['c0']}, {}),
                                   (fallback, {'c1': records['c1']}, fresh), (fallback, {}, {'scalar0': fresh['scalar0']})):
            with self.assertRaises(s.IntegrityFailure):
                s.scalar_component(plan, controls, old, new)
        jobs = [dict(id=f'{arm}{i}', arm=arm) for i in range(2) for arm in ('candidate', 'freshHard', 'scalar')]
        self.assertEqual(len(s.required_jobs(dict(plan, jobs=jobs), reuse)), 4)
        self.assertEqual(len(s.required_jobs(dict(plan, jobs=jobs), fallback)), 6)


def review(path, sha, **changes):
    path.write_text(json.dumps(dict(planSha256=sha, verdict='clear', blockingFindings=[], independent=True,
                                    reviewer='independent') | changes))
    return path


class PhaseBarrierTests(unittest.TestCase):
    def test_fresh_phase_and_clear_matching_review(self):
        for suffix in ('', '-started.json', '-freeze.json', '-failure.json'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); (root/('inner'+suffix)).touch()
                with self.assertRaisesRegex(s.IntegrityFailure, 'no implicit restart'):
                    s.fresh_phase(root, 'inner')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'review.json'
            for changes in ({'planSha256': 'wrong'}, {'verdict': 'blocked'}, {'independent': False}, {'blockingFindings': ['x']}):
                with self.assertRaises(ValueError):
                    s.review_binding(review(path, 'abc', **changes), 'abc')
            self.assertEqual(s.review_binding(review(path, 'abc'), 'abc')['path'], str(path))

    def test_plan_hash_and_review_precede_declaration_and_drift_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); path = root/'plan.json'; path.write_text(json.dumps({'study': s.STUDY}))
            sha = s.files.binding(path)['sha256']
            with patch.object(s, 'BASE', root), patch.object(s, 'build') as build:
                with self.assertRaises(ValueError):
                    s.load_plan(path, '0'*64, review(root/'review.json', sha))
                with self.assertRaises(ValueError):
                    s.load_plan(path, sha, review(root/'review.json', sha, verdict='blocked'))
                build.assert_not_called()
            with patch.object(s, 'BASE', root), patch.object(s, 'build', return_value=({'study': 'changed'}, {})):
                with self.assertRaisesRegex(s.IntegrityFailure, 'declaration changed'):
                    s.load_plan(path, sha, review(root/'review.json', sha))

    def test_each_phase_requires_the_previous_complete_freeze(self):
        plan, pin = dict(cells=[], jobs=[], runtime={}), {'path': '/nonexistent/plan.json', 'sha256': 'p'}
        loaded = (plan, pin, {'path': 'review'}, {})
        with patch.object(s, 'load_plan', return_value=loaded), patch.object(s, 'fresh_phase') as fresh:
            with patch.object(s, 'checked_control_freeze', side_effect=s.IntegrityFailure('Incomplete scalar control freeze')):
                with self.assertRaisesRegex(s.IntegrityFailure, 'control'):
                    s.fit('/nonexistent/plan.json', 'p', 'inner', 'review')
            controls = (dict(decision=dict(scalarReuse=True)), {'path': 'controls'})
            with patch.object(s, 'checked_control_freeze', return_value=controls), \
                 patch.object(s, 'check_freeze', side_effect=s.IntegrityFailure('Incomplete 150-job freeze')):
                with self.assertRaisesRegex(s.IntegrityFailure, 'Incomplete'):
                    s.fit('/nonexistent/plan.json', 'p', 'outer-refit', 'review', '/nonexistent/inner-freeze.json', 'i')
                with self.assertRaisesRegex(s.IntegrityFailure, 'Incomplete'):
                    s.outer('/nonexistent/plan.json', 'p', 'review', '/nonexistent/refit-freeze.json', 'r')
            fresh.assert_not_called()

    def test_incomplete_missing_arm_flag_or_runtime_drift_freeze_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); pin = {'path': str(root/'plan.json'), 'sha256': 'plan'}
            jobs = [dict(id=arm, arm=arm, cell='c0') for arm in ('candidate', 'freshHard', 'scalar')]
            plan = dict(cells=[dict(id='c0')], jobs=jobs, runtime={'torch': '2.8.0'})
            controls = (dict(decision=dict(scalarReuse=True)), {'path': 'controls', 'sha256': 'c'})
            good = dict(complete=True, study=s.STUDY, phase='inner', plan=pin, controls=controls[1], runtime=plan['runtime'],
                        jobCount=2, trainingPerformed=True, outerInferencePerformed=False,
                        runs=[dict(jobId='candidate'), dict(jobId='freshHard')], **s.FLAGS)
            path = root/'inner-freeze.json'
            for changes in (dict(runs=[dict(jobId='candidate')]), dict(runs=[dict(jobId='freshHard'), dict(jobId='candidate')]),
                            dict(trainingPerformed=False), dict(outerInferencePerformed=True), dict(runtime={'torch': '2.9.0'}),
                            dict(clinicalUseEligible=True), dict(complete=False), dict(controls={'path': 'other'})):
                path.write_text(json.dumps(good | changes))
                with patch.object(s, 'checked_control_freeze', return_value=controls):
                    with self.assertRaisesRegex(s.IntegrityFailure, 'Incomplete 2-job inner freeze'):
                        s.check_freeze(plan, pin, path, s.files.binding(path)['sha256'], 'inner', {})
            with patch.object(s, 'checked_control_freeze', return_value=controls):
                with self.assertRaisesRegex(s.IntegrityFailure, 'Canonical'):
                    s.check_freeze(plan, pin, root/'refit-freeze.json', 'x', 'inner', {})
                with self.assertRaises(s.IntegrityFailure):
                    s.paired_initial(jobs[:1], [dict(artifacts={})])

    def test_control_freeze_decision_and_records_must_match_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); pin = {'path': str(root/'plan.json'), 'sha256': 'plan'}
            (root/'controls').mkdir()
            plan = dict(cells=[dict(id=f'c{i}', references=dict(scalar=f'ref{i}')) for i in range(2)], runtime={'torch': '2.8.0'})
            reviewed = s.files.binding(review(root/'review.json', 'plan'))
            global_checks, cells = outcomes(2)

            def write(records, **changes):
                (root/'controls'/'records.json').write_text(json.dumps(records))
                value = dict(complete=True, study=s.STUDY, phase='controls', plan=pin, review=reviewed, runtime=plan['runtime'],
                             globalChecks=global_checks, cells=cells, decision=s.decide(global_checks, cells, 2),
                             records=s.files.binding(root/'controls'/'records.json'), historicalScalarReplayPerformed=True,
                             scoresComputed=False, trainingPerformed=False, outerInferencePerformed=False, **s.FLAGS) | changes
                (root/'controls-freeze.json').write_text(json.dumps(value))

            records = {'c0': {}, 'c1': {}}
            write(records)
            self.assertTrue(s.checked_control_freeze(plan, pin)[0]['decision']['scalarReuse'])
            fallback = s.decide(*outcomes(2, cell_failure='normalization-differs'), 2)
            for bad_records, changes in (({'c0': {}}, {}), ({}, {}), (records, dict(decision=fallback)),
                                         (records, dict(scoresComputed=True)), (records, dict(cells=list(reversed(cells))))):
                write(bad_records, **changes)
                with self.assertRaises(s.IntegrityFailure):
                    s.checked_control_freeze(plan, pin)


class TrainerTests(unittest.TestCase):
    def test_backend_is_the_original_raw1024_compact_trainer(self):
        import ast
        from lexical_compact import core as compact
        from lexical_seed_replication import core as seed
        self.assertIs(s.core, seed)
        self.assertIs(s.core.implementation('pca16-scalars'), compact)
        self.assertEqual(compact.TRANSFORM_RECIPE['input'], 'raw 1024-dimensional target features')
        tree = ast.parse(Path(s.__file__).read_text())
        modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
                  {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertFalse(any(m and m.startswith('temporal_pooling') for m in modules))
        self.assertEqual([p.name for p in s.new_sources()], ['study.py', 'evaluation.py', 'test_study.py', 'test_evaluation.py'])
        closure = {str(p) for p in s.local_closure(s.new_sources())}
        for path in (seed.__file__, compact.__file__, s.validation.__file__, s.x.__file__):
            self.assertIn(str(Path(path).resolve()), closure)

    def test_paired_arms_share_exact_initial_state_and_fit_only_pca(self):
        from lexical_unit_weights.test_core import bundle
        hard = bundle()
        candidate = dict(hard, target=hard['target'].copy())
        candidate['target'][:, :20] += np.random.default_rng(5).normal(size=(76, 20)).astype(np.float32)
        fit = list(range(65))
        prepared = {name: s.core.prepare(value, 'pca16-scalars', fit, 'unweighted') for name, value in
                    (('candidate', candidate), ('freshHard', hard))}
        for data in prepared.values():
            self.assertEqual(data['values'].shape[1], 29)
            self.assertEqual(tuple(data['transform']['basis'].shape), (1024, 16))
            self.assertEqual(data['transform']['fitRows'], fit)
        self.assertEqual(prepared['candidate']['priors'], prepared['freshHard']['priors'])
        self.assertFalse(torch.equal(prepared['candidate']['transform']['center'], prepared['freshHard']['transform']['center']))
        moved = dict(candidate, target=candidate['target'].copy()); moved['target'][65:] += 3.
        again = s.core.prepare(moved, 'pca16-scalars', fit, 'unweighted')
        self.assertTrue(s.core.compact.same_transform(again['transform'], prepared['candidate']['transform']))
        self.assertTrue(torch.equal(again['mean'], prepared['candidate']['mean']) and torch.equal(again['std'], prepared['candidate']['std']))
        for seed in s.SEEDS:
            first, second = (s.core.initialize(29, seed)[0].state_dict() for _ in range(2))
            self.assertTrue(s.same_state(first, second))
        self.assertFalse(s.same_state(s.core.initialize(29, 17)[0].state_dict(), s.core.initialize(29, 29)[0].state_dict()))


class IntegrityRegressionTests(unittest.TestCase):
    def test_malformed_saved_state_stops_even_when_compatibility_would_fail(self):
        cell, job = dict(id='c', outerRows=[0]), dict(id='old', seed=17, fitRows=[0], refitRows=[0], outerRows=[0])
        bundles = dict(cohort=dict(rows=[dict(targetPhone='B')]), historical={})
        for global_ok in (True, False):
            for malformed in ('history', 'optimizer', 'RNG'):
                with patch.object(s, 'structural', return_value=({}, {})), \
                     patch.object(s.validation, 'run', side_effect=ValueError('Malformed '+malformed)), \
                     patch.object(s, 'static_checks') as checks:
                    with self.assertRaisesRegex(s.IntegrityFailure, malformed):
                        s.scalar_cell(cell, job, {}, {}, {}, {'historicalPlan': {}}, bundles, global_ok)
                    checks.assert_not_called()

    def test_valid_numerical_replay_mismatch_falls_back_after_both_saved_state_checks(self):
        cell, job = dict(id='c', outerRows=[0]), dict(id='old', seed=17, fitRows=[0], refitRows=[0], outerRows=[0])
        p = [.2, .3, .5]
        states = {'outer-refit': dict(config=dict(priorState={'B': dict(probabilities=p)}))}
        record = dict(prior=dict(rowIndices=[0], probabilities=[p], logProbabilities=[np.log(p).tolist()]))
        bundles = dict(cohort=dict(rows=[dict(targetPhone='B')]), historical={})
        with patch.object(s, 'structural', return_value=(states, record)), \
             patch.object(s.validation, 'run') as validate, patch.object(s.core, 'prepare', return_value={}), \
             patch.object(s, 'static_checks', return_value={'recipe': lambda: None}), \
             patch.object(s, 'replay_checks', return_value={'outerReplay': lambda: s.compatible(False, 'outer-replay-differs')}):
            outcome, prediction = s.scalar_cell(cell, job, {}, {}, {}, {'historicalPlan': {}}, bundles, True)
        self.assertEqual(validate.call_count, 2)
        self.assertEqual(outcome['checks'], dict(recipe=s.PASS, outerReplay='outer-replay-differs', savedState=s.PASS))
        self.assertIsNone(prediction)

    def test_bound_trainer_source_drift_and_missing_parity_stop_not_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'trainer.py'; source.write_text('original')
            old = dict(inputs={'seedSource/core': s.files.binding(source)}, runtime={}, recipes={}, weightRecipes={})
            source.write_text('changed')
            with patch.object(s, 'parity_receipt') as parity:
                with self.assertRaises(ValueError):
                    s.historical_compatibility({}, old)
                parity.assert_not_called()
            old['inputs']['seedSource/core'] = s.files.binding(source)
            with patch.object(s, 'parity_receipt', side_effect=s.IntegrityFailure('Missing reviewed trainer parity')):
                with self.assertRaisesRegex(s.IntegrityFailure, 'trainer parity'):
                    s.historical_compatibility({}, old)

    def test_parity_runtime_inputs_and_source_are_mandatory(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source.py'; source.write_text('unchanged')
            pins = {k: dict(path=k, sha256=k) for k in (*s.PROBE_INPUTS, 'priorProbePlan', 'priorProbeFreeze', 'priorProbeReview')}
            receipt = dict(independent=True, verdict='clear', blockingFindings=[], bindings={
                'plan.json': pins['priorProbePlan'], 'controls-freeze.json': pins['priorProbeFreeze']})
            good = dict(runtime={'cpu': True}, inputs={k: pins[k] for k in s.PROBE_INPUTS}, sources={'source': s.files.binding(source)})
            plan = dict(inputs=pins, runtime=good['runtime'])
            for bad in (dict(good, runtime={'cpu': False}), dict(good, inputs={})):
                with patch.object(s, 'read', side_effect=[bad, receipt]), patch.object(s.previous, 'checked_control_freeze') as check:
                    with self.assertRaises(s.IntegrityFailure):
                        s.parity_receipt(plan)
                    check.assert_not_called()
            source.write_text('changed')
            with patch.object(s, 'read', side_effect=[good, receipt]):
                with self.assertRaises(ValueError):
                    s.parity_receipt(plan)

    def test_late_current_phase_mutation_cannot_publish_a_complete_freeze(self):
        # Toy byte artifacts and stubbed training/prediction; no real model fit.
        for phase in ('inner', 'outer'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                pin = dict(path=str(root/'plan.json'), sha256='plan')
                _, temporal, rows, _ = fixture()
                originals, _, _, _ = fixture()
                cells = s.make_cells(originals, temporal, rows, positions=25)[:1]
                jobs = s.make_jobs(cells, originals)[:2]
                controls = dict(decision=dict(scalarReuse=True))
                plan = dict(cells=cells, jobs=jobs, runtime={}, inputs={})
                for name in ('controls', 'refit'):
                    (root/(name+'-freeze.json')).write_text('{}')
                control_pin = s.files.binding(root/'controls-freeze.json')
                refit_pin = s.files.binding(root/'refit-freeze.json')
                prior_runs = []
                for job in jobs:
                    path = root/(job['id']+'.pt'); path.write_bytes(b'prior toy checkpoint')
                    prior_runs.append(dict(jobId=job['id'], artifacts={'best.pt': s.files.binding(path)}, selectedEpoch=1))
                bundles = dict(cohort={'rows': rows}, candidate={}, freshHard={})
                loaded = plan, pin, {'path': 'review'}, bundles

                def toy_train(data, selected, output, cfg, **kwargs):
                    output.mkdir()
                    for name in ('initial.pt', 'best.pt'):
                        (output/name).write_bytes(b'toy checkpoint')

                def manifest(output):
                    return {p.name: s.files.binding(p) for p in output.iterdir()}

                def mutate(*args):
                    path = root/phase/jobs[0]['id']/'best.pt' if phase == 'inner' else root/'outer'/(jobs[0]['id']+'.json')
                    path.write_bytes(b'late mutation after earlier validation')

                with patch.object(s, 'load_plan', return_value=loaded), \
                     patch.object(s, 'checked_control_freeze', return_value=(controls, control_pin)), \
                     patch.object(s, 'check_freeze', return_value=({'runs': prior_runs}, refit_pin)), \
                     patch.object(s.core, 'prepare', return_value={}), patch.object(s.core, 'train', side_effect=toy_train), \
                     patch.object(s.core, 'replay', return_value={}), patch.object(s, 'config_value', return_value={}), \
                     patch.object(s.historical.parent.scalar, 'manifest', side_effect=manifest), \
                     patch.object(s.historical.parent.scalar, 'check_manifest', return_value={'bestEpoch': 1}), \
                     patch.object(s, 'validate_run'), patch.object(s, 'same_model'), patch.object(s, 'prior_value', return_value={}), \
                     patch.object(s, 'final_guards', side_effect=mutate):
                    with self.assertRaises(ValueError):
                        if phase == 'inner':
                            s.fit(pin['path'], 'plan', 'inner', 'review')
                        else:
                            s.outer(pin['path'], 'plan', 'review', refit_pin['path'], refit_pin['sha256'])
                self.assertFalse((root/(phase+'-freeze.json')).exists())
                failure = json.loads((root/(phase+'-failure.json')).read_text())
                self.assertEqual((failure['stage'], len(failure['completed'])), ('final guards', 2))

    def test_consumed_chain_rechecks_records_checkpoints_predictions_and_freezes(self):
        for target in ('records', 'checkpoint', 'prediction', 'review', 'inner-freeze'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                artifacts = {}
                for name in ('records', 'checkpoint', 'prediction', 'review'):
                    path = root/name; path.write_text('{}'); artifacts[name] = s.files.binding(path)
                def freeze(name, value):
                    path = root/name; s.files.write_json(path, value); return s.files.binding(path)
                control = freeze('controls-freeze', dict(records=artifacts['records'], review=artifacts['review']))
                inner = freeze('inner-freeze', dict(controls=control, runs=[dict(jobId='j', artifacts={'best.pt': artifacts['checkpoint']})]))
                refit = freeze('refit-freeze', dict(innerFreeze=inner, controls=control))
                outer = freeze('outer-freeze', dict(refitFreeze=refit, controls=control,
                                                   predictions=[dict(jobId='j', artifact=artifacts['prediction'])]))
                s.guard_freeze(outer)
                (root/target).write_text('late change')
                with self.assertRaises(ValueError):
                    s.guard_freeze(outer)


if __name__ == '__main__':
    unittest.main()
