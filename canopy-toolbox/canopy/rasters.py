"""Classified LAS to a CHM with explicit vegetation and observation support."""
from __future__ import annotations

import csv
import os
from pathlib import Path

import arcpy

from . import common
from .tiling import Extent, snap_extent

GROUND_CLASSES = "2"
VEG_CLASSES = "3;4;5"
VEG_RETURNS = "FIRST_OF_MANY;SINGLE"
# Empty vegetation cells are NOT interpolated across roads, lawns, or roofs.
DTM_INTERPOLATION = "TRIANGULATION NATURAL_NEIGHBOR WINDOW_SIZE MINIMUM 1"
DSM_INTERPOLATION = "BINNING MAXIMUM NONE"
NON_CANOPY_CLASSES = "2;6;9;10;11;13;14;15;16;17;20"


def audit(lasd, detailed=False):
    describe = arcpy.Describe(lasd)
    sr = describe.spatialReference
    codes = getattr(describe, "classCodes", "")
    if isinstance(codes, str):
        codes = [int(value) for value in codes.split(";") if value]
    report = {
        "path": os.path.abspath(lasd), "spatial_reference": sr.name,
        "vertical_reference": getattr(getattr(sr, "VCS", None), "name", None),
        "linear_unit": sr.linearUnitName, "point_count": getattr(describe, "pointCount", None),
        "class_codes": sorted(codes), "has_statistics": getattr(describe, "hasStatistics", False),
        "statistics_stale": getattr(describe, "needsUpdateStatistics", True),
    }
    report.update(has_ground=2 in codes, has_vegetation=bool({3, 4, 5} & set(codes)),
                  has_building=6 in codes, has_noise=bool({7, 18} & set(codes)))
    if detailed:
        # This can update LAS statistics: use only on a working copy.
        with common.scratch() as (folder, _):
            csv_path = os.path.join(folder, "statistics.csv")
            arcpy.management.LasDatasetStatistics(
                lasd, "OVERWRITE_EXISTING_STATS", csv_path, "LAS_FILES", "COMMA", "DECIMAL_POINT")
            with open(csv_path, encoding="utf-8-sig", newline="") as handle:
                report["statistics"] = list(csv.DictReader(handle))
    return report


def _las_layer(lasd, name, class_codes, returns):
    arcpy.management.MakeLasDatasetLayer(
        lasd, name, class_code=class_codes, return_values=returns,
        withheld="EXCLUDE_WITHHELD", overlap="EXCLUDE_OVERLAP",
        synthetic="EXCLUDE_SYNTHETIC",
    )
    return name


def _to_raster(layer, path, interpolation, resolution):
    arcpy.conversion.LasDatasetToRaster(
        layer, path, "ELEVATION", interpolation, "FLOAT", "CELLSIZE", resolution, 1)
    return path


def build_chm(lasd, out_workspace, cell_size=0.5, extent=None, prefix="",
              dtm_interpolation=DTM_INTERPOLATION, dsm_interpolation=DSM_INTERPOLATION,
              z_unit=None, source_id=None, building_clearance=.35, classified_background_zero=False):
    from arcpy.sa import Con, IsNull, Raster, SetNull
    common.prefix_name(prefix)
    common.positive(cell_size, "Cell size")
    common.positive(building_clearance, "Building clearance", allow_zero=True)
    if dsm_interpolation != DSM_INTERPOLATION:
        raise ValueError("Vegetation DSM must use BINNING MAXIMUM NONE to preserve unsupported cells")
    sr = common.metric_reference(arcpy.Describe(lasd).spatialReference)
    if not getattr(sr, "VCS", None) and z_unit != "metres":
        raise ValueError("LAS has no vertical units; set z_unit='metres' only after verifying its heights")
    if not os.path.isdir(out_workspace) or out_workspace.lower().endswith(".gdb"):
        raise ValueError("CHM output must be an existing ordinary folder")
    info = audit(lasd)
    if not info["has_statistics"] or info["statistics_stale"]:
        raise ValueError("LAS dataset statistics are missing or stale; refresh them on the working copy after classification")
    if not info["has_ground"]:
        raise ValueError("No ground class 2: classify and verify ground on a working copy first")
    if classified_background_zero and 0 not in info["class_codes"]:
        raise ValueError("Classified background mode requires class 0 in the LAS dataset")
    if not info["has_vegetation"]:
        arcpy.AddWarning("No vegetation classes: this run can only report observed non-canopy or unknown cells")
    if 1 in info["class_codes"] or (0 in info["class_codes"] and not classified_background_zero):
        arcpy.AddWarning("Unclassified points are excluded; unsupported areas remain unknown")
    noncanopy_classes = NON_CANOPY_CLASSES + (";0" if classified_background_zero else "")
    if extent is None:
        box = arcpy.Describe(lasd).extent
        bounds = Extent(box.XMin, box.YMin, box.XMax, box.YMax)
    elif isinstance(extent, str):
        bounds = Extent(*[float(v) for v in extent.split()[:4]])
    else:
        bounds = Extent(extent.XMin, extent.YMin, extent.XMax, extent.YMax)
    bounds = snap_extent(bounds, cell_size)
    paths = {key: common.output(out_workspace, prefix+name+".tif") for key, name in [
        ("dtm", "dtm"), ("dsm", "dsm_veg"), ("chm", "chm"),
        ("support", "vegetation_support"), ("observed", "observed"),
        ("building", "dsm_building"), ("occlusion", "building_occlusion")]}
    manifest = common.output(out_workspace, prefix+"chm.json")
    layers = []
    with common.scratch() as (_, scratch_gdb):
        token = os.path.basename(os.path.dirname(scratch_gdb)).replace("-", "_")
        try:
            with arcpy.EnvManager(extent=bounds.as_arcpy_string(), cellSize=cell_size,
                                  snapRaster=None, outputCoordinateSystem=sr, mask=None,
                                  parallelProcessingFactor="0"):
                ground = _las_layer(lasd, token+"_ground", GROUND_CLASSES, None); layers.append(ground)
                _to_raster(ground, paths["dtm"], dtm_interpolation, cell_size)
            with common.environment(paths["dtm"]):
                vegetation = _las_layer(lasd, token+"_veg", VEG_CLASSES, VEG_RETURNS); layers.append(vegetation)
                other = _las_layer(lasd, token+"_other", noncanopy_classes, VEG_RETURNS); layers.append(other)
                _to_raster(vegetation, paths["dsm"], DSM_INTERPOLATION, cell_size)
                other_path = os.path.join(scratch_gdb, "known_non_canopy")
                _to_raster(other, other_path, "BINNING MAXIMUM NONE", cell_size)
                building_layer = _las_layer(lasd, token+"_building", "6", VEG_RETURNS); layers.append(building_layer)
                _to_raster(building_layer, paths["building"], DSM_INTERPOLATION, cell_size)
                dtm, veg, noncanopy = Raster(paths["dtm"]), Raster(paths["dsm"]), Raster(other_path)
                building = Raster(paths["building"])
                # Upper building returns occlude lower vegetation/wall returns in the SAME cell.
                # Higher canopy survives; no lateral footprint buffer is applied here.
                occluded = Con(IsNull(building) | IsNull(veg), 0,
                               Con(building > veg+building_clearance, 1, 0))
                occluded.save(paths["occlusion"])
                support = Con(IsNull(veg), 0, Con(occluded == 1, 0, 1))
                observed = Con((~IsNull(dtm)) & ((~IsNull(veg)) | (~IsNull(noncanopy))), 1, 0)
                support.save(paths["support"])
                observed.save(paths["observed"])
                difference = veg-dtm
                heights = Con(IsNull(veg) | (occluded == 1), 0, Con(difference < 0, 0, difference))
                SetNull(observed == 0, heights).save(paths["chm"])
        finally:
            for layer in layers:
                arcpy.management.Delete(layer)
    common.write_json(manifest, {
        "source_id": source_id or os.path.abspath(lasd), "input": info,
        "cell_size_m": cell_size, "height_unit": "metres", "extent": bounds,
        "vegetation_classes": VEG_CLASSES, "dsm_interpolation": DSM_INTERPOLATION,
        "building_clearance_m": building_clearance,
        "noncanopy_classes": noncanopy_classes,
        "classified_background_zero": classified_background_zero,
        "building_occlusion_policy": "Class-6 first/single return above vegetation by more than clearance masks that cell; canopy above buildings remains",
        "coverage_policy": "Direct first/single vegetation or recognized non-canopy return; class 0 is non-canopy only when explicitly declared as model-classified background; no vegetation void filling",
        "outputs": paths,
    })
    common.metadata(paths["chm"], "Metre CHM with direct-return support. NoData means unknown, not zero canopy.")
    return paths
