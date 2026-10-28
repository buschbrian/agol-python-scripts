"""Bounded-window maxima, then global plateau reconciliation for counts only.

This does not extend crown segmentation. It uses the existing height bands and
peak representative rule on one canonical raster, with disk-backed work arrays.
"""
from pathlib import Path

import numpy as np
from scipy import ndimage

from .bands import radius_in_cells, validate_bands


def blocks(shape, size):
    for row in range(0, shape[0], size):
        for col in range(0, shape[1], size):
            yield row, col, min(row + size, shape[0]), min(col + size, shape[1])


def local_maxima(array, bands, resolution, smooth_cells):
    if smooth_cells:
        yy, xx = np.ogrid[-smooth_cells:smooth_cells + 1, -smooth_cells:smooth_cells + 1]
        kernel = (xx * xx + yy * yy <= smooth_cells * smooth_cells).astype(float)
        finite = np.isfinite(array)
        total = ndimage.convolve(np.where(finite, array, 0.0), kernel, mode='constant', cval=0)
        weight = ndimage.convolve(finite.astype(float), kernel, mode='constant', cval=0)
        surface = np.divide(total, weight, out=np.full_like(array, np.nan), where=weight > 0)
    else:
        surface = array.copy()
    valid = np.isfinite(array) & (array >= bands[0].low) & (surface >= bands[0].low)
    masked = np.where(valid, surface, -np.inf)
    maxima = np.zeros(array.shape, dtype=bool)
    for band in bands:
        radius = radius_in_cells(band.radius, resolution)
        yy, xx = np.ogrid[-radius:radius + 1, -radius:radius + 1]
        focal = ndimage.maximum_filter(masked, footprint=xx * xx + yy * yy <= radius * radius,
                                      mode='constant', cval=-np.inf)
        inside = (surface >= band.low) & (True if band.high is None else surface < band.high)
        maxima |= valid & inside & (masked >= focal)
    return maxima


def detect(array, bands, resolution, work, smooth_cells=1, block_size=1000, progress=None):
    """Return row, column, raw height; match the bounded detector's plateau rule.

    Global connected-component labels prevent duplicates even when a plateau
    crosses multiple blocks or exceeds the local filtering halo.
    """
    validate_bands(bands)
    if (len(array.shape) != 2 or min(array.shape) < 1 or
            smooth_cells < 0 or int(smooth_cells) != smooth_cells or
            block_size < 1 or int(block_size) != block_size):
        raise ValueError('Expected a nonempty 2D raster and integer window sizes')
    halo = max(radius_in_cells(b.radius, resolution) for b in bands) + smooth_cells
    work = Path(work)
    work.mkdir(exist_ok=False)
    maxima = np.memmap(work / 'maxima.bin', mode='w+', dtype=bool, shape=array.shape)
    for r0, c0, r1, c1 in blocks(array.shape, block_size):
        ra, ca = max(0, r0 - halo), max(0, c0 - halo)
        rb, cb = min(array.shape[0], r1 + halo), min(array.shape[1], c1 + halo)
        mask = local_maxima(np.asarray(array[ra:rb, ca:cb]), bands, resolution, smooth_cells)
        maxima[r0:r1, c0:c1] = mask[r0 - ra:r1 - ra, c0 - ca:c1 - ca]
        if progress:
            progress('maxima', r0, c0)
    maxima.flush()
    labels = np.memmap(work / 'plateaus.bin', mode='w+', dtype='int32', shape=array.shape)
    count = ndimage.label(maxima, structure=np.ones((3, 3)), output=labels)
    labels.flush()
    sums_r, sums_c, sizes = (np.zeros(count + 1, dtype='float64') for _ in range(3))
    heights = np.full(count + 1, -np.inf)
    for r0, c0, r1, c1 in blocks(array.shape, block_size):
        mask = np.asarray(maxima[r0:r1, c0:c1])
        rr, cc = np.nonzero(mask)
        ids = labels[r0:r1, c0:c1][mask]
        sizes += np.bincount(ids, minlength=count + 1)
        sums_r += np.bincount(ids, weights=rr + r0, minlength=count + 1)
        sums_c += np.bincount(ids, weights=cc + c0, minlength=count + 1)
        np.maximum.at(heights, ids, array[r0:r1, c0:c1][mask])
    centres_r = np.divide(sums_r, sizes, out=np.zeros_like(sums_r), where=sizes > 0)
    centres_c = np.divide(sums_c, sizes, out=np.zeros_like(sums_c), where=sizes > 0)
    distances = np.full(count + 1, np.inf)
    positions = np.full(count + 1, np.iinfo('int64').max, dtype='int64')
    for r0, c0, r1, c1 in blocks(array.shape, block_size):
        mask = np.asarray(maxima[r0:r1, c0:c1])
        rr, cc = np.nonzero(mask)
        ids = labels[r0:r1, c0:c1][mask]
        high = array[r0:r1, c0:c1][mask] == heights[ids]
        ids, rr, cc = ids[high], rr[high] + r0, cc[high] + c0
        d = (rr - centres_r[ids]) ** 2 + (cc - centres_c[ids]) ** 2
        np.minimum.at(distances, ids, d)
        # Final row-major tie resolution is independent of block traversal.
        if progress:
            progress('representatives', r0, c0)
    for r0, c0, r1, c1 in blocks(array.shape, block_size):
        mask = np.asarray(maxima[r0:r1, c0:c1])
        rr, cc = np.nonzero(mask)
        ids = labels[r0:r1, c0:c1][mask]
        rr, cc = rr + r0, cc + c0
        d = (rr - centres_r[ids]) ** 2 + (cc - centres_c[ids]) ** 2
        chosen = (array[r0:r1, c0:c1][mask] == heights[ids]) & (d == distances[ids])
        np.minimum.at(positions, ids[chosen], rr[chosen] * array.shape[1] + cc[chosen])
    return [(int(p // array.shape[1]), int(p % array.shape[1]), float(h))
            for p, h in zip(positions[1:], heights[1:])]
