r"""Inputs for roofer on one tile (October 24, 2026): the consensus roof points and the county footprints.

    python reviews/2026-10-23/lod2-check/roofer_input.py TILE OUT

Run with the Myria3D or deep-learning clone's Python (laspy, numpy, arcpy; PYTHONNOUSERSITE=1). Read-only on every input;
writes OUT\<TILE>.las and OUT\footprints.shp (a new folder).
- Points: the October 8 working LAS of the tile, with class 6 where at least two of the three sources (native, FRACTAL
  majority, Esri) call the point building and it is a first or single return that is not withheld, overlap or synthetic
  (exactly the points the consensus roof raster uses; reviews/2026-10-21/roof-consensus), class 2 where the native
  classification says ground, and nothing else. Roofer needs classes 2 and 6.
- Footprints: the October 22 massing footprints (FP_ID kept) lying completely within the tile, so each building has all of its
  points. Same projected coordinate system as the points.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
sys.path.insert(0, str(TOOLBOX/"reviews"/"2026-10-21"/"roof-consensus"))
from canopy import las_records  # noqa: E402
import consensus_roofs as cr  # noqa: E402

MASSING = cr.RUNS/"massing-filled-20261023"/"massing.gdb"
TILE_BOUNDS = {"12TVL2804": (428000.0, 4504000.0, 429000.0, 4505000.0)}


def points(tile, out):
    import laspy
    native, scale, offset, modern, _ = las_records.records(cr.NATIVE/f"{tile}.las")
    esri, s2, o2, m2, _ = las_records.records(cr.esri_path(tile))
    n = len(native)
    for axis in "xyz":
        if not np.array_equal(np.asarray(esri[axis]), np.asarray(native[axis])):
            raise ValueError(f"esri points differ from the working LAS ({axis})")
    first, _ = las_records.return_masks(np.asarray(native["returns"]), modern)
    eligible = first & las_records.clean_flags(np.asarray(native["flags"]), modern)
    cls = cr.classes(native, modern)
    says = {"native": (cls == cr.BUILDING) & eligible,
            "fractal": cr.fractal_building(tile, native, scale, offset) & eligible,
            "esri": (cr.classes(esri, m2) == cr.BUILDING) & eligible}
    votes = sum(v.astype(np.uint8) for v in says.values())
    roof = votes >= cr.MIN_VOTES
    ground = (cls == 2) & ~roof
    keep = roof | ground
    del native, esri
    las = laspy.read(cr.NATIVE/f"{tile}.las")
    if len(las.points) != n:
        raise ValueError("point count changed between reads")
    las.points = las.points[keep]
    las.classification = np.where(roof[keep], 6, 2).astype(np.uint8)
    path = out/f"{tile}.las"
    las.write(path)
    return {"points_in_tile": int(n), "roof_points": int(roof.sum()), "ground_points": int(ground.sum()),
            "written": int(keep.sum()), "las": str(path), "point_format": int(las.header.point_format.id),
            "version": str(las.header.version)}


def footprints(tile, out):
    import arcpy
    x0, y0, x1, y1 = TILE_BOUNDS[tile]
    sr = arcpy.Describe(str(MASSING/"footprints")).spatialReference
    layer = arcpy.management.MakeFeatureLayer(str(MASSING/"footprints"), "fp").getOutput(0)
    box = arcpy.Polygon(arcpy.Array([arcpy.Point(x0, y0), arcpy.Point(x1, y0), arcpy.Point(x1, y1), arcpy.Point(x0, y1)]), sr)
    arcpy.management.SelectLayerByLocation(layer, "COMPLETELY_WITHIN", box)
    shp = str(out/"footprints.shp")
    arcpy.conversion.ExportFeatures(layer, shp, field_mapping='FP_ID "FP_ID" true true false 4 Long 0 0, First, #, fp, FP_ID, -1, -1')
    return {"footprints": int(arcpy.management.GetCount(shp)[0]), "shp": shp, "srs": sr.name, "wkid": sr.factoryCode}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tile")
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=False)
    record = {"tile": a.tile, "points": points(a.tile, a.out.resolve()), "footprints": footprints(a.tile, a.out.resolve())}
    (a.out/"roofer-input.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
