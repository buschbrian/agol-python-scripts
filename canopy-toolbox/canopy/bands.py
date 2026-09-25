"""Height-banded search radii for local-maximum treetop detection.

ArcGIS has no variable-window filter, so the window is approximated by running
Focal Statistics once per height band and combining the results. Pure Python:
no arcpy, so it is unit-testable outside ArcGIS Pro.
"""

from __future__ import annotations

import math
from typing import NamedTuple, Sequence


class Band(NamedTuple):
    low: float
    high: float | None  # None means open-ended
    radius: float       # metres

    def contains(self, height: float) -> bool:
        if height < self.low:
            return False
        return self.high is None or height < self.high


# Open-grown urban defaults. Re-fit these against a local crown-radius sample
# before publishing a count; they are the single biggest accuracy lever.
DEFAULT_BANDS: tuple[Band, ...] = (
    Band(2.0, 6.0, 1.0),
    Band(6.0, 12.0, 1.5),
    Band(12.0, 20.0, 2.0),
    Band(20.0, None, 2.5),
)

DEFAULT_SPEC = "2-6:1.0, 6-12:1.5, 12-20:2.0, 20-:2.5"


def parse_bands(spec: str) -> tuple[Band, ...]:
    """Parse "2-6:1.0, 6-12:1.5, 20-:2.5" into Bands."""
    bands: list[Band] = []
    for chunk in (c.strip() for c in spec.split(",")):
        if not chunk:
            continue
        try:
            extent, radius = chunk.split(":")
            low_text, high_text = extent.split("-", 1)
            low = float(low_text)
            high = float(high_text) if high_text.strip() else None
        except ValueError as exc:
            raise ValueError(f"cannot parse band {chunk!r}; expected 'low-high:radius'") from exc
        bands.append(Band(low, high, float(radius)))
    validate_bands(bands)
    return tuple(bands)


def validate_bands(bands: Sequence[Band]) -> None:
    """Reject gaps, overlaps, and anything that would silently drop trees."""
    if not bands:
        raise ValueError("at least one height band is required")
    for band in bands:
        if not all(math.isfinite(v) for v in (band.low, band.radius)) or (band.high is not None and not math.isfinite(band.high)):
            raise ValueError('height bands must contain finite numbers')
        if band.low < 0:
            raise ValueError('minimum height cannot be negative')
        if band.radius <= 0:
            raise ValueError(f"band {band} has a non-positive radius")
        if band.high is not None and band.high <= band.low:
            raise ValueError(f"band {band} does not ascend")
    for previous, current in zip(bands, bands[1:]):
        if previous.high is None:
            raise ValueError("only the final band may be open-ended")
        if current.low != previous.high:
            raise ValueError(
                f"bands must tile without gaps: {previous.high} -> {current.low}"
            )
    if bands[-1].high is not None:
        raise ValueError("the final band must be open-ended so tall trees are not dropped")


def min_height(bands: Sequence[Band]) -> float:
    return bands[0].low


def radius_for_height(bands: Sequence[Band], height: float) -> float | None:
    for band in bands:
        if band.contains(height):
            return band.radius
    return None


def radius_in_cells(radius_m: float, cell_size: float) -> int:
    """Focal Statistics takes whole cells; never round down to zero."""
    if not math.isfinite(cell_size) or cell_size <= 0:
        raise ValueError("cell size must be positive")
    if not math.isfinite(radius_m) or radius_m <= 0:
        raise ValueError('radius must be finite and positive')
    return max(1, round(radius_m / cell_size))
