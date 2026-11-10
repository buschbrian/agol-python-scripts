"""Compare the corrected footprint layer with the other footprint datasets on hand (November 10, 2026).

Datasets, all already in EPSG 6341 through WGS_1984_(ITRF08)_To_NAD_1983_2011 (none is reprojected here):
- County footprints (the 22,042 the layer replaces).
- Overture 2026-10-21.0 buildings, split by source: OpenStreetMap, Microsoft ML Buildings (only where OSM has nothing)
  and Esri Community Maps.
- USA Structures (FEMA/ORNL, CC BY 4.0): mostly 2010 imagery, nothing under 42 m2.

Each dataset is cut to polygons whose inside point is in the city. Two polygons match when their overlap is at least 30%
of the smaller one (the October 23 rule). Besides agreement, each dataset votes on the sets that rest on a rule or on
Brian's group call: what share of them it also shows as a building.

    python compare_datasets.py OUT     reads OUT/footprints.gdb, writes OUT/compare.json and a copy here
"""
import collections
import csv
import json
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_footprints import COMPARE, COUNTY, DECISIONS, INPUTS, OUTLINES, RUNS  # noqa: E402

HERE = Path(__file__).resolve().parent
OVERTURE = Path(r"Z:\GIS\overture\2026-10-21.0\millcreek\lidar-compare\overture_vs_lidar.gpkg")
USA = RUNS/"usa-structures-20261023"/"usa_structures.gpkg"
MATCH = 0.30
USA_FLOOR_M2 = 42


def in_city(gdf, city):
    pts = gdf.geometry.representative_point()
    return gdf[pts.within(city).values].reset_index(drop=True)


def matches(a, b):
    """pairs (i, j, overlap of smaller, iou) where a[i] and b[j] overlap by at least MATCH of the smaller."""
    tree = shapely.STRtree(list(b.geometry))
    ia, ib = tree.query(list(a.geometry), "intersects")
    out = []
    for i, j in zip(ia, ib):
        x, y = a.geometry.iloc[i], b.geometry.iloc[j]
        inter = x.intersection(y).area
        if inter >= MATCH * min(x.area, y.area):
            out.append((int(i), int(j), inter / (x.area + y.area - inter)))
    return out


def agreement(ours, other, name):
    m = matches(ours, other)
    hit_o = {i for i, _, _ in m}
    hit_d = {j for _, j, _ in m}
    deg_o, deg_d = collections.Counter(i for i, _, _ in m), collections.Counter(j for _, j, _ in m)
    one = [(i, j, iou) for i, j, iou in m if deg_o[i] == 1 and deg_d[j] == 1]
    ratio = [ours.geometry.iloc[i].area / other.geometry.iloc[j].area for i, j, _ in one]
    big_o = ours.geometry.area >= USA_FLOOR_M2
    big_d = other.geometry.area >= USA_FLOOR_M2
    pct = lambda n, d: round(100 * n / d, 1) if d else None
    return {"dataset": name, "polygons": len(other), "ours": len(ours),
            "theirs_found_in_ours_pct": pct(len(hit_d), len(other)),
            "ours_found_in_theirs_pct": pct(len(hit_o), len(ours)),
            "ours_42m2_plus_found_pct": pct(sum(1 for i in hit_o if big_o.iloc[i]), int(big_o.sum())),
            "theirs_42m2_plus_found_pct": pct(sum(1 for j in hit_d if big_d.iloc[j]), int(big_d.sum())),
            "one_to_one_pairs": len(one),
            "one_to_one_median_iou": round(float(np.median([x[2] for x in one])), 3) if one else None,
            "one_to_one_median_area_ours_over_theirs": round(float(np.median(ratio)), 3) if ratio else None,
            "theirs_not_in_ours": len(other) - len(hit_d), "ours_not_in_theirs": len(ours) - len(hit_o)}


def vote(sets, other, name):
    out = {}
    for label, g in sets.items():
        if g.empty:
            continue
        m = matches(g, other)
        hit = {i for i, _, _ in m}
        big = g.geometry.area >= USA_FLOOR_M2
        out[label] = {"n": len(g), "shown_as_building_pct": round(100 * len(hit) / len(g), 1),
                      "n_42m2_plus": int(big.sum()),
                      "shown_42m2_plus_pct": round(100 * sum(1 for i in hit if big.iloc[i]) / big.sum(), 1) if big.sum() else None}
    return {name: out}


def rule_sets(ours, lidar, county):
    """The geometries behind each rule or group call, kept or dropped."""
    with COMPARE.open(encoding="utf-8") as fh:
        groups = {g["GROUP"]: g for g in csv.DictReader(fh)}
    with DECISIONS.open(encoding="utf-8-sig") as fh:
        dec = list(csv.DictReader(fh))
    sel = collections.defaultdict(list)
    for r in dec:
        g = groups[r["GROUP"]]
        lbs = [x for x in g["LIDAR_IDS"].split(";") if x]
        cids = [x for x in g["COUNTY_IDS"].split(";") if x]
        key = (r["REVIEW_GROUP"], r["DECISION"], r["BY"])
        if key[1] in ("VEHICLE", "DROP", "NOT_A_BUILDING"):
            sel[f"dropped: {key[1]} ({key[2]})"] += [lidar.geometry[x] for x in lbs]
        elif key[1] == "GONE":
            sel[f"dropped: county gone ({key[2]})"] += [county.geometry[x] for x in cids]
    pick = {"kept: shed rule (free-standing, under 20 m2)": (ours.DECISION == "SHED") & (ours.DECIDED_BY == "rule"),
            "kept: county under trees (rule)": (ours.SOURCE == "COUNTY") & (ours.CLASS == "COUNTY_ONLY"),
            "kept: LiDAR-only building added (rule)": (ours.CLASS == "LIDAR_ONLY") & (ours.DECISION == "LIDAR_RIGHT"),
            "kept: flagged for hand work": ours.REVIEW_FLAG.fillna("") != ""}
    sets = {k: gpd.GeoDataFrame(geometry=v, crs=ours.crs) for k, v in sorted(sel.items())}
    sets.update({k: ours[m].reset_index(drop=True) for k, m in pick.items()})
    return sets


def main(out):
    out = Path(out)
    city = gpd.read_file(INPUTS, layer="municipal_boundary").union_all()
    ours = in_city(gpd.read_file(out/"footprints.gdb", layer="footprints"), city)
    county = gpd.read_file(COUNTY, layer="building_heights")
    lidar = gpd.read_file(OUTLINES, layer="buildings").set_index("LB_ID")
    ov = gpd.read_file(OVERTURE, layer="overture_buildings")
    usa = gpd.read_file(USA, layer="usa_structures")
    for g in (county, ov, usa):
        assert g.crs.to_epsg() == 6341
    county_c = in_city(county, city)
    ov = in_city(ov, city)
    others = {"County footprints": county_c,
              "OpenStreetMap (Overture)": ov[ov.source_datasets.str.contains("OpenStreetMap")].reset_index(drop=True),
              "Microsoft ML Buildings (Overture, gap fill)": ov[ov.source_datasets == "Microsoft ML Buildings"].reset_index(drop=True),
              "Esri Community Maps (Overture)": ov[ov.source_datasets.str.contains("Esri")].reset_index(drop=True),
              "USA Structures (FEMA/ORNL)": in_city(usa, city)}
    summary = {"match_rule": f"overlap at least {MATCH:.0%} of the smaller polygon", "ours_in_city": len(ours),
               "agreement": [agreement(ours, d, n) for n, d in others.items()]}
    osm = others["OpenStreetMap (Overture)"]
    summary["osm_vs_county"] = agreement(osm, county_c, "County footprints, from OSM's side")
    summary["osm_vs_county"]["note"] = "how far OSM here is a copy of the county layer"
    sets = rule_sets(ours, lidar, county.set_index("SOURCE_ID"))
    summary["votes"] = {}
    voters = ("OpenStreetMap (Overture)", "Microsoft ML Buildings (Overture, gap fill)", "USA Structures (FEMA/ORNL)")
    for n in voters:
        summary["votes"].update(vote(sets, others[n], n))
    anyone = gpd.GeoDataFrame(pd.concat([others[n][["geometry"]] for n in voters], ignore_index=True), crs=ours.crs)
    summary["votes"].update(vote(sets, anyone, "Any of the three"))
    text = json.dumps(summary, indent=1)
    (out/"compare.json").write_text(text, encoding="utf-8")
    (HERE/"compare.json").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1])
