import hashlib
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402


def synth(seed=0, n=120):
    rng = np.random.default_rng(seed)
    ids = np.arange(n, dtype=np.int64) % len(core.PHONES)
    scalars = rng.normal(size=(n, 13)).astype(np.float32)
    logits = 1.5 * scalars[:, :3].astype(np.float64)
    p = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    counts = np.array([rng.multinomial(5, row) for row in p], dtype=np.int64)
    return core.features(scalars, ids), counts, ids


def log_softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    return z - np.log(np.exp(z).sum(axis=1, keepdims=True))


class PureTest(unittest.TestCase):
    def test_features(self):
        x, counts, ids = synth()
        self.assertEqual((x.shape, x.dtype), ((120, 36), np.float32))
        np.testing.assert_array_equal(x[:, 13:].argmax(axis=1), ids)
        np.testing.assert_array_equal(x[:, 13:].sum(axis=1), 1)
        self.assertTrue((x[:, 13:].sum(axis=0) > 0).all())
        self.assertTrue((counts.sum(axis=0) > 0).all() and ((counts > 0).sum(axis=1) > 1).any())
        s = np.zeros((2, 13), np.float32)
        bad = [(s.astype(np.float64), np.array([0, 1])), (np.full((2, 13), np.nan, np.float32), np.array([0, 1])),
               (s, np.array([True, False])), (s, np.array([0, 23])), (s, np.array([0, -1])),
               (s, np.array([0.0, 1.0])), (s, np.array([0])), (s[:, :12], np.array([0, 1])),
               (np.zeros((0, 13), np.float32), np.array([], np.int64))]
        for scalars, phone_ids in bad:
            with self.assertRaises(ValueError):
                core.features(scalars, phone_ids)

    def test_validate_counts_rejects(self):
        np.testing.assert_array_equal(core.validate_counts(np.array([[2, 3, 0]]), 1), [[2, 3, 0]])
        for counts in [np.array([[2, 2, 0]]), np.array([[6, -1, 0]]), np.array([[True, True, False]]),
                       np.array([[2.0, 3.0, 0.0]]), np.array([[2, 3]]), np.array([[5, 0, 0], [5, 0, 0]])]:
            with self.assertRaises(ValueError):
                core.validate_counts(counts, 1)

    def test_expand_votes(self):
        x, _, _ = synth(n=3)
        counts = np.array([[5, 0, 0], [2, 3, 0], [1, 1, 3]])
        copies, y, w, src = core.expand_votes(x, counts)
        np.testing.assert_array_equal(src, [0, 1, 1, 2, 2, 2])
        np.testing.assert_array_equal(y, [0, 0, 1, 0, 1, 2])
        np.testing.assert_array_equal(w, [1.0, 0.4, 0.6, 0.2, 0.2, 0.6])
        np.testing.assert_array_equal(copies, x[src])
        self.assertEqual((y.dtype, w.dtype, src.dtype), (np.int64, np.float64, np.int64))
        _, y_one, _, _ = core.expand_votes(x[:1], counts[:1])  # missing classes allowed here
        np.testing.assert_array_equal(y_one, [0])
        with self.assertRaises(ValueError):
            core.expand_votes(x.astype(np.float64), counts)

    def test_weighted_copy_loss_equals_soft_nll(self):
        x, counts, _ = synth()
        _, y, w, src = core.expand_votes(x, counts)
        logp = log_softmax(np.random.default_rng(2).normal(size=(len(x), 3)))
        copy_loss = -(w * logp[src, y]).sum() / len(x)
        self.assertAlmostEqual(copy_loss, core.nll(logp, counts), places=12)
        np.testing.assert_allclose(np.bincount(src, weights=w), 1.0, rtol=0, atol=1e-15)
        for bad in [np.zeros((len(x), 3)), np.full((len(x), 3), np.nan), logp.astype(np.float32)]:
            with self.assertRaises(ValueError):
                core.nll(bad, counts)

    def test_choose_stage(self):
        near = [(25, 1.0), (50, 1.0 - 5e-8), (100, 0.9), (200, 0.9 - 5e-8), (400, 0.95)]
        self.assertEqual(core.choose_stage(near), 100)
        self.assertEqual(core.choose_stage([(s, 1.0) for s in core.STAGES]), 25)
        self.assertEqual(core.choose_stage([(s, 1.0 - 2e-7 * i) for i, s in enumerate(core.STAGES)]), 400)
        for bad in [near[:4], near[::-1], tuple(near), [(25, 1.0), (50, 1.0), (100, 1.0), (200, 1.0), (401, 1.0)],
                    near[:4] + [(400, float("nan"))], near[:4] + [(400, True)], near[:4] + [[400, 1.0]]]:
            with self.assertRaises(ValueError):
                core.choose_stage(bad)


class FitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.x, cls.counts, _ = synth()
        other = np.random.default_rng(1).multinomial(5, [0.2, 0.3, 0.5], size=len(cls.x)).astype(np.int64)
        cls.a_dir, cls.b_dir = cls.root / "a", cls.root / "b"
        cls.model, cls.receipt = core.fit_model(cls.x, cls.counts, cls.a_dir, depth=4, iterations=8)
        core.fit_model(cls.x, other, cls.b_dir, depth=4, iterations=3)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_borders_from_unexpanded_positions(self):
        a = (self.a_dir / "borders.tsv").read_bytes()
        self.assertTrue(a)
        self.assertEqual(a, (self.b_dir / "borders.tsv").read_bytes())

    def test_model_uses_saved_borders(self):
        saved = {}
        for line in (self.a_dir / "borders.tsv").read_text().splitlines():
            if line.strip():
                feature, border = line.split("\t")[:2]
                saved.setdefault(int(feature), []).append(float(border))
        used = self.model.get_borders()
        self.assertTrue(any(used.values()))
        for feature, borders in used.items():
            for border in borders:
                self.assertTrue(np.isclose(saved.get(feature, []), border, rtol=0, atol=1e-6).any(),
                                (feature, border))

    def test_classes_trees_and_receipt(self):
        self.assertEqual(list(self.model.classes_), [0, 1, 2])
        self.assertEqual(self.model.tree_count_, 8)
        r = self.receipt
        self.assertEqual((r["original_positions"], r["weighted_copies"]), (120, int(np.count_nonzero(self.counts))))
        self.assertAlmostEqual(r["total_weight"], 120.0, places=9)
        self.assertEqual(r["model_sha256"], hashlib.sha256((self.a_dir / "model.cbm").read_bytes()).hexdigest())
        self.assertEqual(json.loads((self.a_dir / "fit.json").read_text()), r)
        params = json.loads((self.a_dir / "parameters.json").read_text())
        self.assertEqual((params["depth"], params["iterations"], params["random_seed"]), (4, 8, 7))

    def test_saved_replay_exact(self):
        loaded = core.load_model(self.a_dir / "model.cbm")
        for trees in (None, 3):
            np.testing.assert_array_equal(core.log_probabilities(loaded, self.x, trees=trees),
                                          core.log_probabilities(self.model, self.x, trees=trees))

    def test_log_probabilities(self):
        logp = core.log_probabilities(self.model, self.x)
        self.assertEqual((logp.shape, logp.dtype), ((120, 3), np.float64))
        np.testing.assert_allclose(np.exp(logp).sum(axis=1), 1.0, atol=1e-12)
        self.assertTrue(np.isfinite(core.nll(logp, self.counts)))
        for trees in (0, True, 9, 2.0):
            with self.assertRaises(ValueError):
                core.log_probabilities(self.model, self.x, trees=trees)
        with self.assertRaises(ValueError):
            core.log_probabilities(self.model, self.x.astype(np.float64))

    def test_fit_rejects(self):
        bad_dir = self.root / "bad"
        one_class = np.tile([5, 0, 0], (len(self.x), 1))
        for kwargs in [dict(depth=5, iterations=3), dict(depth=4, iterations=0), dict(depth=4, iterations=401),
                       dict(depth=4, iterations=True), dict(depth=True, iterations=3)]:
            with self.assertRaises(ValueError):
                core.fit_model(self.x, self.counts, bad_dir, **kwargs)
        with self.assertRaises(ValueError):
            core.fit_model(self.x, one_class, bad_dir, depth=4, iterations=3)
        self.assertFalse(bad_dir.exists())
        with self.assertRaises(ValueError):
            core.fit_model(self.x, self.counts, self.a_dir, depth=4, iterations=3)

    def test_api_has_no_eval_inputs(self):
        self.assertEqual(list(inspect.signature(core.fit_model).parameters),
                         ["x", "counts", "output", "depth", "iterations"])
        self.assertFalse({"eval_metric", "early_stopping_rounds", "od_type", "class_weights",
                          "auto_class_weights"} & set(core.RECIPE))
        self.assertIs(core.RECIPE["use_best_model"], False)


if __name__ == "__main__":
    unittest.main()
