"""Fixed decision tradeoffs, row identity and independent fitting normalization."""
import unittest
import tempfile
from pathlib import Path
import numpy as np
import torch
import multiphone_sequence_audit as subject


class SequenceAuditTests(unittest.TestCase):
    def test_decision_requires_all_predeclared_conditions(self):
        pooled = dict(below2AP=.01, rating0AP=.001, macroNLL=-.002, Brier=-.001)
        folds = [dict(below2AP=.001) for _ in range(5)]
        self.assertTrue(subject.decision(pooled, folds)['consistentDevelopmentGain'])
        for field, value in [('below2AP', 1e-7), ('rating0AP', -.001), ('macroNLL', .001), ('Brier', .001)]:
            with self.subTest(field=field):
                self.assertFalse(subject.decision({**pooled, field:value}, folds)['consistentDevelopmentGain'])
        self.assertFalse(subject.decision(pooled, [dict(below2AP=-.001), *folds[1:]])['consistentDevelopmentGain'])
        for bad in (None, np.nan, np.inf):
            with self.assertRaises(ValueError): subject.decision({**pooled, 'rating0AP':bad}, folds)
        with self.assertRaises(ValueError): subject.decision(pooled, folds[:-1])

    def test_outer_uses_row_identity_and_given_fit_moments(self):
        data = dict(positions={10:0, 20:1, 30:2}, values=np.array([[1., 3.], [5., 7.], [9., 11.]], dtype=np.float32),
                    mean=torch.tensor([1., 1.]), std=torch.tensor([2., 2.]),
                    sequenceMean=torch.tensor([1., 2., 3., 4.]), sequenceStd=torch.tensor([2., 2., 2., 2.]))
        sequence = np.array([[9., 10., 11., 12.], [1., 2., 3., 4.], [5., 6., 7., 8.]], dtype=np.float32)
        clean, augmented = subject.outer_values(data, sequence, [30, 10, 20], [20, 30])
        self.assertTrue(torch.equal(clean, torch.tensor([[2., 3.], [4., 5.]])))
        self.assertTrue(torch.equal(augmented[:, -4:], torch.tensor([[2.]*4, [4.]*4])))
        changed = sequence.copy(); changed[1] = 9999
        self.assertTrue(torch.equal(subject.outer_values(data, changed, [30, 10, 20], [20, 30])[1], augmented))
        with self.assertRaises(ValueError): subject.outer_values(data, sequence, [30, 10, 10], [20])
        with self.assertRaises(ValueError): subject.outer_values(data, sequence, [30, 10, 40], [20])

    def test_checkpoint_lineage_and_both_moment_sets_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'state.pt'
            model = subject.SequenceEvidenceHead().eval()
            data = dict(mean=torch.zeros(1037), std=torch.ones(1037),
                        sequenceMean=torch.zeros(4), sequenceStd=torch.ones(4))
            saved = dict(model=model.state_dict(), epoch=2, configSha256='config', declarationSha256='plan', **data)
            manifest = dict(config={'sha256':'config'})
            def selected():
                torch.save(saved, path)
                return dict(epoch=2, checkpoint=subject.metrics.binding(path))
            loaded = subject.checked_state(selected(), manifest, 'plan', data, candidate=True)
            self.assertTrue(all(torch.equal(a, loaded.state_dict()[k]) for k, a in model.state_dict().items()))
            for field in ('mean', 'std', 'sequenceMean', 'sequenceStd'):
                saved[field] = data[field] + 1
                with self.assertRaises(ValueError): subject.checked_state(selected(), manifest, 'plan', data, candidate=True)
                saved[field] = data[field]
            with self.assertRaises(ValueError): subject.checked_state(selected(), manifest, 'another-plan', data, candidate=True)
            pin = selected(); path.write_bytes(b'changed')
            with self.assertRaises(ValueError): subject.checked_state(pin, manifest, 'plan', data, candidate=True)


if __name__ == '__main__': unittest.main()
