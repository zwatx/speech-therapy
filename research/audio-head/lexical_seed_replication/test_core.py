"""Exact seed-7 equivalence to frozen trainers plus true seeded replication behavior."""
import copy
import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest

import numpy as np
import torch

from lexical_compact import core as compact
from lexical_heads import core as scalar
from lexical_seed_replication import core
from lexical_unit_weights import core as unitcore
from lexical_unit_weights import weights
from lexical_unit_weights.test_core import bundle, same
from multiphone_models import MeanPoolPhoneRatingHead

FIT, HELD, SELECT = list(range(65)), list(range(65, 76)), list(range(65, 71))
FAMILIES = ('scalars', 'pca16-scalars')
FROZEN = ((scalar, ('RECIPE', 'prepare', 'initialize', 'predict', 'train', 'replay', '_save', '_rng')),
          (compact, ('RECIPE', 'TRANSFORM_RECIPE', 'prepare', 'initialize', 'predict', 'train', 'replay',
                     '_save', 'same_transform')),
          (unitcore, ('RECIPE', 'prepare', 'weighted_loss', 'train', 'replay', '_save')),
          (weights, ('RECIPE', 'fit_weights')))


def frozen_trainer(family, objective):
    """Immutable reference: the unit-weight trainer, else the unweighted family trainer."""
    if objective == 'unit-weighted':
        return unitcore
    return scalar if family == 'scalars' else compact


def changed(rows):
    """Repeated fixture with extreme features and labels on rows that must stay unopened."""
    source = bundle(True)
    for i in rows:
        source['target'][i] = 1e5
        source['scalars'][i] = -1e5
        source['cohort']['rows'][i]['raterCounts'] = [5, 0, 0]
    return source


def load(directory, name):
    return torch.load(directory/name, map_location='cpu', weights_only=True)


def text(directory, name):
    return json.loads((directory/name).read_text())


def portable(config):
    """Configuration keeping artifact hashes but not absolute artifact locations."""
    return {k: dict(sha256=v['sha256']) if k in ('weights', 'transform') else v for k, v in config.items()}


def order_sha(order):
    return hashlib.sha256(json.dumps(order, separators=(',', ':')).encode()).hexdigest()


def tensors_equal(left, right):
    return left.keys() == right.keys() and all(torch.equal(left[k], right[k]) for k in left)


def edit_json(change):
    def apply(path):
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    return apply


def edit_torch(change):
    def apply(path):
        value = torch.load(path, map_location='cpu', weights_only=True)
        change(value)
        torch.save(value, path)
    return apply


class SeedReplicationTests(unittest.TestCase):
    def setUp(self):
        self.identities = {(m, n): getattr(m, n) for m, names in FROZEN for n in names}
        self.constants = copy.deepcopy((scalar.RECIPE, compact.RECIPE, compact.TRANSFORM_RECIPE, weights.RECIPE,
                                        core.UNWEIGHTED_RECIPE, core.OBJECTIVES, core.SEEDS))

    def tearDown(self):
        # Neither the new module nor these tests may replace or mutate frozen globals.
        for (module, name), value in self.identities.items():
            self.assertIs(getattr(module, name), value, f'{module.__name__}.{name}')
        self.assertEqual(self.constants, (scalar.RECIPE, compact.RECIPE, compact.TRANSFORM_RECIPE, weights.RECIPE,
                                          core.UNWEIGHTED_RECIPE, core.OBJECTIVES, core.SEEDS))
        self.assertIs(unitcore.RECIPE, scalar.RECIPE)
        self.assertEqual(scalar.RECIPE['seed'], 7)

    def test_recipe_and_initialize_replace_only_the_seed(self):
        self.assertEqual((core.SEEDS, core.OBJECTIVES), ((17, 29, 43), ('unweighted', 'unit-weighted')))
        frozen = {k: v for k, v in scalar.RECIPE.items() if k != 'seed'}
        for seed in core.SEEDS + (0, 7, 2**32 - 1):
            settings = core.recipe(seed)
            self.assertIsNot(settings, scalar.RECIPE)
            self.assertEqual(settings.pop('seed'), seed)
            self.assertEqual(settings, frozen)
        edited = core.recipe(17)
        edited['hidden'] = 1
        self.assertEqual(core.recipe(17)['hidden'], 128)
        for seed in (True, False, 7.0, -1, 2**32, '17', None, np.int64(17)):
            with self.subTest(seed=seed):
                with self.assertRaises(ValueError):
                    core.recipe(seed)
                with self.assertRaises(ValueError):
                    core.initialize(13, seed)
        for width in (1037, 30, 13.0, True):
            with self.assertRaises(ValueError):
                core.initialize(width, 17)
        for width, backend in ((13, scalar), (29, compact)):
            model, generator = core.initialize(width, 7)
            streams = random.getstate(), np.random.get_state()[1].tolist(), torch.get_rng_state()
            reference, reference_generator = backend.initialize(width)
            same(self, model.state_dict(), reference.state_dict())
            self.assertEqual(generator.bit_generator.state, reference_generator.bit_generator.state)
            same(self, streams, (random.getstate(), np.random.get_state()[1].tolist(), torch.get_rng_state()))
            seeded, generator = core.initialize(width, 17)
            self.assertFalse(tensors_equal(seeded.state_dict(), reference.state_dict()))
            self.assertEqual(generator.bit_generator.state, np.random.default_rng(17).bit_generator.state)

    def test_objective_states_share_complete_canonical_geometry(self):
        cohort = bundle(True)['cohort']
        unit = core.fitting_weights(cohort, FIT, 'unit-weighted')
        plain = core.fitting_weights(cohort, FIT, 'unweighted')
        self.assertEqual(unit, weights.fit_weights(cohort, FIT))
        # Rows 0-1 are one recording/sound unit, so 65 positions form 64 units.
        self.assertEqual((unit['unitCount'], unit['normalization']), (64, 65/64))
        self.assertEqual(unit['weights'][:4], [65/128, 65/128, 65/64, 65/64])
        self.assertEqual((plain['fitRows'], plain['canonicalCounts'], plain['unitCount']),
                         (unit['fitRows'], unit['canonicalCounts'], 64))
        self.assertEqual(plain['canonicalCounts'][:4], [2, 2, 1, 1])
        self.assertEqual((plain['normalization'], plain['weights']), (1., [1.] * 65))
        self.assertTrue(all(type(w) is float for w in plain['weights']))
        self.assertIs(plain['recipe']['classWeighting'], False)
        self.assertEqual(plain['recipe']['selection'], weights.RECIPE['selection'])
        self.assertEqual(plain['recipe'], core.UNWEIGHTED_RECIPE)
        self.assertNotEqual(plain['recipe'], unit['recipe'])
        plain['recipe']['raw'] = 'edited'
        self.assertNotEqual(core.fitting_weights(cohort, FIT, 'unweighted')['recipe']['raw'], 'edited')
        for objective in ('weighted', 'Unweighted', None, ['unweighted']):
            with self.assertRaisesRegex(ValueError, 'objective'):
                core.fitting_weights(cohort, FIT, objective)
        for objective in core.OBJECTIVES:
            for rows in (FIT[1:], [0, 2] + FIT[3:]):
                with self.assertRaisesRegex(ValueError, 'every supported canonical position'):
                    core.fitting_weights(cohort, rows, objective)
                with self.assertRaises(ValueError):
                    core.prepare(bundle(True), 'scalars', rows, objective)
            with self.assertRaises(ValueError):
                core.fitting_weights(cohort, tuple(FIT), objective)
            with self.assertRaises(ValueError):
                core.prepare(bundle(True), 'target-scalars', FIT, objective)

    def test_prepare_keeps_frozen_unweighted_moments_and_fit_only_state(self):
        for family, backend in (('scalars', scalar), ('pca16-scalars', compact)):
            reference = backend.prepare(bundle(True), family, FIT)
            unit_reference = unitcore.prepare(bundle(True), family, FIT)
            for objective in core.OBJECTIVES:
                with self.subTest(family=family, objective=objective):
                    data = core.prepare(bundle(True), family, FIT, objective)
                    hidden = core.prepare(changed(HELD), family, FIT, objective)
                    self.assertEqual(data['objective'], objective)
                    self.assertEqual(data['weightState'], core.fitting_weights(bundle(True)['cohort'], FIT, objective))
                    frozen = {k: v for k, v in data.items() if k not in ('objective', 'weightState')}
                    self.assertTrue(np.array_equal(frozen.pop('values'), reference['values']))
                    same(self, frozen, {k: v for k, v in reference.items() if k != 'values'})
                    if objective == 'unit-weighted':
                        same(self, data['weightState'], unit_reference['weightState'])
                    for key in ('mean', 'std', 'priors', 'weightState') + (('transform',) if family != 'scalars' else ()):
                        same(self, data[key], hidden[key])
                    self.assertTrue(np.array_equal(data['values'][FIT], hidden['values'][FIT]))

    def test_seed7_inner_and_refit_equal_frozen_trainers_bit_for_bit(self):
        # 65 fit rows give one full and one partial batch per epoch; unit weights are nonuniform.
        for family in FAMILIES:
            for objective in core.OBJECTIVES:
                data = core.prepare(bundle(True), family, FIT, objective)
                weighted = objective == 'unit-weighted'
                self.assertEqual(len(set(data['weightState']['weights'])) > 1, weighted)
                reference = frozen_trainer(family, objective)
                for epochs in (None, 2):
                    selection = [] if epochs else HELD
                    with self.subTest(family=family, objective=objective, epochs=epochs), \
                            tempfile.TemporaryDirectory() as folder:
                        a, b = Path(folder).resolve()/'old', Path(folder).resolve()/'new'
                        old = reference.train(data, list(selection), a, {}, epochs=epochs)
                        new = core.train(data, list(selection), b, {}, seed=7, epochs=epochs)
                        self.assertTrue(all(row['updates'] == 2 for row in text(b, 'history.json')))
                        shared = ['history.json', 'prior.json']
                        shared += ['selection.json'] if epochs is None else []
                        shared += ['transform.pt'] if family == 'pca16-scalars' else []
                        shared += ['weights.json'] if weighted else []
                        for name in shared:
                            self.assertEqual((a/name).read_bytes(), (b/name).read_bytes(), name)
                        for key in ('complete', 'phase', 'mode', 'fitRows', 'selectionRows', 'epochsRun',
                                    'bestEpoch', 'bestLoss', 'totalUpdates', 'exactSelectionReplay'):
                            self.assertEqual(old[key], new[key], key)
                        self.assertEqual((new['objective'], new['seed']), (objective, 7))
                        weight_sha = new['artifacts']['weights.json']['sha256']
                        for name in ('initial.pt', 'best.pt', 'last.pt'):
                            left, right = load(a, name), load(b, name)
                            # Only configuration hashes and the new unweighted weight provenance may differ.
                            self.assertEqual(left.pop('configSha256'), old['configSha256'])
                            self.assertEqual(right.pop('configSha256'), new['configSha256'])
                            if not weighted:
                                self.assertEqual(right.pop('weightsSha256'), weight_sha)
                            same(self, left, right)
                        left, right = portable(text(a, 'config.json')), portable(text(b, 'config.json'))
                        self.assertEqual((right.pop('objective'), right.pop('seed')), (objective, 7))
                        if not weighted:
                            self.assertEqual(right.pop('weights'), dict(sha256=weight_sha))
                            self.assertIs(right.pop('weightRecipe')['classWeighting'], False)
                            self.assertEqual(text(b, 'weights.json')['weights'], [1.] * 65)
                        self.assertEqual(left, right)
                        for name in ('initial.pt', 'best.pt', 'last.pt'):
                            self.assertEqual(reference.replay(a, data, HELD, name),
                                             core.replay(b, data, HELD, seed=7, checkpoint=name))

    def test_seed_alone_sets_initial_state_rng_and_permutations(self):
        for family, width in (('scalars', 13), ('pca16-scalars', 29)):
            with tempfile.TemporaryDirectory() as folder:
                root, runs = Path(folder).resolve(), {}
                for seed in (17, 29):
                    for objective in core.OBJECTIVES:
                        data = core.prepare(bundle(True), family, FIT, objective)
                        runs[seed, objective] = root/f'{objective}-{seed}'
                        core.train(data, [], runs[seed, objective], {}, seed=seed, epochs=2)
                for seed in (17, 29):
                    # Independent reference: freshly seeded streams and the frozen head constructor.
                    random.seed(seed)
                    np.random.seed(seed)
                    torch.manual_seed(seed)
                    model = MeanPoolPhoneRatingHead(feature_dim=width, num_phones=24, hidden_dim=128, dropout=.1)
                    python, numpy_state, torch_state = random.getstate(), np.random.get_state(), torch.get_rng_state()
                    generator = np.random.default_rng(seed)
                    fresh = generator.bit_generator.state
                    orders = [order_sha(generator.permutation(FIT).tolist()) for _ in range(2)]
                    for objective in core.OBJECTIVES:
                        with self.subTest(family=family, seed=seed, objective=objective):
                            path = runs[seed, objective]
                            initial, last = load(path, 'initial.pt'), load(path, 'last.pt')
                            same(self, initial['model'], model.state_dict())
                            same(self, initial['rng']['python'], python)
                            self.assertTrue(torch.equal(initial['rng']['torch'], torch_state))
                            self.assertEqual(initial['rng']['numpyGlobal']['keys'], numpy_state[1].tolist())
                            self.assertEqual(initial['rng']['numpyGlobal']['position'], numpy_state[2])
                            self.assertEqual(initial['rng']['numpyPermutation'], fresh)
                            self.assertEqual(last['rng']['numpyPermutation'], generator.bit_generator.state)
                            self.assertEqual([row['orderSha256'] for row in text(path, 'history.json')], orders)
                            config = text(path, 'config.json')
                            self.assertEqual((config['seed'], config['recipe']['seed'], config['objective']),
                                             (seed, seed, objective))
                            self.assertEqual({k: v for k, v in config['recipe'].items() if k != 'seed'},
                                             {k: v for k, v in scalar.RECIPE.items() if k != 'seed'})
                    # The objective changes only the loss: same start and order, different trajectory.
                    plain, unit = runs[seed, 'unweighted'], runs[seed, 'unit-weighted']
                    self.assertNotEqual(text(plain, 'history.json')[0]['trainLoss'],
                                        text(unit, 'history.json')[0]['trainLoss'])
                    self.assertFalse(tensors_equal(load(plain, 'last.pt')['model'], load(unit, 'last.pt')['model']))
                seventeen, twentynine = runs[17, 'unweighted'], runs[29, 'unweighted']
                self.assertFalse(tensors_equal(load(seventeen, 'initial.pt')['model'],
                                               load(twentynine, 'initial.pt')['model']))
                self.assertNotEqual(text(seventeen, 'history.json')[0]['orderSha256'],
                                    text(twentynine, 'history.json')[0]['orderSha256'])

    def test_seed17_inner_selection_repeats_exactly_and_seed29_differs(self):
        for family in FAMILIES:
            data = core.prepare(bundle(True), family, FIT, 'unit-weighted')
            with self.subTest(family=family), tempfile.TemporaryDirectory() as folder:
                root = Path(folder).resolve()
                first = core.train(data, HELD, root/'first', {}, seed=17)
                second = core.train(data, HELD, root/'second', {}, seed=17)
                other = core.train(data, HELD, root/'other', {}, seed=29)
                for name in ('history.json', 'selection.json', 'prior.json', 'weights.json'):
                    self.assertEqual((root/'first'/name).read_bytes(), (root/'second'/name).read_bytes(), name)
                for key in ('epochsRun', 'bestEpoch', 'bestLoss', 'totalUpdates', 'exactSelectionReplay'):
                    self.assertEqual(first[key], second[key], key)
                self.assertEqual(portable(text(root/'first', 'config.json')), portable(text(root/'second', 'config.json')))
                for name in ('initial.pt', 'best.pt', 'last.pt'):
                    left, right = load(root/'first', name), load(root/'second', name)
                    left.pop('configSha256')
                    right.pop('configSha256')
                    same(self, left, right)
                self.assertTrue(other['exactSelectionReplay'])
                self.assertFalse(tensors_equal(load(root/'first', 'initial.pt')['model'],
                                               load(root/'other', 'initial.pt')['model']))
                self.assertNotEqual(text(root/'first', 'history.json')[0]['orderSha256'],
                                    text(root/'other', 'history.json')[0]['orderSha256'])
                self.assertEqual(core.replay(root/'first', data, HELD, seed=17), text(root/'first', 'selection.json'))
                with self.assertRaisesRegex(ValueError, 'configuration differs'):
                    core.replay(root/'first', data, HELD, seed=29)
                # The frozen replay pins seed 7 and so cannot replay new-seed runs.
                with self.assertRaisesRegex(ValueError, 'configuration differs'):
                    unitcore.replay(root/'first', data, HELD)

    def test_training_rejects_conflicts_tampered_data_and_partial_fits_before_output(self):
        plain = core.prepare(bundle(True), 'scalars', FIT, 'unweighted')
        unit = core.prepare(bundle(True), 'scalars', FIT, 'unit-weighted')
        changed_weight = copy.deepcopy(unit['weightState'])
        changed_weight['weights'][0] *= 2
        refit = dict(seed=17, epochs=2)
        cases = [(plain, [0] + HELD, {}, dict(seed=17)), (plain, HELD, {}, refit), (plain, [], {}, dict(seed=17)),
                 *[(plain, [], {}, dict(seed=17, epochs=e)) for e in (0, True, 2., 101)],
                 *[(plain, [], {}, dict(seed=s, epochs=2)) for s in (True, 7., -1, 2**32, None)],
                 *[(plain, [], c, refit) for c in (
                     dict(seed=18), dict(objective='unit-weighted'), dict(recipe=scalar.RECIPE),
                     dict(weightRecipe=weights.RECIPE), dict(fitRows=FIT[1:]), dict(authorTestRead=True),
                     dict(outerPredictionsRead=True), dict(phase='inner'), [])],
                 (unit, [], dict(weightRecipe=core.UNWEIGHTED_RECIPE), refit),
                 ({**plain, 'objective': 'unit-weighted'}, [], {}, refit),
                 ({**plain, 'objective': 'weighted'}, [], {}, refit),
                 ({**unit, 'objective': 'unweighted'}, [], {}, refit),
                 ({**plain, 'weightState': unit['weightState']}, [], {}, refit),
                 ({**unit, 'weightState': changed_weight}, [], {}, refit),
                 ({**unit, 'fit': FIT[1:]}, [], {}, refit),
                 ({**plain, 'family': 'target-scalars'}, [], {}, refit)]
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder).resolve()/'run'
            for index, (data, selection, config, options) in enumerate(cases):
                with self.subTest(case=index, config=config, options=options):
                    with self.assertRaises(ValueError):
                        core.train(data, selection, output, config, **options)
                    self.assertFalse(output.exists())
            with self.assertRaises(TypeError):
                core.train(plain, [], output, {}, epochs=2)
            with self.assertRaises(TypeError):
                core.train(plain, [], output, {}, 17, 2)
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, 'weight binding'):
                core.train(plain, [], output, dict(weights=dict(path='elsewhere', sha256='0' * 64)), **refit)
            with self.assertRaisesRegex(ValueError, 'fresh'):
                core.train(plain, [], output, {}, **refit)

    def test_refit_uses_only_fit_rows_and_never_selects(self):
        for family in FAMILIES:
            for objective in core.OBJECTIVES:
                with self.subTest(family=family, objective=objective), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder).resolve()
                    for name, source in (('base', bundle(True)), ('hidden', changed(HELD))):
                        data = core.prepare(source, family, FIT, objective)
                        result = core.train(data, [], root/name, dict(note='caller'), seed=43, epochs=2)
                        self.assertEqual((result['phase'], result['totalUpdates'], result['exactSelectionReplay']),
                                         ('outer-refit', 4, False))
                        self.assertNotIn('selection.json', result['artifacts'])
                        self.assertFalse((root/name/'selection.json').exists())
                        self.assertTrue(all('selection' not in row for row in text(root/name, 'history.json')))
                        self.assertEqual(text(root/name, 'config.json')['note'], 'caller')
                    for name in ('history.json', 'prior.json', 'weights.json'):
                        self.assertEqual((root/'base'/name).read_bytes(), (root/'hidden'/name).read_bytes(), name)
                    self.assertEqual(portable(text(root/'base', 'config.json')), portable(text(root/'hidden', 'config.json')))
                    for name in ('initial.pt', 'best.pt', 'last.pt'):
                        left, right = load(root/'base', name), load(root/'hidden', name)
                        left.pop('configSha256')
                        right.pop('configSha256')
                        same(self, left, right)

    def test_inner_opens_only_selection_rows_and_replay_rejects_mismatch_or_tamper(self):
        for family in FAMILIES:
            unit = core.prepare(bundle(True), family, FIT, 'unit-weighted')
            with self.subTest(family=family), tempfile.TemporaryDirectory() as folder:
                root = Path(folder).resolve()
                path = root/'fit'
                core.train(unit, SELECT, path, {}, seed=29)
                # Rows outside fit and selection carry extreme values; the inner run must not change.
                hidden = core.prepare(changed(HELD[len(SELECT):]), family, FIT, 'unit-weighted')
                core.train(hidden, SELECT, root/'hidden', {}, seed=29)
                for name in ('history.json', 'selection.json'):
                    self.assertEqual((path/name).read_bytes(), (root/'hidden'/name).read_bytes(), name)
                self.assertEqual(portable(text(path, 'config.json')), portable(text(root/'hidden', 'config.json')))
                for name in ('best.pt', 'last.pt'):
                    left, right = load(path, name), load(root/'hidden', name)
                    left.pop('configSha256')
                    right.pop('configSha256')
                    same(self, left, right)

                selected = text(path, 'selection.json')

                def run(seed=29):
                    return core.replay(path, unit, SELECT, seed=seed)

                self.assertEqual(run(), selected)
                for name in ('initial.pt', 'last.pt'):
                    self.assertEqual(core.replay(path, unit, SELECT, seed=29, checkpoint=name)['rowIndices'], SELECT)
                self.assertEqual(core.replay(path, unit, SELECT[:3], seed=29)['rowIndices'], SELECT[:3])
                with self.assertRaisesRegex(ValueError, 'Unknown checkpoint'):
                    core.replay(path, unit, SELECT, seed=29, checkpoint='other.pt')
                with self.assertRaises(TypeError):
                    core.replay(path, unit, SELECT)
                for seed in (7, 17, 43):
                    with self.assertRaisesRegex(ValueError, 'configuration differs'):
                        run(seed)
                for seed in (True, 29.):
                    with self.assertRaises(ValueError):
                        run(seed)
                plain = core.prepare(bundle(True), family, FIT, 'unweighted')
                other_fit = core.prepare(bundle(True), family, list(range(3, 65)), 'unit-weighted')
                for data in (plain, other_fit):
                    with self.assertRaisesRegex(ValueError, 'configuration differs'):
                        core.replay(path, data, SELECT, seed=29)
                tampered_state = copy.deepcopy(unit['weightState'])
                tampered_state['weights'][0] *= 2
                for data in ({**unit, 'objective': 'unweighted'}, {**unit, 'weightState': tampered_state},
                             {**unit, 'weightState': plain['weightState']}):
                    with self.assertRaisesRegex(ValueError, 'weight state'):
                        core.replay(path, data, SELECT, seed=29)
                with self.assertRaisesRegex(ValueError, 'config state'):
                    core.replay(path, {**unit, 'mean': unit['mean'] + 1}, SELECT, seed=29)
                with self.assertRaisesRegex(ValueError, 'configuration differs'):
                    unitcore.replay(path, unit, SELECT)

                tampers = [
                    ('weights.json', edit_json(lambda w: w['weights'].__setitem__(0, 2 * w['weights'][0])),
                     'weight binding', run),
                    ('weights.json', lambda p: p.write_text(json.dumps(json.loads(p.read_text()))), 'weight binding', run),
                    ('config.json', edit_json(lambda c: c.pop('objective')), 'configuration differs', run),
                    ('config.json', edit_json(lambda c: c.update(weightRecipe=core.UNWEIGHTED_RECIPE)),
                     'configuration differs', run),
                    # Rewriting the recorded seed cannot bypass the checkpoint's configuration hash.
                    ('config.json', edit_json(lambda c: c.update(seed=17, recipe={**c['recipe'], 'seed': 17})),
                     'config state', lambda: run(17)),
                    ('best.pt', edit_torch(lambda s: s.update(weightsSha256='0' * 64)), 'Checkpoint weight', run),
                    ('best.pt', edit_torch(lambda s: s.update(mean=s['mean'] + 1)), 'config state', run),
                    ('best.pt', edit_torch(lambda s: s.update(configSha256='0' * 64)), 'config state', run),
                    ('selection.json', edit_json(lambda s: s.update(NLL=s['NLL'] + 1)), 'Selected state', run)]
                if family == 'pca16-scalars':
                    tampers += [
                        ('transform.pt', edit_torch(lambda t: t['basis'].neg_()), 'transform binding', run),
                        ('best.pt', edit_torch(lambda s: s.update(transformSha256='0' * 64)), 'config state', run),
                        ('best.pt', edit_torch(lambda s: s.pop('transformSha256')), 'config state', run),
                        ('config.json', edit_json(lambda c: c.update(
                            transformRecipe={**c['transformRecipe'], 'components': 15})), 'configuration differs', run)]
                else:
                    tampers.append(('best.pt', edit_torch(lambda s: s.update(transformSha256='0' * 64)),
                                    'config state', run))
                for index, (name, change, pattern, attempt) in enumerate(tampers):
                    with self.subTest(tamper=index, artifact=name, pattern=pattern):
                        original = (path/name).read_bytes()
                        try:
                            change(path/name)
                            with self.assertRaisesRegex(ValueError, pattern):
                                attempt()
                        finally:
                            (path/name).write_bytes(original)
                        # Control: the restored artifacts replay exactly again.
                        self.assertEqual(run(), selected)


if __name__ == '__main__':
    unittest.main()
