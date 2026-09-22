"""Compare the toolbox DTM against the delivery-derived 0.5 m DEM over the pilot AOI.

Both surfaces come from the same 2023 point cloud, so agreement is a check on the
toolbox's interpolation, not an independent accuracy assessment.
"""
import json
import tempfile
from pathlib import Path

import arcpy
import numpy as np

arcpy.env.scratchWorkspace = tempfile.mkdtemp()

SURFACES = Path(r"U:\agol-python-scripts\canopy-toolbox\scratch\planning_20260922\millcreek_products\surfaces")
VENDOR = r"G:\GIS\Data\millcreek_dem_half_meter.tif"
OUT = Path(r"U:\agol-python-scripts\canopy-toolbox\scratch\planning_20260922\dem_comparison")
OUT.mkdir(parents=True, exist_ok=True)

CELL = 0.5
XMIN, YMIN, XMAX, YMAX = 428100.0, 4504100.0, 428400.0, 4504400.0
NCOLS = NROWS = int((XMAX - XMIN) / CELL)


def window(path):
    """Read the AOI window from a raster on the shared 0.5 m grid, NaN for NoData."""
    array = arcpy.RasterToNumPyArray(path, arcpy.Point(XMIN, YMIN), NCOLS, NROWS,
                                     nodata_to_value=np.nan)
    if array.shape != (NROWS, NCOLS):
        raise ValueError(f"{path}: got {array.shape}, expected {(NROWS, NCOLS)}")
    return array.astype(np.float64)


def describe(values, label):
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"label": label, "cells": 0}
    return {
        "label": label, "cells": int(values.size),
        "mean_m": float(values.mean()), "median_m": float(np.median(values)),
        "std_m": float(values.std(ddof=1)) if values.size > 1 else 0.0,
        "rmse_m": float(np.sqrt((values ** 2).mean())),
        "mae_m": float(np.abs(values).mean()),
        "p05_m": float(np.percentile(values, 5)), "p95_m": float(np.percentile(values, 95)),
        "min_m": float(values.min()), "max_m": float(values.max()),
        "within_2cm_pct": float(100 * (np.abs(values) <= 0.02).mean()),
        "within_5cm_pct": float(100 * (np.abs(values) <= 0.05).mean()),
        "within_10cm_pct": float(100 * (np.abs(values) <= 0.10).mean()),
    }


toolbox = window(str(SURFACES / "dtm.tif"))
vendor = window(VENDOR)
direct = window(str(SURFACES / "ground_direct.tif"))
distance = window(str(SURFACES / "ground_distance_m.tif"))
roof = window(str(SURFACES / "dsm_building.tif"))

both = np.isfinite(toolbox) & np.isfinite(vendor)
difference = np.where(both, toolbox - vendor, np.nan)

report = {
    "aoi": [XMIN, YMIN, XMAX, YMAX], "cell_size_m": CELL, "grid": [NROWS, NCOLS],
    "toolbox_dtm": str(SURFACES / "dtm.tif"), "vendor_dem": VENDOR,
    "coverage": {
        "total_cells": int(toolbox.size),
        "toolbox_valid": int(np.isfinite(toolbox).sum()),
        "vendor_valid": int(np.isfinite(vendor).sum()),
        "compared": int(both.sum()),
        "toolbox_only": int((np.isfinite(toolbox) & ~np.isfinite(vendor)).sum()),
        "vendor_only": int((~np.isfinite(toolbox) & np.isfinite(vendor)).sum()),
    },
    "elevation_range": {
        "toolbox": [float(np.nanmin(toolbox)), float(np.nanmax(toolbox))],
        "vendor": [float(np.nanmin(vendor)), float(np.nanmax(vendor))],
    },
    "difference_toolbox_minus_vendor": [
        describe(difference, "all compared cells"),
        describe(np.where(np.isfinite(direct), difference, np.nan), "cells with a direct class-2 return"),
        describe(np.where(~np.isfinite(direct), difference, np.nan), "cells with no direct ground return"),
        describe(np.where(np.isfinite(roof), difference, np.nan), "cells under a measured roof"),
        describe(np.where(~np.isfinite(roof), difference, np.nan), "cells not under a roof"),
    ],
    "by_ground_support_distance": [],
}

for low, high in [(0, 0.5), (0.5, 1), (1, 2), (2, 4), (4, 8), (8, 99)]:
    band = (distance >= low) & (distance < high)
    report["by_ground_support_distance"].append(
        describe(np.where(band, difference, np.nan), f"{low}-{high} m from direct ground"))

# Largest disagreements, for inspection in Pro.
flat = np.where(np.isfinite(difference), np.abs(difference), -1)
worst = np.dstack(np.unravel_index(np.argsort(flat, axis=None)[-10:][::-1], flat.shape))[0]
report["largest_disagreements"] = [
    {"easting": XMIN + (int(c) + 0.5) * CELL, "northing": YMAX - (int(r) + 0.5) * CELL,
     "toolbox_m": float(toolbox[r, c]), "vendor_m": float(vendor[r, c]),
     "difference_m": float(difference[r, c]),
     "direct_ground": bool(np.isfinite(direct[r, c])),
     "under_roof": bool(np.isfinite(roof[r, c])),
     "ground_distance_m": float(distance[r, c])}
    for r, c in worst]

(OUT / "dem-comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

fig, axes = plt.subplots(2, 2, figsize=(13, 12))
extent = [0, XMAX - XMIN, 0, YMAX - YMIN]
limit = float(np.nanpercentile(np.abs(difference), 99.5))

im = axes[0, 0].imshow(difference, cmap="RdBu_r", extent=extent,
                       norm=TwoSlopeNorm(vcenter=0, vmin=-limit, vmax=limit))
axes[0, 0].set_title("Toolbox DTM minus delivery DEM (m)")
fig.colorbar(im, ax=axes[0, 0], shrink=.8)

values = difference[np.isfinite(difference)]
axes[0, 1].hist(values, bins=120, range=(-limit, limit), color="#4C72B0")
axes[0, 1].axvline(0, color="k", lw=.8)
axes[0, 1].set_title(f"Differences (n={values.size:,})\nmedian {np.median(values):+.3f} m, "
                     f"RMSE {np.sqrt((values**2).mean()):.3f} m")
axes[0, 1].set_xlabel("metres")

im = axes[1, 0].imshow(np.where(np.isfinite(direct), 1.0, 0.0), cmap="Greys", extent=extent)
axes[1, 0].set_title("Direct class-2 ground support (white = none)")

im = axes[1, 1].imshow(distance, cmap="magma", extent=extent)
axes[1, 1].set_title("Distance to nearest direct ground return (m)")
fig.colorbar(im, ax=axes[1, 1], shrink=.8)

for ax in axes.ravel():
    ax.set_xlabel("metres east"); ax.set_ylabel("metres north")
fig.suptitle("Toolbox DTM vs delivery-derived DEM — 300 x 300 m Millcreek pilot, 0.5 m",
             fontsize=14, fontweight="bold")
fig.tight_layout()
fig.savefig(OUT / "dem-comparison.png", dpi=110)

print(json.dumps({k: v for k, v in report.items() if k != "largest_disagreements"}, indent=2))
