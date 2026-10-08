"""Physical roof context shared by footprint screens and validation; no ArcPy.

Sampling strata retain their historic names and precedence. UNKNOWN is not proof
of an intermediate roof level; its legacy sampling bucket is ROOF_MID.
"""
import math

NEAR_M=1.0
LEVEL_M=.5
OVERHANG_M=2.0


def context(distance, height, roof_height, near=NEAR_M, level=LEVEL_M, overhang=OVERHANG_M):
    if distance is None or not math.isfinite(distance) or distance > near:
        return 'AWAY',None
    if any(value is None or not math.isfinite(value) for value in (height,roof_height)):
        return 'UNKNOWN',None
    above=float(height-roof_height)
    return ('ROOF_LEVEL' if above <= level else 'ABOVE_ROOF' if above > overhang else 'ROOF_MID'),above
