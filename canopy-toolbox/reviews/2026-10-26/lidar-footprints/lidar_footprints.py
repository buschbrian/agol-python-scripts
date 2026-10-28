r"""Building outlines from the 2023 LiDAR alone, and how the county footprints compare with them (October 26, 2026).

Brian's call after reviewing the LiDAR candidates: the LiDAR is right about whole buildings far more often than the county
footprints are, and it is newer. The October 23 candidates kept only roof cells more than 1.5 m from every county
footprint, so a LiDAR building overlapping a wrong county outline came out in pieces, or not at all. Here the county
layer is not used to make the outlines: every 2-of-3 consensus roof cluster becomes an outline, with the same opening,
size and height rules and the same regularization as the candidates (lidar_candidates.py, exclude_m=None).

`compare` then matches the two layers. Pieces overlap when they share at least 10% of the smaller one's area; each
connected group of overlapping county footprints and LiDAR outlines gets one class:

- MATCH            one county, one LiDAR, intersection over union at least 0.6
- RESHAPED         one county, one LiDAR, IoU under 0.6: offset, wrong shape, or rebuilt
- LIDAR_JOINS      one LiDAR outline over several county footprints: attached units, or a redrawn site (LC01389)
- LIDAR_SPLITS     one county footprint over several LiDAR outlines
- TANGLE           several of each
- LIDAR_ONLY       no county footprint: new since the county layer, or missed by it
- COUNTY_ONLY      no LiDAR roof: gone, or hidden under trees (the canopy share says which is more likely)

The LiDAR has two known limits, carried as fields rather than corrected: under trees it sees only part of a roof (an
outline is a lower bound where canopy covers it; COUNTY_ONLY items under canopy are not demolition findings), and its
edge is the drip line, not the wall (eaves), so a matching LiDAR outline is a little larger than the county's. The
median of that offset on MATCH groups is reported, nothing is shrunk. Everything is as of the survey, October-November
2023.

    python lidar_footprints.py detect OUT [--window X0 Y0 X1 Y1]    OUT\lidar.gdb\buildings (ArcGIS Pro Python)
    python lidar_footprints.py compare OUT [ANSWERS_CSV]            OUT\compare.csv, compare.json (ArcPy-free)
"""
import argparse
import collections
import csv
import datetime
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
CANDIDATES = HERE.parents[1].parent/"2026-10-23"/"footprint-candidates"
sys.path.insert(0, str(CANDIDATES))
import footprint_candidates as fc  # noqa: E402  (sets up the toolbox and the October 19/22 paths)

OVERLAP_SHARE = 0.10
MATCH_IOU = 0.6
CANOPY_M = 2.0


def detect(out, window, cut_parcels=False):
    import arcpy
    import lidar_candidates as lc
    out.mkdir(parents=True, exist_ok=True)
    cuts = residential_parcels() if cut_parcels else None
    stats, counts = lc.clusters(out, window, exclude_m=None, cut_parcels=cuts)
    print(json.dumps(counts), flush=True)
    gdb = out/"lidar.gdb"
    if not arcpy.Exists(str(gdb)):
        arcpy.management.CreateFileGDB(str(out), "lidar.gdb")
    shapes, outline_counts = lc.outlines(out, str(gdb), stats)
    target = str(gdb/"buildings")
    if arcpy.Exists(target):
        arcpy.management.Delete(target)
    arcpy.management.CreateFeatureclass(str(gdb), "buildings", "POLYGON", spatial_reference=arcpy.SpatialReference(fc.CRS))
    for name, kind, length in (("LB_ID", "TEXT", 12), ("ROOF_CELLS", "LONG", None), ("ROOF_M2", "DOUBLE", None),
                               ("ROOF_H50_M", "DOUBLE", None), ("OUTLINE", "TEXT", 12), ("AREA_M2", "DOUBLE", None)):
        arcpy.management.AddField(target, name, kind, field_length=length)
    with arcpy.da.InsertCursor(target, ["SHAPE@", "LB_ID", "ROOF_CELLS", "ROOF_M2", "ROOF_H50_M", "OUTLINE", "AREA_M2"]) as cur:
        for code in sorted(shapes):
            shape, how = shapes[code]
            s = stats[code]
            cur.insertRow([shape, f"LB{code:06d}", s["cells"], s["cells"] * 0.25, round(s["h50"], 3), how, round(shape.area, 2)])
    arcpy.management.Delete(str(gdb/"cluster_cells"))
    record = {"schema": "lidar-footprints/1", "created": datetime.datetime.now().isoformat(timespec="seconds"),
              "window": window, "rules": {"county_used": False, "opening": "3 x 3", "connectivity": 8,
                                          "cut_at_parcel_lines": f"{len(cuts)} residential (lot_use R) parcels" if cuts else False,
                                          "min_cells": lc.MIN_CELLS, "min_cluster_median_height_m": lc.MIN_H50_M,
                                          "regularize": lc.REGULARIZE},
              "counts": counts, "outlines": outline_counts, "count": len(shapes), "output": target}
    (out/"detect.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("counts", "outlines", "count")}, indent=1))


def residential_parcels():
    """Residential lots (lot_use R in the 2025-tax-year snapshot): single houses, duplexes and townhouse units. Multi-housing,
    commercial, industrial and road parcels are not cut, so a building over several of them stays whole."""
    import geopandas as gpd
    p = gpd.read_file(fc.INPUTS, layer="parcels", columns=["lot_use"])
    assert p.crs.to_epsg() == fc.CRS
    return [g for g, u in zip(p.geometry, p.lot_use) if isinstance(u, str) and u.strip() == "R" and g is not None]


FILL_PIECE_CANOPY = 0.5     # a hidden piece of a county outline is added when at least half of it is under 2 m+ canopy
FILL_COUNTY_CANOPY = 10.0   # ... of a county footprint with at least 10% canopy over it (Brian's partly-under-trees answers)
FILL_MIN_M2 = 2.0


def treefill(out):
    """Where trees hide part of a building, add that part of the county outline to the LiDAR outline: the LiDAR where it
    sees roof, the county where canopy covers it. Each county footprint with at least 10% canopy over it is cut by the
    LiDAR outlines; a leftover piece of at least 2 m2 that is at least half under canopy joins the LiDAR outline that
    overlaps that county footprint most. County footprints with no LiDAR outline are not touched (COUNTY_ONLY keeps
    them by rule). Writes OUT/lidar.gdb/buildings_filled (ArcGIS Pro Python) and treefill.json."""
    import arcpy
    import geopandas as gpd
    import rasterio
    import shapely
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds
    lidar = gpd.read_file(out/"lidar.gdb", layer="buildings")
    county = gpd.read_file(fc.BUILDINGS.parent, layer=fc.BUILDINGS.name)
    lg = list(lidar.geometry)
    tree = shapely.STRtree(lg)
    added = {}
    stats = {"county_with_canopy": 0, "pieces_added": 0, "m2_added": 0.0}
    with rasterio.open(fc.LIB/"chm_m.tif") as chm:
        def under_canopy(g):
            w = from_bounds(*g.bounds, transform=chm.transform).round_offsets().round_lengths()
            a = chm.read(1, window=w, boundless=True, fill_value=chm.nodata).astype(float)
            if a.size == 0:
                return 0.0
            inside = ~geometry_mask([g], out_shape=a.shape, transform=chm.window_transform(w))
            v = a[inside & (a != chm.nodata)]
            return float((v >= 2).mean()) if v.size else 0.0
        for c in county.geometry:
            hits = [j for j in tree.query(c, predicate="intersects") if c.intersection(lg[j]).area > 1.0]
            if not hits or under_canopy(c) * 100 < FILL_COUNTY_CANOPY:
                continue
            stats["county_with_canopy"] += 1
            target = max(hits, key=lambda j: c.intersection(lg[j]).area)
            rest = c.difference(shapely.union_all([lg[j] for j in hits]))
            for piece in getattr(rest, "geoms", [rest]):
                if piece.geom_type == "Polygon" and piece.area >= FILL_MIN_M2 and under_canopy(piece) >= FILL_PIECE_CANOPY:
                    added.setdefault(target, []).append(piece)
                    stats["pieces_added"] += 1
                    stats["m2_added"] += piece.area
    filled = lidar.copy()
    filled["TREE_FILL_M2"] = 0.0
    for j, pieces in added.items():
        g = shapely.make_valid(shapely.union_all([lg[j]] + pieces))
        filled.loc[filled.index[j], "geometry"] = g
        filled.loc[filled.index[j], "TREE_FILL_M2"] = round(sum(p.area for p in pieces), 2)
    filled["AREA_M2"] = filled.geometry.area.round(2)
    filled["OUTLINE"] = [("TREE_FILLED" if j in added else o) for j, o in enumerate(filled.OUTLINE)]
    tmp = out/"buildings_filled.gpkg"
    filled.to_file(tmp, layer="buildings_filled", driver="GPKG")
    target = str(out/"lidar.gdb"/"buildings_filled")
    if arcpy.Exists(target):
        arcpy.management.Delete(target)
    arcpy.conversion.ExportFeatures(str(tmp/"main.buildings_filled"), target)
    stats.update(buildings_filled=len(added), m2_added=round(stats["m2_added"], 1),
                 rules={"county_canopy_pct_at_least": FILL_COUNTY_CANOPY, "piece_canopy_share_at_least": FILL_PIECE_CANOPY,
                        "piece_m2_at_least": FILL_MIN_M2})
    (out/"treefill.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(json.dumps(stats, indent=1))


def canopy_share(geoms):
    """Share of each outline's cells with vegetation 2 m or more (the October 22 canopy height model)."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds
    out = []
    with rasterio.open(fc.LIB/"chm_m.tif") as chm:
        for g in geoms:
            w = from_bounds(*g.bounds, transform=chm.transform).round_offsets().round_lengths()
            a = chm.read(1, window=w, boundless=True, fill_value=chm.nodata).astype(float)
            if a.size == 0:
                out.append(None)
                continue
            inside = ~geometry_mask([g], out_shape=a.shape, transform=chm.window_transform(w))
            v = a[inside & (a != chm.nodata)]
            out.append(round(100 * float((v >= CANOPY_M).mean()), 1) if v.size else None)
    return out


def compare(out, answers_path, layer="buildings"):
    import geopandas as gpd
    import shapely
    lidar = gpd.read_file(out/"lidar.gdb", layer=layer)
    county = gpd.read_file(fc.BUILDINGS.parent, layer=fc.BUILDINGS.name)
    detect_rec = json.loads((out/"detect.json").read_text(encoding="utf-8"))
    if detect_rec["window"]:
        x0, y0, x1, y1 = detect_rec["window"]
        county = county[county.geometry.within(shapely.box(x0, y0, x1, y1))]
    county = county.reset_index(drop=True)
    # make_valid: unions in treefill and a few county outlines are self-touching
    cg, lg = list(shapely.make_valid(county.geometry.values)), list(shapely.make_valid(lidar.geometry.values))
    tree = shapely.STRtree(lg)
    ci, li = tree.query(cg, predicate="intersects")
    edges = []
    for i, j in zip(ci, li):
        inter = cg[i].intersection(lg[j]).area
        if inter >= OVERLAP_SHARE * min(cg[i].area, lg[j].area):
            edges.append((i, j, inter))
    # connected groups over the bipartite overlap graph (union-find; county i -> i, LiDAR j -> n + j)
    n = len(cg)
    parent = list(range(n + len(lg)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for i, j, _ in edges:
        parent[find(i)] = find(n + j)
    groups = collections.defaultdict(lambda: ([], []))
    for i in range(n):
        groups[find(i)][0].append(i)
    for j in range(len(lg)):
        groups[find(n + j)][1].append(j)
    inter_of = {(i, j): a for i, j, a in edges}
    c_canopy = canopy_share(cg)
    rows, offsets = [], []
    for k, (cs, ls) in enumerate(sorted(groups.values(), key=lambda g: (min(g[0], default=10**9), min(g[1], default=10**9)))):
        if cs and ls:
            if len(cs) == 1 and len(ls) == 1:
                i, j = cs[0], ls[0]
                iou = inter_of[(i, j)] / cg[i].union(lg[j]).area
                cls = "MATCH" if iou >= MATCH_IOU else "RESHAPED"
                if cls == "MATCH":
                    offsets.append((lg[j].area - cg[i].area) / cg[i].length)   # mean outward offset of the LiDAR edge, m
            else:
                iou = None
                cls = "LIDAR_JOINS" if len(ls) == 1 else "LIDAR_SPLITS" if len(cs) == 1 else "TANGLE"
        else:
            iou, cls = None, "LIDAR_ONLY" if ls else "COUNTY_ONLY"
        rows.append({"GROUP": f"G{k + 1:06d}", "CLASS": cls,
                     "COUNTY_IDS": ";".join(str(county.SOURCE_ID[i]) for i in cs),
                     "LIDAR_IDS": ";".join(lidar.LB_ID[j] for j in ls),
                     "N_COUNTY": len(cs), "N_LIDAR": len(ls), "IOU": None if iou is None else round(iou, 3),
                     "COUNTY_M2": round(sum(cg[i].area for i in cs), 1), "LIDAR_M2": round(sum(lg[j].area for j in ls), 1),
                     "COUNTY_ROOF_COV_PCT": ";".join("" if county.ROOF_COV_PCT[i] != county.ROOF_COV_PCT[i]
                                                     else f"{county.ROOF_COV_PCT[i]:.0f}" for i in cs),
                     "COUNTY_CANOPY_PCT": ";".join("" if c_canopy[i] is None else f"{c_canopy[i]:.0f}" for i in cs)})
    with (out/"compare.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    counts = collections.Counter(r["CLASS"] for r in rows)
    county_by_class = collections.Counter()
    for r in rows:
        county_by_class[r["CLASS"]] += r["N_COUNTY"]
    hidden = sum(1 for r in rows if r["CLASS"] == "COUNTY_ONLY" and r["COUNTY_CANOPY_PCT"] and float(r["COUNTY_CANOPY_PCT"]) >= 30)
    summary = {"lidar_outlines": len(lg), "county_footprints": n, "groups": dict(counts),
               "county_footprints_by_class": dict(county_by_class),
               "county_only_under_30pct_canopy_or_more": hidden,
               "match_edge_offset_m": {"median": round(float(np.median(offsets)), 2) if offsets else None,
                                       "p25": round(float(np.percentile(offsets, 25)), 2) if offsets else None,
                                       "p75": round(float(np.percentile(offsets, 75)), 2) if offsets else None,
                                       "note": "LiDAR minus county area over the county perimeter: the LiDAR edge sits this "
                                               "far outside the county wall line on average (eaves)"}}
    if answers_path:
        summary["against_answers"] = against_answers(out, answers_path, rows, county, lidar)
    (out/"compare.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


def against_answers(out, answers_path, rows, county, lidar):
    """How the classes line up with Brian's answers: each answered candidate, county or pair item is placed in the
    group of the LiDAR outline under it (candidates) or of its county footprint (county, pairs, roofs)."""
    import geopandas as gpd
    cand = gpd.read_file(fc.VALLEY/"runs"/"footprint-candidates-lidar-20261023"/"candidates.gdb", layer="candidates")
    group_of_county = {sid: r["CLASS"] for r in rows for sid in r["COUNTY_IDS"].split(";") if sid}
    group_of_lidar = {lb: r["CLASS"] for r in rows for lb in r["LIDAR_IDS"].split(";") if lb}
    hits = gpd.sjoin(cand[["CAND_ID", "geometry"]].assign(geometry=cand.geometry.representative_point()),
                     lidar[["LB_ID", "geometry"]], predicate="within")
    lidar_of_cand = dict(zip(hits.CAND_ID, hits.LB_ID))
    table = collections.defaultdict(collections.Counter)
    with open(answers_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            item, queue = r["ITEM_ID"], r["QUEUE"]
            if queue == "candidates":
                cls = group_of_lidar.get(lidar_of_cand.get(item), "outside the window")
            elif queue in ("county", "pairs", "models"):
                cls = group_of_county.get(item[2:], "outside the window")
            else:
                continue
            table[f"{queue}:{r['ANSWER'] or '(note only)'}"][cls] += 1
    return {k: dict(v) for k, v in sorted(table.items())}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("detect", "treefill", "compare"))
    p.add_argument("out", type=Path)
    p.add_argument("answers", type=Path, nargs="?")
    p.add_argument("--window", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--cut-parcels", action="store_true", help="detect: never join roof across a residential parcel line")
    p.add_argument("--layer", default="buildings", help="compare: the outline layer (buildings_filled after treefill)")
    a = p.parse_args(argv)
    if a.step == "detect":
        detect(a.out, tuple(a.window) if a.window else None, a.cut_parcels)
    elif a.step == "treefill":
        treefill(a.out)
    else:
        compare(a.out, a.answers, a.layer)


if __name__ == "__main__":
    main()
