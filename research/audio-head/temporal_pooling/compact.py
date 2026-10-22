"""Fixed width-aware PCA for the three-bin temporal representation.

The covariance/sign/normalization recipe matches lexical_compact.core.
Only the raw width changes; frozen historical code remains untouched.
"""
import numpy as np
import torch
from lexical_compact import core as historical
from multiphone_child_train import fit_priors

RECIPE = historical.RECIPE
TRANSFORM_RECIPE = dict(historical.TRANSFORM_RECIPE, input='raw 3072-dimensional before/interval/after target features')
require, _indices, predict = historical.require, historical._indices, historical.predict

def prepare(bundle, family, fitRows):
    """Fit the fixed 16-component covariance PCA and normalization on fit rows."""
    require(family == 'pca16-scalars', 'Unknown compact feature family')
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    scalars, target = np.asarray(bundle['scalars']), np.asarray(bundle['target'])
    require(scalars.ndim == 2 and scalars.shape[1] == 13 and scalars.dtype == np.float32
            and np.isfinite(scalars).all(), 'Invalid scalar features')
    require(target.shape == (len(scalars), 3072) and target.dtype == np.float32
            and np.isfinite(target).all(), 'Invalid target features')
    positions = dict(bundle['positions'])
    require(all(type(k) is int and type(v) is int and 0 <= v < len(scalars) for k, v in positions.items())
            and len(set(positions.values())) == len(positions), 'Invalid feature positions')
    data = dict(cohort=bundle['cohort'], positions=positions, family=family, fit=list(fitRows))
    _indices(data, data['fit'])
    x = torch.tensor(target[[positions[i] for i in data['fit']]], dtype=torch.float64)
    center = x.mean(0)
    centered = x - center
    covariance = centered.T @ centered / len(x)
    eigenvalues, vectors = torch.linalg.eigh(covariance)
    eigenvalues, vectors = eigenvalues.flip(0), vectors.flip(1)
    require(bool(torch.isfinite(eigenvalues).all()) and bool(torch.isfinite(vectors).all())
            and eigenvalues[15].item() > 1e-12 * max(1., eigenvalues[0].item()),
            'PCA has fewer than 16 numerically supported components')
    basis = vectors[:, :16].clone()
    for column in range(16):
        anchor = int(basis[:, column].abs().argmax())
        if basis[anchor, column] < 0:
            basis[:, column].neg_()
    fraction = float(eigenvalues[:16].sum() / eigenvalues.sum())
    transform = dict(center=center, basis=basis, eigenvalues=eigenvalues, rank=16,
                     fitRows=list(data['fit']), varianceFraction=fraction)
    projected = ((torch.tensor(target, dtype=torch.float64) - center) @ basis).numpy().astype(np.float32)
    values = np.concatenate((projected, scalars), axis=1)
    require(np.isfinite(values).all(), 'Nonfinite projected features')
    fit_values = values[[positions[i] for i in data['fit']]].astype(np.float64)
    mean, std = fit_values.mean(0), fit_values.std(0)
    std = np.where(std < 1e-6, 1., std)
    require(np.isfinite(mean).all() and np.isfinite(std).all(), 'Nonfinite fit moments')
    data.update(values=values, transform=transform,
                mean=torch.tensor(mean, dtype=torch.float32), std=torch.tensor(std, dtype=torch.float32),
                priors=fit_priors([data['cohort']['rows'][i] for i in data['fit']]))
    return data



def same_transform(saved, expected):
    """Reject wrong geometry before exact scientific-state comparison."""
    for value in (saved, expected):
        if (value.get('center', torch.empty(0)).shape != (3072,)
                or value.get('basis', torch.empty(0)).shape != (3072, 16)
                or value.get('eigenvalues', torch.empty(0)).shape != (3072,)):
            return False
    return historical.same_transform(saved, expected)


def diagnostics(transform, target, positions):
    """Fit-only diagnostics; squared loading mass is not causal importance."""
    require(same_transform(transform, transform), 'Invalid temporal PCA shape')
    x = np.asarray(target)[[positions[i] for i in transform['fitRows']]].astype(np.float64)
    trace = x.var(0).reshape(3, 1024).sum(1)
    basis = transform['basis'].numpy().reshape(3, 1024, 16)
    mass = (basis ** 2).sum(1)
    return dict(binNames=['before','interval','after'], centeredVarianceTrace=trace.tolist(),
                componentSquaredLoadingMass=mass.tolist(),
                pca16VarianceFraction=transform['varianceFraction'])
