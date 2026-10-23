r"""Candidate footprints detected and outlined from the 2023 LiDAR alone (October 23, 2026): clusters of consensus roof
cells outside every county footprint, with the county footprints' roof-height statistics, for a Field Maps review and
massing. Overture's outlines are only a witness afterwards (`witness`), kept out of the candidate layer.

    python reviews/2026-10-23/footprint-candidates/lidar_candidates.py detect OUT --pilot   12TVL2804 only, to check
    python reviews/2026-10-23/footprint-candidates/lidar_candidates.py detect OUT           OUT\candidates.gdb
    python reviews/2026-10-23/footprint-candidates/lidar_candidates.py web OUT              OUT\web.gdb (Web Mercator)
    python reviews/2026-10-23/footprint-candidates/lidar_candidates.py pilot OUT            LOD1.2 blocks for 20
    python reviews/2026-10-23/footprint-candidates/lidar_candidates.py massing OUT          LOD1.2 blocks for all
    python reviews/2026-10-23/footprint-candidates/lidar_candidates.py witness OUT          OUT\witness.gdb, witness.json

ArcGIS Pro Python with 3D Analyst and Spatial Analyst (env millcreek-py3, PYTHONNOUSERSITE=1, -I). Read-only on the
library; writes only under OUT. Brian decided on October 23 that the layer must not be derived from Overture (ODbL), so
`detect` reads only the library's `roof_height_m.tif` and `observed.tif`, the county footprints
(`buildings.gdb/building_heights`) and, for context, the parcels. Rules, all fixed from county data before any comparison:
- Roof cell: `roof_height_m.tif` has a value (2-of-3 consensus roof), inside the city (`observed.tif` != 3).
- Not county: the cell centre is more than 1.5 m from every county footprint cell (cell centres rasterized as
  building_heights counts them). Roof cells just outside the footprints fall from 62% of cells at 0.5 m to 8% at 1.5 m
  and near the 2-3% background by 2.5-3 m: eaves and outline offsets.
- A 3 x 3 opening removes strips narrower than 1.5 m (fence tops, eave remnants); 8-connected clusters follow.
- Kept: at least 40 cells (10 m2; the county footprints' 1st percentile is 12 m2) and a median roof height of at least
  2.0 m (the 1st percentile of county footprints under 40 m2 is 2.2 m).
- Outline: the cluster's cell edges (Raster To Polygon), regularized by Regularize Building Footprint (right angles and
  diagonals, 0.75 m tolerance, 0.75 m densification, 0.25 m precision); where the tool fails the cell outline is kept.
- Heights, nearest county footprint, parcel and review fields: `footprint_candidates.py`'s helpers, i.e. the October 19
  building_heights code (method-checked again here) and the same context and REVIEW_STATUS domain.
"""
import argparse
import collections
import datetime
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import footprint_candidates as fc  # noqa: E402  (sets up the toolbox and October 19 paths)

ROOF_HEIGHT = fc.LIB/"roof_height_m.tif"
OBSERVED = fc.LIB/"observed.tif"
EXCLUDE_M = 1.5
MIN_CELLS = 40
MIN_H50_M = 2.0
REGULARIZE = {"method": "RIGHT_ANGLES_AND_DIAGONALS", "tolerance": 0.75, "densification": 0.75, "precision": 0.25}
PILOT_TILE = (428000.0, 4504000.0, 429000.0, 4505000.0)   # 12TVL2804, the labelled tile
STAGES = {1: "roof on or within 1.5 m of a county footprint", 2: "removed by the opening", 3: "cluster under 10 m2",
          4: "cluster median height under 2.0 m", 5: "candidate"}
WARNING_EXTRA = (" Candidate outlines are clusters of 2023 LiDAR consensus roof cells outside the county footprints, "
                 "regularized; they are not county footprints and have not been reviewed.")
MASSING_TEXT = ("3D massing, LOD1.2, of the LiDAR footprint candidates (roof clusters with no county footprint) from the "
                "consensus roof surface (Extract LOD2 Buildings). Heights are roof-minus-terrain estimates, not "
                "code-defined building heights." + WARNING_EXTRA)
fc.ALIASES.update({"CAND_ID": "Candidate ID", "CLUSTER_CELLS": "Roof cells in the cluster",
                   "CLUSTER_M2": "Cluster area (m2)", "CLUSTER_H50_M": "Cluster median roof height (m)",
                   "OUTLINE": "Outline method"})


def clusters(out, window=None):
    """The cluster raster (candidate number per cell) and a stage raster explaining every roof cell."""
    import geopandas as gpd
    import rasterio
    from rasterio.features import rasterize
    from scipy import ndimage
    with rasterio.open(ROOF_HEIGHT) as h, rasterio.open(OBSERVED) as o:
        assert h.transform == o.transform and h.shape == o.shape and h.crs.to_epsg() == fc.CRS
        profile, transform, shape = h.profile, h.transform, h.shape
        height = h.read(1)
        roof = (height != h.nodata) & np.isfinite(height) & (o.read(1) != 3)
    county = gpd.read_file(fc.BUILDINGS.parent, layer=fc.BUILDINGS.name)
    cm = rasterize(((g, 1) for g in county.geometry), out_shape=shape, transform=transform, fill=0, dtype="uint8",
                   all_touched=False).astype(bool)
    near = ndimage.distance_transform_edt(~cm) * transform.a <= EXCLUDE_M
    del cm
    stage = np.zeros(shape, np.uint8)
    stage[roof & near] = 1
    free = roof & ~near
    del near
    opened = ndimage.binary_opening(free, structure=np.ones((3, 3), bool))
    stage[free & ~opened] = 2
    del free
    labels, n = ndimage.label(opened, structure=np.ones((3, 3), int))
    cells = np.bincount(labels.ravel(), minlength=n + 1)
    idx = np.arange(1, n + 1)
    h50 = np.zeros(n + 1)
    h50[1:] = ndimage.median(height, labels, idx)
    small = cells < MIN_CELLS
    low = ~small & (h50 < MIN_H50_M)
    keep = ~small & ~low
    keep[0] = False
    boxes = ndimage.find_objects(labels)   # boxes[k - 1] bounds cluster k
    if window:
        x0, y0, x1, y1 = window
        c0, r0 = ~transform * (x0, y1)
        c1, r1 = ~transform * (x1, y0)
        within = np.zeros(n + 1, bool)
        within[1:] = [b[0].start >= r0 and b[0].stop <= r1 and b[1].start >= c0 and b[1].stop <= c1 for b in boxes]
        keep &= within
    stage[opened & small[labels]] = 3
    stage[opened & low[labels]] = 4
    stage[opened & keep[labels]] = 5
    # renumber the kept clusters 1..m by the top-left corner of their bounding box (north to south, west to east)
    order = np.zeros(n + 1, np.int32)
    ranked = sorted(np.nonzero(keep)[0], key=lambda k: (boxes[k - 1][0].start, boxes[k - 1][1].start))
    order[ranked] = np.arange(1, len(ranked) + 1)
    cand = order[labels]
    stats = {int(order[k]): {"cells": int(cells[k]), "h50": float(h50[k])} for k in ranked}
    del labels, opened
    out.mkdir(parents=True, exist_ok=True)
    meta = dict(profile, dtype="int32", nodata=0, compress="lzw", tiled=True, blockxsize=512, blockysize=512, count=1)
    with rasterio.open(out/"clusters.tif", "w", **meta) as dst:
        dst.write(cand, 1)
    with rasterio.open(out/"stage.tif", "w", **dict(meta, dtype="uint8", nodata=0)) as dst:
        dst.write(stage, 1)
    counts = {
        "roof_cells_in_city": int(roof.sum()),
        "stage_cells": {STAGES[k]: int((stage == k).sum()) for k in STAGES},
        "clusters_after_opening": int(n), "clusters_under_10m2": int(small[1:].sum()),
        "clusters_median_under_2m": int(low[1:].sum()), "candidates": len(ranked)}
    return stats, counts


def outlines(out, gdb, stats):
    """Cell outlines per cluster, regularized; the cell outline where regularization fails."""
    import arcpy
    raw = str(Path(gdb)/"cluster_cells")
    single = str(Path(gdb)/"cluster_cells_single")
    reg = str(Path(gdb)/"regularized")
    arcpy.conversion.RasterToPolygon(str(out/"clusters.tif"), single, "NO_SIMPLIFY", "Value", "SINGLE_OUTER_PART")
    arcpy.management.Dissolve(single, raw, "gridcode", multi_part="MULTI_PART")
    arcpy.ddd.RegularizeBuildingFootprint(single, reg, REGULARIZE["method"], REGULARIZE["tolerance"],
                                          REGULARIZE["densification"], REGULARIZE["precision"])
    status = "STATUS" if arcpy.ListFields(reg, "STATUS") else None
    regs = collections.defaultdict(list)
    failed = set()
    for row in arcpy.da.SearchCursor(reg, ["gridcode", "SHAPE@"] + ([status] if status else [])):
        if row[1] is None or row[1].area == 0 or (status and row[2] != 0):
            failed.add(row[0])
        else:
            regs[row[0]].append(row[1])
    cells = {code: shape for code, shape in arcpy.da.SearchCursor(raw, ["gridcode", "SHAPE@"])}
    assert set(cells) == set(stats), (len(cells), len(stats))
    shapes = {}
    for code, cell_shape in cells.items():
        parts = regs.get(code)
        if code in failed or not parts:
            shapes[code] = (cell_shape, "CELL_EDGES")
            continue
        shape = parts[0]
        for part in parts[1:]:
            shape = shape.union(part)
        shapes[code] = (shape, "REGULARIZED")
    for path in (single, reg):
        arcpy.management.Delete(path)
    return shapes, {"regularized": sum(1 for s in shapes.values() if s[1] == "REGULARIZED"),
                    "cell_edges": sum(1 for s in shapes.values() if s[1] == "CELL_EDGES"),
                    "status_field": status}


def detect(out, pilot):
    import arcpy
    from canopy import planning
    out = out/"detect-pilot" if pilot else out
    out.mkdir(parents=True, exist_ok=True)
    done = out/"method-check.json"
    check = json.loads(done.read_text(encoding="utf-8")) if done.exists() else fc.method_check(out)
    if not check["exact"]:
        raise RuntimeError("The zonal code does not reproduce building_heights; candidate figures not computed")
    print("clusters", flush=True)
    stats, counts = clusters(out, PILOT_TILE if pilot else None)
    print(json.dumps(counts), flush=True)
    sr = arcpy.SpatialReference(fc.CRS)
    gdb = arcpy.management.CreateFileGDB(str(out), "candidates.gdb")[0]
    shapes, outline_counts = outlines(out, gdb, stats)
    target = str(Path(gdb)/"candidates")
    arcpy.management.CreateFeatureclass(gdb, "candidates", "POLYGON", spatial_reference=sr)
    for name, kind, length in (("CAND_ID", "TEXT", 12), ("CLUSTER_CELLS", "LONG", None), ("CLUSTER_M2", "DOUBLE", None),
                               ("CLUSTER_H50_M", "DOUBLE", None), ("OUTLINE", "TEXT", 12), ("SIZE_CLASS", "TEXT", 20)):
        arcpy.management.AddField(target, name, kind, field_length=length, field_alias=fc.ALIASES[name])
    fc.add_height_and_context_fields(gdb, target)
    with arcpy.da.InsertCursor(target, ["SHAPE@", "CAND_ID", "CLUSTER_CELLS", "CLUSTER_M2", "CLUSTER_H50_M", "OUTLINE",
                                        "SIZE_CLASS"]) as cursor:
        for code in sorted(shapes):
            shape, how = shapes[code]
            s = stats[code]
            cursor.insertRow([shape, f"LC{code:05d}", s["cells"], s["cells"] * 0.25, round(s["h50"], 3), how,
                              fc.size_class(shape.area)])
    arcpy.management.Delete(str(Path(gdb)/"cluster_cells"))
    pilot_check, fallbacks = fc.fill_heights(target, "CAND_ID")
    fc.fill_context(target, gdb)
    planning._metadata(target, "Candidate building footprints detected from the 2023 LiDAR: clusters of consensus roof "
                               "cells more than 1.5 m from every county footprint (at least 10 m2, median roof height at "
                               "least 2 m), outlined from the cells and regularized. Roof statistics by the county "
                               "building_heights code: roof minus interpolated terrain at paired cell centres. For review; "
                               "REVIEW_STATUS is empty until reviewed." + WARNING_EXTRA)
    count = int(arcpy.management.GetCount(target)[0])
    assert count == len(stats)
    record = {"schema": "footprint-candidates-lidar/1", "created": datetime.datetime.now().isoformat(timespec="seconds"),
              "pilot_window": PILOT_TILE if pilot else None,
              "inputs": {"roof_height": str(ROOF_HEIGHT), "observed": str(OBSERVED), "county": str(fc.BUILDINGS),
                         "parcels": str(fc.PARCELS), "roof_elevation": str(fc.ROOF), "terrain": str(fc.TERRAIN),
                         "boundary": str(fc.BOUNDARY), "overture_read": False},
              "rules": {"exclude_within_m_of_county": EXCLUDE_M, "opening": "3 x 3", "connectivity": 8,
                        "min_cells": MIN_CELLS, "min_cluster_median_height_m": MIN_H50_M, "regularize": REGULARIZE},
              "stages": STAGES, "counts": counts, "outlines": outline_counts,
              "method_check": {k: check[k] for k in ("sample", "exact", "field_differences")},
              "rasterization_pilot": pilot_check, "boundary_fallbacks": fallbacks, "output": target, "count": count}
    record["county_overlap"] = county_overlap(target)
    record["summary"] = summarize(target)
    fc._json(out/"candidates.json", record)
    print(json.dumps({k: record[k] for k in ("counts", "outlines", "count", "county_overlap")}, indent=1), flush=True)
    print(json.dumps(record["summary"]["headline"], indent=1), flush=True)


def county_overlap(target):
    """How much of each regularized outline falls on a county footprint (regularization can move edges 0.75 m)."""
    import arcpy
    import shapely
    county = [shapely.from_wkb(bytes(w)) for (w,) in arcpy.da.SearchCursor(str(fc.BUILDINGS), ["SHAPE@WKB"])]
    tree = shapely.STRtree(county)
    shares = []
    for (w,) in arcpy.da.SearchCursor(target, ["SHAPE@WKB"]):
        g = shapely.from_wkb(bytes(w))
        a = sum(shapely.intersection(g, county[j]).area for j in tree.query(g, "intersects"))
        shares.append(100 * a / g.area)
    s = np.array(shares)
    return {"outlines": len(s), "touching_county": int((s > 0).sum()), "over_1pct": int((s > 1).sum()),
            "over_10pct": int((s > 10).sum()), "max_pct": round(float(s.max()), 2) if len(s) else None}


def summarize(target):
    import arcpy
    import pandas as pd
    cols = ["CAND_ID", "OUTLINE", "SIZE_CLASS", "FOOTPRINT_M2", "CLUSTER_M2", "ROOF_COV_PCT", "HEIGHT_P50_M",
            "HEIGHT_P95_M", "HEIGHT_STATUS", "NEAR_FP_DIST_M", "PARCEL_ID", "SAME_PARCEL"]
    df = pd.DataFrame(list(arcpy.da.SearchCursor(target, cols)), columns=cols)
    order = [label for _, _, label in fc.SIZES]
    df["SIZE_CLASS"] = pd.Categorical(df["SIZE_CLASS"], order, ordered=True)
    df["H"] = pd.cut(df["HEIGHT_P95_M"], [-100, 3, 4.5, 6, 9, 100], labels=["under 3 m", "3-4.5 m", "4.5-6 m", "6-9 m",
                                                                              "9 m and over"])
    size_height = pd.crosstab(df["SIZE_CLASS"], df["H"], dropna=False)
    size_height["all"] = size_height.sum(axis=1)
    flags = collections.Counter(f for s in df["HEIGHT_STATUS"] for f in s.split(";"))
    return {
        "headline": {"candidates": len(df), "with_height": int(df["HEIGHT_P50_M"].notna().sum()),
                     "outline_area_m2": fc._q(df["FOOTPRINT_M2"]), "cluster_area_m2": fc._q(df["CLUSTER_M2"]),
                     "outline_over_cluster": fc._q(df["FOOTPRINT_M2"] / df["CLUSTER_M2"]),
                     "height_p95_m": fc._q(df["HEIGHT_P95_M"]), "roof_cov_pct": fc._q(df["ROOF_COV_PCT"]),
                     "near_county_footprint_m": fc._q(df["NEAR_FP_DIST_M"]),
                     "no_parcel": int(df["PARCEL_ID"].isna().sum()),
                     "same_parcel_as_nearest_county_building": df["SAME_PARCEL"].fillna("(unknown)").value_counts().to_dict(),
                     "outline": df["OUTLINE"].value_counts().to_dict()},
        "size_by_height": {str(k): {str(c): int(v) for c, v in row.items()} for k, row in size_height.iterrows()},
        "same_parcel_by_size": {str(k): g["SAME_PARCEL"].fillna("(unknown)").value_counts().to_dict()
                                for k, g in df.groupby("SIZE_CLASS", observed=False)},
        "height_status_flags": dict(flags),
    }


def witness(out):
    """Afterwards only: the LiDAR candidates against the 1,264 Overture-only outlines on a LiDAR roof. Results go to a
    separate witness.gdb table and witness.json; nothing is written to the candidate layer."""
    import arcpy
    import geopandas as gpd
    import pandas as pd
    import rasterio
    import shapely
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, from_bounds, transform as wtransform
    lid = [(cid, shapely.from_wkb(bytes(w))) for cid, w in
           arcpy.da.SearchCursor(str(out/"candidates.gdb"/"candidates"), ["CAND_ID", "SHAPE@WKB"])]
    ov = gpd.read_file(fc.COMPARE, layer="overture_buildings", where=fc.SELECT)
    assert ov.crs.to_epsg() == fc.CRS
    ovg = list(ov.geometry)
    tree = shapely.STRtree(ovg)
    pairs = []
    for cid, g in lid:
        for j in tree.query(g, "intersects"):
            a = shapely.intersection(g, ovg[j]).area
            if a > 0:
                pairs.append({"CAND_ID": cid, "OVERTURE_ID": ov["id"].iloc[j], "INTER_M2": a,
                              "OF_LIDAR": a / g.area, "OF_OVERTURE": a / ovg[j].area,
                              "IOU": a / (g.area + ovg[j].area - a)})
    p = pd.DataFrame(pairs, columns=["CAND_ID", "OVERTURE_ID", "INTER_M2", "OF_LIDAR", "OF_OVERTURE", "IOU"])
    p["FOUND_BY_BOTH"] = (p[["OF_LIDAR", "OF_OVERTURE"]].max(axis=1) >= 0.3)
    both = p[p["FOUND_BY_BOTH"]]
    lid_found, ov_found = set(both["CAND_ID"]), set(both["OVERTURE_ID"])
    # why the Overture-only outlines were missed: the detection stage of the cells under each (cell centres)
    with rasterio.open(out/"stage.tif") as src:
        stage, transform = src.read(1), src.transform
    reasons, missed = collections.Counter(), []
    for oid, g in zip(ov["id"], ovg):
        if oid in ov_found:
            continue
        w = from_bounds(*g.bounds, transform=transform)
        r0, c0 = max(int(np.floor(w.row_off)), 0), max(int(np.floor(w.col_off)), 0)
        r1, c1 = int(np.ceil(w.row_off + w.height)) + 1, int(np.ceil(w.col_off + w.width)) + 1
        inside = ~geometry_mask([g], out_shape=(r1 - r0, c1 - c0),
                                transform=wtransform(Window(c0, r0, c1 - c0, r1 - r0), transform))
        st = stage[r0:r1, c0:c1][inside]
        roof = st[st > 0]
        top = collections.Counter(int(v) for v in roof).most_common(1)
        reason = STAGES[top[0][0]] if top else "no roof cells"
        if top and top[0][0] == 5:
            reason = "candidate overlaps it by under 30%"
        reasons[reason] += 1
        missed.append({"OVERTURE_ID": oid, "AREA_M2": g.area, "REASON": reason,
                       **{f"PCT_{k}": round(100 * float((st == k).mean()), 1) for k in STAGES}})
    gdb = Path(arcpy.management.CreateFileGDB(str(out), "witness.gdb")[0])
    for name, frame in (("pairs", p), ("overture_missed", pd.DataFrame(missed))):
        if not len(frame):
            continue
        kinds = [(n, "?" if pd.api.types.is_bool_dtype(frame[n]) else
                  "<f8" if pd.api.types.is_numeric_dtype(frame[n]) else "<U64") for n in frame.columns]
        table = np.array([tuple(r) for r in frame.itertuples(index=False)], dtype=kinds)
        arcpy.da.NumPyArrayToTable(table, str(gdb/name))
    result = {"note": "Witness only: Overture outlines (ODbL) were not used to choose or shape the candidates.",
              "overture": {"source": str(fc.COMPARE), "where": fc.SELECT, "n": len(ov)},
              "lidar_candidates": len(lid), "rule": "found by both when the overlap is at least 30% of either outline",
              "found_by_both": {"lidar_candidates": len(lid_found), "overture_outlines": len(ov_found)},
              "lidar_only": len(lid) - len(lid_found), "overture_only": len(ov) - len(ov_found),
              "iou_of_best_pairs": fc._q(both.sort_values("IOU").drop_duplicates("OVERTURE_ID", keep="last")["IOU"]),
              "overture_only_by_reason": dict(reasons),
              "overture_only_area_m2": fc._q([m["AREA_M2"] for m in missed]),
              "outputs": {"pairs": str(gdb/"pairs"), "overture_missed": str(gdb/"overture_missed")}}
    fc._json(out/"witness.json", result)
    print(json.dumps(result, indent=1), flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("detect", "web", "pilot", "massing", "witness"))
    p.add_argument("out", type=Path)
    p.add_argument("--pilot", action="store_true", help="detect: only clusters wholly inside 12TVL2804")
    a = p.parse_args(argv)
    out = a.out.resolve()
    if a.step == "detect":
        detect(out, a.pilot)
    elif a.step == "web":
        fc.web(out, WARNING_EXTRA)
    elif a.step == "witness":
        witness(out)
    else:
        fc.massing(out, a.step == "pilot", "CAND_ID", MASSING_TEXT)


if __name__ == "__main__":
    main()
