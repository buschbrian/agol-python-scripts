"""Prospective pilot domains and spatial training exclusion; no ArcPy."""
import math

TILES={'12TVL2804':(428000,4504000,429000,4505000),
       '12TVL3302':(433000,4502000,434000,4503000),
       '12TVL2203':(422000,4503000,423000,4504000)}
HOLDOUT_TILE='12TVL3302'
# Includes the prepared tile's 50 m context, preventing training leakage via halos.
HOLDOUT_EXTENT=(432950,4501950,434050,4503050)
HOLDOUT_NOTE=('Prospective fine-tuning holdout frozen 2026-09-29. This tile has already been '
              'used for exploratory processing; it is not a retrospectively untouched test set.')


def scopes(tiles):
    tiles=sorted(tiles)
    result=[(t,[t]) for t in tiles]
    local=[t for t in tiles if t in ('12TVL2804','12TVL3302')]
    if local: result.append(('MILLCREEK_PILOT_TILES',local))
    external=[t for t in tiles if t=='12TVL2203']
    if external: result.append(('EXTERNAL_TRANSFER',external))
    if len(tiles)>1: result.append(('EXPLORATORY_COMBINED',tiles))
    return result


def assert_training_extents(extents):
    for bounds in extents:
        if len(bounds)!=4 or not all(math.isfinite(v) for v in bounds) or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:
            raise ValueError('Finite, ordered training bounds required')
        if bounds[0]<HOLDOUT_EXTENT[2] and bounds[2]>HOLDOUT_EXTENT[0] and bounds[1]<HOLDOUT_EXTENT[3] and bounds[3]>HOLDOUT_EXTENT[1]:
            raise ValueError('Training extent overlaps the prospective 12TVL3302 holdout or its halo')
    return True
