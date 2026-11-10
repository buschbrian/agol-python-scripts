"""Build the corrected building footprint layer from the LiDAR-first outlines and every decision (November 10, 2026).

Brian: "rebuild the entire footprint layer and get all of that corrected". Order of authority (November 9): the
regularized LiDAR-first outline, then newer imagery (his answers), county data last. Defaults he accepted on November 10:
the roof line is kept (no wall-line shrink), and county address, parcel and year built are carried onto the outlines.

Every compare group (city2/compare.csv, MATCH included) produces its outlines once:
- MATCH, LIDAR_RIGHT, LiDAR-only: the regularized LiDAR outline(s).
- KEEP_UNITS, the 550 joins moved to the LiDAR on November 9 (BY rule-20261109), and SPLIT_BUILDINGS over two or more
  county outlines: the LiDAR outer shape cut along the county outlines inside it (one piece per county outline; LiDAR
  roof outside every county outline joins the piece it shares the longest edge with).
- SPLIT_BUILDINGS over one county outline: nothing to cut by, so the LiDAR outline is kept and flagged SPLIT_BY_HAND.
- KEEP_COUNTY: the county outline(s); the LiDAR outline of the group is not used.
- SHED: the LiDAR outline (or the county outline where the LiDAR saw none), BLDG_TYPE shed.
- ADD_TO_COUNTY: the county outline plus the LiDAR roof outside it. SHIFT_COUNTY: the county outline moved onto the LiDAR
  (best overlap, 0.25 m steps within 5 m), or by its October 23 alignment fit where the LiDAR saw nothing.
- PART_OF_BUILDING: joined, after everything else, to the output outline it shares the longest edge with.
- NEEDS_EDIT, UNSURE: the LiDAR outline where there is one, otherwise the county's, flagged for hand work.
- GONE, VEHICLE, DROP, NOT_A_BUILDING: nothing.

Parcels are joined by location for parcel_id, prop_location, year_built and lot_use only (the table also holds owner
names, which never leave it). Run with the millcreek-py3 Python (-I).

    python build_footprints.py OUT [--pilot]     --pilot builds only the groups Brian answered by hand
"""
import argparse
import collections
import csv
import json
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import shapely
from shapely import affinity

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
COMPARE = RUNS/"lidar-footprints-20261026"/"city2"/"compare.csv"
DECISIONS = RUNS/"lidar-footprints-20261109"/"decisions-20261110.csv"
OUTLINES = RUNS/"lidar-footprints-20261109"/"regularized.gdb"
COUNTY = RUNS/"millcreek-products-20261022"/"buildings.gdb"
ALIGN = RUNS/"county-alignment-20261023"/"county-alignment.gpkg"
INPUTS = RUNS/"city-count-20261008"/"inputs.gdb"
CRS = 6341
FT2 = 0.3048 ** 2
MIN_PIECE_M2 = 2.0      # a unit piece smaller than this joins its neighbour (county lines a little off the roof edge)
JOIN_GAP_M = 1.5        # a PART_OF_BUILDING piece joins an outline this close (regularizing moves edges up to 0.75 m)
DROP = {"GONE", "VEHICLE", "DROP", "NOT_A_BUILDING"}
FLAG = {"NEEDS_EDIT": "NEEDS_EDIT", "UNSURE": "UNSURE"}
PARCEL_FIELDS = ["parcel_id", "prop_location", "year_built", "lot_use"]


def polygonal(g):
    """The polygon parts of a geometry, valid (make_valid can leave lines beside a polygon)."""
    g = shapely.make_valid(g) if not g.is_valid else g
    parts = [p for p in shapely.get_parts(g) if p.geom_type in ("Polygon", "MultiPolygon") and p.area > 0]
    return shapely.union_all(parts) if parts else None


def shared_edge(a, b):
    return a.boundary.intersection(b.boundary).length if a.distance(b) < 0.01 else 0.0


def cut_by_units(outer, units):
    """outer cut along the unit polygons: [(piece, unit id or None)]. Roof outside every unit joins the piece it shares
    the longest edge with; a leftover touching no piece stays as its own piece."""
    pieces, taken = [], None
    for uid, u in units:
        p = outer.intersection(u if taken is None else u.difference(taken))
        p = polygonal(p)
        taken = u if taken is None else taken.union(u)
        if p is not None:
            pieces.append([p, uid])
    rest = polygonal(outer.difference(taken)) if taken is not None else outer
    small = [k for k, (p, _) in enumerate(pieces) if p.area < MIN_PIECE_M2]
    loose = list(shapely.get_parts(rest)) if rest is not None else []
    loose += [pieces[k][0] for k in small]
    pieces = [pc for k, pc in enumerate(pieces) if k not in small]
    for part in sorted(loose, key=lambda g: -g.area):
        edges = [shared_edge(part, p) for p, _ in pieces]
        if pieces and max(edges) > 0:
            k = int(np.argmax(edges))
            pieces[k][0] = polygonal(pieces[k][0].union(part))
        elif part.area >= MIN_PIECE_M2:
            pieces.append([part, None])
    return [(p, uid) for p, uid in pieces]


def best_shift(county, lidar):
    """Translation of county (0.25 m steps within 5 m) with the best overlap with lidar."""
    best = (county.intersection(lidar).area, 0.0, 0.0)
    for dx in np.arange(-5, 5.01, 0.25):
        for dy in np.arange(-5, 5.01, 0.25):
            a = affinity.translate(county, dx, dy).intersection(lidar).area
            if a > best[0] + 1e-6:
                best = (a, dx, dy)
    return best[1], best[2]


def load(pilot):
    with COMPARE.open(encoding="utf-8") as fh:
        groups = list(csv.DictReader(fh))
    with DECISIONS.open(encoding="utf-8-sig") as fh:
        dec = {r["GROUP"]: r for r in csv.DictReader(fh)}
    if pilot:
        groups = [g for g in groups if g["GROUP"] in dec and dec[g["GROUP"]]["BY"] == "Brian"]
    lidar = gpd.read_file(OUTLINES, layer="buildings").set_index("LB_ID")
    county = gpd.read_file(COUNTY, layer="building_heights").set_index("SOURCE_ID")
    align = gpd.read_file(ALIGN, layer="footprints_as_county", ignore_geometry=True).set_index("SOURCE_ID")
    assert lidar.crs.to_epsg() == CRS and county.crs.to_epsg() == CRS
    return groups, dec, lidar, county, align


def check_inputs(groups, dec, lidar, county, pilot):
    lb = collections.Counter(x for g in groups for x in g["LIDAR_IDS"].split(";") if x)
    cid = collections.Counter(x for g in groups for x in g["COUNTY_IDS"].split(";") if x)
    assert max(lb.values()) == 1 and max(cid.values()) == 1, "an outline is in two groups"
    if not pilot:
        assert set(lb) == set(lidar.index), (len(lb), len(lidar))
        assert set(cid) == set(county.index), (len(cid), len(county))
        missing = [g["GROUP"] for g in groups if g["CLASS"] != "MATCH" and g["GROUP"] not in dec]
        assert not missing, missing[:5]
    waiting = [g for g, r in dec.items() if r["BY"] == "waiting"]
    assert not waiting, f"{len(waiting)} decisions still waiting"


def build(groups, dec, lidar, county, align):
    out, joins, used_lb, used_c = [], [], collections.Counter(), collections.Counter()

    def emit(geom, source, g, decision, by, lbs=(), cids=(), btype="building", flag="", shapes=None):
        """shapes: the (lidar ids, county ids) whose geometry this outline is made from, counted to prove none is used
        twice; lbs and cids are what the outline records (a county id can be carried onto several LiDAR outlines)."""
        geom = polygonal(geom)
        if geom is None:
            return
        if shapes is not None:
            used_lb.update(shapes[0])
            used_c.update(shapes[1])
        out.append({"geometry": geom, "SOURCE": source, "BLDG_TYPE": btype, "DECISION": decision, "DECIDED_BY": by,
                    "REVIEW_FLAG": flag, "CLASS": g["CLASS"], "GROUP_ID": g["GROUP"], "LB_IDS": ";".join(lbs),
                    "COUNTY_IDS": ";".join(cids)})

    for g in groups:
        lbs = [x for x in g["LIDAR_IDS"].split(";") if x]
        cids = [x for x in g["COUNTY_IDS"].split(";") if x]
        r = dec.get(g["GROUP"])
        d, by = (r["DECISION"], r["BY"]) if r else ("MATCH", "match")
        lg = {lb: lidar.geometry[lb] for lb in lbs}
        cg = {c: county.geometry[c] for c in cids}
        if d in DROP:
            continue
        units = (d == "KEEP_UNITS" or by == "rule-20261109" or (d == "SPLIT_BUILDINGS" and len(cids) >= 2)) and lbs and cids
        if units:
            used_lb.update(lbs)
            used_c.update(cids)
            for piece, uid in cut_by_units(shapely.union_all(list(lg.values())), list(cg.items())):
                touching = [lb for lb, x in lg.items() if x.intersection(piece).area > 0.01]
                emit(piece, "LIDAR_UNITS", g, d, by, touching, [uid] if uid else [])
        elif d == "PART_OF_BUILDING":
            joins.append((g, d, by, lbs))
        elif d == "KEEP_COUNTY" or (d == "SHED" and not lbs):
            for c, x in cg.items():
                emit(x, "COUNTY", g, d, by, (), [c], "shed" if d == "SHED" else "building", shapes=((), [c]))
        elif d == "ADD_TO_COUNTY":
            emit(shapely.union_all(list(cg.values()) + list(lg.values())), "COUNTY_PLUS_LIDAR", g, d, by, lbs, cids,
                 shapes=(lbs, cids))
        elif d == "SHIFT_COUNTY":
            for c, x in cg.items():
                if lbs:
                    dx, dy = best_shift(x, shapely.union_all(list(lg.values())))
                else:
                    dx, dy = float(align.DX[c]), float(align.DY[c])
                emit(affinity.translate(x, dx, dy), "COUNTY_SHIFTED", g, d, by, lbs, [c], shapes=((), [c]))
        elif lbs:
            flag = FLAG.get(d, "SPLIT_BY_HAND" if d == "SPLIT_BUILDINGS" else "")
            for lb, x in lg.items():
                emit(x, "LIDAR", g, d, by, [lb], cids, "shed" if d == "SHED" else "building", flag, shapes=([lb], ()))
        elif cids:   # NEEDS_EDIT / UNSURE / anything else with no LiDAR outline
            for c, x in cg.items():
                emit(x, "COUNTY", g, d, by, (), [c], "building", FLAG.get(d, "NO_RULE"), shapes=((), [c]))

    tree = shapely.STRtree([o["geometry"] for o in out])
    for g, d, by, lbs in joins:
        for lb in lbs:
            x = lidar.geometry[lb]
            near = [int(k) for k in tree.query(x, "dwithin", JOIN_GAP_M)]
            if near:   # the nearest outline, the gap closed with a square-cornered close
                k = min(near, key=lambda k: (x.distance(out[k]["geometry"]), -out[k]["geometry"].area))
                o = out[k]
                gap = x.distance(o["geometry"]) / 2 + 0.05
                both = o["geometry"].union(x).buffer(gap, join_style="mitre").buffer(-gap, join_style="mitre")
                o["geometry"] = polygonal(both.union(o["geometry"]).union(x))
                o["LB_IDS"] = ";".join(filter(None, [o["LB_IDS"], lb]))
                used_lb[lb] += 1
            else:
                emit(x, "LIDAR", g, d, by, [lb], [], "building", "PART_NOT_TOUCHING", shapes=([lb], ()))
    trimmed = trim_overlaps(out)
    return out, used_lb, used_c, trimmed


def trim_overlaps(out):
    """Where two outlines overlap (neighbours regularized toward each other), the smaller gives the overlap up."""
    geoms = [o["geometry"] for o in out]
    tree = shapely.STRtree(geoms)
    n = 0
    for i, j in zip(*tree.query(geoms, "intersects")):
        if i < j:
            a, b = out[i]["geometry"], out[j]["geometry"]
            if a.intersection(b).area > 0.01:
                small = i if a.area < b.area else j
                big = j if small == i else i
                out[small]["geometry"] = polygonal(out[small]["geometry"].difference(out[big]["geometry"]))
                n += 1
    return n


def attributes(gdf, lidar, county, parcels):
    gdf["BLDG_ID"] = [f"MB{k:06d}" for k in range(1, len(gdf) + 1)]
    first = [c.split(";")[0] if c else None for c in gdf.COUNTY_IDS]
    for f_out, f_in in (("ADDRESS", "ADDRESS"), ("COUNTY_PARCEL", "PARCEL_ID"), ("BUILT_YEAR", "BuiltYear"),
                        ("COUNTY_TYPE", "BuildType")):
        gdf[f_out] = [county[f_in][c] if c else None for c in first]
    def roof_h(row):
        lbs = [x for x in row.LB_IDS.split(";") if x]
        if lbs:
            big = max(lbs, key=lambda lb: lidar.geometry[lb].area)
            return float(lidar.ROOF_H50_M[big])
        c = row.COUNTY_IDS.split(";")[0] if row.COUNTY_IDS else None
        v = county.HEIGHT_P50_M[c] if c else None
        return float(v) if v is not None and v == v else None
    gdf["ROOF_H50_M"] = [roof_h(r) for r in gdf.itertuples()]
    gdf["ROOF_H50_FT"] = [round(h / 0.3048, 1) if h is not None else None for h in gdf.ROOF_H50_M]
    gdf["REG_STATUS"] = [";".join(sorted({lidar.REG_STATUS[x] for x in r.split(";") if x})) for r in gdf.LB_IDS]
    gdf["AREA_M2"] = gdf.geometry.area.round(2)
    gdf["AREA_SQFT"] = (gdf.geometry.area / FT2).round(1)
    pts = gpd.GeoDataFrame(geometry=gdf.geometry.representative_point(), crs=gdf.crs)
    hit = gpd.sjoin(pts, parcels, how="left", predicate="within")
    hit = hit[~hit.index.duplicated()]
    for f in PARCEL_FIELDS:
        gdf[f.upper()] = hit[f].values
    return gdf


def dropped(groups, dec):
    """LiDAR outlines whose shape is meant to go unused: in dropped groups, groups that keep the county outline, and
    SHIFT_COUNTY groups (the LiDAR only places the county outline)."""
    out = set()
    for g in groups:
        r = dec.get(g["GROUP"])
        if r and (r["DECISION"] in DROP or r["DECISION"] in ("KEEP_COUNTY", "SHIFT_COUNTY")):
            out.update(x for x in g["LIDAR_IDS"].split(";") if x)
    return out


def checks(gdf, used_lb, used_c, lidar, county, groups, dec, pilot):
    geoms = list(gdf.geometry)
    tree = shapely.STRtree(geoms)
    overlap = []
    for i, j in zip(*tree.query(geoms, "intersects")):
        if i < j:
            a = geoms[i].intersection(geoms[j]).area
            if a > 1.0:
                overlap.append((round(a, 1), gdf.BLDG_ID.iloc[i], gdf.BLDG_ID.iloc[j], gdf.SOURCE.iloc[i], gdf.SOURCE.iloc[j]))
    srcs = collections.Counter(gdf.SOURCE)
    expected = collections.Counter()
    for g in groups:
        r = dec.get(g["GROUP"])
        expected[(r["DECISION"], r["BY"]) if r else ("MATCH", "match")] += 1
    return {"outlines": len(gdf), "invalid": int((~gdf.geometry.is_valid).sum()),
            "multipart": int((gdf.geometry.geom_type == "MultiPolygon").sum()),
            "overlaps_over_1m2": len(overlap), "overlap_m2": round(sum(o[0] for o in overlap), 1),
            "overlap_pairs_by_source": {"+".join(k): n for k, n in collections.Counter(tuple(sorted(o[3:])) for o in overlap).most_common()},
            "largest_overlaps": sorted(overlap, reverse=True)[:10],
            "under_2m2": int((gdf.geometry.area < 2).sum()),
            "lidar_outlines_used_twice": sum(1 for v in used_lb.values() if v > 1),
            "lidar_outlines_unused": None if pilot else len(set(lidar.index) - set(used_lb)),
            "lidar_unused_not_dropped_or_county": None if pilot else len(set(lidar.index) - set(used_lb) - dropped(groups, dec)),
            "county_outlines_used_twice": sum(1 for v in used_c.values() if v > 1),
            "by_source": dict(srcs), "by_type": dict(collections.Counter(gdf.BLDG_TYPE)),
            "review_flags": dict(collections.Counter(f for f in gdf.REVIEW_FLAG if f)),
            "groups_by_decision": {f"{d} ({b})": n for (d, b), n in expected.most_common()},
            "area_m2": round(float(gdf.geometry.area.sum()), 0)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path)
    p.add_argument("--pilot", action="store_true")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    groups, dec, lidar, county, align = load(a.pilot)
    check_inputs(groups, dec, lidar, county, a.pilot)
    out, used_lb, used_c, trimmed = build(groups, dec, lidar, county, align)
    gdf = gpd.GeoDataFrame([o for o in out if o["geometry"] is not None], crs=CRS)
    parcels = gpd.read_file(INPUTS, layer="parcels", columns=PARCEL_FIELDS)
    assert parcels.crs.to_epsg() == CRS   # never reproject here: GeoPandas would pick a null datum shift
    gdf = attributes(gdf, lidar, county, parcels)
    cols = ["BLDG_ID", "BLDG_TYPE", "SOURCE", "DECISION", "DECIDED_BY", "REVIEW_FLAG", "CLASS", "GROUP_ID", "LB_IDS",
            "COUNTY_IDS", "REG_STATUS", "ROOF_H50_M", "ROOF_H50_FT", "AREA_M2", "AREA_SQFT", "ADDRESS", "COUNTY_PARCEL",
            "BUILT_YEAR", "COUNTY_TYPE"] + [f.upper() for f in PARCEL_FIELDS] + ["geometry"]
    gdf = gdf[cols]
    name = "footprints_pilot" if a.pilot else "footprints"
    gdf.to_file(a.out/"footprints.gpkg", layer=name, driver="GPKG")
    summary = {"layer": str(a.out/"footprints.gpkg") + f"|{name}", "pilot": a.pilot,
               "inputs": {"compare": str(COMPARE), "decisions": str(DECISIONS), "outlines": str(OUTLINES),
                          "county": str(COUNTY), "parcels": str(INPUTS)},
               "defaults": {"line": "roof (no wall-line shrink)", "attributes": "county row where one exists; parcel by location"},
               "overlaps_trimmed": trimmed, **checks(gdf, used_lb, used_c, lidar, county, groups, dec, a.pilot)}
    (a.out/f"{name}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
