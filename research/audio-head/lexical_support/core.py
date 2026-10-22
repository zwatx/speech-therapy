"""Descriptive input support distances and empirical reference ranks; no fitting."""
import numpy as np


def require(ok, message):
    if not ok: raise ValueError(message)


def midrank(reference, values):
    reference=np.asarray(reference,dtype=np.float64);values=np.asarray(values,dtype=np.float64)
    require(reference.ndim==values.ndim==1 and len(reference)>0 and np.isfinite(reference).all() and np.isfinite(values).all(),'Invalid empirical reference')
    ordered=np.sort(reference)
    return (np.searchsorted(ordered,values,side='left')+np.searchsorted(ordered,values,side='right'))/(2.*len(reference))


def scores(scalars,target,mean,std,center,basis):
    scalars,target,mean,std,center,basis=[np.asarray(x,dtype=np.float64) for x in (scalars,target,mean,std,center,basis)]
    require(scalars.ndim==target.ndim==2 and len(scalars)==len(target)>0,'Invalid feature rows')
    require(mean.shape==std.shape==(scalars.shape[1],) and center.shape==(target.shape[1],) and basis.ndim==2 and basis.shape[0]==len(center),'Invalid saved transform dimensions')
    require(all(np.isfinite(x).all() for x in (scalars,target,mean,std,center,basis)) and (std>0).all(),'Invalid saved transform values')
    require(np.allclose(basis.T@basis,np.eye(basis.shape[1]),rtol=0,atol=1e-12),'Basis not orthonormal')
    z=(scalars-mean)/std
    centered=target-center
    # Explicit residual avoids subtracting almost-equal squared norms.
    residual=centered-(centered@basis)@basis.T
    return dict(scalarMaxAbsZ=np.max(np.abs(z),axis=1),scalarZ=z,
                dominantScalar=np.argmax(np.abs(z),axis=1),pcaResidualMSE=np.mean(residual**2,axis=1))


def compare(reference,values,reference_phones,phones):
    reference_phones=np.asarray(reference_phones);phones=np.asarray(phones)
    require(reference_phones.shape==(len(reference),) and phones.shape==(len(values),),'Phone rows differ')
    overall=midrank(reference,values);within=np.empty(len(values));support=np.empty(len(values),dtype=np.int64)
    for phone in np.unique(phones):
        fit=reference_phones==phone;outer=phones==phone
        require(fit.any(),'No fitting support for phone')
        within[outer]=midrank(np.asarray(reference)[fit],np.asarray(values)[outer]);support[outer]=int(fit.sum())
    return dict(globalPercentile=overall,samePhonePercentile=within,samePhoneFitPositions=support)
