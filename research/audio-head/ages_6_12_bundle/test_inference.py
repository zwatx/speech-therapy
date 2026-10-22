"""Synthetic-bundle tests for ages_6_12_bundle.inference.

Fixtures use seeded random head weights and a random orthonormal projection.
They are not trained on, and make no claim about, any real corpus.
"""
import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

import multiphone_models
from ages_6_12_bundle import inference as bundle

PAYLOAD_FILES = ("scalar.pt", "compact.pt", "projection.pt")


def make_payloads():
    payloads = {}
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(7)
        for name, width in (("scalar.pt", 13), ("compact.pt", 29)):
            head = multiphone_models.MeanPoolPhoneRatingHead(width, 24, 128, 0.1)
            state = {key: value.clone() for key, value in head.state_dict().items()}
            state["classifier.3.weight"] *= 5  # spread logits so the two heads clearly differ
            payloads[name] = {"model": state, "mean": torch.randn(width),
                              "std": torch.rand(width) + 0.5, "epochs": 7}
        basis, _ = torch.linalg.qr(torch.randn(1024, 16, dtype=torch.float64))
        payloads["projection.pt"] = {"center": torch.randn(1024, dtype=torch.float64),
                                     "basis": basis.contiguous()}
    return payloads


def write_bundle(root, payloads, edit=None):
    root.mkdir()
    for name in PAYLOAD_FILES:
        torch.save(payloads[name], root / name)
    (root / "provenance.json").write_text(json.dumps({"fixture": "synthetic random weights; no corpus"}))
    manifest = {
        "schemaVersion": 1, "kind": "cadence-expanded-child-mixture", "ageRangeYears": [6, 12],
        "featureWidth": 1037, "targetPhones": list(bundle.PHONES), "mixtureWeights": [0.5, 0.5],
        "learnerFeedbackEligible": False, "clinicalUseEligible": False, "promotionEligible": False,
        "modelSourceSha256": bundle.sha256(multiphone_models.__file__),
        "files": {name: bundle.sha256(root / name) for name in bundle.FILE_NAMES},
    }
    if edit:
        edit(manifest)
    data = json.dumps(manifest).encode()
    (root / "manifest.json").write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def manual_probs(payload, values, ids):
    s = {key: value.double() for key, value in payload["model"].items()}
    gelu = torch.nn.functional.gelu
    x = torch.from_numpy((values - payload["mean"].numpy()) / payload["std"].numpy()).double()
    h = gelu(x @ s["acoustic_projection.0.weight"].T + s["acoustic_projection.0.bias"])
    h = torch.cat((h, s["phone_embedding.weight"][torch.from_numpy(ids)]), dim=1)
    h = gelu(h @ s["classifier.0.weight"].T + s["classifier.0.bias"])
    return torch.softmax(h @ s["classifier.3.weight"].T + s["classifier.3.bias"], dim=1).numpy()


class ResearchMixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads = make_payloads()
        rng = np.random.default_rng(7)
        cls.features = rng.standard_normal((70, 1037)).astype(np.float32)  # spans two 64-row batches
        cls.ids = rng.integers(0, 23, size=70)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def load(self, name="bundle", payloads=None, edit=None):
        root = self.tmp / name
        return bundle.load_bundle(root, write_bundle(root, payloads or self.payloads, edit))

    def compact_reference(self):
        projection = self.payloads["projection.pt"]
        targets = torch.from_numpy(self.features[:, :1024]).double()
        projected = ((targets - projection["center"]) @ projection["basis"]).numpy().astype(np.float32)
        return np.concatenate((projected, self.features[:, 1024:]), axis=1)

    def test_manual_forward_is_log_of_mean_probability(self):
        out = self.load().predict(self.features, self.ids, age_years=8)
        p1 = manual_probs(self.payloads["scalar.pt"], self.features[:, 1024:], self.ids)
        p2 = manual_probs(self.payloads["compact.pt"], self.compact_reference(), self.ids)
        np.testing.assert_allclose(out["probabilities"], 0.5 * (p1 + p2), atol=1e-5)
        np.testing.assert_allclose(out["logProbabilities"], np.log(0.5 * (p1 + p2)), atol=1e-4)
        geometric = 0.5 * (np.log(p1) + np.log(p2))
        self.assertGreater(np.abs(out["logProbabilities"] - geometric).max(), 1e-3)
        for key in ("probabilities", "logProbabilities"):
            self.assertEqual((out[key].dtype, out[key].shape), (np.float64, (70, 3)))
        np.testing.assert_allclose(out["probabilities"].sum(axis=1), 1.0, atol=1e-12)
        self.assertEqual(out["ageRangeYears"], [6, 12])
        for flag in ("learnerFeedbackEligible", "clinicalUseEligible", "promotionEligible"):
            self.assertIs(out[flag], False)

    def test_pca_contract_and_float32_normalization(self):
        _, compact = self.load()._head_inputs(self.features)
        head = self.payloads["compact.pt"]
        expected = (self.compact_reference() - head["mean"].numpy()) / head["std"].numpy()
        self.assertEqual(compact.dtype, np.float32)
        np.testing.assert_array_equal(compact, expected)

    def test_preserves_order_repeats_and_state(self):
        model = self.load()
        full = model.predict(self.features, self.ids, age_years=9)["probabilities"]
        index = [69, 0, 69, 3, 64]
        part = model.predict(self.features[index], self.ids[index], age_years=9)["probabilities"]
        np.testing.assert_allclose(part, full[index], atol=1e-6)
        np.testing.assert_array_equal(model.predict(self.features, self.ids, age_years=9)["probabilities"], full)

    def test_age_scope(self):
        model = self.load()
        x, ids = self.features[:2], self.ids[:2]
        for age in (6, 12.99, np.int64(9), np.float32(6.5)):
            model.predict(x, ids, age_years=age)
        for age in (5.99, 13, float("nan"), float("inf"), True, np.bool_(True), "8", None):
            with self.subTest(age=age), self.assertRaises(ValueError):
                model.predict(x, ids, age_years=age)

    def test_rejects_invalid_features_and_ids(self):
        model = self.load()
        x, ids = self.features[:4], self.ids[:4]
        nan = x.copy()
        nan[1, 5] = np.nan
        for features in (x.astype(np.float64), x[:, :1036], x[:0], nan, x.tolist()):
            with self.subTest(features=type(features)), self.assertRaises(ValueError):
                model.predict(features, ids, age_years=8)
        for bad in (np.array([0, 1, 2, 23]), np.array([0, -1, 2, 3]), ids.astype(np.float64),
                    np.ones(4, dtype=bool), ids[:3], ids[:, None], ids.tolist()):
            with self.subTest(ids=bad), self.assertRaises(ValueError):
                model.predict(x, bad, age_years=8)

    def test_checksums_and_hash_argument(self):
        root = self.tmp / "bundle"
        digest = write_bundle(root, self.payloads)
        for bad in ("0" * 64, digest.upper(), digest[:-1], None):
            with self.subTest(digest=bad), self.assertRaises(ValueError):
                bundle.load_bundle(root, bad)
        with (root / "provenance.json").open("ab") as handle:
            handle.write(b" ")
        with self.assertRaisesRegex(ValueError, "provenance.json"):
            bundle.load_bundle(root, digest)

    def test_manifest_contract(self):
        def missing_flag(m): del m["promotionEligible"]
        def true_flag(m): m["clinicalUseEligible"] = True
        def int_flag(m): m["learnerFeedbackEligible"] = 0
        def bool_version(m): m["schemaVersion"] = True
        def source_drift(m): m["modelSourceSha256"] = "0" * 64
        def traversal(m): m["files"]["../scalar.pt"] = m["files"].pop("scalar.pt")
        for i, edit in enumerate((missing_flag, true_flag, int_flag, bool_version, source_drift, traversal)):
            with self.subTest(edit.__name__), self.assertRaises(ValueError):
                self.load(f"m{i}", edit=edit)
        root = self.tmp / "duplicate"
        write_bundle(root, self.payloads)
        data = b'{"kind": "other", ' + (root / "manifest.json").read_bytes()[1:]
        (root / "manifest.json").write_bytes(data)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            bundle.load_bundle(root, hashlib.sha256(data).hexdigest())

    def test_corrupt_payloads_rejected_after_rehash(self):
        def nan_mean(p): p["scalar.pt"]["mean"][0] = float("nan")
        def zero_std(p): p["compact.pt"]["std"][3] = 0
        def float64_mean(p): p["compact.pt"]["mean"] = p["compact.pt"]["mean"].double()
        def bent_basis(p): p["projection.pt"]["basis"][0, 0] += 1e-3
        def inf_weight(p): p["scalar.pt"]["model"]["classifier.0.weight"][0, 0] = float("inf")
        def missing_weight(p): del p["compact.pt"]["model"]["classifier.3.bias"]
        def bad_epochs(p): p["scalar.pt"]["epochs"] = 101
        for i, corrupt in enumerate((nan_mean, zero_std, float64_mean, bent_basis,
                                     inf_weight, missing_weight, bad_epochs)):
            payloads = copy.deepcopy(self.payloads)
            corrupt(payloads)
            with self.subTest(corrupt.__name__), self.assertRaises(ValueError):
                self.load(f"c{i}", payloads)

    def test_rejects_symlinks(self):
        root = self.tmp / "bundle"
        digest = write_bundle(root, self.payloads)
        link = self.tmp / "link"
        link.symlink_to(root, target_is_directory=True)
        with self.assertRaises(ValueError):
            bundle.load_bundle(link, digest)
        outside = self.tmp / "outside.json"
        (root / "provenance.json").rename(outside)
        (root / "provenance.json").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            bundle.load_bundle(root, digest)

    def test_relocation_rng_and_threads(self):
        source = self.tmp / "source"
        digest = write_bundle(source, self.payloads)
        expected = bundle.load_bundle(source, digest).predict(self.features, self.ids, age_years=10)
        moved = self.tmp / "moved"
        shutil.copytree(source, moved)
        shutil.rmtree(source)
        rng_state, threads = torch.get_rng_state(), torch.get_num_threads()
        model = bundle.load_bundle(moved, digest)
        self.assertTrue(torch.equal(torch.get_rng_state(), rng_state))
        out = model.predict(self.features, self.ids, age_years=10)
        self.assertEqual(torch.get_num_threads(), threads)
        np.testing.assert_array_equal(out["logProbabilities"], expected["logProbabilities"])


if __name__ == "__main__":
    unittest.main()
