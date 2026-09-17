"""Height-banded maxima with one actual raster-cell point per plateau."""
from __future__ import annotations

import hashlib
import math
import os
import uuid

import arcpy
import numpy as np
from scipy import ndimage

from .bands import radius_in_cells, validate_bands
from . import common

MAX_CELLS = 4_000_000


def smooth_surface(array, radius):
    if isinstance(radius, bool) or int(radius) != radius or radius < 0:
        raise ValueError("Smoothing radius must be a non-negative integer")
    if radius == 0:
        return array.copy()
    yy, xx = np.ogrid[-radius:radius+1, -radius:radius+1]
    kernel = (xx*xx+yy*yy <= radius*radius).astype(float)
    valid = np.isfinite(array)
    total = ndimage.convolve(np.where(valid, array, 0.0), kernel, mode="constant", cval=0)
    weight = ndimage.convolve(valid.astype(float), kernel, mode="constant", cval=0)
    return np.divide(total, weight, out=np.full_like(array, np.nan), where=weight > 0)


def peak_cells(array, bands, resolution, smooth_cells):
    """Return plateau representatives, selected by raw height then centroid distance."""
    surface = smooth_surface(array, smooth_cells)
    valid = np.isfinite(array) & (array >= bands[0].low) & (surface >= bands[0].low)
    masked = np.where(valid, surface, -np.inf)
    maxima = np.zeros(array.shape, dtype=bool)
    for band in bands:
        radius = radius_in_cells(band.radius, resolution)
        yy, xx = np.ogrid[-radius:radius+1, -radius:radius+1]
        footprint = xx*xx+yy*yy <= radius*radius
        focal = ndimage.maximum_filter(masked, footprint=footprint, mode="constant", cval=-np.inf)
        inside = (surface >= band.low) & (True if band.high is None else surface < band.high)
        maxima |= valid & inside & (masked >= focal)
    regions, count = ndimage.label(maxima, structure=np.ones((3, 3)))
    peaks = []
    for label, bounds in enumerate(ndimage.find_objects(regions), 1):
        if bounds is None:
            continue
        local = regions[bounds] == label
        rr, cc = np.nonzero(local)
        rr, cc = rr+bounds[0].start, cc+bounds[1].start
        values = array[rr, cc]
        candidates = np.flatnonzero(values == values.max())
        distances = (rr[candidates]-rr.mean())**2 + (cc[candidates]-cc.mean())**2
        selected = candidates[np.argmin(distances)]
        peaks.append((int(rr[selected]), int(cc[selected]), float(values[selected])))
    return peaks


def detect(chm_path, out_workspace, bands, cell_size=None, smooth_cells=1, prefix="", source_id=None):
    validate_bands(bands)
    gdb = common.geodatabase(out_workspace)
    common.prefix_name(prefix)
    raster, resolution = common.grid(chm_path, cell_size, MAX_CELLS)
    path = common.output(gdb, prefix + "treetops")
    array = arcpy.RasterToNumPyArray(raster, nodata_to_value=np.nan)
    peaks = peak_cells(array, bands, resolution, smooth_cells)
    if source_id is None:
        identity = os.path.abspath(chm_path)
        if os.path.isfile(chm_path):
            identity += "|" + str(os.path.getmtime(chm_path))
        source_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    if len(source_id) > 128:
        raise ValueError("Source ID must fit in 128 characters")
    common.create_points(gdb, os.path.basename(path), raster.spatialReference)
    fields = ["SHAPE@XY", "TREE_ID", "HEIGHT_M", "MIN_HEIGHT", "SMOOTH", "SOURCE_ID", "REVIEW_STATUS"]
    with arcpy.da.InsertCursor(path, fields) as cursor:
        for row, col, height in peaks:
            x = raster.extent.XMin+(col+0.5)*resolution
            y = raster.extent.YMax-(row+0.5)*resolution
            identity = f"{source_id}|{raster.spatialReference.factoryCode}|{x:.6f}|{y:.6f}"
            tree_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
            cursor.insertRow([(x, y), tree_id, height, bands[0].low, smooth_cells, source_id, "UNVERIFIED"])
    common.metadata(path, f"Estimated treetops from {chm_path}; source ID {source_id}; minimum {bands[0].low} m.")
    return path
