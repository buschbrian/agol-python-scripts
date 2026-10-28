"""NAIP spectral review screens, never vegetation truth or LAS edits. No ArcPy."""
import numpy as np


def ndvi(red, nir, valid=None):
    red=np.asarray(red,dtype=float);nir=np.asarray(nir,dtype=float)
    if red.shape!=nir.shape: raise ValueError('Red and NIR grids must match')
    mask=np.isfinite(red)&np.isfinite(nir)&(red>=0)&(nir>=0)&((red+nir)>0)
    if valid is not None:
        valid=np.asarray(valid,dtype=bool)
        if valid.shape!=red.shape: raise ValueError('Validity mask grid must match')
        mask &= valid
    result=np.full(red.shape,np.nan)
    np.divide(nir-red,nir+red,out=result,where=mask)
    return result


def screen(value, threshold=.3):
    if not np.isfinite(threshold) or not -1<=threshold<=1: raise ValueError('NDVI threshold must be between -1 and 1')
    value=np.asarray(value,dtype=float)
    return np.where(~np.isfinite(value),'UNKNOWN',np.where(value<threshold,'LOW_GREENNESS_REVIEW','GREEN_SPECTRAL_SUPPORT'))
