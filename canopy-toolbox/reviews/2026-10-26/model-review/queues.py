"""Size and write the roof-model and CFTree review queues (October 26, 2026). ArcPy-free.

Roofs: every County footprint whose three-way hybrid building is not a roofer LoD2.2 model (no model at all, or an Esri
LOD1.2 block / LOD2.0 fallback), the case Brian raised: an old footprint whose building may be gone in the 2023 LiDAR.
Footprints already in the footprint review page's "County footprints with no 2023 roof" queue are reported, not queued
again.

Trees: one row per CFTree model of the complete 61-tile run with its review cues: cross-tile seam overlap (the rule Codex
used in reviews/2026-10-26/gis-review: both models within 100 m of a core edge, different tiles, at least 70% of the
smaller convex outline shared), inferred trunk centre inside a County footprint, share of the outline over footprints,
and how many October 22 treetops fall inside the outline (several treetops in one model is a merged-crown cue). Also the
75 rejected candidates, and the October 22 treetops that no CFTree outline covers (a finding about coverage, not a queue).

Cues are not findings. Writes OUT/roof-queue.csv, OUT/tree-cues.csv, OUT/tree-outlines.parquet and OUT/summary.json.

    python queues.py OUT [--cftree RUN]
"""
import argparse
import collections
import csv
import gzip
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
LIB = RUNS/"millcreek-products-20261022"
CFTREE = Path(r"C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\work\cftree-city-20261025")
HYBRID_CSV = Path(r"C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\outputs\buildings_hybrid_v2_feet.csv")
REVIEW_DATA = RUNS/"footprint-review-20261023"/"data"
FEET = 3.280839895
SEAM_SHARE = 0.70
MERGED_TREETOPS = 3


def indices(boundaries):
    if isinstance(boundaries, int):
        yield boundaries
    else:
        for value in boundaries:
            yield from indices(value)


def read_models(run):
    """Every CFTree model: id, tile, convex XY outline of the crown mesh (EPSG 6341), trunk centre, attributes."""
    from shapely import MultiPoint, Point
    rows, seen = [], set()
    shards = sorted((run/"tiles").glob("*/trees_*.city.json.gz"))
    for n, f in enumerate(shards, 1):
        with gzip.open(f, "rt", encoding="utf-8") as stream:
            d = json.load(stream)
        v = np.asarray(d["vertices"], dtype=np.float64) * d["transform"]["scale"] + d["transform"]["translate"]
        for key, obj in d["CityObjects"].items():
            a = obj["attributes"]
            assert key == "T_" + a["gtid"] and a["gtid"] not in seen
            seen.add(a["gtid"])
            crown = v[np.unique(list(indices(obj["geometry"][0]["boundaries"])))]
            trunk = v[np.unique(list(indices(obj["geometry"][1]["boundaries"])))]
            hull = MultiPoint(crown[:, :2]).convex_hull
            assert hull.geom_type == "Polygon" and hull.is_valid and hull.area > 0
            rows.append({"MODEL_ID": a["gtid"], "TILE_ID": a["tile_id"], "SHARD": f.name,
                         "HEIGHT_FT": a["height_ft"], "CROWN_WIDTH_FT": a["crown_width_ft"],
                         "TRUNK_DIAM_FT": a["modelled_trunk_diameter_ft"], "SOURCE_POINTS": a["source_points"],
                         "EDGE_REVIEW": bool(a["edge_review"]), "CORE_EDGE_FT": a["core_edge_distance_ft"],
                         "geometry": hull,
                         "TRUNK": Point((trunk[:, 0].min() + trunk[:, 0].max()) / 2,
                                        (trunk[:, 1].min() + trunk[:, 1].max()) / 2)})
        if n % 100 == 0:
            print(f"  read {n}/{len(shards)} shards, {len(rows):,} models", flush=True)
    assert len(shards) == 506 and len(rows) == 119410, (len(shards), len(rows))
    return rows


def roof_queue(county):
    with HYBRID_CSV.open(encoding="utf-8-sig") as f:
        level = {r["SOURCE_ID"]: r for r in csv.DictReader(f)}
    assert len(level) == 21561
    index = json.loads((REVIEW_DATA/"index.json").read_text(encoding="utf-8"))
    county_items = {it["id"][2:] for it in index["items"] if it["queue"] == "county"}
    pair_items = {it["id"][2:] for it in index["items"] if it["queue"] == "pairs"}
    with (REVIEW_DATA/"answers"/"footprint-review-answers.csv").open(encoding="utf-8") as f:
        answered = {r["ITEM_ID"]: r["ANSWER"] for r in csv.DictReader(f)}
    rows, counts = [], collections.Counter()
    for r in county.itertuples():
        sid = str(r.SOURCE_ID)
        h = level.get(sid)
        lvl = h["LEVEL"] if h else "No hybrid model"
        if lvl == "roofer LoD2.2":
            counts["roofer LoD2.2"] += 1
            continue
        in_county, in_pairs = sid in county_items, sid in pair_items
        counts[lvl] += 1
        counts[f"{lvl} | already in county no-roof queue"] += in_county
        counts[f"{lvl} | already in offset/rebuilt queue"] += in_pairs
        rows.append({"SOURCE_ID": sid, "LEVEL": lvl, "FALLBACK_REASON": (h or {}).get("FALLBACK_REASON", ""),
                     "HEIGHT_STATUS": r.HEIGHT_STATUS, "ROOF_COV_PCT": r.ROOF_COV_PCT,
                     "AREA_SQFT": r.FOOTPRINT_M2 * FEET**2 if r.FOOTPRINT_M2 == r.FOOTPRINT_M2 else None,
                     "IN_COUNTY_QUEUE": int(in_county), "IN_PAIRS_QUEUE": int(in_pairs),
                     "EXISTING_ANSWER": answered.get(f"CF{sid}") or answered.get(f"PR{sid}") or ""})
    reasons = collections.Counter((r["LEVEL"], r["FALLBACK_REASON"] or "-") for r in rows)
    new = [r for r in rows if not r["IN_COUNTY_QUEUE"]]
    return rows, {"by_level": dict(counts), "not_lod22": len(rows), "new_items": len(new),
                  "new_by_level": dict(collections.Counter(r["LEVEL"] for r in new)),
                  "fallback_reasons": {f"{a} | {b}": n for (a, b), n in reasons.most_common()},
                  "existing_answers": dict(collections.Counter(r["EXISTING_ANSWER"] for r in rows if r["EXISTING_ANSWER"]))}


def tree_cues(models, county):
    import geopandas as gpd
    import shapely
    hulls = [m["geometry"] for m in models]
    tree = shapely.STRtree(hulls)
    # Seam overlap: Codex's rule, unchanged, recording the partner.
    partner, pairs = {}, 0
    left, right = tree.query(hulls, predicate="intersects")
    for i, j in zip(left, right):
        if j <= i:
            continue
        a, b = models[i], models[j]
        if a["TILE_ID"] == b["TILE_ID"] or not (a["EDGE_REVIEW"] and b["EDGE_REVIEW"]):
            continue
        share = hulls[i].intersection(hulls[j]).area / min(hulls[i].area, hulls[j].area)
        if share >= SEAM_SHARE:
            pairs += 1
            for x, y in ((i, j), (j, i)):
                if x not in partner or share > partner[x][1]:
                    partner[x] = (y, share)
    roofs = list(county.geometry)
    roof_tree = shapely.STRtree(roofs)
    centres = [m["TRUNK"] for m in models]
    in_roof = np.zeros(len(models), bool)
    in_roof[np.unique(roof_tree.query(centres, predicate="intersects")[0])] = True
    hit_l, hit_r = roof_tree.query(hulls, predicate="intersects")
    by_hull = collections.defaultdict(list)
    for i, j in zip(hit_l, hit_r):
        by_hull[i].append(j)
    overlap = np.zeros(len(models))
    for i, js in by_hull.items():
        overlap[i] = min(100.0, 100 * hulls[i].intersection(shapely.union_all([roofs[j] for j in js])).area / hulls[i].area)
    # October 22 treetops inside each outline.
    tt = []
    with (LIB/"city-treetops.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tt.append((float(r["X"]), float(r["Y"]), float(r["HEIGHT_M"])))
    tt = np.asarray(tt)
    pts = shapely.points(tt[:, 0], tt[:, 1])
    p_idx, h_idx = tree.query(pts, predicate="within")
    tops = np.bincount(h_idx, minlength=len(models))
    covered = np.zeros(len(tt), bool)
    covered[p_idx] = True
    for k, m in enumerate(models):
        m["SEAM_PARTNER"] = models[partner[k][0]]["MODEL_ID"] if k in partner else ""
        m["SEAM_SHARE"] = round(partner[k][1], 3) if k in partner else None
        m["TRUNK_IN_FOOTPRINT"] = int(in_roof[k])
        m["ROOF_OVERLAP_PCT"] = round(float(overlap[k]), 1)
        m["TREETOPS_INSIDE"] = int(tops[k])
        m["CROWN_AREA_SQFT"] = round(m["geometry"].area * FEET**2, 1)
    bins = [2, 3, 5, 8, 12, 20, 100]
    hist = lambda h: {f"{a}-{b} m": int(((h >= a) & (h < b)).sum()) for a, b in zip(bins[:-1], bins[1:])}  # noqa: E731
    heights = np.array([m["HEIGHT_FT"] / FEET for m in models])
    summary = {
        "models": len(models),
        "seam_models": len(partner), "seam_pairs": pairs,
        "trunk_in_footprint": int(in_roof.sum()),
        "outline_over_footprints_25pct": int((overlap >= 25).sum()),
        "treetops_inside": {"0": int((tops == 0).sum()), "1": int((tops == 1).sum()), "2": int((tops == 2).sum()),
                            "3-5": int(((tops >= 3) & (tops <= 5)).sum()), "6-10": int(((tops >= 6) & (tops <= 10)).sum()),
                            "over 10": int((tops > 10).sum())},
        "treetops": {"total": len(tt), "inside_a_cftree_outline": int(covered.sum()),
                     "outside_every_outline": int((~covered).sum()),
                     "height_outside": hist(tt[~covered, 2]), "height_inside": hist(tt[covered, 2])},
        "cftree_height": hist(heights),
    }
    return summary


def main(argv=None):
    import geopandas as gpd
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path)
    p.add_argument("--cftree", type=Path, default=CFTREE)
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    county = gpd.read_file(LIB/"buildings.gdb", layer="building_heights")
    assert county.crs.to_epsg() == 6341 and len(county) == 22042
    roofs, roof_summary = roof_queue(county)
    with (a.out/"roof-queue.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(roofs[0]))
        w.writeheader()
        w.writerows(roofs)
    print("roofs:", json.dumps(roof_summary, indent=1), flush=True)
    models = read_models(a.cftree)
    tree_summary = tree_cues(models, county)
    with (a.out/"tree-cues.csv").open("w", newline="", encoding="utf-8") as f:
        cols = [k for k in models[0] if k not in ("geometry", "TRUNK")]
        w = csv.DictWriter(f, cols + ["TRUNK_X", "TRUNK_Y"])
        w.writeheader()
        for m in models:
            w.writerow({**{k: m[k] for k in cols}, "TRUNK_X": round(m["TRUNK"].x, 3), "TRUNK_Y": round(m["TRUNK"].y, 3)})
    gpd.GeoDataFrame([{"MODEL_ID": m["MODEL_ID"], "geometry": m["geometry"]} for m in models], crs=6341).to_parquet(
        a.out/"tree-outlines.parquet")
    with (a.cftree/"config.json").open(encoding="utf-8") as f:
        cfg = json.load(f)
    summary = {"roofs": roof_summary, "trees": tree_summary,
               "sources": {"county": str(LIB/"buildings.gdb"), "hybrid": str(HYBRID_CSV), "cftree": str(a.cftree),
                           "cftree_config_hash": cfg.get("config_hash"), "treetops": str(LIB/"city-treetops.csv"),
                           "review_data": str(REVIEW_DATA)}}
    (a.out/"summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("trees:", json.dumps(tree_summary, indent=1))


if __name__ == "__main__":
    main()
