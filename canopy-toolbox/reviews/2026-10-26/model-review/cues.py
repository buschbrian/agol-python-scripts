"""Measure, on every CFTree model and every LiDAR candidate, the problems Brian reported in his first sittings
(October 26, 2026). ArcPy-free. Cues are proposals to check against his answers, not findings.

Trees (all 119,410), from what he saw in the tree, seam and reject queues:
- SHRUB_LIKE      under 3 m tall. CFTree keeps vegetation from 2 m up, so these are tall shrubs or hedges, not ground cover.
- BRUSH_LIKE      under 6 m, at least 40 m2 of crown and less than half as tall as wide: a low, wide mass (scrub oak,
                  a hedge row, a shrub bed).
- ROOF_OR_SHED    the crown outline at least 25% over a county footprint or a LiDAR candidate building (sheds and
                  garages the county layer misses), or the inferred trunk inside a county footprint.
- MERGED_LIKE     6 or more October 22 treetops inside, or a crown over 15 m wide.
- STEEP_GROUND    the terrain under the crown's bounding box rises 3 m or more.

Candidates (all 6,213): REDEVELOPED_SITE when a candidate of 100 m2 or more has two or more county footprints within
3 m whose 2023 roof support is under 80%, the cut-off of the "offset or rebuilt" queue (LC01389: one 422 m2 LiDAR
building among nine old county outlines; under 50% missed it, because the new building roofs part of the old outlines).

Writes OUT/tree-flags.csv, OUT/redeveloped-sites.csv and OUT/cues-summary.json, and prints how the flags fall on the
items Brian has answered.

    python cues.py QUEUES ANSWERS_CSV [--cftree RUN]
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
CAND = RUNS/"footprint-candidates-lidar-20261023"/"candidates.gdb"
CFTREE = Path(r"C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\work\cftree-city-20261025")
FEET = 3.280839895
FLAGS = ("SHRUB_LIKE", "BRUSH_LIKE", "ROOF_OR_SHED", "MERGED_LIKE", "STEEP_GROUND")


def crown_base(run):
    """Model id -> (inferred trunk height, i.e. crown base above ground, m) from the CityJSON shards."""
    out = {}
    for f in sorted((run/"tiles").glob("*/trees_*.city.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as stream:
            for obj in json.load(stream)["CityObjects"].values():
                a = obj["attributes"]
                out[a["gtid"]] = a["trunk_H_m"]
    return out


def relief(dtm, bounds):
    """Highest minus lowest terrain cell in each bounding box (one window read per box)."""
    from rasterio.windows import from_bounds
    out = np.full(len(bounds), np.nan)
    for k, b in enumerate(bounds):
        a = dtm.read(1, window=from_bounds(*b, transform=dtm.transform), boundless=True, fill_value=dtm.nodata)
        a = a[(a != dtm.nodata) & np.isfinite(a)]
        if a.size:
            out[k] = float(a.max() - a.min())
    return out


def overlap_pct(hulls, shapes):
    import shapely
    tree = shapely.STRtree(shapes)
    left, right = tree.query(hulls, predicate="intersects")
    hits = collections.defaultdict(list)
    for i, j in zip(left, right):
        hits[i].append(j)
    pct = np.zeros(len(hulls))
    for i, js in hits.items():
        pct[i] = min(100.0, 100 * hulls[i].intersection(shapely.union_all([shapes[j] for j in js])).area / hulls[i].area)
    return pct


def main(argv=None):
    import geopandas as gpd
    import rasterio
    import shapely
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("queues", type=Path)
    p.add_argument("answers", type=Path)
    p.add_argument("--cftree", type=Path, default=CFTREE)
    a = p.parse_args(argv)

    with (a.queues/"tree-cues.csv").open(encoding="utf-8") as f:
        trees = list(csv.DictReader(f))
    outlines = gpd.read_parquet(a.queues/"tree-outlines.parquet").set_index("MODEL_ID")
    hulls = [outlines.geometry[t["MODEL_ID"]] for t in trees]
    county = gpd.read_file(LIB/"buildings.gdb", layer="building_heights")
    cand = gpd.read_file(CAND, layer="candidates")
    base = crown_base(a.cftree)
    with rasterio.open(LIB/"terrain_m.tif") as dtm:
        rel = relief(dtm, [h.bounds for h in hulls])
    over_cand = overlap_pct(hulls, list(cand.geometry))

    rows, counts = [], collections.Counter()
    for k, t in enumerate(trees):
        h = float(t["HEIGHT_FT"]) / FEET
        w = float(t["CROWN_WIDTH_FT"]) / FEET
        area = float(t["CROWN_AREA_SQFT"]) / FEET**2
        flags = []
        if h < 3:
            flags.append("SHRUB_LIKE")
        if h < 6 and area >= 40 and h < 0.5 * w:
            flags.append("BRUSH_LIKE")
        if float(t["ROOF_OVERLAP_PCT"]) >= 25 or over_cand[k] >= 25 or t["TRUNK_IN_FOOTPRINT"] == "1":
            flags.append("ROOF_OR_SHED")
        if int(t["TREETOPS_INSIDE"]) >= 6 or w > 15:
            flags.append("MERGED_LIKE")
        if np.isfinite(rel[k]) and rel[k] >= 3:
            flags.append("STEEP_GROUND")
        counts.update(flags)
        counts["any"] += bool(flags)
        rows.append({"MODEL_ID": t["MODEL_ID"], "TILE_ID": t["TILE_ID"], "HEIGHT_M": round(h, 2),
                     "CROWN_WIDTH_M": round(w, 2), "CROWN_AREA_M2": round(area, 1),
                     "CROWN_BASE_M": None if base.get(t["MODEL_ID"]) is None else round(base[t["MODEL_ID"]], 2),
                     "TREETOPS_INSIDE": t["TREETOPS_INSIDE"], "COUNTY_OVERLAP_PCT": t["ROOF_OVERLAP_PCT"],
                     "CAND_OVERLAP_PCT": round(float(over_cand[k]), 1), "TRUNK_IN_FOOTPRINT": t["TRUNK_IN_FOOTPRINT"],
                     "GROUND_RELIEF_M": None if not np.isfinite(rel[k]) else round(float(rel[k]), 2),
                     "FLAGS": ";".join(flags)})
    with (a.queues/"tree-flags.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # Redeveloped sites: one big LiDAR building among several weak county outlines
    weak = county[county.ROOF_COV_PCT.isna() | (county.ROOF_COV_PCT < 80)]
    big = cand[cand.FOOTPRINT_M2 >= 100]
    near = gpd.sjoin(big[["CAND_ID", "FOOTPRINT_M2", "HEIGHT_P50_M", "PARCEL_ID", "geometry"]].assign(
        geometry=big.geometry.buffer(3)), weak[["SOURCE_ID", "geometry"]], predicate="intersects")
    sites = near.groupby("CAND_ID").agg(COUNTY_IDS=("SOURCE_ID", lambda s: ";".join(sorted(set(s)))),
                                        N_COUNTY=("SOURCE_ID", "nunique"), FOOTPRINT_M2=("FOOTPRINT_M2", "first"),
                                        HEIGHT_P50_M=("HEIGHT_P50_M", "first"), PARCEL_ID=("PARCEL_ID", "first"))
    sites = sites[sites.N_COUNTY >= 2].sort_values("N_COUNTY", ascending=False).reset_index()
    sites.to_csv(a.queues/"redeveloped-sites.csv", index=False)
    site_county = {sid for ids in sites.COUNTY_IDS for sid in ids.split(";")}

    # How the cues fall on Brian's answers so far
    with a.answers.open(encoding="utf-8") as f:
        answers = list(csv.DictReader(f))
    by_prefix = {r["MODEL_ID"][:8]: r for r in rows}
    versus = collections.defaultdict(collections.Counter)
    for r in answers:
        if r["QUEUE"] in ("trees", "tree_seams") and r["ITEM_ID"][2:] in by_prefix:
            for flag in (by_prefix[r["ITEM_ID"][2:]]["FLAGS"].split(";") if by_prefix[r["ITEM_ID"][2:]]["FLAGS"] else ["none"]):
                versus[flag][r["ANSWER"]] += 1
    with (a.queues/"roof-queue.csv").open(encoding="utf-8") as f:
        queued = list(csv.DictReader(f))
    roof_queue = {r["SOURCE_ID"] for r in queued if r["IN_COUNTY_QUEUE"] == "0"}
    no_roof_queue = {r["SOURCE_ID"] for r in queued if r["IN_COUNTY_QUEUE"] == "1"}
    summary = {"trees": {"models": len(rows), "flagged_any": counts["any"], "flags": {f: counts[f] for f in FLAGS},
                         "thresholds": {"SHRUB_LIKE": "height < 3 m",
                                        "BRUSH_LIKE": "height < 6 m, crown >= 40 m2, height < half the crown width",
                                        "ROOF_OR_SHED": ">= 25% of outline over a county footprint or a LiDAR candidate, "
                                                        "or trunk inside a county footprint",
                                        "MERGED_LIKE": ">= 6 October 22 treetops inside, or crown wider than 15 m",
                                        "STEEP_GROUND": "terrain relief >= 3 m under the crown's bounding box"},
                         "against_brians_answers": {k: dict(v) for k, v in versus.items()}},
               "redeveloped_sites": {"sites": len(sites), "county_footprints_in_them": len(site_county),
                                     "rule": "LiDAR candidate >= 100 m2 with >= 2 county footprints within 3 m whose "
                                             "2023 roof support is under 80%",
                                     "largest": sites.head(10).to_dict("records"),
                                     "lc01389_in_list": bool((sites.CAND_ID == "LC01389").any()),
                                     "md733329_in_a_site": "733329" in site_county,
                                     "roof_queue_items_in_sites": len(site_county & roof_queue),
                                     "county_no_roof_queue_items_in_sites": len(site_county & no_roof_queue)},
               "answers": {"total": len(answers), "with_notes": sum(1 for r in answers if r["NOTE"])}}
    (a.queues/"cues-summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
