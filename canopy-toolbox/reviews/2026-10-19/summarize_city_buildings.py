"""Bounded-window building statistics using existing planning height metrics.

The city rasters remain disk-backed. Each footprint window is <=4 million cells;
overlapping footprints are independent. A stratified actual ArcGIS rasterization
pilot must match before the feature class is processed.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import arcpy
import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy import common, planning_metrics

NUMERIC = ["FOOTPRINT_M2", "AOI_PCT", "ROOF_COV_PCT", "ROOF_Z50_M", "GROUND_Z50_M",
           "HEIGHT_P50_M", "HEIGHT_P95_M", "HEIGHT_MAX_M"]
INTEGER = ["GRID_CELLS", "ROOF_CELLS", "NEG_H_CELLS", "PARTIAL_AOI"]
FIELDS = NUMERIC + INTEGER + ["HEIGHT_STATUS"]
WARNING = ("Unvalidated roof-minus-terrain estimates from 2023 lidar and current county "
           "footprints. Not surveyed or code-defined building heights. Support below 80% "
           "is a review flag, not an accuracy threshold. Negative cells are retained.")


class Windows:
    def __init__(self, outputs, cache=None):
        self.ground = arcpy.Raster(outputs["terrain"])
        self.roof = arcpy.Raster(outputs["roof_elevation"])
        self.cell = self.ground.meanCellWidth
        self.xmin, self.ymin = self.ground.extent.XMin, self.ground.extent.YMin
        for r in (self.ground, self.roof):
            common.metric_reference(r.spatialReference)
            assert r.meanCellWidth == r.meanCellHeight == .5
            assert r.width == self.ground.width and r.height == self.ground.height
            assert abs(r.extent.XMin - self.xmin) < 1e-7 and abs(r.extent.YMin - self.ymin) < 1e-7
        self.arrays = None
        if cache:
            cache = Path(cache)
            cache.mkdir(exist_ok=False)
            shape = (self.ground.height, self.ground.width)
            self.arrays = {}
            for key, reference in (("roof", self.roof), ("ground", self.ground)):
                mapped = np.memmap(cache/(key+".bin"), dtype="float32", mode="w+", shape=shape)
                block_rows = max(1, min(128, 4_000_000//reference.width))
                assert block_rows*reference.width <= 4_000_000
                for offset in range(0, reference.height, block_rows):
                    rows = min(block_rows, reference.height-offset)
                    corner = arcpy.Point(self.xmin, self.ymin+offset*self.cell)
                    data = arcpy.RasterToNumPyArray(reference, corner, reference.width, rows, -9999).astype(np.float32)
                    data[data == -9999] = np.nan
                    start = reference.height-offset-rows
                    mapped[start:start+rows, :] = data
                mapped.flush()
                self.arrays[key] = mapped
                print(f"Disk-backed {key} windows ready", flush=True)
            common.write_json(cache/"grid.json", {"shape":list(shape), "xmin":self.xmin,
                "ymin":self.ymin, "cell_m":self.cell, "dtype":"float32", "row_order":"north to south",
                "source_roof":str(self.roof), "source_ground":str(self.ground), "nodata":"NaN"})

    def read(self, polygon):
        e, c = polygon.extent, self.cell
        i0, j0 = max(0, math.floor((e.XMin-self.xmin)/c)), max(0, math.floor((e.YMin-self.ymin)/c))
        i1 = min(self.ground.width, math.ceil((e.XMax-self.xmin)/c))
        j1 = min(self.ground.height, math.ceil((e.YMax-self.ymin)/c))
        w, h = i1-i0, j1-j0
        if w <= 0 or h <= 0:
            return None
        if w*h > 4_000_000:
            raise ValueError(f"Footprint window exceeds 4-million-cell bound: {w} x {h}")
        x, y = self.xmin+i0*c, self.ymin+j0*c
        corner = arcpy.Point(x, y)
        if self.arrays is None:
            roof = arcpy.RasterToNumPyArray(self.roof, corner, w, h, -9999).astype(np.float32)
            ground = arcpy.RasterToNumPyArray(self.ground, corner, w, h, -9999).astype(np.float32)
            roof[roof == -9999], ground[ground == -9999] = np.nan, np.nan
        else:
            slices = (slice(self.ground.height-j1, self.ground.height-j0), slice(i0, i1))
            roof, ground = self.arrays["roof"][slices], self.arrays["ground"][slices]
        shape = shapely.from_wkb(bytes(polygon.WKB))
        xs, ys = x+(np.arange(w)+.5)*c, y+(h-np.arange(h)-.5)*c
        mask = shapely.contains_xy(shape, xs[None, :], ys[:, None])
        # Exact boundary centres have ambiguous inclusion rules across rasterizers.
        # Use the established ArcGIS CELL_CENTER method for those rare windows.
        boundary = shapely.intersects_xy(shape, xs[None, :], ys[:, None]) & ~mask
        return roof, ground, mask, [x, y, x+w*c, y+h*c], bool(boundary.any())


def arcgis_mask(polygon, bounds, reference, scratch_gdb):
    fc, raster = str(Path(scratch_gdb)/"one_footprint"), str(Path(scratch_gdb)/"footprint_mask")
    with arcpy.EnvManager(extent=" ".join(map(str, bounds)), cellSize=.5, snapRaster=reference,
                          outputCoordinateSystem=polygon.spatialReference, mask=None, parallelProcessingFactor="0"):
        arcpy.management.CopyFeatures([polygon], fc)
        arcpy.conversion.PolygonToRaster(fc, arcpy.Describe(fc).OIDFieldName, raster, "CELL_CENTER", cellsize=.5)
        result = arcpy.RasterToNumPyArray(raster, nodata_to_value=0) > 0
        arcpy.management.Delete(raster)
        arcpy.management.Delete(fc)
    return result


def summarize(geometry, city, windows, scratch_gdb):
    area = geometry.area if geometry else 0
    clipped = geometry.intersect(city, 4) if geometry and area else None
    inside = clipped.area if clipped else 0
    data = windows.read(clipped) if inside else None
    boundary_fallback = False
    if data:
        roof, ground, mask, bounds, boundary_fallback = data
        if boundary_fallback:
            mask = arcgis_mask(clipped, bounds, windows.ground, scratch_gdb)
        result = planning_metrics.height_summary(roof, ground, mask)
    else:
        result = planning_metrics.height_summary(np.empty((0, 0)), np.empty((0, 0)), np.empty((0, 0), dtype=bool))
    result.update(FOOTPRINT_M2=area, AOI_PCT=100*inside/area if area else 0,
                  PARTIAL_AOI=int(inside < area-max(1e-6, area*1e-8)))
    flags = ["UNVALIDATED"]
    if not inside:
        flags.append("OUTSIDE_AOI")
    elif not result["GRID_CELLS"]:
        flags.append("NO_CELL_CENTERS")
    elif not result["ROOF_CELLS"]:
        flags.append("NO_ROOF_SUPPORT")
    elif result["ROOF_COV_PCT"] < 80:
        flags.append("LOW_ROOF_SUPPORT")
    if result["PARTIAL_AOI"]:
        flags.append("PARTIAL_AOI")
    if result["NEG_H_CELLS"]:
        flags.append("NEGATIVE_HEIGHT")
    result["HEIGHT_STATUS"] = ";".join(flags)
    return result, int(boundary_fallback)


def pilot(entries, city, windows, scratch_gdb):
    ordered = sorted(entries, key=lambda r: r[1].area)
    sample = [ordered[i] for i in np.linspace(0, len(ordered)-1, min(12, len(ordered)), dtype=int)]
    chosen = {r[0] for r in sample}
    for key, geometry in entries:
        if len(sample) >= 20:
            break
        if key not in chosen and geometry.intersect(city, 4).area < geometry.area-1e-6:
            sample.append((key, geometry))
            chosen.add(key)
    checked = []
    for key, geometry in sample:
        clipped = geometry.intersect(city, 4)
        if not clipped or not clipped.area:
            continue
        data = windows.read(clipped)
        if data is None:
            continue
        roof, ground, mask, bounds, boundary = data
        if windows.arrays is not None:
            corner = arcpy.Point(bounds[0], bounds[1])
            for cached, reference in ((roof, windows.roof), (ground, windows.ground)):
                direct = arcpy.RasterToNumPyArray(reference, corner, cached.shape[1], cached.shape[0], -9999).astype(np.float32)
                direct[direct == -9999] = np.nan
                assert np.array_equal(cached, direct, equal_nan=True), f"Cached window differs from raster: {key}"
        oracle = arcgis_mask(clipped, bounds, windows.ground, scratch_gdb)
        assert mask.shape == oracle.shape
        if not boundary:
            assert np.array_equal(mask, oracle), f"Mask differs from ArcGIS CELL_CENTER: {key}"
        else:
            mask = oracle
        a = planning_metrics.height_summary(roof, ground, mask)
        b = planning_metrics.height_summary(roof, ground, oracle)
        assert a == b, (key, a, b)
        checked.append({"source_id": key, "cells": int(mask.sum()), "arcgis_exact_match": True,
                        "cached_values_match_raster": windows.arrays is not None, "boundary_fallback": boundary})
    assert checked
    return checked


def main(root):
    root = Path(root).resolve()
    state = {"status": "waiting", "started": time.time(), "warning": WARNING,
             "runtime": common.runtime(), "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    manifest = root/"building-heights.json"
    if manifest.exists():
        raise FileExistsError("Use a fresh building-height output")
    common.write_json(manifest, state)
    try:
        deadline = time.time()+7200
        while True:
            products = json.loads((root/"products.json").read_text(encoding="utf-8"))
            fp = root/"footprints/footprints.json"
            footprints = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {"status": "waiting"}
            if "failed" in (products["status"], footprints["status"]):
                raise RuntimeError("Raster assembly or footprint fetch failed; inspect its manifest")
            if products["status"] == footprints["status"] == "complete":
                break
            if time.time() > deadline:
                raise TimeoutError("Product inputs did not complete within two hours")
            time.sleep(5)
        source, id_field = footprints["footprints"], footprints["id_field"]
        entries = list(arcpy.da.SearchCursor(source, [id_field, "SHAPE@"]))
        assert len(entries) == len({r[0] for r in entries}) == footprints["city_footprints"]
        assert all(key and geometry and geometry.area for key, geometry in entries)
        parts = [r[0] for r in arcpy.da.SearchCursor(products["boundary"], ["SHAPE@"])]
        city = parts[0]
        for part in parts[1:]:
            city = city.union(part)
        state["status"] = "caching bounded raster windows"
        common.write_json(manifest, state)
        windows = Windows(products["outputs"], cache=root/"building-array-cache")
        state.update(status="pilot", source_footprints=source, id_field=id_field, expected=len(entries))
        common.write_json(manifest, state)
        with common.scratch() as (_, scratch_gdb):
            state["pilot"] = pilot(entries, city, windows, scratch_gdb)
            print(f"Building pilot: {len(state['pilot'])} ArcGIS rasterization matches", flush=True)
            gdb = str(root/"buildings.gdb")
            arcpy.management.CreateFileGDB(str(root), "buildings.gdb")
            target = str(Path(gdb)/"building_heights")
            assert not ({f.name.upper() for f in arcpy.ListFields(source)} & set(FIELDS))
            arcpy.management.CopyFeatures(source, target)
            common.add_fields(target, [(f,"DOUBLE",None) for f in NUMERIC] +
                              [(f,"LONG",None) for f in INTEGER] + [("HEIGHT_STATUS","TEXT",160)])
            state.update(status="summarizing", output=target, completed=0)
            common.write_json(manifest, state)
            counts = Counter()
            repaired = set(footprints.get("geometry_repaired_source_ids", []))
            with (root/"building-heights.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=[id_field]+FIELDS)
                writer.writeheader()
                with arcpy.da.UpdateCursor(target, [id_field,"SHAPE@"]+FIELDS) as cursor:
                    for row in cursor:
                        summary, fallback = summarize(row[1], city, windows, scratch_gdb)
                        if row[0] in repaired:
                            summary["HEIGHT_STATUS"] += ";GEOMETRY_REPAIRED"
                        cursor.updateRow(row[:2]+[summary[f] for f in FIELDS])
                        writer.writerow({id_field: row[0], **summary})
                        counts["footprints"] += 1
                        counts["with_height"] += int(summary["HEIGHT_P50_M"] is not None)
                        counts["boundary_fallbacks"] += fallback
                        for flag in summary["HEIGHT_STATUS"].split(";"):
                            counts[flag] += 1
                        if counts["footprints"] % 250 == 0:
                            state["completed"] = counts["footprints"]
                            common.write_json(manifest, state)
                            print(f"Buildings {state['completed']}/{len(entries)}", flush=True)
            assert counts["footprints"] == len(entries)
            # Geometry and all original attributes must match by the stored source ID.
            fields = [f.name for f in arcpy.ListFields(source)
                      if f.type not in ("OID", "Geometry") and f.name != id_field]
            source_rows = {r[0]: tuple(r[1:]) for r in arcpy.da.SearchCursor(source, [id_field,"SHAPE@WKB"]+fields)}
            output_rows = {r[0]: tuple(r[1:]) for r in arcpy.da.SearchCursor(target, [id_field,"SHAPE@WKB"]+fields)}
            assert source_rows == output_rows, "Source geometry or attributes changed in output copy"
            common.metadata(target, WARNING + " Paired cell statistics; overlapping polygons are independent. "
                            "AOI_PCT is polygon share inside the municipal boundary; GRID_CELLS uses clipped cell centres.")
            state.update(status="complete", completed=len(entries), counts=dict(counts), finished=time.time(),
                         original_geometry_and_attributes_preserved=True,
                         csv=str(root/"building-heights.csv"), max_window_cells=4_000_000)
            state["seconds"] = state["finished"]-state["started"]
            common.write_json(manifest, state)
            print(json.dumps({k:state[k] for k in ("status","output","counts","seconds")}, indent=2), flush=True)
    except BaseException as exc:
        state.update(status="failed", error=str(exc), finished=time.time())
        common.write_json(manifest, state)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    main(parser.parse_args().root)
